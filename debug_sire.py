# -*- coding: utf-8 -*-
import logging
import sys
from driver_sunat.database.operations import get_local_db_connection, get_active_contribuyentes
from driver_sunat.automation.sire.sire_client import SireClient

def check_ruc(ruc):
    print(f"--- DIAGNÓSTICO PARA RUC {ruc} ---")
    conn = get_local_db_connection()
    cursor = conn.cursor()
    
    # 1. Verificar tabla contribuyentes
    print("\n[1] Verificando tabla 'contribuyentes' (Usuario SOL)...")
    cursor.execute("SELECT * FROM contribuyentes WHERE ruc = ?", (ruc,))
    row = cursor.fetchone()
    contribuyente_data = None
    
    if row:
        print(f"    ✅ Encontrado. Activo: {row['is_active']}")
        if row['is_active'] != 1:
            print("    ❌ ERROR: El contribuyente está marcado como INACTIVO (is_active=0).")
        
        # Necesitamos desencriptar la clave SOL para la prueba de conexión
        contribuyentes = get_active_contribuyentes()
        contribuyente_data = next((c for c in contribuyentes if c['ruc'] == ruc), None)
    else:
        print("    ❌ ERROR: RUC no encontrado en tabla 'contribuyentes'. Ejecuta 'python main.py sync_contribuyentes'.")
        conn.close()
        return

    # 2. Verificar tabla otras_credenciales
    print("\n[2] Verificando tabla 'otras_credenciales' (Client ID / Secret)...")
    cursor.execute("SELECT * FROM otras_credenciales WHERE ruc = ?", (ruc,))
    rows = cursor.fetchall()
    
    valid_db_entry = False
    if not rows:
        print("    ❌ ERROR: No hay registros en 'otras_credenciales' para este RUC.")
        print("       Ejecuta 'python main.py sync_otras_credenciales' si ya están en la BD Central.")
    else:
        for r in rows:
            tipo = r['tipo']
            obs = r['observaciones'] or ""
            print(f"    - Registro encontrado -> Tipo: '{tipo}' | Observaciones: '{obs}'")
            
            if tipo == 'APISUNAT' and 'SIRE' in obs:
                valid_db_entry = True
                print("      ✅ ESTE REGISTRO ES VÁLIDO (Cumple Tipo='APISUNAT' y 'SIRE' en observaciones).")
            elif tipo == 'APISUNAT':
                print("      ⚠️  ADVERTENCIA: Tipo es correcto pero falta la palabra 'SIRE' en observaciones.")
        
        if not valid_db_entry:
            print("\n    ❌ CONCLUSIÓN BD: El sistema ignora este RUC porque ningún registro cumple las condiciones.")
            print("       Solución: Asegúrate que el campo 'observaciones' incluya la palabra 'SIRE'.")
            conn.close()
            return

    conn.close()

    # 3. Prueba de conexión REAL (si hay credenciales válidas en BD)
    print("\n[3] Prueba de conexión con API SUNAT (Obtención de Token)...")
    if not contribuyente_data:
        print("    ❌ No se puede probar conexión porque no se pudo recuperar el usuario SOL.")
        return

    try:
        # Configurar logger básico para ver output
        logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
        logger = logging.getLogger("test_sire")
        
        print("    Intentando instanciar SireClient...")
        client = SireClient(logger, ruc)
        
        print("    Solicitando Token a SUNAT (POST /oauth2/token/)...")
        # Usamos el método interno _get_token para forzar la llamada
        token = client._get_token(ruc, contribuyente_data['user_sol'], contribuyente_data['password_sol'])
        
        if token:
            print(f"    ✅ ¡ÉXITO! Token obtenido correctamente.")
            print(f"    Token (primeros 15 chars): {token[:15]}...")
            print("    Las credenciales son válidas y funcionales.")
        else:
            print("    ❌ FALLO: La API no devolvió un token.")

    except Exception as e:
        print(f"    ❌ ERROR CRÍTICO durante la prueba de conexión: {e}")
        print("    Verifica que el Client ID y Client Secret sean correctos y correspondan a este RUC.")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        check_ruc(sys.argv[1])
    else:
        print("Uso: python debug_sire.py <NUMERO_RUC>")
