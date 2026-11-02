from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base, Session

from app.core.config import DATABASE_URL


engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}
    if DATABASE_URL.startswith("sqlite")
    else {},
)

if DATABASE_URL.startswith("sqlite"):

    @event.listens_for(engine, "connect")
    def _pragmas_sqlite(conexion, _registro):
        """Ajustes de SQLite pensados para un concentrador que puede perder la energia.

        - WAL: una escritura a medias no deja la base danada y las consultas no bloquean la ingesta.
        - synchronous=FULL: cuando la API responde 201, el dato ya esta en disco.
        - busy_timeout: dos peticiones simultaneas esperan su turno en vez de fallar.
        """
        cursor = conexion.cursor()
        try:
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=FULL")
            cursor.execute("PRAGMA busy_timeout=5000")
        finally:
            cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
