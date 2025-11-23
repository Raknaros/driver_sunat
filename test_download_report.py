# -*- coding: utf-8 -*-
"""
Script de prueba para descargar reportes T-Registro listos.
Requiere que haya un reporte pendiente con ticket en la BD (ejecutar test_request_report.py primero).
"""

from driver_sunat.automation.driver_manager import get_webdriver
from driver_sunat.automation.tasks.download_report import DownloadReportTask

if __name__ == '__main__':
    # Credenciales de ejemplo (reemplaza con las tuyas)
    CONTRIBUYENTE = {
        'ruc': '10726501306',
        'user_sol': 'USANKYUL',
        'password_sol': 'liroalort'
    }

    # Ticket específico (opcional; None para todos los pendientes)
    TICKET_ESPECIFICO = None  # O especifica un ticket como "12345"

    driver = get_webdriver(headless=False)  # Cambia a True para headless
    try:
        task = DownloadReportTask(driver)
        task.run(CONTRIBUYENTE, TICKET_ESPECIFICO)
        
        print("\n=== VERIFICACIÓN DE DESCARGAS COMPLETADA ===")
        print("Revisa el directorio de descargas y la BD para confirmar descargas exitosas.")
        print("Reportes descargados se marcan como 'DESCARGADO' en la tabla 'reportes_tregistro'.")

    except Exception as e:
        print(f"\n=== ERROR EN PRUEBA ===")
        print(f"Error: {e}")
    finally:
        driver.quit()