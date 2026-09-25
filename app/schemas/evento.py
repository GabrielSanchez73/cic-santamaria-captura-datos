from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from app.models.enums import AnimalIdOrigen, EstadoSesion, OrigenDato


class EventoOrdenoIn(BaseModel):
    id_evento: str = Field(..., description="UUID de idempotencia del evento")
    version_esquema: str = Field(default="1.0", description="Version del contrato")
    estacion_id: str = Field(..., pattern=r"^(R[1-5]|L[1-5])$")
    sesion_id: str = Field(...)
    animal_id: Optional[str] = Field(default=None, pattern=r"^\d{4}$")
    animal_id_origen: AnimalIdOrigen
    animal_id_confianza: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    ts_inicio: datetime
    ts_lectura: datetime
    secuencia: int = Field(..., ge=1)
    volumen_l: float = Field(..., ge=0)
    duracion_s: Optional[int] = Field(default=None, ge=0)
    flujo_l_min: Optional[float] = Field(default=None)
    estado: EstadoSesion
    origen_dato: OrigenDato


class EventoOrdenoOut(BaseModel):
    id_evento: str
    sesion_id: str
    estado_sesion: str
    secuencia: int