from datetime import datetime
from enum import Enum

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum as SAEnum,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.db.session import Base
from app.models.enums import AnimalIdOrigen, EstadoSesion, OrigenDato


class Estacion(Base):
    __tablename__ = "estacion"

    id = Column(String, primary_key=True)
    tipo_medidor = Column(SAEnum("ALLFLEX", "WAIKATO", name="tipo_medidor_enum"), nullable=False)

    sesiones = relationship("SesionOrdeno", back_populates="estacion")


class Animal(Base):
    __tablename__ = "animal"

    chapeta = Column(String, primary_key=True)
    activo = Column(Boolean, default=True)

    sesiones = relationship("SesionOrdeno", back_populates="animal")


class SesionOrdeno(Base):
    __tablename__ = "sesion_ordeno"

    id = Column(String, primary_key=True)
    estacion_id = Column(String, ForeignKey("estacion.id"), nullable=False)
    animal_chapeta = Column(String, ForeignKey("animal.chapeta"), nullable=True)
    ts_inicio = Column(DateTime, nullable=False)
    ts_fin = Column(DateTime, nullable=True)
    estado = Column(SAEnum(EstadoSesion, name="estado_sesion_enum"), nullable=False)
    volumen_final_l = Column(Float, nullable=True)
    duracion_final_s = Column(Integer, nullable=True)
    flujo_l_min = Column(Float, nullable=True)

    estacion = relationship("Estacion", back_populates="sesiones")
    animal = relationship("Animal", back_populates="sesiones")
    lecturas = relationship(
        "LecturaParcial",
        back_populates="sesion",
        cascade="all, delete-orphan",
    )


class LecturaParcial(Base):
    __tablename__ = "lectura_parcial"

    id_evento = Column(String, primary_key=True)
    sesion_id = Column(String, ForeignKey("sesion_ordeno.id"), nullable=False)
    secuencia = Column(Integer, nullable=False)
    ts_lectura = Column(DateTime, nullable=False)
    volumen_l = Column(Float, nullable=False)
    duracion_s = Column(Integer, nullable=True)
    animal_id_origen = Column(SAEnum(AnimalIdOrigen, name="animal_id_origen_enum"), nullable=False)
    animal_id_confianza = Column(Float, nullable=True)
    origen_dato = Column(SAEnum(OrigenDato, name="origen_dato_enum"), nullable=False)
    version_esquema = Column(String, nullable=False)
    recibido_en = Column(DateTime, default=datetime.utcnow, nullable=False)

    sesion = relationship("SesionOrdeno", back_populates="lecturas")

    __table_args__ = (
        UniqueConstraint("sesion_id", "secuencia", name="uq_sesion_secuencia"),
    )