from collections.abc import Generator
from app.config import get_settings
from app.database.base import Base
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

settings = get_settings()

connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args["check_same_thread"] = False

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,
    future=True,
)


@event.listens_for(engine, "connect")
def _enforce_sqlite_foreign_keys(dbapi_connection, connection_record):  # type: ignore[no-untyped-def]
    if settings.DATABASE_URL.startswith("sqlite"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    class_=Session,
)


def init_db() -> None:
    """Creates all tables defined on Base metadata if they do not exist yet."""
    import app.models.models  # noqa: F401

    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a transactional database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
