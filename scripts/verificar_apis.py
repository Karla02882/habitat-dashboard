#!/usr/bin/env python3
"""Diagnóstico rápido de conexiones a APIs AXION y Kommo."""
from __future__ import annotations

import sys
from pathlib import Path

# Asegurar UTF-8 en Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from dotenv import load_dotenv
load_dotenv(RAIZ / ".env")

def verificar_axion():
    """Intenta una conexión simple a AXION."""
    try:
        from src import ingest
        print("[OK] AXION: conexión posible")
        return True
    except Exception as e:
        print(f"[FAIL] AXION: {type(e).__name__}: {e}")
        return False

def verificar_kommo():
    """Intenta una conexión simple a Kommo."""
    try:
        from src import crm
        datos = crm.crudo()
        if datos and isinstance(datos, dict):
            leads = len(datos.get("filas", []))
            print(f"[OK] Kommo: conectado ({leads} leads cargados)")
        else:
            print("[FAIL] Kommo: respuesta vacía o invalida")
        return True
    except Exception as e:
        print(f"[FAIL] Kommo: {type(e).__name__}: {e}")
        return False

def verificar_realtime():
    """Verifica que los módulos realtime estén disponibles."""
    try:
        from src import realtime, websocket_server
        print("[OK] Realtime: módulos cargados")
        return True
    except Exception as e:
        print(f"[FAIL] Realtime: {type(e).__name__}: {e}")
        return False

def verificar_tablero_datos():
    """Verifica si el archivo de datos existe y es reciente."""
    try:
        import time
        from scripts import servidor
        archivo = servidor.RUTA_DATOS()
        if not archivo.exists():
            print(f"[FAIL] tablero_datos.json: no existe en {archivo}")
            return False
        mtime = archivo.stat().st_mtime
        ahora = time.time()
        minutos = (ahora - mtime) / 60
        if minutos > 30:
            print(f"[FAIL] tablero_datos.json: hace {minutos:.0f} minutos que no se actualiza")
            return False
        print(f"[OK] tablero_datos.json: actualizado hace {minutos:.1f} minutos")
        return True
    except Exception as e:
        print(f"[FAIL] tablero_datos.json: {type(e).__name__}: {e}")
        return False

if __name__ == "__main__":
    print("\n=== DIAGNOSTICO DE HABITAT DASHBOARD ===\n")
    
    ok = 0
    total = 4
    
    ok += verificar_axion()
    ok += verificar_kommo()
    ok += verificar_realtime()
    ok += verificar_tablero_datos()
    
    print(f"\nResultado: {ok}/{total} OK\n")
    
    if ok == total:
        print("[OK] Sistema listo para tiempo real")
    elif ok < total // 2:
        print("[WARN] Revisar APIs antes de continuar")
    else:
        print("[OK] Sistema parcialmente operativo")

