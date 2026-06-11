import boto3
from botocore.exceptions import ClientError

from core.config import settings


class S3StorageManager:
    """Gestor de almacenamiento en AWS S3 (o S3-compatible como Cloudflare R2)."""

    def __init__(self):
        endpoint_url = settings.AWS_ENDPOINT_URL or None
        self.client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_REGION,
        )
        self.bucket = settings.AWS_BUCKET_NAME

    def upload_file_bytes(self, file_bytes: bytes, s3_key: str) -> str:
        """
        Sube bytes a S3 y retorna la URI del objeto.

        Args:
            file_bytes: Contenido del archivo en bytes.
            s3_key: Ruta/destino dentro del bucket (ej: "sire/202501/12345678.zip").

        Returns:
            str: URI del objeto en formato s3://bucket/key.

        Raises:
            ClientError: Si falla la subida a S3.
        """
        try:
            self.client.put_object(
                Bucket=self.bucket,
                Key=s3_key,
                Body=file_bytes,
            )
            return f"s3://{self.bucket}/{s3_key}"
        except ClientError as e:
            raise RuntimeError(f"Error al subir archivo a S3: {e}") from e