"""Consulta de la jornada y de cada sesion (G-19)."""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.tiempo import hoy_local
from app.db.session import get_db
from app.services import jornada as servicio

router = APIRouter(prefix="/v1", tags=["consulta"])


@router.get("/jornada")
def consultar_jornada(
    fecha: Optional[date] = Query(default=None, description="Dia local (AAAA-MM-DD). Por defecto, hoy."),
    db: Session = Depends(get_db),
):
    """Sesiones de ordeno del dia, separadas en en curso, completas, inconclusas y estimadas."""
    return servicio.jornada(db, fecha or hoy_local())


@router.get("/sesiones/{sesion_id}")
def consultar_sesion(sesion_id: str, db: Session = Depends(get_db)):
    """Una sesion con todas sus lecturas parciales."""
    datos = servicio.detalle_sesion(db, sesion_id)
    if datos is None:
        raise HTTPException(status_code=404, detail={"error": "sesion_no_encontrada", "sesion_id": sesion_id})
    return datos
