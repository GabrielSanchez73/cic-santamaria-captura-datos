"""Medicion de desempeno (G-22): tiempos de respuesta del propio concentrador.

Mide el tiempo que el servidor tarda en atender cada peticion (no incluye la red entre el nodo y el
concentrador; esa se mide desde el cliente con scripts/medir_latencia.py).
"""
import math
import threading
from collections import deque
from typing import Dict, Optional

GRUPOS = ("ingesta", "consulta")


def grupo_de(metodo: str, ruta: str) -> Optional[str]:
    if metodo == "POST" and ruta == "/v1/eventos":
        return "ingesta"
    if metodo == "GET" and (ruta.startswith(("/v1/jornada", "/v1/sesiones")) or ruta == "/jornada"):
        return "consulta"
    return None


def _percentil(ordenados, p: float) -> float:
    """Percentil por rango mas cercano; no depende de numpy."""
    k = max(0, math.ceil(p / 100.0 * len(ordenados)) - 1)
    return ordenados[k]


class Metricas:
    def __init__(self, capacidad: int = 5000):
        self._datos: Dict[str, deque] = {g: deque(maxlen=capacidad) for g in GRUPOS}
        self._totales: Dict[str, int] = {g: 0 for g in GRUPOS}
        self._lock = threading.Lock()

    def registrar(self, grupo: str, milisegundos: float) -> None:
        with self._lock:
            self._datos[grupo].append(milisegundos)
            self._totales[grupo] += 1

    def reiniciar(self) -> None:
        with self._lock:
            for g in GRUPOS:
                self._datos[g].clear()
                self._totales[g] = 0

    def resumen(self) -> dict:
        salida = {}
        with self._lock:
            for g in GRUPOS:
                valores = sorted(self._datos[g])
                if not valores:
                    salida[g] = {"peticiones": self._totales[g], "muestras": 0}
                    continue
                salida[g] = {
                    "peticiones": self._totales[g],
                    "muestras": len(valores),
                    "media_ms": round(sum(valores) / len(valores), 3),
                    "p50_ms": round(_percentil(valores, 50), 3),
                    "p95_ms": round(_percentil(valores, 95), 3),
                    "p99_ms": round(_percentil(valores, 99), 3),
                    "max_ms": round(valores[-1], 3),
                }
        return salida


metricas = Metricas()
