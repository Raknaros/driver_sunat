"""
Cliente base resiliente para APIs de SUNAT.

Provee:
- Cliente HTTPX asíncrono con timeout configurable.
- Reintentos automáticos con backoff exponencial ante errores 5xx, timeout y conexión.
- Caché de tokens en Redis para compartir entre workers de Celery.
- Refresco automático de token ante error 401.
- Manejo de reportes vacíos (EmptyReportError).
"""

import logging
from abc import ABC, abstractmethod
from typing import Optional

import httpx
import redis.asyncio as aioredis
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)

from core.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Redis connection pool (singleton)
# ---------------------------------------------------------------------------
_redis_pool: Optional[aioredis.Redis] = None


async def get_redis() -> aioredis.Redis:
    """Obtiene conexión Redis (pool global)."""
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = aioredis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
        )
    return _redis_pool


# ---------------------------------------------------------------------------
# Configuración de reintentos para SUNAT
# ---------------------------------------------------------------------------
sunat_retry = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(
        (httpx.HTTPStatusError, httpx.TimeoutException, httpx.ConnectError)
    ),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)


# ---------------------------------------------------------------------------
# Excepciones personalizadas
# ---------------------------------------------------------------------------
class EmptyReportError(Exception):
    """
    Se levanta cuando el reporte se generó correctamente
    pero no contiene registros/comprobantes.
    """
    def __init__(self, ticket: str, mensaje: str = "El reporte no contiene registros"):
        self.ticket = ticket
        super().__init__(mensaje)


class SunatAuthError(Exception):
    """Error de autenticación contra SUNAT."""
    pass


# ---------------------------------------------------------------------------
# Base client
# ---------------------------------------------------------------------------
class BaseSunatAPIClient(ABC):
    """
    Cliente base abstracto para consumir APIs de SUNAT.

    Modo de uso recomendado::

        async with SireClient(ruc, username, password) as client:
            ticket = await client.solicitar_descarga_propuesta(...)
    """

    BASE_URL: str = ""

    def __init__(self, ruc: str, username: str, password: str):
        self.ruc = ruc
        self.username = username
        self.password = password
        self._access_token: Optional[str] = None
        self._client: Optional[httpx.AsyncClient] = None

    # ---- context managers -------------------------------------------------

    async def __aenter__(self):
        self._client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            timeout=settings.SUNAT_API_TIMEOUT,
        )
        await self._ensure_token()
        return self

    async def __aexit__(self, *args):
        if self._client:
            await self._client.aclose()

    # ---- token management -------------------------------------------------

    async def _get_cached_token(self) -> Optional[str]:
        """Obtiene token desde Redis cache."""
        redis = await get_redis()
        return await redis.get(f"sire:token:{self.ruc}")

    async def _set_cached_token(self, token: str):
        """Guarda token en Redis con TTL."""
        redis = await get_redis()
        await redis.setex(
            f"sire:token:{self.ruc}",
            settings.SUNAT_TOKEN_EXPIRY,
            token,
        )

    async def _invalidate_cached_token(self):
        """Invalida token en caché (ej: tras un 401)."""
        redis = await get_redis()
        await redis.delete(f"sire:token:{self.ruc}")

    async def _ensure_token(self):
        """Asegura que tenemos un token válido, usando caché Redis si es posible."""
        cached = await self._get_cached_token()
        if cached:
            self._access_token = cached
            logger.debug("Token obtenido desde Redis cache para RUC %s", self.ruc)
        else:
            self._access_token = await self._authenticate()
            await self._set_cached_token(self._access_token)
            logger.debug("Token generado y cacheado en Redis para RUC %s", self.ruc)

    @abstractmethod
    async def _authenticate(self) -> str:
        """
        Autentica contra SUNAT y retorna el access_token.
        Cada subclase implementa su propia lógica de autenticación.
        """
        ...

    # ---- request core -----------------------------------------------------

    @sunat_retry
    async def _make_request(
        self,
        method: str,
        endpoint: str,
        **kwargs,
    ) -> httpx.Response:
        """
        Método central para todas las llamadas HTTP a SUNAT.

        - Incluye header de autorización automáticamente.
        - Reintenta ante 5xx, timeout y errores de conexión (hasta 3 veces).
        - Si recibe 401, refresca el token y reintenta una vez.
        """
        if not self._client:
            raise RuntimeError(
                "Cliente no inicializado. Usar 'async with Cliente(...)'"
            )

        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {self._access_token}"

        response = await self._client.request(
            method, endpoint, headers=headers, **kwargs
        )

        # Si el token expiró → refrescamos y reintentamos 1 vez
        if response.status_code == 401:
            logger.warning(
                "Token expirado para RUC %s. Refrescando...", self.ruc
            )
            await self._invalidate_cached_token()
            self._access_token = await self._authenticate()
            await self._set_cached_token(self._access_token)
            headers["Authorization"] = f"Bearer {self._access_token}"
            response = await self._client.request(
                method, endpoint, headers=headers, **kwargs
            )

        response.raise_for_status()
        return response