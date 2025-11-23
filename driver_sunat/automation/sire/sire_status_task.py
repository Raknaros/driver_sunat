# -*- coding: utf-8 -*-
import time
from datetime import datetime
from .sire_client import SireClient
from ...database import operations as db

class SireStatusTask:
    """
    Tarea para consultar el estado de reportes SIRE pendientes.
    """

    def __init__(self, logger, ruc):
        self.logger = logger
        self.client = SireClient(logger, ruc)

    def run(self, contribuyente: dict, ticket: str, tipo: str, periodo: str):
        """
        Consulta el estado de un ticket SIRE.

        Args:
            contribuyente: Datos del contribuyente
            ticket: Ticket del reporte
            tipo: 'ventas' o 'compras'
            periodo: Período tributario
        """
        self.logger.info(f"Consultando estado de ticket SIRE {ticket} para RUC {contribuyente['ruc']}")

        try:
            status_data = self.client.query_status(
                contribuyente['ruc'],
                contribuyente['user_sol'],
                contribuyente['password_sol'],
                tipo,
                periodo,
                ticket
            )

            if status_data and 'data' in status_data:
                # Asumir que data es lista de tickets
                for item in status_data['data']:
                    if str(item.get('numTicket')) == str(ticket):
                        estado = item.get('desEstado', '').upper()
                        if 'TERMINADO' in estado or 'LISTO' in estado:
                            self.logger.info(f"Ticket {ticket} está listo para descarga")
                            # Podría marcar como listo, pero dejar para download task
                            return 'LISTO'
                        elif 'PROCESANDO' in estado:
                            self.logger.info(f"Ticket {ticket} aún procesando")
                            return 'PROCESANDO'
                        else:
                            self.logger.warning(f"Estado desconocido para ticket {ticket}: {estado}")
                            return 'DESCONOCIDO'

            self.logger.warning(f"No se encontró información de estado para ticket {ticket}")
            return None

        except Exception as e:
            self.logger.error(f"Error consultando estado de ticket SIRE: {e}")
            raise