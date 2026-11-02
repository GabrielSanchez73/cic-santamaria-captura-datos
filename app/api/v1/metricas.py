"""Tiempos de respuesta del concentrador (G-22)."""
from fastapi import APIRouter

from app.core.metricas import metricas

router = APIRouter(prefix="/v1", tags=["desempeno"])


@router.get("/metricas")
def ver_metricas():
    """Media, p50, p95, p99 y maximo (en milisegundos) de la ingesta y de la consulta."""
    return metricas.resumen()


@router.delete("/metricas")
def reiniciar_metricas():
    """Pone los contadores en cero antes de una serie de mediciones."""
    metricas.reiniciar()
    return {"reiniciado": True}
