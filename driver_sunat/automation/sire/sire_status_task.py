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
                        cod_estado = item.get('codEstado')
                        des_estado = item.get('desEstado', '').upper()
                        if cod_estado == '6' or 'TERMINADO' in des_estado or 'LISTO' in des_estado:
                            self.logger.info(f"Ticket {ticket} está listo para descarga (estado {cod_estado})")
                            return 'LISTO'
                        elif cod_estado in ['1', '2', '3', '4', '5'] or 'PROCESANDO' in des_estado:
                            self.logger.info(f"Ticket {ticket} aún procesando (estado {cod_estado})")
                            return 'PROCESANDO'
                        else:
                            self.logger.warning(f"Estado desconocido para ticket {ticket}: {cod_estado} - {des_estado}")
                            return 'DESCONOCIDO'

            self.logger.warning(f"No se encontró información de estado para ticket {ticket}")
            return None

        except Exception as e:
            self.logger.error(f"Error consultando estado de ticket SIRE: {e}")
            raise