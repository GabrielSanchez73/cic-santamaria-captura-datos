"""Consolidacion de lecturas parciales y estados del registro (G-06 y G-08).

Reglas de dominio, sin depender de la capa HTTP:

* ``volumen_l`` de cada lectura es el volumen ACUMULADO de la sesion hasta ese momento. El volumen
  de la sesion es el de la lectura con mayor ``secuencia``; nunca se suman las lecturas.
* Una sesion solo es ``COMPLETA`` cuando llega la lectura final marcada ``COMPLETA``. Una sesion cortada
  a la mitad nunca se presenta como completa: queda ``INCONCLUSA``.
* ``INCONCLUSA`` no es definitiva: si despues llegan las lecturas que el nodo guardo durante el corte,
  la sesion se reabre o se completa con el dato real.
* Precedencia: COMPLETA > ESTIMADA > INCONCLUSA > EN_CURSO.
"""
from datetime import timedelta
from typing import List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core import config
from app.core.tiempo import ahora_utc
from app.models.entidades import LecturaParcial, SesionOrdeno
from app.models.enums import EstadoSesion

CERRADAS_DEFINITIVAS = (EstadoSesion.COMPLETA, EstadoSesion.ESTIMADA)


def lecturas_ordenadas(sesion: SesionOrdeno) -> List[LecturaParcial]:
    return sorted(sesion.lecturas, key=lambda lec: lec.secuencia)


def secuencias_faltantes(sesion: SesionOrdeno) -> List[int]:
    """Numeros de secuencia que no llegaron entre la primera y la ultima lectura (huecos)."""
    presentes = {lec.secuencia for lec in sesion.lecturas}
    if not presentes:
        return []
    return [n for n in range(1, max(presentes) + 1) if n not in presentes]


def resumen_parcial(sesion: SesionOrdeno) -> dict:
    """Volumen, duracion y marcas de la sesion segun las lecturas recibidas hasta el momento."""
    lecturas = lecturas_ordenadas(sesion)
    if not lecturas:
        return {
            "n_lecturas": 0, "volumen_l": None, "duracion_s": None,
            "ts_ultima_lectura": None, "recibido_ultimo": None,
        }
    ultima = lecturas[-1]
    # La duracion es la de la ultima lectura que la trae; los puntos Waikato no la reportan.
    duracion = next((lec.duracion_s for lec in reversed(lecturas) if lec.duracion_s is not None), None)
    return {
        "n_lecturas": len(lecturas),
        "volumen_l": ultima.volumen_l,
        "duracion_s": duracion,
        "ts_ultima_lectura": ultima.ts_lectura,
        "recibido_ultimo": max(lec.recibido_en for lec in lecturas),
    }


def _flujo(volumen: Optional[float], duracion: Optional[int]) -> Optional[float]:
    """Litros por minuto. Sin duracion (punto Waikato) no se inventa: queda nulo."""
    if volumen is None or not duracion or duracion <= 0:
        return None
    return volumen / (duracion / 60.0)


def cerrar_completa(sesion: SesionOrdeno, lectura: LecturaParcial) -> None:
    """La lectura final del nodo fija el resultado de la sesion."""
    sesion.estado = EstadoSesion.COMPLETA
    sesion.ts_fin = lectura.ts_lectura
    sesion.volumen_final_l = lectura.volumen_l
    sesion.duracion_final_s = lectura.duracion_s
    sesion.flujo_l_min = _flujo(lectura.volumen_l, lectura.duracion_s)


def cerrar_estimada(sesion: SesionOrdeno, lectura: LecturaParcial) -> None:
    """El nodo declara el valor como estimado. Se guarda marcado, sin calcular flujo."""
    sesion.estado = EstadoSesion.ESTIMADA
    sesion.ts_fin = lectura.ts_lectura
    sesion.volumen_final_l = lectura.volumen_l
    sesion.duracion_final_s = lectura.duracion_s
    sesion.flujo_l_min = None


def cerrar_inconclusa(sesion: SesionOrdeno) -> None:
    """Corte sin lectura final: se conserva lo ultimo que se supo, pero NO se calcula flujo.

    ``volumen_final_l`` es entonces una cota inferior (lo ordenado hasta la ultima lectura), por eso
    el estado impide sumarlo como produccion completa.
    """
    res = resumen_parcial(sesion)
    sesion.estado = EstadoSesion.INCONCLUSA
    sesion.ts_fin = res["ts_ultima_lectura"]
    sesion.volumen_final_l = res["volumen_l"]
    sesion.duracion_final_s = res["duracion_s"]
    sesion.flujo_l_min = None


def reabrir(sesion: SesionOrdeno) -> None:
    """Llegaron lecturas nuevas de una sesion que se habia dado por cortada."""
    sesion.estado = EstadoSesion.EN_CURSO
    sesion.ts_fin = None
    sesion.volumen_final_l = None
    sesion.duracion_final_s = None
    sesion.flujo_l_min = None


def aplicar_evento(sesion: SesionOrdeno, lectura: LecturaParcial, estado_evento: EstadoSesion) -> None:
    """Actualiza el estado de la sesion con la lectura recien guardada."""
    if estado_evento == EstadoSesion.COMPLETA:
        cerrar_completa(sesion, lectura)  # el dato final real siempre manda
        return
    if sesion.estado == EstadoSesion.COMPLETA:
        return  # una lectura tardia no reabre una sesion ya completa
    if estado_evento == EstadoSesion.ESTIMADA:
        cerrar_estimada(sesion, lectura)
        return
    if sesion.estado == EstadoSesion.ESTIMADA:
        return
    if estado_evento == EstadoSesion.INCONCLUSA:
        cerrar_inconclusa(sesion)
        return
    # EN_CURSO: solo una lectura mas nueva que todas las demas demuestra que el ordeno sigue vivo.
    if sesion.estado == EstadoSesion.INCONCLUSA:
        if lecturas_ordenadas(sesion)[-1] is lectura:
            reabrir(sesion)
    elif sesion.estado is None:
        sesion.estado = EstadoSesion.EN_CURSO


def marcar_inconclusas(db: Session, ahora=None, timeout_seg: Optional[int] = None) -> int:
    """Marca INCONCLUSA toda sesion EN_CURSO que lleva ``timeout_seg`` sin recibir lecturas.

    Usa la hora de RECEPCION de la ultima lectura, no la marca que trae el evento: asi un reloj mal
    puesto en el nodo no hace parecer cortada una sesion que si esta llegando.
    Devuelve cuantas sesiones cambio.
    """
    ahora = ahora or ahora_utc()
    limite = ahora - timedelta(seconds=timeout_seg or config.SESION_TIMEOUT_SEG)
    ultimas = (
        db.query(LecturaParcial.sesion_id, func.max(LecturaParcial.recibido_en).label("ultimo"))
        .group_by(LecturaParcial.sesion_id)
        .subquery()
    )
    candidatas = (
        db.query(SesionOrdeno)
        .join(ultimas, ultimas.c.sesion_id == SesionOrdeno.id)
        .filter(SesionOrdeno.estado == EstadoSesion.EN_CURSO, ultimas.c.ultimo < limite)
        .all()
    )
    for sesion in candidatas:
        cerrar_inconclusa(sesion)
    if candidatas:
        db.commit()
    return len(candidatas)


def recuperar_al_arrancar(db: Session) -> int:
    """Tras un reinicio (corte de energia) revisa de inmediato las sesiones que quedaron abiertas."""
    return marcar_inconclusas(db)
