# -*- coding: utf-8 -*-
import logging
import time
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from apscheduler.schedulers.blocking import BlockingScheduler
from .automation.driver_manager import get_webdriver
from .automation.tasks.base_task import BusinessRuleException
from .automation.tasks.check_mailbox import CheckMailboxTask
from .automation.tasks.download_invoices import DownloadInvoicesTask
from .automation.tasks.request_report import RequestReportTask
from .automation.tasks.download_report import DownloadReportTask
from .automation.sire.sire_client import SireClient
from .automation.sire.sire_request_task import SireRequestTask
from .automation.sire.sire_status_task import SireStatusTask
from .automation.sire.sire_download_task import SireDownloadTask
from .database import operations as db
from .database.operations import get_active_contribuyentes, get_active_contribuyentes_with_sire_creds, initialize_local_db, sync_clients_from_central_db, update_central_db_observacion
from .config import config

logger = logging.getLogger(__name__)

# --- Constante de Reintentos ---
MAX_TASK_RETRIES = 3

# --- Funciones Auxiliares ---

def _generate_period_range(start_period: str, end_period: str) -> list[str]:
    """Genera una lista de periodos en formato YYYYMM entre dos fechas."""
    try:
        start_date = datetime.strptime(start_period, "%Y%m")
        end_date = datetime.strptime(end_period, "%Y%m")
    except ValueError:
        logger.error("Formato de periodo inválido. Use YYYYMM.")
        return []

    periods = []
    current_date = start_date
    while current_date <= end_date:
        periods.append(current_date.strftime("%Y%m"))
        current_date += relativedelta(months=1)
    return periods

# --- Funciones de Tareas Individuales ---

def run_sire_proposals_request(periodo_unico=None, desde_periodo=None, hasta_periodo=None):
    """
    Solicita propuestas SIRE para todos los contribuyentes con credenciales.
    Puede procesar un periodo único, un rango, o el mes anterior por defecto.
    """
    logger.info("INICIANDO TAREA: Solicitud de propuestas SIRE")

    periods_to_process = []
    if periodo_unico:
        periods_to_process = [periodo_unico]
        logger.info(f"Se procesará el periodo específico: {periodo_unico}")
    elif desde_periodo and hasta_periodo:
        periods_to_process = _generate_period_range(desde_periodo, hasta_periodo)
        logger.info(f"Se procesará el rango de periodos desde {desde_periodo} hasta {hasta_periodo}: {len(periods_to_process)} periodos en total.")
    else:
        last_month = datetime.now().replace(day=1) - timedelta(days=1)
        default_period = last_month.strftime("%Y%m")
        periods_to_process = [default_period]
        logger.info(f"No se especificó periodo. Se usará el mes anterior por defecto: {default_period}")

    if not periods_to_process:
        logger.error("No se pudieron determinar los periodos a procesar. Abortando.")
        return

    contribuyentes = get_active_contribuyentes_with_sire_creds()
    if not contribuyentes:
        logger.warning("No hay contribuyentes activos con credenciales SIRE válidas para procesar.")
        return

    logger.info(f"Se procesarán {len(contribuyentes)} contribuyentes para {len(periods_to_process)} periodo(s).")
    
    sire_clients = {}  # Cache de clientes para reutilizar tokens
    tipos = ['ventas', 'compras']

    for contribuyente in contribuyentes:
        ruc = contribuyente['ruc']
        if ruc not in sire_clients:
            sire_clients[ruc] = SireClient(logger, ruc)
        client = sire_clients[ruc]

        for tipo in tipos:
            for periodo in periods_to_process:
                try:
                    task = SireRequestTask(logger, ruc, client=client)
                    task.run(contribuyente, tipo, periodo=periodo)
                except Exception as e:
                    error_msg = f"Error solicitando propuesta SIRE {tipo} para RUC {ruc} en periodo {periodo}: {e}"
                    logger.error(error_msg)
                    db.add_observation(ruc, error_msg, "LOCAL")
    
    logger.info(f"Tarea de solicitud de propuestas SIRE finalizada.")


def run_sire_status_check():
    """Verifica el estado de los reportes SIRE solicitados y los descarga si están listos."""
    logger.info("INICIANDO TAREA: Verificación de estado de reportes SIRE")

    max_wait_minutes = 30
    check_interval_seconds = 120
    start_time = time.time()
    
    sire_clients = {}

    while time.time() - start_time < max_wait_minutes * 60:
        pending_reports = db.get_pending_sire_reports()
        if not pending_reports:
            logger.info("Todos los reportes SIRE han sido procesados.")
            break

        logger.info(f"Quedan {len(pending_reports)} reportes SIRE pendientes. Verificando estado...")
        
        contribuyentes_activos = get_active_contribuyentes_with_sire_creds()
        
        for report in pending_reports:
            ruc = report['ruc']
            try:
                contribuyente = next((c for c in contribuyentes_activos if c['ruc'] == ruc), None)
                if not contribuyente:
                    logger.warning(f"No se encontró contribuyente activo para RUC {ruc}. Omitiendo reporte ID {report['id']}.")
                    continue

                if ruc not in sire_clients:
                    sire_clients[ruc] = SireClient(logger, ruc)
                client = sire_clients[ruc]

                status_task = SireStatusTask(logger, ruc, client=client)
                status_result = status_task.run(contribuyente, report['ticket'], report['periodo'])
                
                estado = status_result.get('status')

                if estado == 'LISTO':
                    logger.info(f"Reporte SIRE ID {report['id']} (RUC {ruc}) está LISTO. Iniciando descarga.")
                    download_params = status_result.get('params')
                    
                    download_task = SireDownloadTask(logger, ruc, client=client)
                    download_task.run(contribuyente, report['id'], download_params)

                elif estado == 'ERROR':
                     logger.error(f"Reporte SIRE ID {report['id']} (RUC {ruc}) tiene estado de ERROR en SUNAT.")
                     db.update_sire_status(report['id'], 'ERROR')
                else:
                    logger.info(f"Reporte SIRE ID {report['id']} (RUC {ruc}) sigue en estado: {estado}.")

            except Exception as e:
                error_msg = f"Error procesando estado del reporte SIRE ID {report['id']} (RUC {ruc}): {e}"
                logger.error(error_msg)
                db.add_observation(ruc, error_msg, "LOCAL")
        
        if db.get_pending_sire_reports():
            logger.info(f"Esperando {check_interval_seconds} segundos para la siguiente verificación...")
            time.sleep(check_interval_seconds)
    else:
        if db.get_pending_sire_reports():
            logger.warning(f"Timeout de {max_wait_minutes} minutos alcanzado. Algunos reportes SIRE siguen pendientes.")

    logger.info("Tarea de verificación de estado SIRE finalizada.")


# --- Jobs para el Scheduler (APScheduler) ---

def job_sire_full_process():
    """Job mensual que ejecuta el proceso completo de SIRE (mes anterior)."""
    logger.info("INICIANDO JOB MENSUAL: Proceso completo de propuestas SIRE")
    run_sire_proposals_request() # Llama sin argumentos para usar el mes anterior
    run_sire_status_check()
    logger.info("JOB MENSUAL FINALIZADO: Proceso completo de propuestas SIRE")

def job_check_all_mailboxes():
    """Job que revisa el buzón para todos los contribuyentes con arquitectura infalible."""
    logger.info("INICIANDO JOB PROGRAMADO: Revisión de todos los buzones")
    contribuyentes = get_active_contribuyentes()
    if not contribuyentes:
        logger.warning("No hay contribuyentes activos para procesar.")
        return

    logger.info(f"Se procesarán {len(contribuyentes)} contribuyentes.")

    for client in contribuyentes:
        success = False
        for attempt in range(MAX_TASK_RETRIES):
            driver = None
            try:
                logger.info(f"Procesando RUC {client['ruc']}, Intento {attempt + 1}/{MAX_TASK_RETRIES}")
                driver = get_webdriver(headless=False)
                task = CheckMailboxTask(driver)
                task.run(client)
                success = True
                break
            except Exception as e:
                logger.error(f"Intento {attempt + 1} falló para RUC {client['ruc']}: {e}")
                if attempt < MAX_TASK_RETRIES - 1:
                    logger.info("Se reiniciará el driver y se reintentará...")
                else:
                    logger.critical(f"Todos los {MAX_TASK_RETRIES} intentos fallaron para RUC {client['ruc']}. Registrando observación.")
                    update_central_db_observacion(client['ruc'], "FALLA CRITICA AUTOMATIZACION")
            finally:
                if driver:
                    driver.quit()
        
        if success:
            logger.info(f"Tarea completada exitosamente para RUC {client['ruc']}.")

    db.sync_determinant_observations_to_central()
    logger.info("JOB PROGRAMADO FINALIZADO: Revisión de buzones")

def job_check_mailbox_for_ruc(ruc: str):
    """Job que ejecuta la revisión de buzón para un RUC específico con reintentos."""
    logger.info(f"INICIANDO JOB: Revisión de buzón para RUC {ruc}")
    contribuyente = next((c for c in get_active_contribuyentes() if c['ruc'] == ruc), None)
    if not contribuyente:
        logger.error(f"RUC {ruc} no encontrado o no activo")
        return

    for attempt in range(MAX_TASK_RETRIES):
        driver = None
        try:
            logger.info(f"Procesando RUC {ruc}, Intento {attempt + 1}/{MAX_TASK_RETRIES}")
            driver = get_webdriver(headless=False)
            task = CheckMailboxTask(driver)
            task.run(contribuyente)
            logger.info(f"JOB FINALIZADO: Revisión de buzón para RUC {ruc}")
            return
        except Exception as e:
            logger.error(f"Intento {attempt + 1} falló para RUC {ruc}: {e}")
        finally:
            if driver:
                driver.quit()
    
    logger.critical(f"Todos los intentos fallaron para RUC {ruc}.")
    update_central_db_observacion(ruc, "FALLA CRITICA AUTOMATIZACION")

def job_download_invoices_for_ruc(ruc: str, start_date=None, end_date=None):
    """Job que descarga facturas para un RUC específico con reintentos."""
    if not start_date or not end_date:
        today = datetime.now()
        start_date = f"01/{today.month:02d}/{today.year}"
        next_month = today.replace(day=28) + timedelta(days=4)
        end_date = f"{(next_month - timedelta(days=next_month.day)).day:02d}/{today.month:02d}/{today.year}"

    logger.info(f"INICIANDO JOB: Descarga de facturas para RUC {ruc} ({start_date} - {end_date})")
    contribuyente = next((c for c in get_active_contribuyentes() if c['ruc'] == ruc), None)
    if not contribuyente:
        logger.error(f"RUC {ruc} no encontrado o no activo")
        return

    for attempt in range(MAX_TASK_RETRIES):
        driver = None
        try:
            logger.info(f"Procesando RUC {ruc}, Intento {attempt + 1}/{MAX_TASK_RETRIES}")
            driver = get_webdriver(headless=False)
            task = DownloadInvoicesTask(driver)
            task.run(contribuyente, start_date, end_date)
            logger.info(f"JOB FINALIZADO: Descarga de facturas para RUC {ruc}")
            return
        except Exception as e:
            logger.error(f"Intento {attempt + 1} falló para RUC {ruc}: {e}")
        finally:
            if driver:
                driver.quit()

    logger.critical(f"Todos los intentos de descarga de facturas fallaron para RUC {ruc}.")
    update_central_db_observacion(ruc, "FALLA CRITICA DESCARGA FACTURAS")

def job_request_report_for_ruc(ruc: str, tipo_reporte: str):
    """Solicita un reporte T-Registro para un RUC específico con reintentos."""
    logger.info(f"INICIANDO JOB: Solicitud de reporte T-Registro tipo {tipo_reporte} para RUC {ruc}")
    contribuyente = next((c for c in get_active_contribuyentes() if c['ruc'] == ruc), None)
    if not contribuyente:
        logger.error(f"RUC {ruc} no encontrado o no activo para solicitar reporte.")
        return

    for attempt in range(MAX_TASK_RETRIES):
        driver = None
        try:
            logger.info(f"Procesando RUC {ruc}, Intento {attempt + 1}/{MAX_TASK_RETRIES}")
            driver = get_webdriver(headless=False)
            task = RequestReportTask(driver)
            task.run(contribuyente, tipo_reporte)
            logger.info(f"Solicitud de reporte para RUC {ruc} completada exitosamente.")
            return # Termina la función si es exitoso
        except BusinessRuleException as bre:
            logger.warning(f"Fallo por regla de negocio para RUC {ruc}: {bre}. No se reintentará.")
            # La observación ya fue registrada en la tarea, solo salimos del bucle.
            break
        except Exception as e:
            logger.error(f"Intento {attempt + 1} de solicitud de reporte falló para RUC {ruc}: {e}")
            if attempt >= MAX_TASK_RETRIES - 1:
                logger.critical(f"Todos los intentos de solicitud de reporte fallaron para RUC {ruc}.")
                update_central_db_observacion(ruc, "FALLA CRITICA SOLICITUD REPORTE")
        finally:
            if driver:
                driver.quit()

def job_request_reports_monthly(tipo_reporte: str = "6"):
    """Job mensual que solicita reportes T-Registro para todos los contribuyentes activos."""
    logger.info(f"INICIANDO JOB MENSUAL: Solicitud de reportes T-Registro tipo {tipo_reporte}")
    contribuyentes = get_active_contribuyentes()
    if not contribuyentes:
        logger.warning("No hay contribuyentes activos para solicitar reportes.")
        return
    
    logger.info(f"Se procesarán {len(contribuyentes)} contribuyentes.")
    for contribuyente in contribuyentes:
        job_request_report_for_ruc(contribuyente['ruc'], tipo_reporte)
    
    logger.info("JOB MENSUAL FINALIZADO: Solicitud de reportes T-Registro")

def job_download_reports_for_all():
    """Job que descarga reportes listos para todos los contribuyentes."""
    logger.info("INICIANDO JOB: Descarga de reportes listos para todos")
    contribuyentes = get_active_contribuyentes()
    if not contribuyentes:
        logger.warning("No hay contribuyentes activos para descargar reportes.")
        return

    for contribuyente in contribuyentes:
        for attempt in range(MAX_TASK_RETRIES):
            driver = None
            try:
                driver = get_webdriver(headless=False)
                task = DownloadReportTask(driver)
                task.run(contribuyente)
                break
            except Exception as e:
                logger.error(f"Intento {attempt + 1} falló para RUC {contribuyente['ruc']}: {e}")
            finally:
                if driver:
                    driver.quit()
    logger.info("JOB FINALIZADO: Descarga de reportes para todos")

def start_scheduler():
    initialize_local_db()
    scheduler = BlockingScheduler(timezone="America/Lima")

    # Tarea 1: Sincronizar clientes
    sync_config = config.SCHEDULE_CONFIG['sync_clients']
    scheduler.add_job(sync_clients_from_central_db, 'cron', hour=sync_config['hour'], minute=sync_config['minute'], name="Sincronización diaria de clientes")

    # Tarea 2: Revisar buzones
    mailbox_config = config.SCHEDULE_CONFIG['check_mailbox']
    scheduler.add_job(job_check_all_mailboxes, 'cron', hour=mailbox_config['hour'], minute=mailbox_config['minute'], name="Revisión diaria de buzones SUNAT")

    # Tarea 3: Descargar facturas
    invoice_config = config.SCHEDULE_CONFIG['download_invoices']
    scheduler.add_job(job_download_all_invoices_monthly, 'cron', day=invoice_config['day'], hour=invoice_config['hour'], minute=invoice_config['minute'], name="Descarga mensual de facturas")

    # Tarea 4: Solicitar reportes T-Registro
    report_request_config = config.SCHEDULE_CONFIG.get('request_reports', {'day': 1, 'hour': 3, 'minute': 0})
    scheduler.add_job(job_request_reports_monthly, 'cron', day=report_request_config['day'], hour=report_request_config['hour'], minute=report_request_config['minute'], name="Solicitud mensual de reportes T-Registro")

    # Tarea 5: Descargar reportes T-Registro
    report_download_config = config.SCHEDULE_CONFIG.get('download_reports', {'hour': 9, 'minute': 0})
    scheduler.add_job(job_download_reports_for_all, 'cron', hour=report_download_config['hour'], minute=report_download_config['minute'], name="Descarga diaria de reportes T-Registro")

    # Tarea 6: Proceso SIRE
    sire_config = config.SCHEDULE_CONFIG.get('sire_reports', {'day': 9, 'hour': 9, 'minute': 0})
    scheduler.add_job(job_sire_full_process, 'cron', day=sire_config['day'], hour=sire_config['hour'], minute=sire_config['minute'], name="Proceso completo mensual de propuestas SIRE")

    logger.info("Scheduler iniciado. Tareas programadas:")
    scheduler.print_jobs()
    logger.info("Presiona Ctrl+C para detener el programador.")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler detenido.")


def job_download_all_invoices_monthly():
    """Job mensual que descarga facturas para todos los contribuyentes activos."""
    logger.info("INICIANDO JOB MENSUAL: Descarga de facturas para todos")
    contribuyentes = get_active_contribuyentes()
    if not contribuyentes:
        logger.warning("No hay contribuyentes activos para descargar facturas.")
        return
    logger.info(f"Se procesarán {len(contribuyentes)} contribuyentes.")
    for contribuyente in contribuyentes:
        job_download_invoices_for_ruc(contribuyente['ruc'])
    logger.info("JOB MENSUAL FINALIZADO: Descarga de facturas")