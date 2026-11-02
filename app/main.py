import asyncio
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from sqlalchemy import text

import app.models  # noqa: F401  (registra las tablas)
from app.api.v1.eventos import router as eventos_router
from app.api.v1.jornada import router as jornada_router
from app.api.v1.metricas import router as metricas_router
from app.api.vista import router as vista_router
from app.core import config
from app.core.metricas import grupo_de, metricas
from app.core.tiempo import ahora_utc
from app.db.session import Base, SessionLocal, engine
from app.services import consolidacion

logger = logging.getLogger("concentrador")

Base.metadata.create_all(bind=engine)


def _barrer() -> int:
    """Marca como INCONCLUSA toda sesion que lleva demasiado tiempo sin lecturas."""
    with SessionLocal() as db:
        return consolidacion.marcar_inconclusas(db)


async def _barrido_periodico():
    while True:
        await asyncio.sleep(config.BARRIDO_SEG)
        try:
            n = await asyncio.to_thread(_barrer)
            if n:
                logger.warning("%s sesion(es) marcada(s) INCONCLUSA por falta de lecturas", n)
        except Exception:  # el barrido nunca debe tumbar el servicio
            logger.exception("fallo el barrido de sesiones inconclusas")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(bind=engine)
    # Tras un corte de energia, lo que quedo abierto se revisa de inmediato, sin intervencion.
    try:
        with SessionLocal() as db:
            n = consolidacion.recuperar_al_arrancar(db)
        logger.info("concentrador iniciado; sesiones inconclusas al arrancar: %s", n)
    except Exception:
        logger.exception("no se pudo revisar las sesiones al arrancar")
    tarea = asyncio.create_task(_barrido_periodico())
    try:
        yield
    finally:
        tarea.cancel()


app = FastAPI(
    title="Plataforma de Ingesta de Datos de Ordeño",
    version="1.1.0",
    lifespan=lifespan,
)
app.include_router(eventos_router)
app.include_router(jornada_router)
app.include_router(metricas_router)
app.include_router(vista_router)


@app.middleware("http")
async def medir_tiempo(request: Request, call_next):
    inicio = time.perf_counter()
    respuesta = await call_next(request)
    ms = (time.perf_counter() - inicio) * 1000.0
    respuesta.headers["X-Process-Time-ms"] = f"{ms:.3f}"
    grupo = grupo_de(request.method, request.url.path)
    if grupo:
        metricas.registrar(grupo, ms)
    return respuesta


@app.exception_handler(RequestValidationError)
async def evento_rechazado(request: Request, exc: RequestValidationError):
    """Deja en el registro del servidor QUE campo fallo y desde donde, para depurar el nodo."""
    campos = "; ".join(
        f"{'.'.join(str(p) for p in e['loc'][1:]) or e['loc'][0]}: {e['msg']}" for e in exc.errors()
    )
    cliente = request.client.host if request.client else "?"
    logger.warning("422 en %s %s desde %s -> %s", request.method, request.url.path, cliente, campos)
    return await request_validation_exception_handler(request, exc)


@app.get("/health")
def health():
    try:
        with engine.connect() as con:
            con.execute(text("SELECT 1"))
        db = "ok"
    except Exception:
        db = "error"
    return {
        "status": "ok" if db == "ok" else "degradado",
        "base_de_datos": db,
        "version": app.version,
        "hora_utc": ahora_utc().isoformat(timespec="seconds") + "Z",
    }
