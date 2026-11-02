"""Utilidades de tiempo.

Regla del proyecto: toda marca de tiempo se guarda en UTC (sin zona, porque SQLite no guarda el
desfase) y se convierte a hora local solo para mostrarla o para decidir a que dia pertenece.
"""
from datetime import date, datetime, timedelta, timezone, tzinfo

from app.core import config

# Colombia no tiene horario de verano: si el sistema no trae la base de zonas horarias
# (pasa en Windows sin el paquete tzdata) se usa el desfase fijo UTC-5.
_FALLBACK = timezone(timedelta(hours=-5), "America/Bogota")


def zona_local() -> tzinfo:
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo(config.TZ)
    except Exception:  # zona desconocida o sin base de datos de zonas
        return _FALLBACK


def ahora_utc() -> datetime:
    """Instante actual en UTC, sin zona (el formato en que se guarda todo)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def a_local(ts_utc: datetime) -> datetime:
    """Convierte una marca guardada (UTC sin zona) a hora local con zona."""
    return ts_utc.replace(tzinfo=timezone.utc).astimezone(zona_local())


def hoy_local() -> date:
    return datetime.now(zona_local()).date()


def rango_utc_del_dia(dia: date) -> tuple:
    """Inicio y fin (UTC sin zona) del dia local indicado: [inicio, fin)."""
    zona = zona_local()
    inicio_local = datetime(dia.year, dia.month, dia.day, tzinfo=zona)
    fin_local = datetime(dia.year, dia.month, dia.day, tzinfo=zona) + timedelta(days=1)
    a_utc = lambda d: d.astimezone(timezone.utc).replace(tzinfo=None)
    return a_utc(inicio_local), a_utc(fin_local)


def iso_local(ts_utc) -> str:
    """Marca guardada -> texto ISO 8601 con la zona local explicita (o None)."""
    return a_local(ts_utc).isoformat(timespec="seconds") if ts_utc is not None else None
