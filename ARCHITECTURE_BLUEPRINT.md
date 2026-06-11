## Visión General de la Arquitectura

**Objetivo:** Transformar `driver_sunat` en un microservicio _headless_, _stateless_ y orientado a eventos.

**Stack Tecnológico:**

- **API Web:** FastAPI + Uvicorn
    
- **Procesamiento Background:** Celery + Redis
    
- **Peticiones HTTP:** HTTPX (asíncrono) + Tenacity (reintentos)
    
- **Base de Datos:** PostgreSQL (SQLAlchemy)
    
- **Almacenamiento:** AWS S3 (Boto3)
    

## 📂 Estructura de Directorios Deseada

Al finalizar, tu proyecto debe tener esta estructura. Usaremos esto como mapa:

Plaintext

```
driver_sunat/
├── api_clients/
│   ├── __init__.py
│   ├── base_client.py       # Lógica HTTPX + Tenacity + Tokens
│   └── sire/
│       ├── __init__.py
│       ├── client.py        # Implementación de endpoints SIRE
│       └── schemas.py       # Estructuras de datos (Pydantic)
├── core/
│   ├── config.py            # Variables de entorno (Pydantic BaseSettings)
│   ├── database.py          # Conexión SQLAlchemy a PostgreSQL
│   └── storage.py           # S3Manager (Boto3)
├── models/
│   ├── base.py              # Declarative Base
│   ├── credenciales.py      # Mapeo a priv.entities (Solo Lectura)
│   └── operaciones.py       # Tabla sire_operaciones (Escritura)
├── api/
│   ├── routes/
│   │   └── sire.py          # Endpoints FastAPI
│   └── main.py              # Inicialización de FastAPI
├── workers/
│   ├── celery_app.py        # Configuración de Celery
│   └── sire_tasks.py        # Tareas background (Descarga, Webhooks)
├── ARCHITECTURE_BLUEPRINT.md
├── requirements.txt
├── Dockerfile
└── docker-compose.yml
```

## 🛠️ Fases de Implementación (Paso a Paso)

### Fase 1: Limpieza y Dependencias (Pruning)

**Objetivo:** Eliminar el rastro monolítico y preparar el entorno moderno.

1. **Eliminar:** Borrar la carpeta `automation/tasks/` por completo (Selenium). Borrar `driver_manager.py`. Borrar `scheduler.py`. Borrar `cli.py`.
    
2. **Actualizar `requirements.txt`:** Reemplazar el contenido con:
    
    Plaintext
    
    ```
    fastapi
    uvicorn
    pydantic
    pydantic-settings
    celery
    redis
    httpx
    tenacity
    boto3
    sqlalchemy
    psycopg2-binary
    cryptography
    ```
    

### Fase 2: Capa Core (Configuración, BD y Almacenamiento)

**Objetivo:** Establecer las conexiones externas de forma robusta.

1. **`core/config.py`:** Migrar las variables usando `pydantic-settings`. Añadir variables para `REDIS_URL`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_BUCKET_NAME` y `ORCHESTRATOR_WEBHOOK_URL`.
    
2. **`core/database.py`:** Crear el motor asíncrono o síncrono de `SQLAlchemy` conectado a la BD central PostgreSQL.
    
3. **`models/`:** * Mapear las tablas oficiales (`credenciales`, `otras_credenciales`) asegurando que SQLAlchemy sepa que son **Solo Lectura**.
    
    - Crear el modelo `SireOperacion` (ID, ruc, periodo, tipo_operacion, ticket, s3_url, estado, log).
        
4. **`core/storage.py`:** Crear la clase `S3StorageManager` con el método `upload_file_bytes(file_bytes, s3_key)`.
    

### Fase 3: Cliente API Resiliente (El Corazón)

**Objetivo:** Abstraer las llamadas a SUNAT con tolerancia a fallos.

1. **`api_clients/base_client.py`:**
    
    - Crear `BaseSunatAPIClient`.
        
    - Implementar método `_make_request(method, url, ...)` usando `httpx.AsyncClient`.
        
    - Decorar este método con `@retry` de `tenacity` (Ej: esperar 2s, luego 4s, máximo 3 intentos ante errores 500, 502, 503, 504 de SUNAT).
        
    - Implementar la lógica automática de intercepción de error 401 (refrescar token y reintentar).
        
2. **`api_clients/sire/client.py`:**
    
    - Heredar de `BaseSunatAPIClient`.
        
    - Crear los **Cascarones de SIRE** (Implementarás el código interno después):
        
        Python
        
        ```
        class SireClient(BaseSunatAPIClient):
            async def solicitar_descarga_propuesta(self, periodo: str, tipo: str) -> str:
                # Retorna el Ticket
                pass
        
            async def consultar_estado_ticket(self, ticket: str) -> dict:
                # Retorna estado y params de descarga si está listo
                pass
        
            async def descargar_archivo(self, download_params: dict) -> bytes:
                # Retorna los bytes del ZIP en memoria. NADA DE DISCO.
                pass
        
            async def aceptar_propuesta(self, periodo: str, tipo: str) -> str:
                # Endpoint para aceptar la propuesta de SUNAT
                pass
        
            async def reemplazar_propuesta(self, periodo: str, tipo: str, file_bytes: bytes) -> str:
                # Endpoint para subir archivo ZIP/TXT que reemplaza propuesta
                pass
        
            async def agregar_comprobantes(self, periodo: str, file_bytes: bytes) -> str:
                # Añadir facturas a la propuesta
                pass
        
            async def generar_registro(self, periodo: str, tipo: str) -> str:
                # Consolidar y generar registro
                pass
        ```
        

### Fase 4: Procesamiento Background (Celery)

**Objetivo:** Manejar las largas esperas de SUNAT sin bloquear.

1. **`workers/celery_app.py`:** Configurar la instancia de Celery apuntando a `REDIS_URL`.
    
2. **`workers/sire_tasks.py`:**
    
    - Crear `@celery.task` llamada `task_procesar_descarga_sire(ruc, periodo, tipo, webhook_url)`.
        
    - **Lógica de la tarea:**
        
        1. Instanciar `SireClient`.
            
        2. Llamar `solicitar_descarga_propuesta`. Actualizar PostgreSQL a `PROCESSING` con el `ticket`.
            
        3. Entrar en un bucle inteligente (o hacer _chaining_ de tareas de Celery) que llame a `consultar_estado_ticket` cada X minutos.
            
        4. Cuando esté listo, llamar a `descargar_archivo` (obtiene `bytes`).
            
        5. Llamar a `S3StorageManager.upload_file_bytes()`. Actualizar PostgreSQL a `S3_UPLOADED`.
            
        6. Llamar a `httpx.post(webhook_url)` enviando la ruta de S3 al Orquestador.
            

### Fase 5: API REST Frontal (FastAPI)

**Objetivo:** Proveer la interfaz para el Orquestador.

1. **`api/routes/sire.py`:**
    
    - Crear endpoint `POST /api/v1/sire/descargar`.
        
    - **Lógica:** Recibe un JSON (`RUC`, `periodo`, `tipo`, `webhook_url`). Valida en PostgreSQL si las credenciales existen. Encola la tarea llamando a `task_procesar_descarga_sire.delay(...)`.
        
    - Retorna inmediatamente `{"status": "accepted", "job_id": "..."}` con un código `HTTP 202`.
        
2. **`api/main.py`:** Configurar el app de FastAPI, incluir el router de SIRE y un endpoint `GET /health` (vital para Docker/Kubernetes).
    

### Fase 6: Dockerización

**Objetivo:** Despliegue agnóstico en el servidor Debian.

1. **`Dockerfile`:** Usar imagen `python:3.11-slim`. Instalar requerimientos, copiar código.
    
2. **`docker-compose.yml`:**
    
    - Definir el servicio `redis:alpine` (para no tener que instalar Redis nativo en Debian).
        
    - Definir el servicio `api` (FastAPI). Comando: `uvicorn api.main:app --host 0.0.0.0`.
        
    - Definir el servicio `celery_worker`. Comando: `celery -A workers.celery_app worker --loglevel=info`.
        