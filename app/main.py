from fastapi import FastAPI

from app.api.v1.eventos import router as eventos_router
from app.db.session import Base, engine

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Plataforma de Ingesta de Datos de Ordeño",
    version="1.0",
)
app.include_router(eventos_router)


@app.get("/health")
def health():
    return {"status": "ok"}