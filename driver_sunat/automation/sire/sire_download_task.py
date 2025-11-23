# -*- coding: utf-8 -*-
from datetime import datetime
from .sire_client import SireClient
from ...database import operations as db

class SireDownloadTask:
    """
    Tarea para descargar reportes SIRE listos.
    """

    def __init__(self, logger):
        self.logger = logger
        self.client = SireClient(logger)

    def run(self, contribuyente: dict, sire_id: int):
        """
        Descarga un reporte SIRE si está listo.

        Args:
            contribuyente: Datos del contribuyente
            sire_id: ID del registro en sire_reportes
        """
        # Obtener datos del reporte
        reports = db.get_pending_sire_reports()
        report = next((r for r in reports if r['id'] == sire_id), None)
        if not report:
            self.logger.error(f"No se encontró reporte SIRE con ID {sire_id}")
            return

        ticket = report['ticket']
        tipo = report['tipo']
        periodo = report['periodo']

        self.logger.info(f"Verificando descarga para reporte SIRE ID {sire_id}, ticket {ticket}")

        try:
            # Consultar estado primero
            from .sire_status_task import SireStatusTask
            status_task = SireStatusTask(self.logger)
            estado = status_task.run(contribuyente, ticket, tipo, periodo)

            if estado == 'LISTO':
                # Asumir datos de archivo (en producción, obtener de status response)
                nom_archivo = f"LE{contribuyente['ruc']}{periodo}0100014040001EXP2.zip"  # Ejemplo
                cod_tipo_archivo = "00"
                cod_libro = "140000"  # Ajustar según tipo

                file_path = self.client.download_file(
                    contribuyente['ruc'],
                    contribuyente['user_sol'],
                    contribuyente['password_sol'],
                    tipo,
                    periodo,
                    ticket,
                    nom_archivo,
                    cod_tipo_archivo,
                    cod_libro
                )

                if file_path:
                    db.update_sire_status(
                        sire_id,
                        'DESCARGADO',
                        nom_archivo,
                        datetime.now().isoformat()
                    )
                    self.logger.info(f"Reporte SIRE ID {sire_id} descargado exitosamente")
                else:
                    self.logger.error("Fallo en descarga del archivo")
            else:
                self.logger.info(f"Reporte SIRE ID {sire_id} no está listo aún (estado: {estado})")

        except Exception as e:
            self.logger.error(f"Error descargando reporte SIRE ID {sire_id}: {e}")
            raise