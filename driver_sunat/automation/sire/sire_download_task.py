# -*- coding: utf-8 -*-
from datetime import datetime
from .sire_client import SireClient
from ...database import operations as db

class SireDownloadTask:
    """
    Tarea para descargar un reporte SIRE usando parámetros pre-validados.
    """

    def __init__(self, logger, ruc, client: SireClient = None):
        self.logger = logger
        # Permite reutilizar un SireClient existente
        self.client = client if client else SireClient(logger, ruc)

    def run(self, contribuyente: dict, sire_id: int, download_params: dict):
        """
        Descarga un archivo de reporte SIRE.

        Args:
            contribuyente: Datos del contribuyente.
            sire_id: ID del registro en la tabla sire_reportes para actualizar su estado.
            download_params: Diccionario con los parámetros necesarios para la descarga,
                             obtenidos de la consulta de estado.
        """
        nom_archivo = download_params.get('nomArchivoReporte')
        self.logger.info(f"Iniciando descarga del archivo '{nom_archivo}' para el reporte SIRE ID {sire_id}")

        try:
            file_path = self.client.download_file(
                contribuyente['ruc'],
                contribuyente['user_sol'],
                contribuyente['password_sol'],
                download_params
            )

            if file_path:
                # Actualizar el estado en la base de datos
                db.update_sire_status(
                    sire_id,
                    'DESCARGADO',
                    nom_archivo,
                    datetime.now().isoformat()
                )
                self.logger.info(f"Reporte SIRE ID {sire_id} marcado como DESCARGADO.")
            else:
                self.logger.error(f"La descarga del reporte SIRE ID {sire_id} falló, no se recibió una ruta de archivo.")
                db.update_sire_status(sire_id, 'ERROR')

        except Exception as e:
            self.logger.error(f"Error crítico durante la descarga del reporte SIRE ID {sire_id}: {e}")
            db.update_sire_status(sire_id, 'ERROR')
            # No relanzar la excepción para no detener el procesamiento de otros reportes
