# 📋 Guía de Integración - Paso a Paso

Este archivo guía la integración del sistema de tiempo real con el servidor existente.

## Paso 1: Verificar Requirements (✅ HECHO)

Ya está actualizado en `requirements.txt` con:
- flask==3.0.0
- flask-socketio==5.3.5
- python-socketio==5.10.0
- python-engineio==4.8.0

## Paso 2: Integrar en servidor.py

Se necesita agregar AL FINAL de `servidor.py`, después de crear el ThreadingHTTPServer:

```python
# ===== INICIO: Integración Tiempo Real =====

def _iniciar_tiempo_real() -> None:
    """Inicia el sistema de WebSocket para actualizaciones en tiempo real."""
    try:
        from src import websocket_server
        websocket_server.iniciar_tiempo_real(puerto_ws=5000)
    except ImportError:
        print("  Advertencia: Módulos de realtime no disponibles")
    except Exception as e:
        print(f"  Error iniciando tiempo real: {e}")

# Agregar después de que el servidor HTTP esté listo
threading.Thread(target=_iniciar_tiempo_real, daemon=True).start()

# ===== FIN: Integración Tiempo Real =====
```

## Paso 3: Modificar generar_tablero.py

**Ubicación**: `scripts/generar_tablero.py`

**Agregar estas líneas después de publicar el tablero**:

```python
# Al inicio del archivo, con otros imports:
from src import realtime

# Dentro de la función _main() o _publica(), después de publicar tablero_datos.json:
try:
    realtime.actualizar_datos("tablero", datos_tablero, forzar=True)
except Exception:
    pass  # Si falla, no rompe la generación del tablero
```

## Paso 4: Actualizar cockpit.html

**Ubicación**: `design/cockpit.html`

**Agregar estas líneas en la sección `<head>`**:

```html
<!-- WebSocket para actualizaciones en tiempo real -->
<script src="https://cdn.socket.io/4.7.2/socket.io.js"></script>
<script src="/design/realtime.js"></script>
```

## Paso 5: Modificar cockpit.js (o equivalente)

**Ubicación**: `design/cockpit.js`

**Reemplazar o agregar**:

```javascript
// Suscribirse a actualizaciones del tablero en tiempo real
if (window.REALTIME) {
  REALTIME.suscribir("tablero", function(datos) {
    console.log("📊 Datos actualizados en tiempo real");
    // Aquí va la lógica para actualizar el dashboard
    REGISTRO.refrescar_datos(datos);
  });

  // Escuchar eventos de conexión
  REALTIME.on("conexion", function(data) {
    console.log("✓ Conectado a servidor realtime");
    // Mostrar indicador de conexión en UI
  });

  REALTIME.on("desconexion", function(data) {
    console.log("✗ Desconectado de servidor realtime");
    // Mostrar aviso de reconexión
  });
}
```

## Paso 6: Crear función de actualización incremental (OPCIONAL)

Si quieres actualizar solo lo que cambió (más eficiente):

```python
# En src/generar_tablero.py

def _enviar_actualizacion_realtime(datos_nuevos, datos_anterior):
    """Envía solo los cambios (delta) en tiempo real."""
    from src import realtime
    
    # Implementar lógica delta si es complejo
    # Para simplificar, enviar todo
    realtime.actualizar_datos("tablero", datos_nuevos)
```

## Paso 7: Testing

### Test en Local

```bash
# Terminal 1: Iniciar servidor
python scripts/servidor.py

# Terminal 2: Verificar que WebSocket escucha
netstat -an | grep 5000

# Terminal 3: Probar conexión
python -c "
from src import websocket_server
print('WebSocket disponible:', websocket_server.SOCKETIO_DISPONIBLE)
"
```

### Test en Navegador

1. Abrir DevTools (F12)
2. Console tab
3. Ver que aparezca: "✓ Cliente Realtime Habitat cargado"
4. Ver logs: "[Realtime] ✓ Conectado al servidor en tiempo real"

### Test Funcional

1. Abrir dashboard: http://localhost:8777
2. Ir a DevTools → Console
3. Ejecutar:
```javascript
REALTIME.suscribir("tablero", (datos) => {
  console.log("Datos recibidos:", Object.keys(datos));
});
```

4. Modificar un archivo de datos y debería actualizar automáticamente

## Paso 8: Deployment a Render

El archivo `render.yaml` **NO necesita cambios** porque:
- ✅ Solo hay un start command (servidor.py se encarga de todo)
- ✅ Flask-SocketIO se integra automáticamente
- ✅ Puerto 5000 está disponible en Render

Cambios en `.env` (si quieres):

```bash
# Port (asignado automáticamente por Render)
PORT=8777

# WebSocket (usa puerto automático si no se especifica)
WEBSOCKET_PUERTO=5000

# Refrescco del tablero cada 30 minutos (opcional reducir)
TABLERO_REFRESCO_MIN=30
```

## Paso 9: Monitoreo en Producción

Ver logs de Render:

```bash
# Ver últimas líneas
render logs

# Ver logs en tiempo real
render logs -f
```

Buscar:
- "✓ Sistema de tiempo real inicializado" = OK
- "Tiempo real deshabilitado" = Falta alguna dependencia
- "[WS] Cliente conectado" = Alguien se conectó

## Rollback (si algo falla)

Si por algún motivo necesitas deshabilitar realtime sin modificar código:

```bash
# En .env o en Render env vars
REALTIME_DESHABILITADO=1

# En servidor.py
if os.getenv("REALTIME_DESHABILITADO"):
    print("  Tiempo real deshabilitado por config")
else:
    _iniciar_tiempo_real()
```

## Checklist Final

- [ ] requirements.txt actualizado
- [ ] src/realtime.py creado
- [ ] src/websocket_server.py creado
- [ ] design/realtime.js creado
- [ ] servidor.py: integración en inicio
- [ ] scripts/generar_tablero.py: llamadas a realtime.actualizar_datos()
- [ ] design/cockpit.html: <script src="realtime.js">
- [ ] design/cockpit.js: REALTIME.suscribir() callbacks
- [ ] Testear en local
- [ ] Testear en Render
- [ ] Monitor funcionamiento

## Preguntas Frecuentes

**P: ¿Se rompe el polling antiguo?**
R: No. Si WebSocket falla, se puede mantener polling como fallback.

**P: ¿Qué pasa si hay múltiples instancias en Render?**
R: WebSocket actual funciona en 1 instancia. Para varias, necesitarías Redis como message broker.

**P: ¿Afecta el consumo de memoria?**
R: Mínimamente. Cada conexión usa ~50-100 KB. 100 clientes = ~5-10 MB.

**P: ¿Cuál es la latencia?**
R: Típicamente 50-200ms entre cambio en servidor y UI actualizada (vs 5-30 minutos antes).

**P: ¿Se puede desactivar por user/rol?**
R: Sí, agregando lógica en `websocket_server.py` handlers.

---

**Preguntas? Revisar REALTIME_README.md para más detalles técnicos.**
