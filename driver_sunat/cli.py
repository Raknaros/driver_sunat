# -*- coding: utf-8 -*-
import click
from .scheduler import start_scheduler, job_check_mailbox, job_download_invoices
from .database.operations import initialize_db

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
def check_mailbox():
    """Ejecuta la revisión del buzón electrónico una sola vez."""
    click.echo(click.style("Ejecutando la tarea de revisión del buzón...", fg="blue"))
    job_check_mailbox()
    click.echo(click.style("Tarea de revisión de buzón finalizada.", fg="green"))



# Añadir el grupo de tareas al CLI principal
cli.add_command(tasks)
