# -*- coding: utf-8 -*-
import logging
from apscheduler.schedulers.blocking import BlockingScheduler
from .automation.driver_manager import get_webdriver
from .automation.tasks.check_mailbox import CheckMailboxTask
from .automation.tasks.download_invoices import DownloadInvoicesTask
from .automation.tasks.request_report import RequestReportTask
from .automation.tasks.download_report import DownloadReportTask
from .automation.sire.sire_request_task import SireRequestTask
from .automation.sire.sire_status_task import SireStatusTask
from .automation.sire.sire_download_task import SireDownloadTask
from .database import operations as db
from .database.operations import get_active_contribuyentes, initialize_local_db, sync_clients_from_central_db
from .config import config

logger = logging.getLogger(__name__)

def job_check_all_mailboxes():
    """Job que obtiene todos los clientes activos y ejecuta la revisión de buzón para cada uno."""
    logger.info("INICIANDO JOB PROGRAMADO: Revisión de todos los buzones")

    contribuyentes = get_active_contribuyentes()
    if not contribuyentes:
        logger.warning("No hay contribuyentes activos en la BD local para procesar.")
        return

    logger.info(f"Se procesarán {len(contribuyentes)} contribuyentes.")
    driver = get_webdriver(headless=False)
    try:
        task = CheckMailboxTask(driver)
        for client in contribuyentes:
            task.run(client)
            logger.debug(f"Procesado contribuyente {client['ruc']}")
    finally:
        driver.quit()

    # Sync determinantes observations to central DB
    db.sync_determinant_observations_to_central()

    logger.info("JOB PROGRAMADO FINALIZADO: Revisión de buzones")

def job_check_mailbox_for_ruc(ruc: str):
    """Job que ejecuta la revisión de buzón para un RUC específico."""
    logger.info(f"INICIANDO JOB: Revisión de buzón para RUC {ruc}")

    contribuyentes = get_active_contribuyentes()
    contribuyente = next((c for c in contribuyentes if c['ruc'] == ruc), None)

    if not contribuyente:
        logger.error(f"RUC {ruc} no encontrado o no activo")
        return

    driver = get_webdriver(headless=False)
    try:
        task = CheckMailboxTask(driver)
        task.run(contribuyente)
        logger.info(f"JOB FINALIZADO: Revisión de buzón para RUC {ruc}")
    finally:
        driver.quit()

def job_download_invoices_for_ruc(ruc: str, start_date=None, end_date=None):
    """Job que descarga facturas para un RUC específico."""
    from datetime import datetime, timedelta

    # Si no se especifican fechas, usar el mes actual
    if not start_date or not end_date:
        today = datetime.now()
        start_date = f"01/{today.month:02d}/{today.year}"
        # Último día del mes
        next_month = today.replace(day=28) + timedelta(days=4)
        end_date = f"{(next_month - timedelta(days=next_month.day)).day:02d}/{today.month:02d}/{today.year}"

    logger.info(f"INICIANDO JOB: Descarga de facturas para RUC {ruc} ({start_date} - {end_date})")

    contribuyentes = get_active_contribuyentes()
    contribuyente = next((c for c in contribuyentes if c['ruc'] == ruc), None)

    if not contribuyente:
        logger.error(f"RUC {ruc} no encontrado o no activo")
        return

    driver = get_webdriver(headless=True)
    try:
        task = DownloadInvoicesTask(driver)
        task.run(contribuyente, start_date, end_date)
        logger.info(f"JOB FINALIZADO: Descarga de facturas para RUC {ruc}")
    finally:
        driver.quit()

def start_scheduler():
    """Configura e inicia el programador de tareas."""
    initialize_local_db()
    scheduler = BlockingScheduler(timezone="America/Lima")

    # Tarea 1: Sincronizar clientes desde la BD central
    sync_config = config.SCHEDULE_CONFIG['sync_clients']
    scheduler.add_job(
        sync_clients_from_central_db,
        trigger='cron',
        hour=sync_config['hour'],
        minute=sync_config['minute'],
        name="Sincronización diaria de clientes"
    )

    # Tarea 2: Revisar los buzones de todos los clientes
    mailbox_config = config.SCHEDULE_CONFIG['check_mailbox']
    scheduler.add_job(
        job_check_all_mailboxes,
        trigger='cron',
        hour=mailbox_config['hour'],
        minute=mailbox_config['minute'],
        name="Revisión diaria de buzones SUNAT"
    )

    # Tarea 3: Descargar facturas mensuales (se ejecutará para todos los RUC activos)
    invoice_config = config.SCHEDULE_CONFIG['download_invoices']
    scheduler.add_job(
        job_download_all_invoices_monthly,
        trigger='cron',
        day=invoice_config['day'],
        hour=invoice_config['hour'],
        minute=invoice_config['minute'],
        name="Descarga mensual de facturas"
    )

    # Tarea 4: Solicitar reportes T-Registro mensuales
    report_request_config = config.SCHEDULE_CONFIG.get('request_reports', {'day': 1, 'hour': 3, 'minute': 0})
    scheduler.add_job(
        job_request_reports_monthly,
        trigger='cron',
        day=report_request_config['day'],
        hour=report_request_config['hour'],
        minute=report_request_config['minute'],
        name="Solicitud mensual de reportes T-Registro"
    )

    # Tarea 5: Descargar reportes listos (diaria, después de la solicitud)
    report_download_config = config.SCHEDULE_CONFIG.get('download_reports', {'hour': 9, 'minute': 0})
    scheduler.add_job(
        job_download_reports_for_all,
        trigger='cron',
        hour=report_download_config['hour'],
        minute=report_download_config['minute'],
        name="Descarga diaria de reportes T-Registro"
    )

    # Tarea 6: Procesar reportes SIRE mensuales (día 9)
    sire_config = config.SCHEDULE_CONFIG.get('sire_reports', {'day': 9, 'hour': 9, 'minute': 0})
    scheduler.add_job(
        job_sire_reports,
        trigger='cron',
        day=sire_config['day'],
        hour=sire_config['hour'],
        minute=sire_config['minute'],
        name="Procesamiento mensual de reportes SIRE"
    )

    logger.info("Scheduler iniciado. Tareas programadas:")
    scheduler.print_jobs()
    logger.info("Presiona Ctrl+C para detener el programador.")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler detenido.")

def job_download_all_invoices_monthly():
    """Job mensual que descarga facturas para todos los contribuyentes activos."""
    logger.info("INICIANDO JOB MENSUAL: Descarga de facturas para todos los contribuyentes")

    contribuyentes = get_active_contribuyentes()
    if not contribuyentes:
        logger.warning("No hay contribuyentes activos para descargar facturas.")
        return

    logger.info(f"Se procesarán {len(contribuyentes)} contribuyentes para descarga de facturas.")

    for contribuyente in contribuyentes:
        try:
            job_download_invoices_for_ruc(contribuyente['ruc'])
            logger.debug(f"Descarga completada para RUC {contribuyente['ruc']}")
        except Exception as e:
            logger.error(f"Error descargando facturas para RUC {contribuyente['ruc']}: {e}")

    logger.info("JOB MENSUAL FINALIZADO: Descarga de facturas")

def job_request_reports_monthly():
    """Job mensual que solicita reportes T-Registro para todos los contribuyentes activos."""
    logger.info("INICIANDO JOB MENSUAL: Solicitud de reportes T-Registro")

    contribuyentes = get_active_contribuyentes()
    if not contribuyentes:
        logger.warning("No hay contribuyentes activos para solicitar reportes.")
        return

    # Tipo de reporte a solicitar (solo uno por mes para evitar sobrecarga)
    tipo_reporte = "6"  # Reporte de prestadores de servicios

    for contribuyente in contribuyentes:
        driver = get_webdriver(headless=True)
        try:
            task = RequestReportTask(driver)
            report_id = task.run(contribuyente, tipo_reporte)

            if report_id:
                logger.info(f"Reporte solicitado exitosamente para RUC {contribuyente['ruc']} - esperando 1 hora para descarga")

            logger.debug(f"Solicitud de reporte completada para RUC {contribuyente['ruc']}")
        except Exception as e:
            logger.error(f"Error solicitando reporte para RUC {contribuyente['ruc']}: {e}")
        finally:
            driver.quit()

    logger.info("JOB MENSUAL FINALIZADO: Solicitud de reportes T-Registro")
    logger.info("Los reportes estarán disponibles para descarga en aproximadamente 1 hora")

def job_download_reports_for_all():
    """Job que descarga reportes listos para todos los contribuyentes."""
    logger.info("INICIANDO JOB: Descarga de reportes listos para todos")

    contribuyentes = get_active_contribuyentes()
    if not contribuyentes:
        logger.warning("No hay contribuyentes activos para descargar reportes.")
        return

    for contribuyente in contribuyentes:
        driver = get_webdriver(headless=True)
        try:
            task = DownloadReportTask(driver)
            task.run(contribuyente)
        except Exception as e:
            logger.error(f"Error descargando reportes para RUC {contribuyente['ruc']}: {e}")
        finally:
            driver.quit()

    logger.info("JOB FINALIZADO: Descarga de reportes para todos")

def job_sire_reports():
    """Job mensual que solicita, consulta y descarga reportes SIRE para todos los contribuyentes."""
    from datetime import datetime
    logger.info("INICIANDO JOB MENSUAL: Procesamiento de reportes SIRE")

    contribuyentes = get_active_contribuyentes()
    if not contribuyentes:
        logger.warning("No hay contribuyentes activos para procesar SIRE.")
        return

    periodo = datetime.now().strftime("%Y%m")  # Mes actual
    tipos = ['ventas', 'compras']

    # Solicitar reportes para todos
    sire_ids = []
    for tipo in tipos:
        for contribuyente in contribuyentes:
            try:
                task = SireRequestTask(logger, contribuyente['ruc'])
                sire_id = task.run(contribuyente, tipo, periodo)
                if sire_id:
                    sire_ids.append((sire_id, tipo, periodo, contribuyente))
            except Exception as e:
                logger.error(f"Error solicitando SIRE {tipo} para RUC {contribuyente['ruc']}: {e}")

    # Polling de status cada 5 min hasta listo o timeout
    import time
    max_attempts = 12  # 1 hora
    for attempt in range(max_attempts):
        logger.info(f"Consulta de status SIRE - Intento {attempt+1}/{max_attempts}")
        all_ready = True
        for sire_id, tipo, periodo, contribuyente in sire_ids:
            try:
                status_task = SireStatusTask(logger, contribuyente['ruc'])
                estado = status_task.run(contribuyente, db.get_pending_sire_reports(ruc=contribuyente['ruc'], tipo=tipo)[0]['ticket'], tipo, periodo)
                if estado == 'LISTO':
                    download_task = SireDownloadTask(logger, contribuyente['ruc'])
                    download_task.run(contribuyente, sire_id)
                elif estado != 'PROCESANDO':
                    all_ready = False
            except Exception as e:
                logger.error(f"Error procesando SIRE ID {sire_id}: {e}")
                all_ready = False

        if all_ready:
            break
        time.sleep(300)  # 5 min

    logger.info("JOB MENSUAL FINALIZADO: Procesamiento de reportes SIRE")