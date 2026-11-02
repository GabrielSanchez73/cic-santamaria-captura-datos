"""Consulta de la jornada de ordeno (G-19).

Separa lo que se midio completo de lo que quedo cortado o estimado, para que un volumen parcial
nunca se confunda con produccion completa.
"""
from datetime import date
from typing import Optional

from sqlalchemy.orm import Session, selectinload

from app.core.config import SESION_TIMEOUT_SEG, TZ
from app.core.tiempo import iso_local, rango_utc_del_dia
from app.models.entidades import SesionOrdeno
from app.models.enums import EstadoSesion
from app.services import consolidacion


def _fila(sesion: SesionOrdeno) -> dict:
    res = consolidacion.resumen_parcial(sesion)
    cerrada = sesion.estado in (EstadoSesion.COMPLETA, EstadoSesion.ESTIMADA)
    # En una sesion cerrada manda el resultado final; en una abierta o cortada, lo ultimo que se supo.
    volumen = sesion.volumen_final_l if sesion.volumen_final_l is not None else res["volumen_l"]
    duracion = sesion.duracion_final_s if sesion.duracion_final_s is not None else res["duracion_s"]
    return {
        "sesion_id": sesion.id,
        "estacion_id": sesion.estacion_id,
        "tipo_medidor": sesion.estacion.tipo_medidor if sesion.estacion else None,
        "animal_id": sesion.animal_chapeta,
        "estado": sesion.estado.value,
        "ts_inicio": iso_local(sesion.ts_inicio),
        "ts_fin": iso_local(sesion.ts_fin),
        "ts_ultima_lectura": iso_local(res["ts_ultima_lectura"]),
        "volumen_l": volumen,
        # Cota inferior: lo ordenado hasta la ultima lectura. Solo es total en una sesion COMPLETA.
        "volumen_es_parcial": not cerrada,
        "duracion_s": duracion,
        "flujo_l_min": None if sesion.flujo_l_min is None else round(sesion.flujo_l_min, 3),
        "n_lecturas": res["n_lecturas"],
        "secuencias_faltantes": consolidacion.secuencias_faltantes(sesion),
    }


def _suma(filas) -> float:
    return round(sum(f["volumen_l"] or 0.0 for f in filas), 3)


def jornada(db: Session, dia: date) -> dict:
    # Antes de contestar, se actualiza lo que ya se corto: la consulta nunca muestra como "en curso"
    # una sesion que lleva mas del tiempo limite sin lecturas.
    consolidacion.marcar_inconclusas(db)

    inicio, fin = rango_utc_del_dia(dia)
    sesiones = (
        db.query(SesionOrdeno)
        .options(selectinload(SesionOrdeno.lecturas), selectinload(SesionOrdeno.estacion))
        .filter(SesionOrdeno.ts_inicio >= inicio, SesionOrdeno.ts_inicio < fin)
        .order_by(SesionOrdeno.ts_inicio, SesionOrdeno.id)
        .all()
    )
    filas = [_fila(s) for s in sesiones]
    por_estado = {e.value: [f for f in filas if f["estado"] == e.value] for e in EstadoSesion}
    completas = por_estado["COMPLETA"]
    return {
        "fecha": dia.isoformat(),
        "zona_horaria": TZ,
        "tiempo_limite_sesion_s": SESION_TIMEOUT_SEG,
        "totales": {
            "sesiones": len(filas),
            "en_curso": len(por_estado["EN_CURSO"]),
            "completas": len(completas),
            "inconclusas": len(por_estado["INCONCLUSA"]),
            "estimadas": len(por_estado["ESTIMADA"]),
            "con_secuencias_faltantes": sum(1 for f in filas if f["secuencias_faltantes"]),
            # Solo las sesiones COMPLETA se suman como produccion; el resto se informa aparte.
            "volumen_completas_l": _suma(completas),
            "volumen_estimado_l": _suma(por_estado["ESTIMADA"]),
            "volumen_inconcluso_minimo_l": _suma(por_estado["INCONCLUSA"]),
        },
        "en_curso": por_estado["EN_CURSO"],
        "completas": completas,
        "inconclusas": por_estado["INCONCLUSA"],
        "estimadas": por_estado["ESTIMADA"],
    }


def detalle_sesion(db: Session, sesion_id: str) -> Optional[dict]:
    consolidacion.marcar_inconclusas(db)
    sesion = (
        db.query(SesionOrdeno)
        .options(selectinload(SesionOrdeno.lecturas), selectinload(SesionOrdeno.estacion))
        .filter(SesionOrdeno.id == sesion_id)
        .first()
    )
    if sesion is None:
        return None
    datos = _fila(sesion)
    datos["lecturas"] = [
        {
            "id_evento": lec.id_evento,
            "secuencia": lec.secuencia,
            "ts_lectura": iso_local(lec.ts_lectura),
            "volumen_l": lec.volumen_l,
            "duracion_s": lec.duracion_s,
            "animal_id_origen": lec.animal_id_origen.value,
            "animal_id_confianza": lec.animal_id_confianza,
            "origen_dato": lec.origen_dato.value,
        }
        for lec in consolidacion.lecturas_ordenadas(sesion)
    ]
    return datos
