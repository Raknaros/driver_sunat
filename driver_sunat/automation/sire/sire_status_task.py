# -*- coding: utf-8 -*-
from .sire_client import SireClient

class SireStatusTask:
    """
    Tarea para consultar el estado de un reporte SIRE y devolver los parámetros de descarga.
    """

    def __init__(self, logger, ruc, client: SireClient = None):
        self.logger = logger
        # Permite reutilizar un SireClient existente para no re-autenticar
        self.client = client if client else SireClient(logger, ruc)

    def run(self, contribuyente: dict, ticket: str, periodo: str):
        """
        Consulta el estado de un ticket SIRE.

        Devuelve un diccionario con el estado y, si está listo, los parámetros para la descarga.
        Ej: {'status': 'LISTO', 'params': {...}}
        Ej: {'status': 'PROCESANDO'}
        Ej: {'status': 'ERROR'}
        """
        self.logger.info(f"Consultando estado de ticket SIRE {ticket} para RUC {contribuyente['ruc']}")

        try:
            status_data = self.client.query_status(
                contribuyente['ruc'],
                contribuyente['user_sol'],
                contribuyente['password_sol'],
                ticket,
                periodo
            )

            # Escenario 1: La respuesta no contiene datos o la lista de registros está vacía
            if not status_data or not status_data.get('registros'):
                self.logger.warning(f"Respuesta de SUNAT no contiene 'registros' para el ticket {ticket}. Asumiendo 'PROCESANDO'.")
                return {'status': 'PROCESANDO'}

            # Buscar el ticket específico en la lista de registros
            ticket_info = None
            for registro in status_data['registros']:
                if str(registro.get('numTicket')) == str(ticket):
                    ticket_info = registro
                    break
            
            if not ticket_info:
                self.logger.warning(f"No se encontró el ticket {ticket} en la respuesta de SUNAT. Asumiendo 'PROCESANDO'.")
                return {'status': 'PROCESANDO'}

            # Escenario 2: Se encontró el ticket, analizar su estado
            detalle = ticket_info.get('detalleTicket', {})
            cod_estado = detalle.get('codEstadoEnvio')

            if cod_estado == '06':  # Terminado
                self.logger.info(f"Ticket {ticket} está LISTO para descarga.")
                
                archivo_reporte_lista = ticket_info.get('archivoReporte')
                if not archivo_reporte_lista:
                    self.logger.error(f"Ticket {ticket} está listo pero no contiene la sección 'archivoReporte'.")
                    return {'status': 'ERROR'}
                
                # Extraer parámetros para la descarga
                archivo_info = archivo_reporte_lista[0]
                download_params = {
                    'nomArchivoReporte': archivo_info.get('nomArchivoReporte'),
                    'codTipoArchivoReporte': archivo_info.get('codTipoAchivoReporte'), # Ojo: 'Achivo' en la API
                    'codLibro': ticket_info.get('codLibro', '140400' if 'rvie' in archivo_info.get('nomArchivoReporte','').lower() else '080100'), # Estimar libro
                    'perTributario': ticket_info.get('perTributario'),
                    'codProceso': ticket_info.get('codProceso', '10'),
                    'numTicket': ticket
                }
                
                # Validar que los parámetros esenciales no son nulos
                if not all(download_params.values()):
                    self.logger.error(f"Faltan parámetros de descarga para el ticket {ticket}. Datos: {download_params}")
                    return {'status': 'ERROR'}

                return {'status': 'LISTO', 'params': download_params}

            elif cod_estado == '04': # Con errores
                self.logger.error(f"Ticket {ticket} reporta un error en SUNAT (estado {cod_estado}).")
                return {'status': 'ERROR'}
            
            else: # 01, 02, 03, 05, etc. (en proceso)
                self.logger.info(f"Ticket {ticket} aún en proceso (estado {cod_estado}: {detalle.get('desEstadoEnvio')}).")
                return {'status': 'PROCESANDO'}

        except Exception as e:
            self.logger.error(f"Error consultando estado de ticket SIRE {ticket}: {e}")
            # Devolver PROCESANDO para que se reintente en el siguiente ciclo
            return {'status': 'PROCESANDO'}
