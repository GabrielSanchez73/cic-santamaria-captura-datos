import os

from dotenv import load_dotenv

# Lee el archivo .env si existe. Una variable ya definida en el entorno (por ejemplo la que fija
# una prueba o el servicio de systemd) tiene prioridad sobre el archivo.
load_dotenv()


def _lista(nombre: str) -> frozenset:
    """Lee una variable de entorno con valores separados por coma."""
    crudo = os.getenv(nombre, "")
    return frozenset(x.strip().upper() for x in crudo.split(",") if x.strip())


def _entero(nombre: str, defecto: int) -> int:
    try:
        valor = int(os.getenv(nombre, defecto))
    except ValueError:
        return defecto
    return valor if valor > 0 else defecto


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./concentrador.db")
TZ = os.getenv("TZ", "America/Bogota")
UMBRAL_CONFIANZA_ANIMAL = float(os.getenv("UMBRAL_CONFIANZA_ANIMAL", "0.80"))

# El nodo envia una lectura parcial cada INTERVALO_LECTURA_PARCIAL_SEG durante el ordeno.
INTERVALO_LECTURA_PARCIAL_SEG = _entero("INTERVALO_LECTURA_PARCIAL_SEG", 120)

# Una sesion EN_CURSO que lleva SESION_TIMEOUT_SEG sin recibir lecturas se marca INCONCLUSA.
# Por defecto son tres intervalos: tolera que se pierda una lectura sin dar la sesion por cortada.
SESION_TIMEOUT_SEG = _entero("SESION_TIMEOUT_SEG", 3 * INTERVALO_LECTURA_PARCIAL_SEG)

# Cada cuanto revisa el concentrador si hay sesiones cortadas (ademas de al arrancar y al consultar).
BARRIDO_SEG = _entero("BARRIDO_SEG", 60)

# Que puntos de ordeno tienen medidor Waikato y cuales Allflex. La sala tiene 10
# puntos (6 Allflex y 4 Waikato) y la letra R/L de la estacion NO indica el tipo.
# Hasta confirmar el mapa real con la finca, un punto no listado queda SIN_DEFINIR.
PUNTOS_WAIKATO = _lista("PUNTOS_WAIKATO")
PUNTOS_ALLFLEX = _lista("PUNTOS_ALLFLEX")
