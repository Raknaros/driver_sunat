# ---------------------------------------------------------------------------
# Dockerfile para el microservicio driver_sunat
# ---------------------------------------------------------------------------
# Usa una imagen slim de Python 3.11 para mantener el tamaño reducido.
# Instala dependencias del sistema necesarias para psycopg2 y cryptography.
# ---------------------------------------------------------------------------

FROM python:3.11-slim

# Variables de entorno para Python
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Establecer directorio de trabajo
WORKDIR /app

# Instalar dependencias del sistema necesarias para psycopg2
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        gcc \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copiar requirements e instalar dependencias Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el código de la aplicación
COPY . .

# Puerto por defecto para Uvicorn
EXPOSE 8000

# Comando por defecto: inicia Uvicorn con la app FastAPI
# Se puede sobrescribir en docker-compose para el worker de Celery
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]