"""El JSON que arma el firmware (firmware/esp32_prueba_ingesta/evento_json.h) cumple el contrato.

Se compila el mismo encabezado C++ que usa el ESP32 y se valida su salida contra el esquema real
del concentrador. Asi se detecta en el computador, antes de cargar la placa, cualquier campo mal
escrito o formato incorrecto. Se omite si no hay compilador de C++ en la maquina.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from app.schemas.evento import EventoOrdenoIn

RAIZ = Path(__file__).resolve().parents[2]
FUENTE = RAIZ / "firmware" / "pruebas" / "compilar_prueba.cpp"
CXX = shutil.which("g++") or shutil.which("c++") or shutil.which("clang++")

pytestmark = pytest.mark.skipif(CXX is None, reason="no hay compilador de C++")

UUID = "3f2b8c1e-9d4a-4e6b-8a7c-1d2e3f4a5b6c"
IZ = "2026-10-31T11:45:00-05:00"


def caso(**cambios):
    d = dict(id=UUID, est="R1", ses="ESP-20261031-114500-R1", animal="2101", origen="RFID", conf="0.98",
             ini=IZ, lec="2026-10-31T11:47:00-05:00", seq="2", vol="4.2", dur="120", estado="EN_CURSO", dato="OCR")
    d.update(cambios)
    return "|".join(d.values())


@pytest.fixture(scope="module")
def ejecutar(tmp_path_factory):
    exe = tmp_path_factory.mktemp("fw") / "prueba_json"
    subprocess.run([CXX, "-std=c++11", "-Wall", "-Wextra", "-Werror", str(FUENTE), "-o", str(exe)],
                   check=True, capture_output=True, text=True)

    def run(*lineas):
        r = subprocess.run([str(exe)], input="\n".join(lineas) + "\n", capture_output=True, text=True, check=True)
        return r.stdout.strip().split("\n")

    return run


def test_evento_normal_cumple_el_contrato(ejecutar):
    (salida,) = ejecutar(caso())
    ev = EventoOrdenoIn.model_validate_json(salida)   # extra="forbid": un campo de mas o de menos falla
    assert ev.volumen_l == pytest.approx(4.2) and ev.secuencia == 2 and ev.animal_id == "2101"
    assert len(json.loads(salida)) == 15


def test_campos_nulos_waikato(ejecutar):
    (salida,) = ejecutar(caso(animal="-", origen="INFERIDO_POR_POSICION", conf="-1", dur="-1", dato="MANUAL"))
    ev = EventoOrdenoIn.model_validate_json(salida)
    assert ev.animal_id is None and ev.animal_id_confianza is None and ev.duracion_s is None


def test_lectura_final_completa(ejecutar):
    (salida,) = ejecutar(caso(seq="6", vol="9.9", estado="COMPLETA"))
    assert EventoOrdenoIn.model_validate_json(salida).estado.value == "COMPLETA"


def test_volumen_siempre_con_punto_decimal(ejecutar):
    (salida,) = ejecutar(caso(vol="12.5"))
    assert '"volumen_l":12.50' in salida


def test_rechaza_texto_que_romperia_el_json(ejecutar):
    malos = [caso(ses='ESP"X'), caso(ses="ESP\\X"), caso(est=""), caso(seq="0"), caso(vol="-1")]
    assert ejecutar(*malos) == ["RECHAZADO"] * len(malos)


def test_no_desborda_el_buffer(ejecutar):
    assert ejecutar(caso(ses="S" * 700)) == ["RECHAZADO"]
