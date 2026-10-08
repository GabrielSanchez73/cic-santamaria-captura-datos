import os
import tempfile
from pathlib import Path

# La app crea las tablas al importarse; que lo haga en un archivo temporal y no en concentrador.db.
os.environ["DATABASE_URL"] = "sqlite:///" + Path(tempfile.mkdtemp(), "import.db").as_posix()

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  (registra las tablas)
from app.db.session import Base, get_db
from app.main import app


@pytest.fixture()
def db():
    """Base SQLite en memoria, limpia en cada prueba."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    sesion = Session()
    yield sesion
    sesion.close()
    engine.dispose()


@pytest.fixture()
def client(db):
    def _get_db():
        yield db

    app.dependency_overrides[get_db] = _get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture()
def evento():
    """Fabrica de eventos validos del contrato v1.0; cada prueba cambia lo que necesite."""

    def _crear(**cambios):
        base = {
            "id_evento": "9f2c1e40-3b7a-4c11-9d5e-8a1f0b6d2e77",
            "version_esquema": "1.0",
            "estacion_id": "R1",
            "sesion_id": "SES-20260903-R1-004",
            "animal_id": "2101",
            "animal_id_origen": "RFID",
            "animal_id_confianza": 0.98,
            "ts_inicio": "2026-09-03T06:12:00-05:00",
            "ts_lectura": "2026-09-03T06:16:00-05:00",
            "secuencia": 1,
            "volumen_l": 8.4,
            "duracion_s": 240,
            "flujo_l_min": None,
            "estado": "EN_CURSO",
            "origen_dato": "OCR",
        }
        base.update(cambios)
        return base

    return _crear
