from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.config import settings

# Motor síncrono (para Celery workers, scripts, etc.)
engine_sync = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)
SessionSync = sessionmaker(bind=engine_sync)

# Motor asíncrono (para FastAPI) - lazy, solo se crea si se necesita
_async_engine = None


def _get_async_engine():
    """Crea el engine asíncrono bajo demanda (lazy loading)."""
    global _async_engine
    if _async_engine is None:
        from sqlalchemy.ext.asyncio import create_async_engine

        async_url = settings.DATABASE_URL.replace(
            "postgresql://", "postgresql+asyncpg://"
        )
        _async_engine = create_async_engine(
            async_url,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
        )
    return _async_engine


def get_session_sync():
    """Generador de sesión síncrona. Ideal para workers de Celery."""
    session = SessionSync()
    try:
        yield session
    finally:
        session.close()


async def get_session_async():
    """Generador de sesión asíncrona. Ideal para endpoints FastAPI."""
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.orm import sessionmaker

    engine = _get_async_engine()
    async_session = sessionmaker(bind=engine, class_=AsyncSession)
    async with async_session() as session:
        yield session
