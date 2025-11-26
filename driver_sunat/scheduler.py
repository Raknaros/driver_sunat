# -*- coding: utf-8 -*-
import logging
import time
from apscheduler.schedulers.blocking import BlockingScheduler
from .automation.driver_manager import get_webdriver
from .automation.tasks.check_mailbox import CheckMailboxTask
from .automation.tasks.download_invoices import DownloadInvoicesTask
from .automation.tasks.request_report import RequestReportTask
from .automation.tasks.download_report import DownloadReportTask
from .automation.sire.sire_client import SireClient
from .automation.sire.sire_request_task import SireRequestTask
from .automation.sire.sire_status_task import SireStatusTask
from .automation.sire.sire_download_task import SireDownloadTask
from .database import operations as db
from .database.operations import get_active_contribuyentes, get_active_contribuyentes_with_sire_creds, initialize_local_db, sync_clients_from_central_db
from .config import config

logger = logging.getLogger(__name__)

# --- Funciones de Tareas Individuales (para ejecución manual) ---

def run_sire_proposals_request():
    """Solicita propuestas SIRE para todos los contribuyentes con credenciales."""
    logger.info("INICIANDO TAREA: Solicitud de propuestas SIRE")
    contribuyentes = get_active_contribuyentes_with_sire_creds()
    if not contribuyentes:
        logger.warning("No hay contribuyentes activos con credenciales SIRE válidas para procesar.")
        return

    tipos = ['ventas', 'compras']
    solicitudes_count = 0
    sire_clients = {}  # Cache de clientes para reutilizar tokens

    for contribuyente in contribuyentes:
        ruc = contribuyente['ruc']
        if ruc not in sire_clients:
            sire_clients[ruc] = SireClient(logger, ruc)
        
        client = sire_clients[ruc]

        for tipo in tipos:
            try:
                # La tarea ahora puede aceptar un cliente existente
                task = SireRequestTask(logger, ruc, client=client)
                sire_id = task.run(contribuyente, tipo)
                if sire_id:
                    solicitudes_count += 1
            except Exception as e:
                error_msg = f"Error solicitando propuesta SIRE {tipo} para RUC {ruc}: {e}"
                logger.error(error_msg)
                db.add_observation(ruc, error_msg, "LOCAL")
    
    logger.info(f"Tarea finalizada. Se iniciaron {solicitudes_count} solicitudes de reporte SIRE.")

def run_sire_status_check():
    """Verifica el estado de los reportes SIRE solicitados y los descarga si están listos."""
    logger.info("INICIANDO TAREA: Verificación de estado de reportes SIRE")

    max_wait_minutes = 30
    check_interval_seconds = 120  # 2 minutos
    start_time = time.time()
    
    sire_clients = {} # Cache de clientes para reutilizar tokens durante la verificación

    while time.time() - start_time < max_wait_minutes * 60:
        pending_reports = db.get_pending_sire_reports()
        if not pending_reports:
            logger.info("Todos los reportes SIRE han sido procesados.")
            break

        logger.info(f"Quedan {len(pending_reports)} reportes SIRE pendientes. Verificando estado...")
        
        # Obtener la lista completa de contribuyentes una sola vez por ciclo
        contribuyentes_activos = get_active_contribuyentes_with_sire_creds()
        
        for report in pending_reports:
            ruc = report['ruc']
            try:
                contribuyente = next((c for c in contribuyentes_activos if c['ruc'] == ruc), None)
                if not contribuyente:
                    logger.warning(f"No se encontró contribuyente activo para RUC {ruc}. Omitiendo reporte ID {report['id']}.")
                    continue

                # Reutilizar o crear el SireClient para el RUC actual
                if ruc not in sire_clients:
                    sire_clients[ruc] = SireClient(logger, ruc)
                client = sire_clients[ruc]

                # Pasar el cliente a la tarea de estado para reutilizar el token
                status_task = SireStatusTask(logger, ruc, client=client)
                status_result = status_task.run(contribuyente, report['ticket'], report['periodo'])
                
                estado = status_result.get('status')

                if estado == 'LISTO':
                    logger.info(f"Reporte SIRE ID {report['id']} (RUC {ruc}) está LISTO. Iniciando descarga.")
                    download_params = status_result.get('params')
                    
                    # Pasar el cliente a la tarea de descarga
                    download_task = SireDownloadTask(logger, ruc, client=client)
                    download_task.run(contribuyente, report['id'], download_params)

                elif estado == 'ERROR':
                     logger.error(f"Reporte SIRE ID {report['id']} (RUC {ruc}) tiene estado de ERROR en SUNAT. Se marcará como tal.")
                     db.update_sire_status(report['id'], 'ERROR')
                else: # PROCESANDO u otro
                    logger.info(f"Reporte SIRE ID {report['id']} (RUC {ruc}) sigue en estado: {estado}.")

            except Exception as e:
                error_msg = f"Error procesando estado del reporte SIRE ID {report['id']} (RUC {ruc}): {e}"
                logger.error(error_msg)
                db.add_observation(ruc, error_msg, "LOCAL")
        
        # Si todavía hay reportes pendientes después de la ronda, esperar
        if db.get_pending_sire_reports():
            logger.info(f"Esperando {check_interval_seconds} segundos para la siguiente verificación...")
            time.sleep(check_interval_seconds)
    else:
        # Este bloque se ejecuta si el bucle while termina por timeout
        if db.get_pending_sire_reports():
            logger.warning(f"Timeout de {max_wait_minutes} minutos alcanzado. Algunos reportes SIRE siguen pendientes.")

    logger.info("Tarea de verificación de estado SIRE finalizada.")


# --- Jobs para el Scheduler (APScheduler) ---

def job_sire_full_process():
    """Job mensual que ejecuta el proceso completo de SIRE: solicita y luego verifica/descarga."""
    logger.info("INICIANDO JOB MENSUAL: Proceso completo de propuestas SIRE")
    run_sire_proposals_request()
    run_sire_status_check()
    logger.info("JOB MENSUAL FINALIZADO: Proceso completo de propuestas SIRE")

# ... (El resto de funciones de jobs y scheduler no necesitan cambios) ...

def job_check_all_mailboxes():
    logger.info("INICIANDO JOB PROGRAMADO: Revisión de todos los buzones")
    # ...
def job_check_mailbox_for_ruc(ruc: str):
    logger.info(f"INICIANDO JOB: Revisión de buzón para RUC {ruc}")
    # ...
def job_download_invoices_for_ruc(ruc: str, start_date=None, end_date=None):
    logger.info(f"INICIANDO JOB: Descarga de facturas para RUC {ruc} ({start_date} - {end_date})")
    # ...
def start_scheduler():
    initialize_local_db()
    scheduler = BlockingScheduler(timezone="America/Lima")
    # ... (configuración de jobs)
    sire_config = config.SCHEDULE_CONFIG.get('sire_reports', {'day': 9, 'hour': 9, 'minute': 0})
    scheduler.add_job(
        job_sire_full_process,
        trigger='cron',
        day=sire_config['day'],
        hour=sire_config['hour'],
        minute=sire_config['minute'],
        name="Proceso completo mensual de propuestas SIRE"
    )
    # ...
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler detenido.")

def job_download_all_invoices_monthly():
    logger.info("INICIANDO JOB MENSUAL: Descarga de facturas para todos los contribuyentes")
    # ...
def job_request_reports_monthly():
    logger.info("INICIANDO JOB MENSUAL: Solicitud de reportes T-Registro")
    # ...
def job_download_reports_for_all():
    logger.info("INICIANDO JOB: Descarga de reportes listos para todos")
    # ...
