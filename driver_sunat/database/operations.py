# -*- coding: utf-8 -*-
import sqlite3
import psycopg2
import os
from datetime import datetime
from ..config import config
from ..security import encrypt_password, decrypt_password

# --- Operaciones con la BD Local (SQLite) ---

def get_local_db_connection():
    """Crea y devuelve una conexión a la base de datos local SQLite."""
    os.makedirs(os.path.dirname(config.DATABASE_PATH), exist_ok=True)
    conn = sqlite3.connect(config.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def initialize_local_db():
    """Inicializa la base de datos local, creando las tablas si no existen."""
    print("Inicializando la base de datos local (SQLite)...")
    conn = get_local_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS contribuyentes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ruc TEXT NOT NULL UNIQUE,
        user_sol TEXT NOT NULL,
        password_sol_encrypted BLOB NOT NULL,
        is_active BOOLEAN NOT NULL DEFAULT 1
    );
    """)
    print("Tabla 'contribuyentes' lista.")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS buzon_mensajes (
        id INTEGER PRIMARY KEY,
        ruc TEXT NOT NULL,
        asunto TEXT,
        fecha_publicacion TEXT,
        leido BOOLEAN DEFAULT 0,
        fecha_revision TEXT
    );
    """)
    print("Tabla 'buzon_mensajes' lista.")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS reportes_tregistro (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ruc TEXT NOT NULL,
        tipo_reporte TEXT NOT NULL,
        ticket TEXT,
        estado TEXT DEFAULT 'SOLICITADO',
        fecha_solicitud TEXT,
        fecha_descarga TEXT
    );
    """)
    print("Tabla 'reportes_tregistro' lista.")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS observaciones (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ruc TEXT NOT NULL,
        mensaje TEXT NOT NULL,
        tipo TEXT DEFAULT 'LOCAL',  -- 'LOCAL' o 'DETERMINANTE'
        estado TEXT DEFAULT 'PENDIENTE',  -- 'PENDIENTE' o 'SINCRONIZADO'
        timestamp TEXT NOT NULL
    );
    """)
    print("Tabla 'observaciones' lista.")

    # Add columns if not exist
    try:
        cursor.execute("ALTER TABLE observaciones ADD COLUMN tipo TEXT DEFAULT 'LOCAL'")
        print("Columna 'tipo' agregada a 'observaciones'.")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE observaciones ADD COLUMN estado TEXT DEFAULT 'PENDIENTE'")
        print("Columna 'estado' agregada a 'observaciones'.")
    except sqlite3.OperationalError:
        pass

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS sire_reportes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ruc TEXT NOT NULL,
        tipo TEXT NOT NULL,  -- 'ventas' o 'compras'
        periodo TEXT NOT NULL,
        ticket TEXT,
        estado TEXT DEFAULT 'SOLICITADO',
        fecha_solicitud TEXT,
        fecha_descarga TEXT,
        nom_archivo TEXT
    );
    """)
    print("Tabla 'sire_reportes' lista.")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS sire_tokens (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ruc TEXT NOT NULL,
        token_encrypted BLOB NOT NULL,
        expires_at TEXT NOT NULL
    );
    """)
    print("Tabla 'sire_tokens' lista.")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS otras_credenciales (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ruc TEXT NOT NULL,
        tipo TEXT NOT NULL,
        usuario TEXT,
        contrasena TEXT,
        credencial3 TEXT,
        observaciones TEXT
    );
    """)
    print("Tabla 'otras_credenciales' lista.")

    # Add columns if not exist
    try:
        cursor.execute("ALTER TABLE otras_credenciales ADD COLUMN observaciones TEXT")
        print("Columna 'observaciones' agregada a 'otras_credenciales'.")
    except sqlite3.OperationalError:
        pass

    conn.commit()
    conn.close()

def get_active_contribuyentes():
    """Obtiene todos los contribuyentes activos de la BD local SQLite y descifra sus claves."""
    conn = get_local_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT ruc, user_sol, password_sol_encrypted FROM contribuyentes WHERE is_active = 1")
    rows = cursor.fetchall()
    conn.close()

    key = config.ENCRYPTION_KEY.encode('utf-8')
    contribuyentes = []
    for row in rows:
        try:
            decrypted_pass = decrypt_password(row['password_sol_encrypted'], key)
            contribuyentes.append({
                "ruc": row['ruc'],
                "user_sol": row['user_sol'],
                "password_sol": decrypted_pass
            })
        except Exception as e:
            print(f"ADVERTENCIA: No se pudo descifrar la contraseña para el RUC {row['ruc']}. Error: {e}")
    return contribuyentes

def get_active_contribuyentes_with_sire_creds():
    """Obtiene contribuyentes activos que tienen credenciales SIRE válidas (tipo APISUNAT y credencial3 LIKE '%SIRE%')."""
    conn = get_local_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT c.ruc, c.user_sol, c.password_sol_encrypted
    FROM contribuyentes c
    JOIN otras_credenciales oc ON c.ruc = oc.ruc
    WHERE c.is_active = 1 AND oc.tipo = 'APISUNAT' AND oc.observaciones LIKE '%SIRE%'
    """)
    rows = cursor.fetchall()
    conn.close()

    key = config.ENCRYPTION_KEY.encode('utf-8')
    contribuyentes = []
    for row in rows:
        try:
            decrypted_pass = decrypt_password(row['password_sol_encrypted'], key)
            contribuyentes.append({
                "ruc": row['ruc'],
                "user_sol": row['user_sol'],
                "password_sol": decrypted_pass
            })
        except Exception as e:
            print(f"ADVERTENCIA: No se pudo descifrar la contraseña para el RUC {row['ruc']}. Error: {e}")
    return contribuyentes

# --- Funciones para el Buzón ---

def get_messages_by_ruc_as_dict(ruc: str):
    """Devuelve los mensajes de un RUC como un diccionario para búsqueda rápida."""
    conn = get_local_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, leido FROM buzon_mensajes WHERE ruc = ?", (ruc,))
    return {row['id']: {'leido': bool(row['leido'])} for row in cursor.fetchall()}

def add_message(msg_data: dict):
    """Añade un nuevo mensaje a la base de datos local."""
    conn = get_local_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO buzon_mensajes (id, ruc, asunto, fecha_publicacion, leido, fecha_revision)
    VALUES (:id, :ruc, :asunto, :fecha_publicacion, :leido, :fecha_revision)
    """, msg_data)
    conn.commit()
    conn.close()

def update_message_status(msg_id: int, leido: bool, fecha_revision: str):
    """Actualiza el estado 'leido' de un mensaje existente."""
    conn = get_local_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE buzon_mensajes SET leido = ?, fecha_revision = ? WHERE id = ?", (leido, fecha_revision, msg_id))
    conn.commit()
    conn.close()

# --- Funciones para Reportes T-Registro ---

def add_report_request(report_data: dict):
    """Añade una nueva solicitud de reporte a la base de datos local."""
    conn = get_local_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO reportes_tregistro (ruc, tipo_reporte, ticket, estado, fecha_solicitud)
    VALUES (:ruc, :tipo_reporte, :ticket, :estado, :fecha_solicitud)
    """, report_data)
    cursor.execute("SELECT id FROM reportes_tregistro ORDER BY id DESC LIMIT 1")
    result = cursor.fetchone()
    report_id = result[0] if result else 0
    conn.commit()
    cursor.close()
    conn.close()
    return report_id

def get_pending_reports(ruc=None):
    """Obtiene reportes pendientes de descarga."""
    conn = get_local_db_connection()
    cursor = conn.cursor()
    if ruc:
        cursor.execute("SELECT * FROM reportes_tregistro WHERE ruc = ? AND estado = 'SOLICITADO'", (ruc,))
    else:
        cursor.execute("SELECT * FROM reportes_tregistro WHERE estado = 'SOLICITADO'")
    reports = cursor.fetchall()
    conn.close()
    return reports

def update_report_status(report_id: int, estado: str, fecha_descarga=None):
    """Actualiza el estado de un reporte."""
    conn = get_local_db_connection()
    cursor = conn.cursor()
    if fecha_descarga:
        cursor.execute("UPDATE reportes_tregistro SET estado = ?, fecha_descarga = ? WHERE id = ?",
                      (estado, fecha_descarga, report_id))
    else:
        cursor.execute("UPDATE reportes_tregistro SET estado = ? WHERE id = ?", (estado, report_id))
    conn.commit()
    conn.close()

def update_report_ticket(report_id: int, ticket: str):
    """Actualiza el ticket de un reporte."""
    conn = get_local_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE reportes_tregistro SET ticket = ? WHERE id = ?", (ticket, report_id))
    conn.commit()
    conn.close()

# --- Operaciones con la BD Central (PostgreSQL) ---

def get_central_db_connection():
    """Crea y devuelve una conexión a la base de datos central PostgreSQL."""
    try:
        conn = psycopg2.connect(
            host=config.PG_HOST,
            port=config.PG_PORT,
            dbname=config.PG_DBNAME,
            user=config.PG_USER,
            password=config.PG_PASSWORD
        )
        return conn
    except psycopg2.OperationalError as e:
        print(f"ERROR: No se pudo conectar a la base de datos PostgreSQL. Revisa las credenciales en .env. Detalle: {e}")
        return None

def sync_clients_from_central_db():
    """Sincroniza los clientes desde PostgreSQL a la base de datos local SQLite."""
    print("Iniciando sincronización de clientes desde la BD Central...")
    pg_conn = get_central_db_connection()
    if not pg_conn:
        print("Sincronización fallida.")
        return

    # !!! IMPORTANTE: Ajusta esta consulta a tu esquema de BD real. !!!
    query = "SELECT ruc, usuario_sol, clave_sol, activo FROM priv.entities WHERE activo = TRUE"
    
    try:
        pg_cursor = pg_conn.cursor()
        pg_cursor.execute(query)
        clients = pg_cursor.fetchall()
    except Exception as e:
        print(f"ERROR: Falló la consulta a la base de datos central. Revisa la consulta y los nombres de tablas/columnas. Detalle: {e}")
        pg_conn.close()
        return
    finally:
        pg_conn.close()

    print(f"Se encontraron {len(clients)} clientes activos en la BD Central. Sincronizando...")
    local_conn = get_local_db_connection()
    local_cursor = local_conn.cursor()
    key = config.ENCRYPTION_KEY.encode('utf-8')

    active_rucs = []
    for client in clients:
        ruc, user_sol, plain_password, is_active = client
        active_rucs.append(str(ruc))
        if not plain_password:
            print(f"ADVERTENCIA: Se omite el RUC {ruc} porque no tiene contraseña definida en la BD Central.")
            continue

        encrypted_pass = encrypt_password(plain_password, key)

        local_cursor.execute("""
        INSERT INTO contribuyentes (ruc, user_sol, password_sol_encrypted, is_active)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(ruc) DO UPDATE SET
            user_sol = excluded.user_sol,
            password_sol_encrypted = excluded.password_sol_encrypted,
            is_active = excluded.is_active;
        """, (str(ruc), user_sol, encrypted_pass, is_active))

    # Desactivar clientes no presentes en la lista activa
    if active_rucs:
        placeholders = ','.join('?' for _ in active_rucs)
        local_cursor.execute(f"UPDATE contribuyentes SET is_active = 0 WHERE ruc NOT IN ({placeholders})", active_rucs)

    local_conn.commit()
    local_conn.close()
    print("Sincronización completada.")

def add_observation(ruc: str, mensaje: str, tipo: str = "LOCAL", estado: str = "PENDIENTE"):
    """Añade una nueva observación a la base de datos local."""
    conn = get_local_db_connection()
    cursor = conn.cursor()
    timestamp = datetime.now().isoformat()
    cursor.execute("""
    INSERT INTO observaciones (ruc, mensaje, tipo, estado, timestamp)
    VALUES (?, ?, ?, ?, ?)
    """, (ruc, mensaje, tipo, estado, timestamp))
    conn.commit()
    conn.close()

def update_central_db_observacion(ruc: str, observacion: str):
    """Añade una observación a un cliente en la BD Central PostgreSQL, concatenando con el texto existente."""
    print(f"Registrando observación para el RUC {ruc} en la BD Central...")
    pg_conn = get_central_db_connection()
    if not pg_conn:
        return

    try:
        pg_cursor = pg_conn.cursor()
        # Query current observaciones
        pg_cursor.execute("SELECT observaciones FROM priv.entities WHERE ruc = %s", (str(ruc),))
        row = pg_cursor.fetchone()
        current = row[0] if row and row[0] else ""
        # Concatenate
        new_observacion = f"{current}|{observacion}" if current else observacion

        # Update
        query = "UPDATE priv.entities SET observaciones = %s WHERE ruc = %s"
        pg_cursor.execute(query, (new_observacion, str(ruc)))
        pg_conn.commit()
        print("Observación registrada correctamente.")
    except Exception as e:
        print(f"ERROR al actualizar la BD Central: {e}")
        pg_conn.rollback()
    finally:
        pg_conn.close()

def sync_determinant_observations_to_central():
    """Sincroniza observaciones determinantes pendientes para todos los RUC a la BD central."""
    conn = get_local_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, ruc, mensaje FROM observaciones WHERE tipo = 'DETERMINANTE' AND estado = 'PENDIENTE'")
    pending = cursor.fetchall()
    conn.close()

    if not pending:
        return

    for obs_id, ruc, mensaje in pending:
        update_central_db_observacion(ruc, mensaje)
        # Mark as synced
        conn = get_local_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE observaciones SET estado = 'SINCRONIZADO' WHERE id = ?", (obs_id,))
        conn.commit()
        conn.close()

def sync_buzon_to_central(ruc: str):
    """Sincroniza mensajes de buzón local a la tabla central priv.buzon_sunat."""
    conn = get_local_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, asunto, fecha_publicacion, leido, fecha_revision FROM buzon_mensajes WHERE ruc = ?", (ruc,))
    local_messages = cursor.fetchall()
    conn.close()

    if not local_messages:
        return

    pg_conn = get_central_db_connection()
    if not pg_conn:
        return

    try:
        pg_cursor = pg_conn.cursor()
        for msg in local_messages:
            msg_id, asunto, fecha_publicacion_str, leido_int, fecha_revision = msg
            leido = bool(leido_int)  # Convert to bool
            # Parse fecha_publicacion to date
            try:
                fecha_recepcion = datetime.strptime(fecha_publicacion_str, "%d/%m/%Y %H:%M:%S").date()
            except ValueError:
                print(f"Error parsing fecha_publicacion: {fecha_publicacion_str}")
                continue
            # Check if exists
            pg_cursor.execute("SELECT leido FROM priv.buzon_sunat WHERE id = %s", (msg_id,))
            existing = pg_cursor.fetchone()
            if existing:
                # Update if leido changed to true
                if not existing[0] and leido:
                    pg_cursor.execute("""
                        UPDATE priv.buzon_sunat
                        SET leido = %s, fecha_revision = %s
                        WHERE id = %s
                    """, (leido, fecha_revision, msg_id))
            else:
                # Insert new
                pg_cursor.execute("""
                    INSERT INTO priv.buzon_sunat (id, asunto, fecha_recepcion, fecha_revision, leido, observaciones, ruc)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (msg_id, asunto, fecha_recepcion, fecha_revision, leido, '', ruc))
        pg_conn.commit()
    except Exception as e:
        print(f"Error syncing buzon to central: {e}")
        pg_conn.rollback()
    finally:
        pg_conn.close()

# --- Funciones para SIRE ---

def add_sire_request(sire_data: dict):
    """Añade una nueva solicitud de reporte SIRE a la base de datos local."""
    conn = get_local_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO sire_reportes (ruc, tipo, periodo, ticket, estado, fecha_solicitud)
    VALUES (:ruc, :tipo, :periodo, :ticket, :estado, :fecha_solicitud)
    """, sire_data)
    cursor.execute("SELECT id FROM sire_reportes ORDER BY id DESC LIMIT 1")
    result = cursor.fetchone()
    sire_id = result[0] if result else 0
    conn.commit()
    cursor.close()
    conn.close()
    return sire_id

def get_pending_sire_reports(ruc=None, tipo=None):
    """Obtiene reportes SIRE pendientes."""
    conn = get_local_db_connection()
    cursor = conn.cursor()
    query = "SELECT * FROM sire_reportes WHERE estado = 'SOLICITADO'"
    params = []
    if ruc:
        query += " AND ruc = ?"
        params.append(ruc)
    if tipo:
        query += " AND tipo = ?"
        params.append(tipo)
    cursor.execute(query, params)
    reports = cursor.fetchall()
    conn.close()
    return reports

def update_sire_status(sire_id: int, estado: str, nom_archivo=None, fecha_descarga=None):
    """Actualiza el estado de un reporte SIRE."""
    conn = get_local_db_connection()
    cursor = conn.cursor()
    if fecha_descarga:
        cursor.execute("UPDATE sire_reportes SET estado = ?, nom_archivo = ?, fecha_descarga = ? WHERE id = ?",
                      (estado, nom_archivo, fecha_descarga, sire_id))
    else:
        cursor.execute("UPDATE sire_reportes SET estado = ? WHERE id = ?", (estado, sire_id))
    conn.commit()
    conn.close()

# --- Funciones para SIRE Tokens ---

def save_sire_token(ruc: str, token: str, expires_at: str):
    """Guarda un token SIRE en la BD local (cifrado)."""
    conn = get_local_db_connection()
    cursor = conn.cursor()
    key = config.ENCRYPTION_KEY.encode('utf-8')
    encrypted_token = encrypt_password(token, key)
    cursor.execute("""
    INSERT OR REPLACE INTO sire_tokens (ruc, token_encrypted, expires_at)
    VALUES (?, ?, ?)
    """, (ruc, encrypted_token, expires_at))
    conn.commit()
    conn.close()

def get_valid_sire_token(ruc: str):
    """Obtiene un token SIRE válido de la BD local (descifrado)."""
    conn = get_local_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT token_encrypted, expires_at FROM sire_tokens WHERE ruc = ?", (ruc,))
    row = cursor.fetchone()
    conn.close()
    if row:
        token_encrypted, expires_at = row
        if datetime.fromisoformat(expires_at) > datetime.now():
            key = config.ENCRYPTION_KEY.encode('utf-8')
            return decrypt_password(token_encrypted, key)
    return None

def clean_expired_sire_tokens():
    """Limpia tokens SIRE expirados."""
    conn = get_local_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM sire_tokens WHERE expires_at < ?", (datetime.now().isoformat(),))
    conn.commit()
    conn.close()

# --- Funciones para otras_credenciales ---

def sync_otras_credenciales_from_central_db():
    """Sincroniza otras_credenciales desde PostgreSQL a SQLite."""
    print("Iniciando sincronización de otras_credenciales desde BD Central...")
    pg_conn = get_central_db_connection()
    if not pg_conn:
        print("Sincronización fallida.")
        return

    query = "SELECT ruc, tipo, usuario, contrasena, credencial3, observaciones FROM priv.otras_credenciales"
    try:
        pg_cursor = pg_conn.cursor()
        pg_cursor.execute(query)
        creds = pg_cursor.fetchall()
    except Exception as e:
        print(f"ERROR: Falló consulta en BD central: {e}")
        pg_conn.close()
        return
    finally:
        pg_conn.close()

    print(f"Se encontraron {len(creds)} registros de otras_credenciales.")
    local_conn = get_local_db_connection()
    local_cursor = local_conn.cursor()

    for cred in creds:
        ruc, tipo, usuario, contrasena, credencial3, observaciones = cred
        local_cursor.execute("""
        INSERT OR REPLACE INTO otras_credenciales (ruc, tipo, usuario, contrasena, credencial3, observaciones)
        VALUES (?, ?, ?, ?, ?, ?)
        """, (str(ruc), tipo, usuario, contrasena, credencial3, observaciones))

    local_conn.commit()
    local_conn.close()
    print("Sincronización de otras_credenciales completada.")

def get_otras_credenciales(ruc=None, tipo=None):
    """Obtiene otras_credenciales."""
    conn = get_local_db_connection()
    cursor = conn.cursor()
    query = "SELECT * FROM otras_credenciales"
    params = []
    if ruc:
        query += " WHERE ruc = ?"
        params.append(ruc)
    if tipo:
        query += (" AND" if ruc else " WHERE") + " tipo = ?"
        params.append(tipo)
    cursor.execute(query, params)
    creds = cursor.fetchall()
    conn.close()
    return creds

def get_sire_credentials(ruc: str):
    """Obtiene credenciales SIRE para un RUC (tipo APISUNAT con SIRE en credencial3)."""
    conn = get_local_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT oc.usuario, oc.contrasena, c.user_sol
    FROM otras_credenciales oc
    JOIN contribuyentes c ON oc.ruc = c.ruc
    WHERE oc.ruc = ? AND oc.tipo = 'APISUNAT' AND oc.observaciones LIKE '%SIRE%'
    """, (ruc,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {
            'client_id': row[0],
            'client_secret': row[1],
            'user_sol': row[2]
        }
    return None
