# -*- coding: utf-8 -*-
from apscheduler.schedulers.blocking import BlockingScheduler
from .automation.driver_manager import get_webdriver
from .automation.tasks.check_mailbox import CheckMailboxTask
from .database.operations import get_active_contribuyentes, initialize_local_db, sync_clients_from_central_db

def job_check_all_mailboxes():
    """Job que obtiene todos los clientes activos y ejecuta la revisión de buzón para cada uno."""
    print("\n" + "="*50)
    print("INICIANDO JOB PROGRAMADO: Revisión de todos los buzones")
    print("="*50)
    
    contribuyentes = get_active_contribuyentes()
    if not contribuyentes:
        print("No hay contribuyentes activos en la BD local para procesar.")
        return

    print(f"Se procesarán {len(contribuyentes)} contribuyentes.")
    driver = get_webdriver(headless=True)
    try:
        task = CheckMailboxTask(driver)
        for client in contribuyentes:
            task.run(client)
            print("-"*20)
    finally:
        driver.quit()
    print("\n" + "="*50)
    print("JOB PROGRAMADO FINALIZADO")
    print("="*50)

def start_scheduler():
    """Configura e inicia el programador de tareas."""
    initialize_local_db()
    scheduler = BlockingScheduler(timezone="America/Lima")

    # Tarea 1: Sincronizar clientes desde la BD central todos los días a la 1:00 AM
    scheduler.add_job(
        sync_clients_from_central_db, 
        trigger='cron', 
        hour=1, 
        minute=0,
        name="Sincronización diaria de clientes"
    )

    # Tarea 2: Revisar los buzones de todos los clientes todos los días a las 8:00 AM
    scheduler.add_job(
        job_check_all_mailboxes, 
        trigger='cron', 
        hour=8, 
        minute=0,
        name="Revisión diaria de buzones SUNAT"
    )

    print("Scheduler iniciado. Tareas programadas:")
    scheduler.print_jobs()
    print("Presiona Ctrl+C para detener el programador.")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("Scheduler detenido.")