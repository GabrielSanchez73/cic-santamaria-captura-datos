import os


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./concentrador.db")
TZ = os.getenv("TZ", "America/Bogota")
UMBRAL_CONFIANZA_ANIMAL = float(os.getenv("UMBRAL_CONFIANZA_ANIMAL", "0.80"))