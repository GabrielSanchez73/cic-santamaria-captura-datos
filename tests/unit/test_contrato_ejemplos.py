"""Los ejemplos publicados en docs/contrato/ejemplos cumplen el esquema vigente."""
import json
from pathlib import Path

import pytest

from app.schemas.evento import EventoOrdenoIn

EJEMPLOS = sorted((Path(__file__).resolve().parents[2] / "docs" / "contrato" / "ejemplos").glob("*.json"))


def test_hay_ejemplos():
    assert EJEMPLOS


@pytest.mark.parametrize("ruta", EJEMPLOS, ids=lambda r: r.name)
def test_ejemplo_valido(ruta):
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    for evento in datos if isinstance(datos, list) else [datos]:
        EventoOrdenoIn.model_validate(evento)
