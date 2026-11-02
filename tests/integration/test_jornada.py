"""Consulta de la jornada (G-19), medicion de desempeno (G-22) y arranque."""
import uuid
from datetime import timedelta

from fastapi.testclient import TestClient

from app.core import config
from app.core.metricas import metricas
from app.main import app
from app.models import LecturaParcial

URL = "/v1/eventos"
DIA = "2026-09-03"


def nuevo_id():
    return str(uuid.uuid4())


def sesion(client, evento, sid, n_lecturas, final=None, estacion="R1", animal="2101", hora="06", **extra):
    """Crea una sesion con n lecturas EN_CURSO y, si se pide, una lectura final."""
    for n in range(1, n_lecturas + 1):
        r = client.post(URL, json=evento(
            id_evento=nuevo_id(), sesion_id=sid, estacion_id=estacion, animal_id=animal, secuencia=n,
            volumen_l=round(2.0 * n, 1), duracion_s=120 * n,
            ts_inicio=f"2026-09-03T{hora}:00:00-05:00", ts_lectura=f"2026-09-03T{hora}:{2 * n:02d}:00-05:00",
            **extra))
        assert r.status_code == 201
    if final:
        n = n_lecturas + 1
        r = client.post(URL, json=evento(
            id_evento=nuevo_id(), sesion_id=sid, estacion_id=estacion, animal_id=animal, secuencia=n,
            estado="COMPLETA", volumen_l=final, duracion_s=120 * n,
            ts_inicio=f"2026-09-03T{hora}:00:00-05:00", ts_lectura=f"2026-09-03T{hora}:{2 * n:02d}:00-05:00",
            **extra))
        assert r.status_code == 201


def envejecer(db, sesion_id, segundos):
    for lec in db.query(LecturaParcial).filter(LecturaParcial.sesion_id == sesion_id).all():
        lec.recibido_en = lec.recibido_en - timedelta(seconds=segundos)
    db.commit()


# ---------------------------------------------------------------- G-19: la jornada
def test_la_jornada_separa_completas_inconclusas_y_en_curso(client, evento, db):
    sesion(client, evento, "S-COMPLETA", 2, final=9.0, estacion="R1", animal="2101", hora="06")
    sesion(client, evento, "S-CORTADA", 2, estacion="R2", animal="2102", hora="07")
    sesion(client, evento, "S-VIVA", 1, estacion="R3", animal="2103", hora="08")
    envejecer(db, "S-CORTADA", config.SESION_TIMEOUT_SEG + 60)

    r = client.get("/v1/jornada", params={"fecha": DIA})
    assert r.status_code == 200
    j = r.json()
    assert [f["sesion_id"] for f in j["completas"]] == ["S-COMPLETA"]
    assert [f["sesion_id"] for f in j["inconclusas"]] == ["S-CORTADA"]
    assert [f["sesion_id"] for f in j["en_curso"]] == ["S-VIVA"]
    assert j["estimadas"] == []
    t = j["totales"]
    assert t["sesiones"] == 3 and t["completas"] == 1 and t["inconclusas"] == 1 and t["en_curso"] == 1


def test_el_volumen_inconcluso_nunca_se_suma_a_la_produccion_completa(client, evento, db):
    sesion(client, evento, "S-COMPLETA", 2, final=9.0, hora="06")
    sesion(client, evento, "S-CORTADA", 2, estacion="R2", animal="2102", hora="07")   # 4.0 L parciales
    envejecer(db, "S-CORTADA", config.SESION_TIMEOUT_SEG + 60)

    t = client.get("/v1/jornada", params={"fecha": DIA}).json()["totales"]
    assert t["volumen_completas_l"] == 9.0
    assert t["volumen_inconcluso_minimo_l"] == 4.0


def test_cada_fila_dice_si_su_volumen_es_parcial(client, evento, db):
    sesion(client, evento, "S-COMPLETA", 1, final=5.0, hora="06")
    sesion(client, evento, "S-VIVA", 1, estacion="R2", animal="2102", hora="07")
    j = client.get("/v1/jornada", params={"fecha": DIA}).json()
    assert j["completas"][0]["volumen_es_parcial"] is False
    assert j["en_curso"][0]["volumen_es_parcial"] is True


def test_la_consulta_marca_inconclusa_una_sesion_cortada_aunque_nadie_haya_barrido(client, evento, db):
    sesion(client, evento, "S-CORTADA", 2, hora="06")
    envejecer(db, "S-CORTADA", config.SESION_TIMEOUT_SEG + 60)
    j = client.get("/v1/jornada", params={"fecha": DIA}).json()
    assert j["totales"]["inconclusas"] == 1 and j["totales"]["en_curso"] == 0


def test_la_jornada_solo_trae_las_sesiones_de_ese_dia_local(client, evento):
    sesion(client, evento, "S-DIA3", 1, hora="06")
    # 23:30 hora local del 3 de septiembre ya es el 4 en UTC; sigue siendo del dia 3 para la finca.
    sesion(client, evento, "S-NOCHE3", 1, estacion="R2", animal="2102", hora="23")
    r4 = client.post(URL, json=evento(
        id_evento=nuevo_id(), sesion_id="S-DIA4", estacion_id="R3", animal_id="2103",
        ts_inicio="2026-09-04T05:00:00-05:00", ts_lectura="2026-09-04T05:02:00-05:00"))
    assert r4.status_code == 201

    d3 = client.get("/v1/jornada", params={"fecha": "2026-09-03"}).json()
    d4 = client.get("/v1/jornada", params={"fecha": "2026-09-04"}).json()
    assert {f["sesion_id"] for f in d3["en_curso"]} == {"S-DIA3", "S-NOCHE3"}
    assert {f["sesion_id"] for f in d4["en_curso"]} == {"S-DIA4"}


def test_la_jornada_sin_registros_responde_vacia(client):
    j = client.get("/v1/jornada", params={"fecha": "2030-01-01"}).json()
    assert j["totales"]["sesiones"] == 0 and j["completas"] == []


def test_una_fecha_mal_escrita_responde_422(client):
    assert client.get("/v1/jornada", params={"fecha": "03/09/2026"}).status_code == 422


def test_las_horas_de_la_jornada_salen_en_hora_local_con_zona(client, evento):
    sesion(client, evento, "S-1", 1, hora="06")
    f = client.get("/v1/jornada", params={"fecha": DIA}).json()["en_curso"][0]
    assert f["ts_inicio"] == "2026-09-03T06:00:00-05:00"


def test_el_detalle_de_la_sesion_trae_sus_lecturas_en_orden(client, evento):
    sesion(client, evento, "S-1", 3, final=8.0)
    d = client.get("/v1/sesiones/S-1").json()
    assert [lec["secuencia"] for lec in d["lecturas"]] == [1, 2, 3, 4]
    assert d["estado"] == "COMPLETA" and d["n_lecturas"] == 4


def test_una_sesion_inexistente_responde_404(client):
    r = client.get("/v1/sesiones/NO-EXISTE")
    assert r.status_code == 404
    assert r.json()["detail"]["error"] == "sesion_no_encontrada"


def test_el_detalle_avisa_las_secuencias_faltantes(client, evento):
    for n in (1, 4):
        client.post(URL, json=evento(id_evento=nuevo_id(), sesion_id="S-H", secuencia=n))
    assert client.get("/v1/sesiones/S-H").json()["secuencias_faltantes"] == [2, 3]


# ---------------------------------------------------------------- vista web
def test_la_pagina_de_la_jornada_se_muestra_con_sus_secciones(client, evento):
    sesion(client, evento, "S-1", 1, final=5.0)
    r = client.get("/jornada", params={"fecha": DIA})
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    for texto in ("Completas", "Inconclusas", "En curso", "Estimadas", "S-1"):
        assert texto in r.text


def test_la_pagina_escapa_el_contenido_para_evitar_inyeccion_html(client, evento):
    client.post(URL, json=evento(id_evento=nuevo_id(), sesion_id="<script>alert(1)</script>"))
    r = client.get("/jornada", params={"fecha": DIA})
    assert "<script>alert(1)</script>" not in r.text
    assert "&lt;script&gt;" in r.text


# ---------------------------------------------------------------- G-22: desempeno
def test_las_metricas_cuentan_ingesta_y_consulta_por_separado(client, evento):
    metricas.reiniciar()
    for n in range(1, 4):
        client.post(URL, json=evento(id_evento=nuevo_id(), secuencia=n))
    client.get("/v1/jornada", params={"fecha": DIA})
    m = client.get("/v1/metricas").json()
    assert m["ingesta"]["peticiones"] == 3
    assert m["consulta"]["peticiones"] == 1
    for g in ("ingesta", "consulta"):
        assert 0 < m[g]["p50_ms"] <= m[g]["p95_ms"] <= m[g]["max_ms"]


def test_la_respuesta_incluye_el_tiempo_de_proceso(client):
    r = client.get("/health")
    assert float(r.headers["X-Process-Time-ms"]) >= 0


def test_consultar_las_metricas_no_cuenta_como_consulta(client):
    metricas.reiniciar()
    client.get("/v1/metricas")
    assert client.get("/v1/metricas").json()["consulta"]["peticiones"] == 0


def test_se_pueden_reiniciar_las_metricas(client, evento):
    client.post(URL, json=evento())
    assert client.delete("/v1/metricas").json() == {"reiniciado": True}
    assert client.get("/v1/metricas").json()["ingesta"]["peticiones"] == 0


# ---------------------------------------------------------------- salud y arranque
def test_health_informa_el_estado_de_la_base(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok" and r.json()["base_de_datos"] == "ok"


def test_el_servicio_arranca_y_se_detiene_limpiamente():
    # `with` ejecuta el arranque real: tablas, revision de sesiones abiertas y barrido periodico.
    with TestClient(app) as c:
        assert c.get("/health").status_code == 200


def test_un_evento_rechazado_deja_rastro_en_el_registro_del_servidor(client, evento, caplog):
    import logging

    with caplog.at_level(logging.WARNING, logger="concentrador"):
        r = client.post(URL, json=evento(volumen_l=-5))
    assert r.status_code == 422
    assert "volumen_l" in caplog.text and "422" in caplog.text
