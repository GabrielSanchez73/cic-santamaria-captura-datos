from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import PUNTOS_ALLFLEX, PUNTOS_WAIKATO
from app.models.entidades import Animal, Estacion, LecturaParcial, SesionOrdeno
from app.services import consolidacion


class ConflictoSecuencia(Exception):
    """La sesion ya tiene una lectura con esa secuencia bajo otro id_evento."""

    def __init__(self, sesion_id: str, secuencia: int):
        self.sesion_id = sesion_id
        self.secuencia = secuencia
        super().__init__(f"La sesion {sesion_id} ya tiene la secuencia {secuencia} con otro id_evento")


def _a_utc(ts: datetime) -> datetime:
    """Normaliza a UTC y quita la zona: SQLite no guarda el desfase, asi que se guarda siempre en UTC."""
    return ts.astimezone(timezone.utc).replace(tzinfo=None)


def _tipo_medidor(estacion_id: str) -> str:
    """El tipo de medidor sale de la configuracion, no de la letra de la estacion."""
    if estacion_id in PUNTOS_WAIKATO:
        return "WAIKATO"
    if estacion_id in PUNTOS_ALLFLEX:
        return "ALLFLEX"
    return "SIN_DEFINIR"


def _lectura_existente(db: Session, id_evento: str):
    return db.query(LecturaParcial).filter(LecturaParcial.id_evento == id_evento).first()


def registrar_evento(db: Session, evento):
    # Idempotencia: si el evento ya fue recibido, devolver el registro existente.
    existente = _lectura_existente(db, evento.id_evento)
    if existente is not None:
        return existente

    try:
        lectura = _guardar(db, evento)
        db.commit()
        return lectura
    except IntegrityError:
        db.rollback()
        # Dos envios simultaneos del mismo evento: gana el primero, el segundo lo devuelve.
        existente = _lectura_existente(db, evento.id_evento)
        if existente is not None:
            return existente
        # Misma sesion y secuencia con otro id_evento: es un conflicto, no un error del servidor.
        raise ConflictoSecuencia(evento.sesion_id, evento.secuencia)


def _guardar(db: Session, evento):
    # Estacion: crear si no existe.
    if db.get(Estacion, evento.estacion_id) is None:
        db.add(Estacion(id=evento.estacion_id, tipo_medidor=_tipo_medidor(evento.estacion_id)))

    # Animal: crear si viene identificado y no existe.
    if evento.animal_id is not None and db.get(Animal, evento.animal_id) is None:
        db.add(Animal(chapeta=evento.animal_id))

    # Sesion: crear si no existe.
    sesion = db.get(SesionOrdeno, evento.sesion_id)
    if sesion is None:
        sesion = SesionOrdeno(
            id=evento.sesion_id,
            estacion_id=evento.estacion_id,
            animal_chapeta=evento.animal_id,
            ts_inicio=_a_utc(evento.ts_inicio),
            estado=evento.estado,
        )
        db.add(sesion)
    elif sesion.animal_chapeta is None and evento.animal_id is not None:
        # El animal puede identificarse despues de la primera lectura.
        sesion.animal_chapeta = evento.animal_id

    # Lectura parcial.
    lectura = LecturaParcial(
        id_evento=evento.id_evento,
        sesion_id=evento.sesion_id,
        secuencia=evento.secuencia,
        ts_lectura=_a_utc(evento.ts_lectura),
        volumen_l=evento.volumen_l,
        duracion_s=evento.duracion_s,
        animal_id_origen=evento.animal_id_origen,
        animal_id_confianza=evento.animal_id_confianza,
        origen_dato=evento.origen_dato,
        version_esquema=evento.version_esquema,
    )
    db.add(lectura)

    # Se escribe ya (sin confirmar) para que la sesion "vea" todas sus lecturas, incluida la nueva, y
    # para que una secuencia repetida falle aqui, dentro del manejo de IntegrityError.
    db.flush()
    db.expire(sesion, ["lecturas"])

    # Consolidacion: el estado de la sesion se decide en un solo lugar.
    consolidacion.aplicar_evento(sesion, lectura, evento.estado)
    return lectura
