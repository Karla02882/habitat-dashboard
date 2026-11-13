"""WEBSOCKET · Servidor de conexiones WebSocket en tiempo real para el dashboard."""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

try:
    from flask import Flask, request, render_template_string
    from flask_socketio import SocketIO, emit, join_room, leave_room, rooms
    SOCKETIO_DISPONIBLE = True
except ImportError:
    SOCKETIO_DISPONIBLE = False
    print("Advertencia: flask-socketio no disponible; tiempo real deshabilitado")

from . import realtime

RAIZ = Path(__file__).resolve().parent.parent


class ServidorTiempoReal:
    """Servidor WebSocket integrado para actualizaciones en tiempo real."""
    
    def __init__(self, puerto_websocket: int = 5000, debug: bool = False):
        """Inicializa el servidor WebSocket.
        
        Args:
            puerto_websocket: puerto para WebSocket (puede ser el mismo que HTTP si se configura CORS)
            debug: modo debug
        """
        self.puerto = puerto_websocket
        self.debug = debug
        self.app: Flask | None = None
        self.socketio: SocketIO | None = None
        self._corriendo = False
        self._candado = threading.Lock()
        self._clientes_conectados: dict[str, dict] = {}  # {sid: {canal: timestamp}}
        
    def inicializar(self) -> bool:
        """Configura la app Flask y SocketIO. Retorna True si tuvo éxito."""
        if not SOCKETIO_DISPONIBLE:
            return False
        
        try:
            self.app = Flask("habitat-realtime")
            self.socketio = SocketIO(
                self.app,
                cors_allowed_origins="*",
                async_mode="threading",
                ping_timeout=60,
                ping_interval=25,
            )
            self._configurar_handlers()
            return True
        except Exception as e:
            print(f"  Error inicializando WebSocket: {e}")
            return False
    
    def _configurar_handlers(self) -> None:
        """Configura los handlers de SocketIO."""
        @self.socketio.on("connect")
        def handle_connect():
            sid = request.sid
            with self._candado:
                self._clientes_conectados[sid] = {}
            print(f"  [WS] Cliente conectado: {sid}")
            emit("conexion", {
                "status": "conectado",
                "tiempo_servidor": time.time(),
                "mensaje": "Conectado a actualizaciones en tiempo real"
            })
        
        @self.socketio.on("disconnect")
        def handle_disconnect():
            sid = request.sid
            with self._candaco:
                self._clientes_conectados.pop(sid, None)
            print(f"  [WS] Cliente desconectado: {sid}")
        
        @self.socketio.on("suscribir")
        def handle_suscribir(data):
            """Suscribir a un canal de datos.
            
            Espera: {"canal": "tablero", "desde": timestamp_opcional}
            """
            sid = request.sid
            canal = data.get("canal", "")
            desde = data.get("desde", 0)
            
            if canal not in realtime._CACHE_DATOS:
                emit("error", {"mensaje": f"Canal no válido: {canal}"})
                return
            
            # Registrar suscripción
            with self._candaco:
                if sid not in self._clientes_conectados:
                    self._clientes_conectados[sid] = {}
                self._clientes_conectados[sid][canal] = desde
            
            # Enviar datos actuales
            resultado = realtime.obtener_datos(canal)
            if resultado:
                datos, timestamp = resultado
                emit("actualizacion", {
                    "canal": canal,
                    "datos": datos,
                    "timestamp": timestamp,
                })
            
            emit("suscripcion", {
                "canal": canal,
                "status": "suscrito",
                "mensaje": f"Suscrito a {canal}"
            })
            print(f"  [WS] Cliente {sid} suscrito a {canal}")
        
        @self.socketio.on("desuscribir")
        def handle_desuscribir(data):
            """Desuscribirse de un canal."""
            sid = request.sid
            canal = data.get("canal", "")
            
            with self._candaco:
                if sid in self._clientes_conectados:
                    self._clientes_conectados[sid].pop(canal, None)
            
            emit("suscripcion", {
                "canal": canal,
                "status": "desuscrito"
            })
        
        @self.socketio.on("estado")
        def handle_estado():
            """Obtiene el estado actual de todos los canales."""
            estado = realtime.obtener_estado_cache()
            emit("estado", estado)
        
        # Registrar callback de realtime para notificaciones
        def notificar_cambio(canal: str, datos):
            with self._candaco:
                for sid, canales in self._clientes_conectados.items():
                    if canal in canales:
                        self.socketio.emit(
                            "actualizacion",
                            {
                                "canal": canal,
                                "datos": datos,
                                "timestamp": time.time(),
                            },
                            room=sid,
                            skip_sid=None
                        )
        
        # Registrar el callback para todos los canales
        for canal in realtime._CACHE_DATOS:
            realtime.registrar_suscriptor(canal, notificar_cambio)
    
    def iniciar(self) -> bool:
        """Inicia el servidor WebSocket en background.
        
        Returns:
            True si se inició correctamente
        """
        if not self.inicializar():
            return False
        
        def run_server():
            try:
                print(f"  Iniciando servidor WebSocket en puerto {self.puerto}...")
                self.socketio.run(
                    self.app,
                    host="0.0.0.0",
                    port=self.puerto,
                    debug=self.debug,
                    use_reloader=False,
                    allow_unsafe_werkzeug=True,
                )
            except Exception as e:
                print(f"  Error en servidor WebSocket: {e}")
        
        with self._candaco:
            if self._corriendo:
                return True
            
            self._corriendo = True
            thread = threading.Thread(target=run_server, daemon=True, name="websocket-server")
            thread.start()
            time.sleep(2)  # Esperar a que arrange
            return True
    
    def detener(self) -> None:
        """Detiene el servidor WebSocket."""
        with self._candaco:
            self._corriendo = False
        if self.socketio:
            self.socketio.stop()


# Instancia global del servidor
_SERVIDOR: ServidorTiempoReal | None = None
_SERVIDOR_CANDADO = threading.Lock()


def obtener_servidor() -> ServidorTiempoReal:
    """Obtiene o crea la instancia global del servidor WebSocket."""
    global _SERVIDOR
    if _SERVIDOR is None:
        puerto = int(os.getenv("WEBSOCKET_PUERTO") or "5000")
        with _SERVIDOR_CANDADO:
            if _SERVIDOR is None:
                _SERVIDOR = ServidorTiempoReal(puerto)
    return _SERVIDOR


def iniciar_tiempo_real(puerto_ws: int = 5000) -> bool:
    """Inicia tanto el worker de realtime como el servidor WebSocket."""
    if not SOCKETIO_DISPONIBLE:
        print("  Tiempo real deshabilitado: flask-socketio no está instalado")
        return False
    
    try:
        # Iniciar worker que lee cambios en archivos
        realtime.iniciar_worker_tiempo_real(intervalo_s=5)
        
        # Iniciar servidor WebSocket
        servidor = obtener_servidor()
        if servidor.iniciar():
            print("✓ Sistema de tiempo real inicializado")
            return True
        else:
            print("✗ No se pudo iniciar tiempo real")
            return False
    except Exception as e:
        print(f"  Error iniciando tiempo real: {e}")
        return False


def detener_tiempo_real() -> None:
    """Detiene tiempo real y WebSocket."""
    realtime.detener_worker_tiempo_real()
    if _SERVIDOR:
        _SERVIDOR.detener()
