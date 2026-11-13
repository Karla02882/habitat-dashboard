/**
 * CLIENTE REALTIME · Conexión WebSocket para actualizaciones en tiempo real
 * Se conecta automáticamente al servidor WebSocket y recibe actualizaciones instantáneas
 */

class ClienteRealtimeHabitat {
  constructor(urlServidor = "") {
    this.urlServidor = urlServidor || this._detectarUrlServidor();
    this.socket = null;
    this.conectado = false;
    this.canalesActivos = new Set();
    this.datosCacheados = {};
    this.callbacks = {
      "conexion": [],
      "desconexion": [],
      "actualizacion": [],
      "error": [],
      "suscripcion": [],
    };
    this.ultimasActualizaciones = {}; // {canal: timestamp}
    this._conectarAutomatico();
  }

  _detectarUrlServidor() {
    const protocolo = window.location.protocol === "https:" ? "https:" : "http:";
    const host = window.location.hostname;
    const puerto = window.location.port ? `:${window.location.port}` : "";
    return `${protocolo}//${host}${puerto}`;
  }

  _conectarAutomatico() {
    if (typeof io === "undefined") {
      console.warn("[Realtime] Socket.IO no disponible. Descargas fallidas silenciosas.");
      return;
    }

    try {
      this.socket = io(this.urlServidor, {
        reconnection: true,
        reconnectionDelay: 1000,
        reconnectionDelayMax: 5000,
        reconnectionAttempts: 5,
      });

      this._configurarEventos();
    } catch (error) {
      console.error("[Realtime] Error conectando:", error);
    }
  }

  _configurarEventos() {
    this.socket.on("connect", () => {
      this.conectado = true;
      console.log("[Realtime] ✓ Conectado al servidor en tiempo real");
      this._emitirCallback("conexion", { conectado: true });
      this._resucririrCanales();
    });

    this.socket.on("disconnect", () => {
      this.conectado = false;
      console.log("[Realtime] ✗ Desconectado del servidor");
      this._emitirCallback("desconexion", { reconectando: true });
    });

    this.socket.on("conexion", (data) => {
      console.log("[Realtime] Conexión confirmada:", data);
      this._emitirCallback("conexion", data);
    });

    this.socket.on("actualizacion", (data) => {
      const { canal, datos, timestamp } = data;
      this.datosCacheados[canal] = datos;
      this.ultimasActualizaciones[canal] = timestamp;
      console.log(`[Realtime] 📊 Actualización en ${canal}`);
      this._emitirCallback("actualizacion", { canal, datos, timestamp });
      this._notificarQueCambió(canal, datos);
    });

    this.socket.on("suscripcion", (data) => {
      console.log(`[Realtime] Suscripción: ${data.canal} - ${data.status}`);
      this._emitirCallback("suscripcion", data);
    });

    this.socket.on("estado", (estado) => {
      console.log("[Realtime] Estado del servidor:", estado);
      this._emitirCallback("estado", estado);
    });

    this.socket.on("error", (data) => {
      console.error("[Realtime] Error del servidor:", data);
      this._emitirCallback("error", data);
    });
  }

  _resucririrCanales() {
    // Re-suscribirse a todos los canales activos después de reconexión
    for (const canal of this.canalesActivos) {
      this.suscribir(canal);
    }
  }

  suscribir(canal, callback = null) {
    if (!this.conectado) {
      console.warn(`[Realtime] No conectado. Reintentando suscripción a ${canal}...`);
      setTimeout(() => this.suscribir(canal, callback), 2000);
      return;
    }

    this.canalesActivos.add(canal);
    if (callback) {
      this.on("actualizacion-" + canal, callback);
    }

    this.socket.emit("suscribir", {
      canal: canal,
      desde: this.ultimasActualizaciones[canal] || 0,
    });

    console.log(`[Realtime] Suscrito a: ${canal}`);
  }

  desuscribir(canal) {
    this.canalesActivos.delete(canal);
    this.socket.emit("desuscribir", { canal });
    console.log(`[Realtime] Desuscrito de: ${canal}`);
  }

  obtenerDatos(canal) {
    return this.datosCacheados[canal] || null;
  }

  // Listener pattern
  on(evento, callback) {
    if (!this.callbacks[evento]) {
      this.callbacks[evento] = [];
    }
    this.callbacks[evento].push(callback);
  }

  off(evento, callback) {
    if (this.callbacks[evento]) {
      this.callbacks[evento] = this.callbacks[evento].filter((c) => c !== callback);
    }
  }

  _emitirCallback(evento, datos) {
    const callbacks = this.callbacks[evento] || [];
    callbacks.forEach((cb) => {
      try {
        cb(datos);
      } catch (error) {
        console.error(`[Realtime] Error en callback de ${evento}:`, error);
      }
    });
  }

  _notificarQueCambió(canal, datos) {
    // Notificar a listeners específicos del canal
    const evento = "actualizacion-" + canal;
    this._emitirCallback(evento, datos);
  }

  obtenerEstado() {
    if (!this.conectado) {
      return null;
    }
    this.socket.emit("estado");
  }

  desconectar() {
    if (this.socket) {
      this.socket.disconnect();
    }
  }

  reconectar() {
    if (this.socket) {
      this.socket.connect();
    }
  }
}

// Crear instancia global (disponible como window.REALTIME)
window.REALTIME = new ClienteRealtimeHabitat();

console.log("✓ Cliente Realtime Habitat cargado");
