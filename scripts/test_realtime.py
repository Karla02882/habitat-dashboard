#!/usr/bin/env python3
"""TEST · Verificar que el sistema de tiempo real está funcionando correctamente."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
os.chdir(RAIZ)

from src import realtime


def test_cache_basico():
    """Test 1: Actualizar datos y verificar caché."""
    print("\n[Test 1] Cache Básico")
    print("-" * 50)
    
    datos_test = {"registro": 1, "valor": 100}
    
    resultado = realtime.actualizar_datos("tablero", datos_test)
    print(f"  ✓ Datos actualizados: {resultado}")
    
    datos_recuperados, timestamp = realtime.obtener_datos("tablero")
    print(f"  ✓ Datos recuperados: {datos_recuperados}")
    print(f"  ✓ Timestamp: {timestamp}")
    
    assert datos_recuperados == datos_test, "Los datos no coinciden"
    print("  ✅ Test 1 PASÓ")


def test_deteccion_cambios():
    """Test 2: Verificar que detecta cambios (hash)."""
    print("\n[Test 2] Detección de Cambios")
    print("-" * 50)
    
    # Primer update
    datos1 = {"a": 1}
    realtime.actualizar_datos("stock", datos1, forzar=True)
    print("  ✓ Primer update")
    
    # Mismo dato (no debería actualizar)
    resultado2 = realtime.actualizar_datos("stock", datos1)
    print(f"  ✓ Segundo update (mismo dato): {resultado2}")
    assert resultado2 is False, "Debería detectar que no cambió"
    
    # Esperar a que pasen el rate limit (2.1 segundos)
    print("  ⏳ Esperando rate limit...")
    time.sleep(2.1)
    
    # Dato diferente (debería actualizar)
    datos2 = {"a": 2}
    resultado3 = realtime.actualizar_datos("stock", datos2)
    print(f"  ✓ Tercer update (dato distinto): {resultado3}")
    assert resultado3 is True, f"Debería detectar el cambio (got {resultado3})"
    
    print("  ✅ Test 2 PASÓ")


def test_suscriptores():
    """Test 3: Verificar sistema de suscriptores."""
    print("\n[Test 3] Suscriptores")
    print("-" * 50)
    
    cambios_recibidos = []
    
    def callback(canal: str, datos):
        cambios_recibidos.append((canal, datos))
        print(f"  ✓ Callback recibido: {canal}")
    
    # Registrar
    realtime.registrar_suscriptor("ventas", callback)
    print("  ✓ Suscriptor registrado")
    
    # Actualizar (debería llamar el callback)
    datos = {"ventas": 10000}
    realtime.actualizar_datos("ventas", datos, forzar=True)
    
    time.sleep(0.1)  # Dar tiempo al callback
    assert len(cambios_recibidos) > 0, "El callback no fue llamado"
    print(f"  ✓ Callback ejecutado: {cambios_recibidos[-1]}")
    
    # Desregistrar
    realtime.desregistrar_suscriptor("ventas", callback)
    print("  ✓ Suscriptor desregistrado")
    
    cambios_recibidos.clear()
    realtime.actualizar_datos("ventas", {"ventas": 20000}, forzar=True)
    time.sleep(0.1)
    assert len(cambios_recibidos) == 0, "El callback debería estar desregistrado"
    print("  ✓ Verificado que callback no se ejecuta después de desregistrar")
    
    print("  ✅ Test 3 PASÓ")


def test_rate_limiting():
    """Test 4: Verificar rate limiting."""
    print("\n[Test 4] Rate Limiting")
    print("-" * 50)
    
    # Intentar actualizar muy rápido
    datos = {"counter": 0}
    resultado1 = realtime.actualizar_datos("crm", datos, forzar=True)
    print(f"  ✓ Primera actualización: {resultado1}")
    assert resultado1 is True
    
    # Segundo intento inmediato (debería ser rechazado)
    datos["counter"] = 1
    resultado2 = realtime.actualizar_datos("crm", datos)
    print(f"  ✓ Segunda actualización (rechazada por rate limit): {resultado2}")
    assert resultado2 is False, "Debería ser rechazado por rate limit"
    
    # Esperar y reintentar
    print("  ⏳ Esperando 2.5 segundos...")
    time.sleep(2.5)
    resultado3 = realtime.actualizar_datos("crm", datos)
    print(f"  ✓ Tercera actualización (después de esperar): {resultado3}")
    assert resultado3 is True, "Debería permitirse después de esperar"
    
    print("  ✅ Test 4 PASÓ")


def test_estado_cache():
    """Test 5: Obtener estado del caché."""
    print("\n[Test 5] Estado del Caché")
    print("-" * 50)
    
    # Llenar algunos canales
    realtime.actualizar_datos("tablero", {"data": "tablero"}, forzar=True)
    realtime.actualizar_datos("stock", {"data": "stock"}, forzar=True)
    
    estado = realtime.obtener_estado_cache()
    print(f"  ✓ Estado del cache obtenido")
    
    for canal, info in estado.items():
        print(f"    {canal}:")
        print(f"      - Tiene datos: {info['tiene_datos']}")
        print(f"      - Hace segundos: {info['hace_segundos']}")
        print(f"      - Hash: {info['hash']}")
    
    assert estado["tablero"]["tiene_datos"] is True
    assert estado["stock"]["tiene_datos"] is True
    print("  ✅ Test 5 PASÓ")


def test_limpiar_cache():
    """Test 6: Limpiar caché."""
    print("\n[Test 6] Limpiar Caché")
    print("-" * 50)
    
    realtime.actualizar_datos("tablero", {"data": "test"}, forzar=True)
    assert realtime.obtener_datos("tablero") is not None
    print("  ✓ Datos en caché antes de limpiar")
    
    realtime.limpiar_cache()
    resultado = realtime.obtener_datos("tablero")
    assert resultado is None
    print("  ✓ Caché limpiado correctamente")
    
    print("  ✅ Test 6 PASÓ")


def test_websocket_disponible():
    """Test 7: Verificar disponibilidad de WebSocket."""
    print("\n[Test 7] Disponibilidad WebSocket")
    print("-" * 50)
    
    try:
        from src import websocket_server
        disponible = websocket_server.SOCKETIO_DISPONIBLE
        print(f"  ✓ WebSocket disponible: {disponible}")
        
        if disponible:
            print("  ✅ Flask-SocketIO está instalado")
        else:
            print("  ⚠️  Flask-SocketIO NO está disponible")
            print("     Run: pip install flask-socketio")
    except ImportError as e:
        print(f"  ✗ Error importando websocket_server: {e}")
    
    print("  ✅ Test 7 COMPLETÓ")


def main():
    """Ejecutar todos los tests."""
    print("\n" + "=" * 60)
    print(" TEST - Sistema de Tiempo Real Habitat")
    print("=" * 60)
    
    tests = [
        test_cache_basico,
        test_deteccion_cambios,
        test_suscriptores,
        test_rate_limiting,
        test_estado_cache,
        test_limpiar_cache,
        test_websocket_disponible,
    ]
    
    pasaron = 0
    fallaron = 0
    
    for test in tests:
        try:
            test()
            pasaron += 1
        except Exception as e:
            print(f"  ❌ Test FALLÓ: {e}")
            import traceback
            traceback.print_exc()
            fallaron += 1
    
    print("\n" + "=" * 60)
    print(f" RESULTADO: {pasaron} pasaron, {fallaron} fallaron")
    print("=" * 60 + "\n")
    
    return 0 if fallaron == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
