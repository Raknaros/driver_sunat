# -*- coding: utf-8 -*-
from driver_sunat.cli import cli
from driver_sunat.config import setup_logging

if __name__ == "__main__":
    """
    Este es el punto de entrada principal de la aplicación.
    Cuando ejecutas `python main.py` en la terminal, se invoca esta sección.
    Llama al objeto `cli` de Click, que se encarga de parsear los argumentos
    de la línea de comandos y ejecutar el comando correspondiente.
    """
    setup_logging()
    cli()