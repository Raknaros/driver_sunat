# -*- coding: utf-8 -*-
import click
from .scheduler import (
    start_scheduler, 
    job_check_all_mailboxes, 
    job_check_mailbox_for_ruc,
    run_sire_proposals_request, 
    run_sire_status_check,
    job_request_reports_monthly,
    job_request_report_for_ruc # Necesitaremos crear esta función
)
from .database.operations import (
    initialize_local_db, 
    get_active_contribuyentes, 
    sync_clients_from_central_db,
    sync_otras_credenciales_from_central_db, 
    sync_buzon_to_central
)
from .automation.driver_manager import get_webdriver
from .automation.tasks.download_invoices import DownloadInvoicesTask
from .automation.tasks.request_report import RequestReportTask
from .automation.tasks.download_report import DownloadReportTask
from .automation.sire.sire_request_task import SireRequestTask
from .automation.sire.sire_download_task import SireDownloadTask

@click.group()
def cli():
    """
    Driver para la automatización de tareas en el portal de la SUNAT.
    Este es el punto de entrada para todos los comandos de la aplicación.
    Usa --help en cualquier comando para ver sus opciones.
    """
    pass

@cli.command()
def scheduler():
    """Inicia el programador de tareas en modo 'blocking'."""
    click.echo(click.style("Iniciando el programador de tareas. Presiona Ctrl+C para salir.", fg="green"))
    start_scheduler()

@cli.command()
def init_db():
    """(Re)Inicializa la base de datos y crea las tablas."""
    click.echo(click.style("Inicializando la base de datos...", fg="yellow"))
    initialize_local_db()
    click.echo(click.style("Base de datos lista.", fg="green"))

@cli.command()
def sync_otras_credenciales():
    """Sincroniza otras_credenciales desde la base de datos central."""
    click.echo(click.style("Sincronizando otras_credenciales...", fg="yellow"))
    sync_otras_credenciales_from_central_db()
    click.echo(click.style("Sincronización completada.", fg="green"))

@cli.command()
def sync_contribuyentes():
    """Sincroniza contribuyentes desde la base de datos central."""
    click.echo(click.style("Sincronizando contribuyentes...", fg="yellow"))
    sync_clients_from_central_db()
    click.echo(click.style("Sincronización completada.", fg="green"))

# --- Comandos para Tareas Manuales ---

@click.group()
def tasks():
    """Grupo de comandos para ejecutar tareas manualmente."""
    pass

@tasks.command()
@click.option('--ruc', help='RUC específico (opcional, por defecto todos los activos)')
def check_mailbox(ruc):
    """Ejecuta la revisión del buzón electrónico para todos o un RUC específico."""
    if ruc:
        click.echo(click.style(f"Ejecutando revisión de buzón para RUC: {ruc}", fg="blue"))
        job_check_mailbox_for_ruc(ruc)
    else:
        click.echo(click.style("Ejecutando revisión de buzón para todos los contribuyentes activos...", fg="blue"))
        job_check_all_mailboxes()
    click.echo(click.style("Tarea de revisión de buzón finalizada.", fg="green"))

@tasks.command()
@click.option('--ruc', required=True, help='RUC del contribuyente')
@click.option('--start-date', required=True, help='Fecha inicio (DD/MM/YYYY)')
@click.option('--end-date', required=True, help='Fecha fin (DD/MM/YYYY)')
def download_invoices(ruc, start_date, end_date):
    """Descarga facturas para un RUC específico en rango de fechas."""
    click.echo(click.style(f"Descargando facturas para RUC {ruc} ({start_date} - {end_date})", fg="blue"))
    # ... (la lógica interna no cambia)
    
@tasks.command(name="request-report")
@click.option('--ruc', help='RUC específico a procesar.')
@click.option('--all', 'process_all', is_flag=True, help='Procesar todos los contribuyentes activos.')
@click.option('--tipo-reporte', default="6", help='Tipo de reporte a solicitar (default: 6 - Prestadores de servicios).')
def request_report_command(ruc, process_all, tipo_reporte):
    """Solicita reportes T-Registro para uno o todos los contribuyentes."""
    if not ruc and not process_all:
        raise click.UsageError("Debe especificar --ruc o --all.")
    if ruc and process_all:
        raise click.UsageError("No puede usar --ruc y --all al mismo tiempo.")

    if ruc:
        click.echo(click.style(f"Solicitando reporte tipo {tipo_reporte} para RUC {ruc}", fg="blue"))
        job_request_report_for_ruc(ruc, tipo_reporte)
    elif process_all:
        click.echo(click.style(f"Solicitando reporte tipo {tipo_reporte} para TODOS los contribuyentes activos...", fg="blue"))
        job_request_reports_monthly(tipo_reporte)
    
    click.echo(click.style("Tarea de solicitud de reportes finalizada.", fg="green"))


@tasks.command()
@click.option('--ruc', help='RUC específico (opcional, por defecto todos los activos)')
def download_reports(ruc):
    """Descarga reportes T-Registro listos para un RUC o todos."""
    # ... (la lógica interna no cambia)

# --- Comandos para SIRE ---

@tasks.command(name="sire-request")
@click.option('--periodo', 'periodo_unico', help="Periodo único a solicitar (formato YYYYMM).")
@click.option('--desde', 'desde_periodo', help="Periodo inicial del rango a solicitar (formato YYYYMM).")
@click.option('--hasta', 'hasta_periodo', help="Periodo final del rango a solicitar (formato YYYYMM).")
def sire_proposals_request_command(periodo_unico, desde_periodo, hasta_periodo):
    """
    Solicita propuestas SIRE (Ventas/Compras) para todos los contribuyentes activos.
    Puede solicitar un periodo, un rango o el mes anterior por defecto.
    """
    if periodo_unico and (desde_periodo or hasta_periodo):
        raise click.UsageError("No se puede usar --periodo junto con --desde o --hasta.")
    
    click.echo(click.style("Ejecutando la solicitud de propuestas SIRE...", fg="blue"))
    try:
        run_sire_proposals_request(
            periodo_unico=periodo_unico,
            desde_periodo=desde_periodo,
            hasta_periodo=hasta_periodo
        )
        click.echo(click.style("Solicitud de propuestas SIRE completada.", fg="green"))
    except Exception as e:
        click.echo(click.style(f"Error durante la solicitud de propuestas SIRE: {e}", fg="red"))

@tasks.command()
def sire_status_check():
    """Verifica el estado de las propuestas SIRE solicitadas y las descarga si están listas."""
    click.echo(click.style("Ejecutando la verificación de estado de propuestas SIRE...", fg="blue"))
    try:
        run_sire_status_check()
        click.echo(click.style("Verificación de estado SIRE completada.", fg="green"))
    except Exception as e:
        click.echo(click.style(f"Error durante la verificación de estado SIRE: {e}", fg="red"))

@tasks.command()
@click.option('--ruc', required=True, help='RUC del contribuyente')
def sync_buzon(ruc):
    """Sincroniza mensajes de buzón local a la base de datos central."""
    click.echo(click.style(f"Sincronizando buzón para RUC {ruc}...", fg="blue"))
    try:
        sync_buzon_to_central(ruc)
        click.echo(click.style("Sincronización de buzón completada", fg="green"))
    except Exception as e:
        click.echo(click.style(f"Error en sincronización: {e}", fg="red"))

# Añadir el grupo de tareas al CLI principal
cli.add_command(tasks)
