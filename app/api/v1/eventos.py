"""Router HTTP de ingesta de eventos."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.evento import EventoOrdenoIn, EventoOrdenoOut
from app.services.ingesta import ConflictoSecuencia, registrar_evento

router = APIRouter(prefix="/v1", tags=["eventos"])


@router.post(
    "/eventos",
    status_code=status.HTTP_201_CREATED,
    response_model=EventoOrdenoOut,
)
def crear_evento(evento: EventoOrdenoIn, db: Session = Depends(get_db)):
    """Recibe un evento de ordeno, valida, consolida y persiste."""
    try:
        lectura = registrar_evento(db, evento)
    except ConflictoSecuencia as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "secuencia_duplicada",
                "sesion_id": exc.sesion_id,
                "secuencia": exc.secuencia,
                "mensaje": "La sesion ya tiene una lectura con esa secuencia bajo otro id_evento.",
            },
        )
    return EventoOrdenoOut(
        id_evento=str(lectura.id_evento),
        sesion_id=lectura.sesion_id,
        estado_sesion=lectura.sesion.estado.value,
        secuencia=lectura.secuencia,
    )
