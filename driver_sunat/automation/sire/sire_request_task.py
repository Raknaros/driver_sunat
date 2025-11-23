# -*- coding: utf-8 -*-
from datetime import datetime
from .sire_client import SireClient
from ...database import operations as db

class SireRequestTask:
    """
    Tarea para solicitar reportes SIRE (Ventas/Compras) via API.
    """

    def __init__(self, logger):
        self.logger = logger
        self.client = SireClient(logger)

    def run(self, contribuyente: dict, tipo: str, periodo: str):
        """
        Solicita una propuesta de reporte SIRE.

        Args:
            contribuyente: Datos del contribuyente
            tipo: 'ventas' o 'compras'
            periodo: Período tributario (ej. '202509')
        """
        self.logger.info(f"Solicitando reporte SIRE {tipo} para RUC {contribuyente['ruc']}, período {periodo}")

        try:
            ticket = self.client.request_proposal(
                contribuyente['ruc'],
                contribuyente['user_sol'],
                contribuyente['password_sol'],
                tipo,
                periodo
            )

            if ticket:
                sire_data = {
                    'ruc': contribuyente['ruc'],
                    'tipo': tipo,
                    'periodo': periodo,
                    'ticket': ticket,
                    'estado': 'SOLICITADO',
                    'fecha_solicitud': datetime.now().isoformat()
                }
                sire_id = db.add_sire_request(sire_data)
                self.logger.info(f"Reporte SIRE solicitado registrado en BD con ID {sire_id}, Ticket {ticket}")
                return sire_id
            else:
                self.logger.error("No se pudo obtener ticket para la solicitud SIRE")
                return None

        except Exception as e:
            self.logger.error(f"Error solicitando reporte SIRE: {e}")
            raise