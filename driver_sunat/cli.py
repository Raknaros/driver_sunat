# -*- coding: utf-8 -*-
import click
from .scheduler import start_scheduler, job_check_mailbox, job_download_invoices_for_ruc
from .database.operations import initialize_db, get_active_contribuyentes
from .automation.driver_manager import get_webdriver
from .automation.tasks.check_mailbox import CheckMailboxTask
from .automation.tasks.download_invoices import DownloadInvoicesTask
from .automation.tasks.request_report import RequestReportTask
from .automation.tasks.download_report import DownloadReportTask

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
    initialize_db()
    click.echo(click.style("Base de datos lista.", fg="green"))

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
        job_check_mailbox()
    click.echo(click.style("Tarea de revisión de buzón finalizada.", fg="green"))

@tasks.command()
@click.option('--ruc', required=True, help='RUC del contribuyente')
@click.option('--start-date', required=True, help='Fecha inicio (DD/MM/YYYY)')
@click.option('--end-date', required=True, help='Fecha fin (DD/MM/YYYY)')
def download_invoices(ruc, start_date, end_date):
    """Descarga facturas para un RUC específico en rango de fechas."""
    click.echo(click.style(f"Descargando facturas para RUC {ruc} ({start_date} - {end_date})", fg="blue"))

    # Obtener datos del contribuyente
    contribuyentes = get_active_contribuyentes()
    contribuyente = next((c for c in contribuyentes if c['ruc'] == ruc), None)

    if not contribuyente:
        click.echo(click.style(f"Error: RUC {ruc} no encontrado o no activo", fg="red"))
        return

    driver = get_webdriver(headless=False)
    try:
        task = DownloadInvoicesTask(driver)
        task.run(contribuyente, start_date, end_date)
        click.echo(click.style("Descarga completada exitosamente", fg="green"))
    except Exception as e:
        click.echo(click.style(f"Error en descarga: {e}", fg="red"))
    finally:
        driver.quit()

@tasks.command()
@click.option('--ruc', required=True, help='RUC del contribuyente')
@click.option('--tipo-reporte', default="6", help='Tipo de reporte a solicitar (default: 6 - Prestadores de servicios)')
def request_report(ruc, tipo_reporte):
    """Solicita un reporte T-Registro para un RUC específico."""
    click.echo(click.style(f"Solicitando reporte tipo {tipo_reporte} para RUC {ruc}", fg="blue"))

    # Obtener datos del contribuyente
    contribuyentes = get_active_contribuyentes()
    contribuyente = next((c for c in contribuyentes if c['ruc'] == ruc), None)

    if not contribuyente:
        click.echo(click.style(f"Error: RUC {ruc} no encontrado o no activo", fg="red"))
        return

    driver = get_webdriver(headless=False)
    try:
        task = RequestReportTask(driver)
        report_id = task.run(contribuyente, tipo_reporte)
        if report_id:
            click.echo(click.style(f"Solicitud de reporte completada exitosamente (ID: {report_id})", fg="green"))
            click.echo(click.style("El reporte estará disponible para descarga en aproximadamente 1 hora", fg="yellow"))
        else:
            click.echo(click.style("Solicitud completada pero no se pudo registrar el ticket", fg="yellow"))
    except Exception as e:
        click.echo(click.style(f"Error en solicitud de reporte: {e}", fg="red"))
    finally:
        driver.quit()

@tasks.command()
@click.option('--ruc', help='RUC específico (opcional, por defecto todos los activos)')
def download_reports(ruc):
    """Descarga reportes T-Registro listos para un RUC o todos."""
    if ruc:
        click.echo(click.style(f"Descargando reportes listos para RUC: {ruc}", fg="blue"))
        # Obtener datos del contribuyente
        contribuyentes = get_active_contribuyentes()
        contribuyente = next((c for c in contribuyentes if c['ruc'] == ruc), None)

        if not contribuyente:
            click.echo(click.style(f"Error: RUC {ruc} no encontrado o no activo", fg="red"))
            return

        driver = get_webdriver(headless=False)
        try:
            task = DownloadReportTask(driver)
            task.run(contribuyente)
            click.echo(click.style("Descarga de reportes completada", fg="green"))
        except Exception as e:
            click.echo(click.style(f"Error en descarga de reportes: {e}", fg="red"))
        finally:
            driver.quit()
    else:
        click.echo(click.style("Descargando reportes listos para todos los contribuyentes activos...", fg="blue"))
        # Lógica para todos los RUC (similar a job_download_reports_for_all)
        contribuyentes = get_active_contribuyentes()
        for contribuyente in contribuyentes:
            driver = get_webdriver(headless=True)
            try:
                task = DownloadReportTask(driver)
                task.run(contribuyente)
            except Exception as e:
                click.echo(click.style(f"Error descargando reportes para RUC {contribuyente['ruc']}: {e}", fg="red"))
            finally:
                driver.quit()
        click.echo(click.style("Descarga de reportes completada para todos", fg="green"))

# Añadir el grupo de tareas al CLI principal
cli.add_command(tasks)
