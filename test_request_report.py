# -*- coding: utf-8 -*-
"""
Script de prueba para solicitar reportes T-Registro e imprimir el ticket generado en consola.
"""

from driver_sunat.automation.driver_manager import get_webdriver
from driver_sunat.automation.tasks.request_report import RequestReportTask

if __name__ == '__main__':
    # Credenciales de ejemplo (reemplaza con las tuyas)
    CONTRIBUYENTE = {
        'ruc': '10726501306',
        'user_sol': 'USANKYUL',
        'password_sol': 'liroalort'
    }

    # Tipo de reporte a solicitar (6 = Prestadores de servicios)
    TIPO_REPORTE = "6"

    driver = get_webdriver(headless=False)  # Cambia a True para headless
    try:
        task = RequestReportTask(driver)
        report_id = task.run(CONTRIBUYENTE, TIPO_REPORTE)
        print(f"DEBUG: report_id = {report_id}, type = {type(report_id)}")
    
        if report_id:
            print(f"\n=== SOLICITUD DE REPORTE EXITOSA ===")
            print(f"ID de reporte en BD: {report_id}")
            print("El reporte estará disponible para descarga en aproximadamente 1 hora")
            print("Ejecuta 'python main.py tasks download-reports' para descargar cuando esté listo")
        else:
            print(f"\n=== ERROR EN SOLICITUD DE REPORTE ===")
            print("No se pudo completar la solicitud")

    except Exception as e:
        print(f"\n=== ERROR EN PRUEBA ===")
        print(f"Error: {e}")
    finally:
        driver.quit()