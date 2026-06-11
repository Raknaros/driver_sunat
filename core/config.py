from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database
    DATABASE_URL: str = "postgresql://user:password@localhost:5432/dbname"

    # Redis (Celery + Token Cache)
    REDIS_URL: str = "redis://localhost:6379/0"

    # AWS S3 (o S3-compatible como Cloudflare R2)
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_BUCKET_NAME: str = ""
    AWS_REGION: str = "us-east-1"
    AWS_ENDPOINT_URL: str = ""  # Para R2: https://<accountid>.r2.cloudflarestorage.com

    # Webhook
    ORCHESTRATOR_WEBHOOK_URL: str = ""

    # SUNAT API
    SUNAT_API_TIMEOUT: int = 60
    SUNAT_TOKEN_EXPIRY: int = 1800  # 30 minutos en segundos


settings = Settings()