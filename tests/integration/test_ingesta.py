"""Pruebas de la ingesta. Cubren los criterios de G-03, G-04 y G-07 del cronograma."""
import uuid

from app.models import LecturaParcial, SesionOrdeno

URL = "/v1/eventos"


def nuevo_id():
    return str(uuid.uuid4())


def campos_con_error(respuesta):
    return {".".join(str(p) for p in e["loc"][1:]) for e in respuesta.json()["detail"]}


# ---------------------------------------------------------------- G-03: validacion
def test_evento_valido_responde_201(client, evento):
    r = client.post(URL, json=evento())
    assert r.status_code == 201
    assert r.json()["estado_sesion"] == "EN_CURSO"


def test_sin_volumen_responde_422_y_dice_cual_falta(client, evento):
    e = evento()
    del e["volumen_l"]
    r = client.post(URL, json=e)
    assert r.status_code == 422
    assert "volumen_l" in campos_con_error(r)


def test_sin_animal_se_guarda(client, evento, db):
    r = client.post(URL, json=evento(animal_id=None, animal_id_origen="INFERIDO_POR_POSICION"))
    assert r.status_code == 201
    assert db.query(SesionOrdeno).one().animal_chapeta is None


def test_secuencia_cero_responde_422(client, evento):
    assert client.post(URL, json=evento(secuencia=0)).status_code == 422


def test_volumen_negativo_responde_422(client, evento):
    assert client.post(URL, json=evento(volumen_l=-1)).status_code == 422


def test_confianza_fuera_de_rango_responde_422(client, evento):
    assert client.post(URL, json=evento(animal_id_confianza=1.5)).status_code == 422


def test_estacion_inexistente_responde_422(client, evento):
    assert client.post(URL, json=evento(estacion_id="R9")).status_code == 422


def test_estado_invalido_responde_422(client, evento):
    assert client.post(URL, json=evento(estado="XXXX")).status_code == 422


def test_chapeta_de_tres_digitos_responde_422(client, evento):
    assert client.post(URL, json=evento(animal_id="210")).status_code == 422


def test_timestamp_sin_zona_horaria_responde_422(client, evento):
    r = client.post(URL, json=evento(ts_lectura="2026-09-03T06:16:00"))
    assert r.status_code == 422
    assert "ts_lectura" in campos_con_error(r)


def test_id_evento_que_no_es_uuid_responde_422(client, evento):
    assert client.post(URL, json=evento(id_evento="hola")).status_code == 422


def test_version_de_esquema_distinta_responde_422(client, evento):
    assert client.post(URL, json=evento(version_esquema="9.9")).status_code == 422


def test_campo_fuera_del_contrato_responde_422(client, evento):
    r = client.post(URL, json=evento(tsInicio="2026-09-03T06:12:00-05:00"))
    assert r.status_code == 422


def test_lectura_anterior_al_inicio_responde_422(client, evento):
    assert client.post(URL, json=evento(ts_lectura="2026-09-03T05:00:00-05:00")).status_code == 422


# ---------------------------------------------------------------- G-04: idempotencia
def test_el_mismo_evento_tres_veces_deja_una_sola_fila(client, evento, db):
    e = evento()
    respuestas = [client.post(URL, json=e) for _ in range(3)]
    assert [r.status_code for r in respuestas] == [201, 201, 201]
    assert respuestas[0].json() == respuestas[2].json()
    assert db.query(LecturaParcial).count() == 1


def test_misma_sesion_y_secuencia_con_otro_id_responde_409_no_500(client, evento, db):
    assert client.post(URL, json=evento()).status_code == 201
    r = client.post(URL, json=evento(id_evento=nuevo_id()))
    assert r.status_code == 409
    assert r.json()["detail"]["error"] == "secuencia_duplicada"
    assert db.query(LecturaParcial).count() == 1


def test_despues_de_un_conflicto_el_servicio_sigue_aceptando_eventos(client, evento, db):
    client.post(URL, json=evento())
    client.post(URL, json=evento(id_evento=nuevo_id()))  # 409
    r = client.post(URL, json=evento(id_evento=nuevo_id(), secuencia=2))
    assert r.status_code == 201
    assert db.query(LecturaParcial).count() == 2


# ---------------------------------------------------------------- G-07: modo degradado
def test_punto_waikato_sin_duracion_ni_animal_se_guarda(client, evento):
    e = evento(
        estacion_id="L1", animal_id=None, animal_id_confianza=None, duracion_s=None,
        animal_id_origen="INFERIDO_POR_POSICION", origen_dato="MANUAL",
    )
    assert client.post(URL, json=e).status_code == 201


def test_punto_waikato_cierra_sesion_sin_calcular_flujo(client, evento, db):
    base = dict(
        estacion_id="L1", sesion_id="SES-L1", animal_id=None, animal_id_confianza=None,
        duracion_s=None, animal_id_origen="INFERIDO_POR_POSICION", origen_dato="MANUAL",
    )
    client.post(URL, json=evento(id_evento=nuevo_id(), **base))
    r = client.post(URL, json=evento(id_evento=nuevo_id(), secuencia=2, estado="COMPLETA", volumen_l=9.0, **base))
    assert r.status_code == 201
    s = db.get(SesionOrdeno, "SES-L1")
    assert s.estado.value == "COMPLETA"
    assert s.volumen_final_l == 9.0
    assert s.duracion_final_s is None and s.flujo_l_min is None


def test_cierre_de_sesion_calcula_el_flujo(client, evento, db):
    client.post(URL, json=evento())
    client.post(URL, json=evento(
        id_evento=nuevo_id(), secuencia=2, estado="COMPLETA", volumen_l=12.6, duracion_s=480,
        ts_lectura="2026-09-03T06:24:00-05:00",
    ))
    s = db.get(SesionOrdeno, "SES-20260903-R1-004")
    assert s.estado.value == "COMPLETA"
    assert round(s.flujo_l_min, 3) == 1.575


def test_el_animal_que_se_identifica_despues_se_asigna_a_la_sesion(client, evento, db):
    client.post(URL, json=evento(animal_id=None, animal_id_origen="INFERIDO_POR_POSICION"))
    client.post(URL, json=evento(id_evento=nuevo_id(), secuencia=2, animal_id="2101"))
    assert db.get(SesionOrdeno, "SES-20260903-R1-004").animal_chapeta == "2101"


def test_el_tipo_de_medidor_no_se_deduce_de_la_letra_de_la_estacion(client, evento, db):
    from app.models import Estacion

    client.post(URL, json=evento(estacion_id="R5"))
    assert db.get(Estacion, "R5").tipo_medidor == "SIN_DEFINIR"


def test_las_marcas_de_tiempo_se_guardan_en_utc(client, evento, db):
    client.post(URL, json=evento())  # 06:12 en -05:00 equivale a 11:12 UTC
    s = db.get(SesionOrdeno, "SES-20260903-R1-004")
    assert (s.ts_inicio.hour, s.ts_inicio.minute) == (11, 12)
