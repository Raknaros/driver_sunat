from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

from core.config import settings

# Motor síncrono (para Celery workers, scripts, etc.)
engine_sync = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)
SessionSync = sessionmaker(bind=engine_sync)

# Motor asíncrono (para FastAPI)
ASYNC_DATABASE_URL = settings.DATABASE_URL.replace(
    "postgresql://", "postgresql+asyncpg://"
)
engine_async = create_async_engine(
    ASYNC_DATABASE_URL,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)
SessionAsync = sessionmaker(bind=engine_async, class_=AsyncSession)


def get_session_sync():
    """Generador de sesión síncrona. Ideal para workers de Celery."""
    session = SessionSync()
    try:
        yield session
    finally:
        session.close()


async def get_session_async():
    """Generador de sesión asíncrona. Ideal para endpoints FastAPI."""
    async with SessionAsync() as session:
        yield session