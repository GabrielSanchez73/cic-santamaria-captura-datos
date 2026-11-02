"""Pruebas de consolidacion y estados. Cubren los criterios de G-06 y G-08 del cronograma."""
import uuid
from datetime import timedelta

from app.core import config
from app.core.tiempo import ahora_utc
from app.models import LecturaParcial, SesionOrdeno
from app.services import consolidacion

URL = "/v1/eventos"
SES = "SES-20260903-R1-004"


def nuevo_id():
    return str(uuid.uuid4())


def enviar(client, evento, n, estado="EN_CURSO", volumen=None, duracion=None, **extra):
    """Envia la lectura numero n de la sesion (una cada 2 minutos)."""
    cambios = dict(
        id_evento=nuevo_id(), secuencia=n, estado=estado,
        volumen_l=volumen if volumen is not None else round(2.1 * n, 1),
        duracion_s=duracion if duracion is not None else 120 * n,
        ts_lectura=f"2026-09-03T06:{12 + 2 * n:02d}:00-05:00",
    )
    cambios.update(extra)
    return client.post(URL, json=evento(**cambios))


def envejecer(db, segundos):
    """Simula que pasaron `segundos` desde la ultima lectura recibida."""
    for lec in db.query(LecturaParcial).all():
        lec.recibido_en = lec.recibido_en - timedelta(seconds=segundos)
    db.commit()


# ---------------------------------------------------------------- G-06: consolidacion
def test_seis_lecturas_parciales_producen_una_sesion_con_volumen_y_duracion_correctos(client, evento, db):
    for n in range(1, 6):
        assert enviar(client, evento, n).status_code == 201
    assert enviar(client, evento, 6, estado="COMPLETA", volumen=12.6, duracion=720).status_code == 201

    assert db.query(SesionOrdeno).count() == 1
    assert db.query(LecturaParcial).count() == 6
    s = db.get(SesionOrdeno, SES)
    assert s.estado.value == "COMPLETA"
    assert s.volumen_final_l == 12.6          # el volumen es acumulado: NO se suman las lecturas
    assert s.duracion_final_s == 720
    assert round(s.flujo_l_min, 3) == 1.05


def test_el_volumen_parcial_es_el_de_la_lectura_mas_reciente_no_la_suma(client, evento, db):
    enviar(client, evento, 1, volumen=2.0)
    enviar(client, evento, 2, volumen=4.5)
    enviar(client, evento, 3, volumen=6.1)
    res = consolidacion.resumen_parcial(db.get(SesionOrdeno, SES))
    assert res["n_lecturas"] == 3
    assert res["volumen_l"] == 6.1


def test_las_lecturas_que_llegan_desordenadas_se_consolidan_por_secuencia(client, evento, db):
    enviar(client, evento, 3, volumen=6.1)
    enviar(client, evento, 1, volumen=2.0)
    enviar(client, evento, 2, volumen=4.5)
    res = consolidacion.resumen_parcial(db.get(SesionOrdeno, SES))
    assert res["volumen_l"] == 6.1
    assert [lec.secuencia for lec in consolidacion.lecturas_ordenadas(db.get(SesionOrdeno, SES))] == [1, 2, 3]


def test_se_detectan_los_huecos_en_la_secuencia(client, evento, db):
    for n in (1, 2, 5):
        enviar(client, evento, n)
    assert consolidacion.secuencias_faltantes(db.get(SesionOrdeno, SES)) == [3, 4]


def test_sin_huecos_no_hay_secuencias_faltantes(client, evento, db):
    for n in (1, 2, 3):
        enviar(client, evento, n)
    assert consolidacion.secuencias_faltantes(db.get(SesionOrdeno, SES)) == []


# ---------------------------------------------------------------- G-08: estados
def test_una_sesion_cortada_queda_inconclusa_nunca_completa(client, evento, db):
    for n in (1, 2, 3):
        enviar(client, evento, n)
    envejecer(db, config.SESION_TIMEOUT_SEG + 30)

    assert consolidacion.marcar_inconclusas(db) == 1
    s = db.get(SesionOrdeno, SES)
    assert s.estado.value == "INCONCLUSA"
    assert s.volumen_final_l == 6.3           # lo ultimo que se supo (cota inferior)
    assert s.flujo_l_min is None              # no se calcula flujo de un ordeno incompleto


def test_una_sesion_reciente_no_se_marca_inconclusa(client, evento, db):
    enviar(client, evento, 1)
    envejecer(db, config.SESION_TIMEOUT_SEG - 60)
    assert consolidacion.marcar_inconclusas(db) == 0
    assert db.get(SesionOrdeno, SES).estado.value == "EN_CURSO"


def test_una_sesion_completa_nunca_se_marca_inconclusa(client, evento, db):
    enviar(client, evento, 1)
    enviar(client, evento, 2, estado="COMPLETA")
    envejecer(db, 10 * config.SESION_TIMEOUT_SEG)
    assert consolidacion.marcar_inconclusas(db) == 0
    assert db.get(SesionOrdeno, SES).estado.value == "COMPLETA"


def test_el_reloj_del_nodo_no_hace_parecer_cortada_una_sesion_que_si_llega(client, evento, db):
    # El nodo arranco sin hora (2020) pero sus lecturas estan llegando ahora: no esta cortada.
    enviar(client, evento, 1, ts_inicio="2020-01-01T00:00:00-05:00", ts_lectura="2020-01-01T00:02:00-05:00")
    assert consolidacion.marcar_inconclusas(db) == 0


def test_las_lecturas_tardias_de_la_reconexion_reabren_la_sesion(client, evento, db):
    enviar(client, evento, 1)
    enviar(client, evento, 2)
    envejecer(db, config.SESION_TIMEOUT_SEG + 30)
    consolidacion.marcar_inconclusas(db)
    assert db.get(SesionOrdeno, SES).estado.value == "INCONCLUSA"

    assert enviar(client, evento, 3).status_code == 201   # el nodo recupero la conexion
    s = db.get(SesionOrdeno, SES)
    assert s.estado.value == "EN_CURSO"
    assert s.ts_fin is None and s.volumen_final_l is None


def test_la_lectura_final_que_llega_tras_un_corte_completa_la_sesion(client, evento, db):
    enviar(client, evento, 1)
    envejecer(db, config.SESION_TIMEOUT_SEG + 30)
    consolidacion.marcar_inconclusas(db)

    enviar(client, evento, 4, estado="COMPLETA", volumen=9.0, duracion=480)
    s = db.get(SesionOrdeno, SES)
    assert s.estado.value == "COMPLETA"
    assert s.volumen_final_l == 9.0 and s.duracion_final_s == 480
    assert consolidacion.secuencias_faltantes(s) == [2, 3]   # y se avisa que faltaron lecturas


def test_una_lectura_tardia_no_reabre_una_sesion_completa(client, evento, db):
    enviar(client, evento, 1)
    enviar(client, evento, 3, estado="COMPLETA", volumen=7.0, duracion=360)
    enviar(client, evento, 2, volumen=4.0)                  # llega tarde y desordenada
    s = db.get(SesionOrdeno, SES)
    assert s.estado.value == "COMPLETA"
    assert s.volumen_final_l == 7.0


def test_una_lectura_vieja_no_reabre_una_sesion_inconclusa(client, evento, db):
    enviar(client, evento, 1)
    enviar(client, evento, 3)
    envejecer(db, config.SESION_TIMEOUT_SEG + 30)
    consolidacion.marcar_inconclusas(db)

    enviar(client, evento, 2)                               # numero menor al ultimo que ya se tenia
    assert db.get(SesionOrdeno, SES).estado.value == "INCONCLUSA"


def test_un_evento_inconclusa_del_nodo_cierra_la_sesion_sin_calcular_flujo(client, evento, db):
    enviar(client, evento, 1)
    enviar(client, evento, 2, estado="INCONCLUSA", volumen=4.2, duracion=240)
    s = db.get(SesionOrdeno, SES)
    assert s.estado.value == "INCONCLUSA"
    assert s.volumen_final_l == 4.2 and s.flujo_l_min is None


def test_un_evento_estimada_se_guarda_marcado_y_sin_flujo(client, evento, db):
    enviar(client, evento, 1)
    enviar(client, evento, 2, estado="ESTIMADA", volumen=10.0, duracion=None, origen_dato="ESTIMADO")
    s = db.get(SesionOrdeno, SES)
    assert s.estado.value == "ESTIMADA"
    assert s.volumen_final_l == 10.0 and s.flujo_l_min is None


def test_al_arrancar_se_revisan_las_sesiones_que_quedaron_abiertas(client, evento, db):
    enviar(client, evento, 1)
    envejecer(db, config.SESION_TIMEOUT_SEG + 30)       # el concentrador estuvo apagado
    assert consolidacion.recuperar_al_arrancar(db) == 1
    assert db.get(SesionOrdeno, SES).estado.value == "INCONCLUSA"


def test_marcar_inconclusas_acepta_un_tiempo_limite_explicito(client, evento, db):
    enviar(client, evento, 1)
    envejecer(db, 100)
    assert consolidacion.marcar_inconclusas(db, ahora=ahora_utc(), timeout_seg=50) == 1


def test_un_evento_inconclusa_o_estimada_tardio_no_degrada_una_sesion_completa(client, evento, db):
    enviar(client, evento, 2, estado="COMPLETA", volumen=7.0, duracion=360)
    enviar(client, evento, 3, estado="INCONCLUSA", volumen=1.0)
    enviar(client, evento, 4, estado="ESTIMADA", volumen=2.0, origen_dato="ESTIMADO")
    s = db.get(SesionOrdeno, SES)
    assert s.estado.value == "COMPLETA" and s.volumen_final_l == 7.0


def test_un_evento_inconclusa_tardio_no_degrada_una_sesion_estimada(client, evento, db):
    enviar(client, evento, 1, estado="ESTIMADA", volumen=5.0, origen_dato="ESTIMADO")
    enviar(client, evento, 2, estado="INCONCLUSA", volumen=1.0)
    assert db.get(SesionOrdeno, SES).estado.value == "ESTIMADA"
