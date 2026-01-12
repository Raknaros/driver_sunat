# Driver SUNAT - Financial Automation System

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?style=for-the-badge&logo=python)](https://www.python.org/)
[![Selenium](https://img.shields.io/badge/Selenium-4.0%2B-green?style=for-the-badge&logo=selenium)](https://www.selenium.dev/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-14%2B-336791?style=for-the-badge&logo=postgresql)](https://www.postgresql.org/)
[![License](https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge)](LICENSE)

[English Version](#english-version) | [Versión en Español](#versión-en-español)

---

<a name="english-version"></a>
## 🇬🇧 English Version

### Overview
**Driver SUNAT** is a high-performance financial automation system designed to interact with the Peruvian Tax Administration (SUNAT) portal. Developed by a Software Engineer with a background in Economics and over 8 years of accounting experience, this tool bridges the gap between raw tax data and actionable financial intelligence.

It automates critical accounting workflows such as electronic mailbox monitoring, invoice retrieval, and tax report generation (T-Registro, SIRE), ensuring compliance and efficiency for accounting firms and enterprises managing multiple tax IDs (RUCs).

### Key Features
*   **Robust Automation Engine**: Built on **Selenium WebDriver** with a custom `BaseTask` architecture that handles login sessions, retries, and error recovery gracefully.
*   **Multi-Tenant Support**: capable of managing hundreds of taxpayers (RUCs) simultaneously, with secure credential management.
*   **Financial Data Pipeline**:
    *   **Electronic Mailbox**: Scrapes, parses, and synchronizes official SUNAT notifications to a central database.
    *   **SIRE Integration**: Automates the request and download of Sales and Purchases proposals (Sistema Integrado de Registros Electrónicos).
    *   **T-Registro Reports**: Automates the request and retrieval of employee and service provider reports.
*   **Hybrid Database Architecture**:
    *   **Local Cache (SQLite)**: For high-speed session management and temporary data storage.
    *   **Central Warehouse (PostgreSQL)**: For persistent storage, analytics, and integration with ERP systems.
*   **Enterprise Scheduler**: Powered by **APScheduler**, it orchestrates tasks like daily mailbox checks (8:00 AM) and monthly tax report generation.
*   **Security First**: Implements **Fernet (symmetric encryption)** for safeguarding sensitive tax credentials.

### Tech Stack
*   **Core**: Python 3.10+
*   **Automation**: Selenium WebDriver, WebDriver Manager
*   **Data Processing**: Pandas, NumPy
*   **Scheduling**: APScheduler (BlockingScheduler)
*   **CLI**: Click (Command Line Interface)
*   **Database**: PostgreSQL (psycopg2), SQLite
*   **Security**: Cryptography (Fernet)

### Installation & Setup

1.  **Clone the repository**:
    ```bash
    git clone https://github.com/your-repo/driver_sunat.git
    cd driver_sunat
    ```

2.  **Install dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

3.  **Environment Configuration**:
    Create a `.env` file in the root directory:
    ```env
    ENCRYPTION_KEY=your_32_byte_base64_key
    PG_HOST=localhost
    PG_PORT=5432
    PG_DBNAME=financial_db
    PG_USER=admin
    PG_PASSWORD=secret
    ```

4.  **Initialize Local Database**:
    ```bash
    python main.py init_db
    ```

### Usage

The system is controlled via a CLI entry point `main.py`.

*   **Start the Scheduler (Production Mode)**:
    ```bash
    python main.py scheduler
    ```
    *Runs background jobs for mailbox checks, SIRE reports, and data synchronization.*

*   **Manual Task Execution**:
    ```bash
    # Check mailbox for a specific Tax ID (RUC)
    python main.py tasks check-mailbox --ruc 20123456789

    # Request SIRE Proposals (Sales/Purchases)
    python main.py tasks sire-request --periodo 202310

    # Download T-Registro Reports
    python main.py tasks download-reports --ruc 20123456789
    ```

---

<a name="versión-en-español"></a>
## 🇵🇪 Versión en Español

### Descripción General
**Driver SUNAT** es un sistema de automatización financiera de alto rendimiento diseñado para interactuar con el portal de la SUNAT (Superintendencia Nacional de Aduanas y de Administración Tributaria). Desarrollado con una perspectiva dual de Ingeniería de Software y Economía, esta herramienta transforma datos tributarios crudos en información financiera procesable.

Automatiza flujos de trabajo contables críticos como el monitoreo del Buzón Electrónico, la descarga de comprobantes de pago y la generación de reportes tributarios (SIRE, T-Registro), asegurando el cumplimiento normativo y la eficiencia operativa para estudios contables y empresas.

### Características Principales
*   **Motor de Automatización Robusto**: Construido sobre **Selenium WebDriver** con una arquitectura `BaseTask` personalizada que maneja sesiones de login, reintentos automáticos y recuperación de errores.
*   **Soporte Multi-Empresa**: Capacidad para gestionar cientos de contribuyentes (RUCs) simultáneamente, con gestión segura de credenciales (Clave SOL).
*   **Pipeline de Datos Financieros**:
    *   **Buzón Electrónico**: Extrae, procesa y sincroniza notificaciones oficiales hacia una base de datos central.
    *   **Integración SIRE**: Automatiza la solicitud y descarga de propuestas de Ventas y Compras del Sistema Integrado de Registros Electrónicos.
    *   **Reportes T-Registro**: Automatiza la solicitud y recuperación de reportes de planilla y locadores de servicios.
*   **Arquitectura de Base de Datos Híbrida**:
    *   **Caché Local (SQLite)**: Para gestión de sesiones de alta velocidad y almacenamiento temporal.
    *   **Almacén Central (PostgreSQL)**: Para persistencia, análisis financiero e integración con ERPs.
*   **Programador Empresarial**: Impulsado por **APScheduler**, orquesta tareas como la revisión diaria de buzones (8:00 AM) y la generación mensual de reportes.
*   **Seguridad**: Implementa cifrado **Fernet** para proteger las credenciales tributarias sensibles.

### Stack Tecnológico
*   **Core**: Python 3.10+
*   **Automatización**: Selenium WebDriver, WebDriver Manager
*   **Procesamiento de Datos**: Pandas, NumPy
*   **Scheduling**: APScheduler (BlockingScheduler)
*   **CLI**: Click (Interfaz de Línea de Comandos)
*   **Base de Datos**: PostgreSQL (psycopg2), SQLite
*   **Seguridad**: Cryptography (Fernet)

### Instalación y Configuración

1.  **Clonar el repositorio**:
    ```bash
    git clone https://github.com/tu-repo/driver_sunat.git
    cd driver_sunat
    ```

2.  **Instalar dependencias**:
    ```bash
    pip install -r requirements.txt
    ```

3.  **Configuración de Entorno**:
    Crear un archivo `.env` en la raíz del proyecto:
    ```env
    ENCRYPTION_KEY=tu_clave_base64_de_32_bytes
    PG_HOST=localhost
    PG_PORT=5432
    PG_DBNAME=financial_db
    PG_USER=admin
    PG_PASSWORD=secreto
    ```

4.  **Inicializar Base de Datos Local**:
    ```bash
    python main.py init_db
    ```

### Uso

El sistema se controla a través del CLI `main.py`.

*   **Iniciar el Programador (Modo Producción)**:
    ```bash
    python main.py scheduler
    ```
    *Ejecuta tareas en segundo plano para revisión de buzones, reportes SIRE y sincronización.*

*   **Ejecución Manual de Tareas**:
    ```bash
    # Revisar buzón para un RUC específico
    python main.py tasks check-mailbox --ruc 20123456789

    # Solicitar Propuestas SIRE (Ventas/Compras)
    python main.py tasks sire-request --periodo 202310

    # Descargar Reportes T-Registro
    python main.py tasks download-reports --ruc 20123456789
    ```

### Arquitectura del Sistema / System Architecture

```mermaid
graph TD
    subgraph "Core Controller"
        CLI[CLI (Click)] --> Scheduler[APScheduler]
        Scheduler --> TaskManager[Task Manager]
    end

    subgraph "Automation Layer"
        TaskManager --> BaseTask[Base Task (Selenium)]
        BaseTask --> Login[Auth Module]
        BaseTask --> Mailbox[Mailbox Scraper]
        BaseTask --> SIRE[SIRE API Client]
        BaseTask --> TReg[T-Registro Bot]
    end

    subgraph "Data Layer"
        LocalDB[(SQLite Local Cache)]
        CentralDB[(PostgreSQL Warehouse)]
        
        Mailbox --> LocalDB
        SIRE --> LocalDB
        TReg --> LocalDB
        
        LocalDB <--> SyncService[Sync Service]
        SyncService <--> CentralDB
    end

    subgraph "External"
        SUNAT[SUNAT Portal / API]
        Login --> SUNAT
        Mailbox --> SUNAT
        SIRE --> SUNAT
    end
```

### Contact / Contacto

**Developer**: Giusseppe Marchan
**Role**: Economist & Software Engineer
**Specialization**: Financial Automation & Tax Compliance Systems

---
*Note: This software is not affiliated with SUNAT. Use responsibly and in accordance with local regulations.*
