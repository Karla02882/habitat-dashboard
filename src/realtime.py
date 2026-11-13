"""TIEMPO REAL · Sistema de actualización de datos instantáneamente via WebSocket."""
from __future__ import annotations

import json
import threading
import time
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from . import reloj

RAIZ = Path(__file__).resolve().parent.parent

# Cache de datos con timestamp para detectar cambios
_CACHE_DATOS: dict[str, dict[str, Any]] = {
    "tablero": {"data": None, "timestamp": 0, "hash": ""},
    "stock": {"data": None, "timestamp": 0, "hash": ""},
    "ventas": {"data": None, "timestamp": 0, "hash": ""},
    "finanzas": {"data": None, "timestamp": 0, "hash": ""},
    "crm": {"data": None, "timestamp": 0, "hash": ""},
}

_CACHE_CANDADO = threading.Lock()
_SUSCRIPTORES: dict[str, list[Callable]] = defaultdict(list)
_SUSCRIPTORES_CANDADO = threading.Lock()

# Control de actualizaciones
_ULTIMAS_ACTUALIZACIONES: dict[str, float] = {}
_RATE_LIMIT_MIN_S = 2  # Mínimo 2 segundos entre actualizaciones


def _hash_datos(data: Any) -> str:
    """Genera un hash simple de los datos para detectar cambios."""
    try:
        import hashlib
        contenido = json.dumps(data, sort_keys=True, default=str)
        return hashlib.md5(contenido.encode()).hexdigest()[:8]
    except (TypeError, ValueError):
        return ""


def registrar_suscriptor(canal: str, callback: Callable[[str, Any], None]) -> None:
    """Registra una función para ser notificada cuando hay cambios en un canal.
    
    Args:
        canal: identificador del canal (e.g., "tablero", "stock", "ventas")
        callback: función(canal, datos) que será llamada cuando hay actualizaciones
    """
    with _SUSCRIPTORES_CANDADO:
        if callback not in _SUSCRIPTORES[canal]:
            _SUSCRIPTORES[canal].append(callback)


def desregistrar_suscriptor(canal: str, callback: Callable) -> None:
    """Desregistra un suscriptor de un canal."""
    with _SUSCRIPTORES_CANDADO:
        _SUSCRIPTORES[canal] = [c for c in _SUSCRIPTORES[canal] if c != callback]


def _notificar_suscriptores(canal: str, datos: Any) -> None:
    """Notifica a todos los suscriptores de un canal."""
    with _SUSCRIPTORES_CANDADO:
        callbacks = list(_SUSCRIPTORES[canal])
    
    for callback in callbacks:
        try:
            callback(canal, datos)
        except Exception as e:
            print(f"  Error notificando suscriptor en {canal}: {e}")


def _puede_actualizar(canal: str) -> bool:
    """Verifica si es momento de actualizar este canal (rate limiting)."""
    ahora = time.time()
    ultima = _ULTIMAS_ACTUALIZACIONES.get(canal, 0)
    if ahora - ultima >= _RATE_LIMIT_MIN_S:
        _ULTIMAS_ACTUALIZACIONES[canal] = ahora
        return True
    return False


def actualizar_datos(canal: str, datos: Any, forzar: bool = False) -> bool:
    """Actualiza los datos de un canal y notifica a suscriptores si cambió.
    
    Args:
        canal: identificador del canal
        datos: los nuevos datos
        forzar: si True, notifica aunque el hash sea igual
        
    Returns:
        True si se actualizó y notificó; False si se rechazó por rate limit
    """
    if canal not in _CACHE_DATOS:
        print(f"  Advertencia: canal desconocido '{canal}'")
        return False
    
    # Rate limiting
    if not forzar and not _puede_actualizar(canal):
        return False
    
    nuevo_hash = _hash_datos(datos)
    
    with _CACHE_CANDADO:
        entrada = _CACHE_DATOS[canal]
        cambió = (nuevo_hash != entrada["hash"] or forzar)
        
        if cambió:
            entrada.update({
                "data": datos,
                "timestamp": time.time(),
                "hash": nuevo_hash,
            })
            # Actualizar rate limit timestamp DENTRO del lock
            _ULTIMAS_ACTUALIZACIONES[canal] = time.time()
    
    if cambió:
        _notificar_suscriptores(canal, datos)
        return True
    
    return False


def obtener_datos(canal: str) -> tuple[Any, float] | None:
    """Obtiene los datos de un canal y su timestamp.
    
    Returns:
        Tupla (datos, timestamp) o None si el canal no existe o está vacío
    """
    if canal not in _CACHE_DATOS:
        return None
    
    with _CACHE_CANDADO:
        entrada = _CACHE_DATOS[canal]
        if entrada["data"] is None:
            return None
        return entrada["data"], entrada["timestamp"]


def limpiar_cache() -> None:
    """Limpia todo el cache (útil después de un ciclo de actualización)."""
    with _CACHE_CANDADO:
        for canal in _CACHE_DATOS:
            _CACHE_DATOS[canal]["data"] = None
            _CACHE_DATOS[canal]["timestamp"] = 0
            _CACHE_DATOS[canal]["hash"] = ""


def obtener_estado_cache() -> dict[str, dict]:
    """Devuelve información sobre el estado actual del cache."""
    with _CACHE_CANDADO:
        return {
            canal: {
                "tiene_datos": entrada["data"] is not None,
                "timestamp": entrada["timestamp"],
                "hace_segundos": round(time.time() - entrada["timestamp"]),
                "hash": entrada["hash"],
            }
            for canal, entrada in _CACHE_DATOS.items()
        }


def diferencia_desde(canal: str, timestamp_anterior: float) -> dict | None:
    """Obtiene qué cambió desde un timestamp anterior (para actualizaciones delta).
    
    Esto es más eficiente que enviar todos los datos cada vez.
    """
    datos_actuales, ts_actual = obtener_datos(canal) or (None, 0)
    if datos_actuales is None or ts_actual <= timestamp_anterior:
        return None
    
    return {
        "canal": canal,
        "timestamp": ts_actual,
        "datos": datos_actuales,
    }


# Thread worker para actualizar datos periódicamente
_WORKER_VIVO = False
_WORKER_CANDACO = threading.Lock()


def iniciar_worker_tiempo_real(intervalo_s: int = 30) -> None:
    """Inicia un thread worker que chequea cambios en archivos cada `intervalo_s`.
    
    Este worker:
    - Lee el tablero_datos.json si cambió
    - Detecta cambios en stock en vivo
    - Notifica a los suscriptores
    """
    global _WORKER_VIVO
    
    def worker():
        ruta_tablero = RAIZ / "data" / "tablero_datos.json"
        ruta_stock = RAIZ / "data" / "stock_vivo.json"
        
        mtimes = {
            "tablero": 0,
            "stock": 0,
        }
        
        while _WORKER_VIVO:
            try:
                ahora = time.time()
                
                # Chequear tablero_datos.json
                if ruta_tablero.exists():
                    mtime = ruta_tablero.stat().st_mtime
                    if mtime > mtimes["tablero"]:
                        mtimes["tablero"] = mtime
                        try:
                            datos = json.loads(ruta_tablero.read_text(encoding="utf-8"))
                            actualizar_datos("tablero", datos)
                        except (json.JSONDecodeError, OSError):
                            pass
                
                # Chequear stock_vivo.json
                if ruta_stock.exists():
                    mtime = ruta_stock.stat().st_mtime
                    if mtime > mtimes["stock"]:
                        mtimes["stock"] = mtime
                        try:
                            datos = json.loads(ruta_stock.read_text(encoding="utf-8"))
                            actualizar_datos("stock", datos)
                        except (json.JSONDecodeError, OSError):
                            pass
                
                # Esperar hasta el próximo intervalo
                espera = intervalo_s - (time.time() - ahora)
                if espera > 0:
                    time.sleep(min(espera, 1))  # Chequear cancelación cada segundo
                    
            except Exception as e:
                print(f"  Error en worker realtime: {e}")
                time.sleep(5)
    
    with _WORKER_CANDACO:
        if not _WORKER_VIVO:
            _WORKER_VIVO = True
            thread = threading.Thread(target=worker, daemon=True, name="realtime-worker")
            thread.start()
            print("✓ Worker de tiempo real iniciado")


def detener_worker_tiempo_real() -> None:
    """Detiene el worker de tiempo real."""
    global _WORKER_VIVO
    with _WORKER_CANDACO:
        _WORKER_VIVO = False


# Typo corregido: candado
_SUSCRIPTORES_CANDADO = threading.Lock()
_CACHE_CANDADO = threading.Lock()
