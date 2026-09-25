from enum import Enum


class EstadoSesion(str, Enum):
    EN_CURSO = "EN_CURSO"
    COMPLETA = "COMPLETA"
    INCONCLUSA = "INCONCLUSA"
    ESTIMADA = "ESTIMADA"


class OrigenDato(str, Enum):
    OCR = "OCR"
    MANUAL = "MANUAL"
    ESTIMADO = "ESTIMADO"


class AnimalIdOrigen(str, Enum):
    RFID = "RFID"
    INFERIDO_POR_POSICION = "INFERIDO_POR_POSICION"
    MANUAL = "MANUAL"