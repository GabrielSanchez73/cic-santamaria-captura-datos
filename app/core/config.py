import os


def _lista(nombre: str) -> frozenset:
    """Lee una variable de entorno con valores separados por coma."""
    crudo = os.getenv(nombre, "")
    return frozenset(x.strip().upper() for x in crudo.split(",") if x.strip())


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./concentrador.db")
TZ = os.getenv("TZ", "America/Bogota")
UMBRAL_CONFIANZA_ANIMAL = float(os.getenv("UMBRAL_CONFIANZA_ANIMAL", "0.80"))

# Que puntos de ordeno tienen medidor Waikato y cuales Allflex. La sala tiene 10
# puntos (6 Allflex y 4 Waikato) y la letra R/L de la estacion NO indica el tipo.
# Hasta confirmar el mapa real con la finca, un punto no listado queda SIN_DEFINIR.
PUNTOS_WAIKATO = _lista("PUNTOS_WAIKATO")
PUNTOS_ALLFLEX = _lista("PUNTOS_ALLFLEX")
