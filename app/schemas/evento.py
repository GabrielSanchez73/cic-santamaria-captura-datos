import uuid
from typing import Literal, Optional

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.models.enums import AnimalIdOrigen, EstadoSesion, OrigenDato


class EventoOrdenoIn(BaseModel):
    """Contrato de datos v1.0. Los nombres de campo son los acordados con el nodo de captura."""

    # Un campo que no esta en el contrato (por ejemplo uno mal escrito) se rechaza con 422.
    model_config = ConfigDict(extra="forbid")

    id_evento: str = Field(..., description="UUID de idempotencia del evento")
    version_esquema: Literal["1.0"]
    estacion_id: str = Field(..., pattern=r"^(R[1-5]|L[1-5])$")
    sesion_id: str = Field(..., min_length=1)
    animal_id: Optional[str] = Field(default=None, pattern=r"^\d{4}$")
    animal_id_origen: AnimalIdOrigen
    animal_id_confianza: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    # Toda marca de tiempo lleva zona horaria explicita (AwareDatetime rechaza las ingenuas).
    ts_inicio: AwareDatetime
    ts_lectura: AwareDatetime
    secuencia: int = Field(..., ge=1)
    volumen_l: float = Field(..., ge=0)
    duracion_s: Optional[int] = Field(default=None, ge=0)
    # No lo envia el nodo: lo calcula la plataforma. Se acepta nulo por compatibilidad.
    flujo_l_min: Optional[float] = Field(default=None)
    estado: EstadoSesion
    origen_dato: OrigenDato

    @field_validator("id_evento")
    @classmethod
    def _id_evento_es_uuid(cls, v: str) -> str:
        try:
            return str(uuid.UUID(v))
        except ValueError:
            raise ValueError("id_evento debe ser un UUID valido")

    @model_validator(mode="after")
    def _lectura_no_antes_del_inicio(self):
        if self.ts_lectura < self.ts_inicio:
            raise ValueError("ts_lectura no puede ser anterior a ts_inicio")
        return self


class EventoOrdenoOut(BaseModel):
    id_evento: str
    sesion_id: str
    estado_sesion: str
    secuencia: int
