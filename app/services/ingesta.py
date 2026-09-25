from sqlalchemy.orm import Session

from app.models.entidades import (
    Animal,
    Estacion,
    LecturaParcial,
    SesionOrdeno,
)
from app.models.enums import EstadoSesion


def registrar_evento(db: Session, evento):
    # Idempotencia: si el evento ya fue recibido, devolver el registro existente.
    existente = (
        db.query(LecturaParcial)
        .filter(LecturaParcial.id_evento == evento.id_evento)
        .first()
    )
    if existente is not None:
        return existente

    # Estacion: crear si no existe.
    estacion = (
        db.query(Estacion)
        .filter(Estacion.id == evento.estacion_id)
        .first()
    )
    if estacion is None:
        tipo = "ALLFLEX" if evento.estacion_id.startswith("R") else "WAIKATO"
        estacion = Estacion(id=evento.estacion_id, tipo_medidor=tipo)
        db.add(estacion)

    # Animal: crear si viene identificado y no existe.
    animal = None
    if evento.animal_id is not None:
        animal = (
            db.query(Animal)
            .filter(Animal.chapeta == evento.animal_id)
            .first()
        )
        if animal is None:
            animal = Animal(chapeta=evento.animal_id)
            db.add(animal)

    # Sesion: crear si no existe.
    sesion = (
        db.query(SesionOrdeno)
        .filter(SesionOrdeno.id == evento.sesion_id)
        .first()
    )
    if sesion is None:
        sesion = SesionOrdeno(
            id=evento.sesion_id,
            estacion_id=evento.estacion_id,
            animal_chapeta=evento.animal_id,
            ts_inicio=evento.ts_inicio,
            ts_fin=None,
            estado=estado_a_guardar(evento),
            volumen_final_l=None,
            duracion_final_s=None,
            flujo_l_min=None,
        )
        db.add(sesion)

    # Lectura parcial.
    lectura = LecturaParcial(
        id_evento=evento.id_evento,
        sesion_id=evento.sesion_id,
        secuencia=evento.secuencia,
        ts_lectura=evento.ts_lectura,
        volumen_l=evento.volumen_l,
        duracion_s=evento.duracion_s,
        animal_id_origen=evento.animal_id_origen,
        animal_id_confianza=evento.animal_id_confianza,
        origen_dato=evento.origen_dato,
        version_esquema=evento.version_esquema,
    )
    db.add(lectura)

    # Cierre automatico si el evento marca la sesiócompleta.
    if evento.estado == EstadoSesion.COMPLETA:
        sesion.ts_fin = evento.ts_lectura
        sesion.volumen_final_l = evento.volumen_l
        sesion.duracion_final_s = evento.duracion_s
        sesion.estado = EstadoSesion.COMPLETA
        if evento.duracion_s and evento.duracion_s > 0:
            sesion.flujo_l_min = (
                evento.volumen_l / (evento.duracion_s / 60.0)
            )
        else:
            sesion.flujo_l_min = None

    db.commit()
    return lectura


def estado_a_guardar(evento):
    """El estado inicial de la sesióes el estado del primer evento."""
    return evento.estado