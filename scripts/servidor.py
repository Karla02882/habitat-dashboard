"""EL SERVIDOR DEL TABLERO."""
from __future__ import annotations

import base64
import gzip
import hashlib
import hmac
import json
import os
import posixpath
import shutil
import subprocess
import sys
import re
import threading
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from src import reloj  # noqa: E402
load_dotenv(RAIZ / ".env")

if sys.stdout is None or sys.stderr is None:
    _log = RAIZ / "data" / "cockpit.log"
    _log.parent.mkdir(parents=True, exist_ok=True)
    sys.stdout = sys.stderr = open(_log, "a", encoding="utf-8", buffering=1)
    print(f"\n===== cockpit arrancado {reloj.sello()} =====")
else:
    sys.stdout.reconfigure(line_buffering=True)

PUERTO = int(os.getenv("TABLERO_PUERTO") or os.getenv("PORT") or 8777)

EN_LA_NUBE = bool(os.getenv("RENDER") or (os.getenv("PORT") and not os.getenv("TABLERO_PUERTO")))

_defecto_interfaz = "0.0.0.0" if EN_LA_NUBE else "127.0.0.1"  # noqa: S104

def _carpeta_datos() -> Path:
    v = (os.getenv("TABLERO_DATOS_DIR") or "").strip()
    if v:
        return Path(v)
    if EN_LA_NUBE and Path("/var/data").is_dir():
        return Path("/var/data")
    return RAIZ


def RUTA_DATOS() -> Path:
    """El `tablero_datos.json` vigente. Funcion y no constante: si el disco."""
    return _carpeta_datos() / "tablero_datos.json"
INTERFAZ = (os.getenv("TABLERO_INTERFAZ") or _defecto_interfaz).strip() or _defecto_interfaz
ESCUCHA_SOLO_LOCAL = INTERFAZ in ("127.0.0.1", "localhost", "::1")


def RUTA_STOCK() -> Path:  # noqa: N802 — va con RUTA_DATOS
    """El archivo del personal externo, al lado del grande."""
    return _carpeta_datos() / "stock_datos.json"


def RUTA_FINANZAS() -> Path:  # noqa: N802 — va con RUTA_DATOS
    """El archivo de la cuenta de Finanzas (el contador externo), al lado del."""
    return _carpeta_datos() / "finanzas_datos.json"


def RUTA_OBRAS() -> Path:  # noqa: N802 — va con RUTA_DATOS
    """El archivo de la cuenta del equipo de obras, al lado del grande. Lo."""
    return _carpeta_datos() / "obras_datos.json"


def RUTA_VENTAS() -> Path:  # noqa: N802 — va con RUTA_DATOS
    return _carpeta_datos() / "ventas_datos.json"


def RUTA_CLIENTES() -> Path:  # noqa: N802 — va con RUTA_DATOS
    """Los clientes de Kommo CON nombre y teléfono."""
    c = _carpeta_datos()
    if c.resolve() == RAIZ.resolve():
        c = RAIZ / "data"
    return c / "clientes_kommo.json"

def RUTA_CAMBIOS() -> Path:  # noqa: N802 — va con RUTA_DATOS
    return RUTA_CLIENTES().parent / "cambios_inventario.json"


def RUTA_STOCK_VIVO() -> Path:  # noqa: N802 — va con RUTA_DATOS
    return RUTA_CLIENTES().parent / "stock_vivo.json"


def RUTA_MOROSOS() -> Path:  # noqa: N802 — va con RUTA_DATOS
    """Los morosos de AXION CON nombre y teléfono."""
    return RUTA_CLIENTES().parent / "morosos.json"


def RUTA_COMENTARIOS() -> Path:  # noqa: N802
    return RUTA_CLIENTES().parent / "morosos_comentarios.json"


ROLES_MOROSOS = ("admin", "habitat", "comercial")
ROLES_COMENTAN = ("admin", "comercial")
_COMENTARIOS_CANDADO = threading.Lock()
COMENTARIO_MAX = 1000


def RUTA_INFORMES() -> Path:  # noqa: N802
    return RUTA_CLIENTES().parent / "informes_quincenales.json"


ROLES_INFORMES = ("admin", "habitat", "comercial")
INFORME_AREAS = ("ventas", "marketing", "administracion", "obras", "logistica", "oficina")
INFORME_AREAS_PROYECTO = ("obras",)
INFORME_PROYECTO_MAX = 120
INFORME_CAMPOS = ("de", "objetivos", "actividades", "tareas", "observaciones", "recomendaciones")
INFORME_CAMPO_MAX = 6000
INFORME_IMG_MAX_N = 10                 # por informe
INFORME_IMG_MAX_BYTES = 800_000
INFORME_IMG_CUERPO_MAX = 1_300_000     # lo que se lee de un POST de imagen
_INFORME_IMG_ID = re.compile(r"[0-9a-f]{24}\.(?:jpg|png)")
_INFORMES_CANDADO = threading.Lock()


def RUTA_INFORMES_IMAGENES() -> Path:  # noqa: N802 — va con RUTA_INFORMES
    return RUTA_INFORMES().parent / "informes_imagenes"


def _periodo_valido(q: str) -> bool:
    return bool(re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", q))


def _clave_informe(area: str, proyecto: str, q: str) -> str:
    return f"{area}:{proyecto}|{q}" if area in INFORME_AREAS_PROYECTO else f"{area}|{q}"


def usuario_dueno() -> str:
    u = (os.getenv("TABLERO_USUARIO") or "").strip()
    return u if u and (os.getenv("TABLERO_CLAVE") or "").strip() else ""

ROL_ADMIN = "admin"
ROL_HABITAT = "habitat"
ROL_COMERCIAL = "comercial"
ROL_EXTERNO = "externo"
ROL_FINANZAS = "finanzas"
ROL_OBRAS = "obras"
ROL_VENTAS = "ventas"

HOJAS_VEDADAS = {
    ROL_HABITAT: ["estado", "clientes"],
    ROL_ADMIN: [],
    ROL_COMERCIAL: ["hoy", "caja", "gasto-d", "obras-d", "compras", "cabidas",
                    "contasis",
                    "ratios-axion", "comparativo",
                    "estado",
                    "bitacora", "contratos", "cotizaciones", "atencion",
                    "cronogramas", "clientes",
                    "resultados", "scorecard", "ventas", "cobranza", "comercial",
                    "obra", "logistica", "finanzas",
                    "rentabilidad", "gastos"],
}

SOLO_VE = {
    ROL_EXTERNO: ["stock"],
    # las seis subhojas del grupo Finanzas de `cockpit.js`, en su orden
    ROL_FINANZAS: ["caja", "gasto-d", "compras", "contasis", "ratios-axion", "comparativo"],
    # las siete subhojas del grupo Obras de `cockpit.js`, en su orden
    ROL_OBRAS: ["obras-d", "cabidas", "bitacora", "contratos", "cotizaciones", "atencion",
                "cronogramas"],
    ROL_VENTAS: ["comercial-d", "asesores", "crm", "crm-informe", "marketing", "stock"],
}

_HOJAS_CACHE: dict = {}
_HOJAS_CANDADO = threading.Lock()
HOJAS_MINIMO = ["hoy", "caja", "comercial-d", "gasto-d", "obras-d", "compras", "contasis",
                "ratios-axion", "comparativo",
                "ventas-kpi", "asesores", "crm", "crm-informe", "informe-quincenal", "marketing",
                "cabidas", "bitacora", "contratos", "cotizaciones", "atencion",
                "cronogramas", "stock", "cambios-stock", "clientes", "morosos", "estado"]


def hojas_del_paquete() -> list:
    """Los ids que `design/cockpit.html` registra hoy."""
    f = RAIZ / "design" / "cockpit.html"
    try:
        st = f.stat()
        clave = (st.st_size, int(st.st_mtime))
    except OSError:
        return list(HOJAS_MINIMO)
    with _HOJAS_CANDADO:
        if _HOJAS_CACHE.get("clave") == clave:
            return list(_HOJAS_CACHE["ids"])
    try:
        txt = f.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return list(HOJAS_MINIMO)
    ids = re.findall(r'REGISTRO\["([a-z0-9-]+)"\]', txt)
    vistos = []
    for x in ids:
        if x not in vistos:
            vistos.append(x)
    if not vistos:
        return list(HOJAS_MINIMO)
    with _HOJAS_CANDADO:
        _HOJAS_CACHE["clave"] = clave
        _HOJAS_CACHE["ids"] = list(vistos)
    return vistos


def hojas_vedadas(rol: str, todas: list) -> list:
    """Qué NO ve este rol, mire por lista blanca o por lista de vedadas."""
    blanca = SOLO_VE.get(rol)
    if blanca is not None:
        return sorted(set(todas) - set(blanca))
    return HOJAS_VEDADAS.get(rol, [])

HOJA_DE_ENTRADA = {ROL_EXTERNO: "stock", ROL_VENTAS: "comercial-d"}


INTENTOS_TOPE = 5
ESPERA_TOPE_S = 8.0

SESION_DIAS = 7
_SECRETO: list = [b""]
_LOGO_B64: list = [""]


def _secreto_de(cuentas) -> bytes:
    v = (os.getenv("TABLERO_SECRETO") or "").strip()
    if v:
        return v.encode("utf-8")
    base = "|".join(f"{u}:{c}:{r}" for u, c, r in cuentas)
    return hashlib.sha256(("habitat-cockpit|" + base).encode("utf-8")).digest()


def _firmar(usuario: str, vence: int) -> str:
    return hmac.new(_SECRETO[0], f"{usuario}|{vence}".encode("utf-8"),
                    hashlib.sha256).hexdigest()


def _cookie_nueva(usuario: str) -> str:
    vence = int(time.time()) + SESION_DIAS * 86400
    u = base64.urlsafe_b64encode(usuario.encode("utf-8")).decode().rstrip("=")
    return f"{u}.{vence}.{_firmar(usuario, vence)}"


def _usuario_de_cookie(valor: str) -> str | None:
    """El usuario que firma esta cookie, o None si no vale. Falla cerrado."""
    try:
        u64, vence_s, firma = valor.split(".")
        vence = int(vence_s)
        if vence < time.time():
            return None
        relleno = "=" * (-len(u64) % 4)
        usuario = base64.urlsafe_b64decode(u64 + relleno).decode("utf-8")
    except Exception:  # noqa: BLE001 — cookie rota = no pasa
        return None
    if not _igual(firma, _firmar(usuario, vence)):
        return None
    return usuario


def _pagina_acceso(error: str = "", usuario: str = "") -> bytes:
    """`design/acceso.html` con sus tres marcas reemplazadas. Se lee del."""
    plantilla = (RAIZ / "design" / "acceso.html").read_text(encoding="utf-8")
    if not _LOGO_B64[0]:
        f = RAIZ / "assets" / "logo-white.png"
        _LOGO_B64[0] = base64.b64encode(f.read_bytes()).decode() if f.exists() else ""
    bloque = ""
    if error:
        bloque = ('<div class="error" role="alert"><span>&#9888;</span>'
                  f"<span><b>{error}</b></span></div>")
    seguro = (usuario.replace("&", "&amp;").replace("<", "&lt;")
              .replace('"', "&quot;"))
    return (plantilla.replace("__LOGO__", _LOGO_B64[0])
                     .replace("__ERROR__", bloque)
                     .replace("__USUARIO__", seguro)).encode("utf-8")
def _igual(a: str, b: str) -> bool:
    """¿Son la misma cadena? En tiempo constante, y con CUALQUIER carácter."""
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


_FALLOS: dict = {}
_FALLOS_LOCK = threading.Lock()


def _castigo(ip: str) -> float:
    """Cuántos segundos se demora la respuesta a esta IP por sus fallos."""
    with _FALLOS_LOCK:
        n = _FALLOS.get(ip, 0)
    if n < INTENTOS_TOPE:
        return 0.0
    return min(ESPERA_TOPE_S, 0.5 * (2 ** (n - INTENTOS_TOPE)))


def _anotar_fallo(ip: str) -> None:
    with _FALLOS_LOCK:
        _FALLOS[ip] = _FALLOS.get(ip, 0) + 1


def _limpiar_fallos(ip: str) -> None:
    """Una entrada buena borra la cuenta: el castigo es para quien falla."""
    with _FALLOS_LOCK:
        _FALLOS.pop(ip, None)

RAIZ_PERMITIDA = frozenset({
    "/tablero.html",            # el entregable anterior, sigue vivo
    "/tablero_datos.json",      # la data y la sonda de recarga (HEAD)
    "/tablero_revision.html",
    "/data/crm_leads.json",
})
PWA_PUBLICA = {
    "/manifest.webmanifest": ("manifest.webmanifest", "application/manifest+json; charset=utf-8"),
    "/sw.js": ("sw.js", "text/javascript; charset=utf-8"),
    "/sin-conexion.html": ("sin-conexion.html", "text/html; charset=utf-8"),
    "/icono-192.png": ("icono-192.png", "image/png"),
    "/icono-512.png": ("icono-512.png", "image/png"),
    "/icono-maskable-512.png": ("icono-maskable-512.png", "image/png"),
    "/apple-touch-icon.png": ("apple-touch-icon.png", "image/png"),
}

CARPETAS_PERMITIDAS = {
    "/design/": (".html", ".css", ".js"),
    "/assets/": (".css", ".js", ".png", ".jpg", ".jpeg", ".svg", ".webp",
                 ".ico"),
}

_r = os.getenv("TABLERO_REFRESCO_MIN")
REFRESCO_MIN = 0 if (_r or "").strip() in ("0", "off", "no") else max(5, int(_r or 30))


_s = os.getenv("TABLERO_STOCK_MIN")
STOCK_REFRESCO_MIN = 0 if (_s or "").strip() in ("0", "off", "no") else max(2, int(_s or 5))


_REGENERANDO = threading.Lock()
_CICLO = threading.Lock()

_INICIO: list = [None]

SIN_VENTANA = getattr(subprocess, "CREATE_NO_WINDOW", 0)

PRIORIDAD_BAJA = getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0)


_VERSION_VIVA = {"t": 0.0, "v": ""}


def version_viva() -> str:
    ahora = time.time()
    if _VERSION_VIVA["t"] and ahora - _VERSION_VIVA["t"] < 60:
        return _VERSION_VIVA["v"]

    def git(*args: str) -> str:
        try:
            r = subprocess.run(["git", *args], cwd=str(RAIZ), text=True,
                               capture_output=True, timeout=10,
                               creationflags=SIN_VENTANA)
            return r.stdout.strip() if r.returncode == 0 else ""
        except Exception:  # noqa: BLE001
            return ""

    h = git("log", "-1", "--format=%h")
    if h:
        f = git("log", "-1", "--format=%cd", "--date=format:%Y-%m-%d")
        n = ("" if git("rev-parse", "--is-shallow-repository") == "true"
             else git("rev-list", "--count", "HEAD"))
        v = (f"v{n} · " if n else "") + h + (f" · {f}" if f else "")
    else:
        rc = (os.getenv("RENDER_GIT_COMMIT") or "").strip()
        v = rc[:7]
    _VERSION_VIVA.update(t=ahora, v=v)
    return v
_NICE = None if sys.platform.startswith("win") else shutil.which("nice")


def _de_fondo(argv: list) -> list:
    """El mismo comando, pidiendo prioridad baja donde el sistema deje."""
    return [_NICE, "-n", "19", *argv] if _NICE else list(argv)

PY = RAIZ / "venv" / "Scripts" / "pythonw.exe"
if not PY.exists():
    PY = RAIZ / "venv" / "Scripts" / "python.exe"
if not PY.exists():
    PY = Path(sys.executable)


_ULT_ERROR: list = [None]


_EXPORTANDO = threading.Lock()


def _correr_exportador(script: str, que: str, plazo: int = 1200) -> None:
    """Corre un exportador de `scripts/`. Si falla, queda el archivo anterior."""
    try:
        k = subprocess.run(
            _de_fondo([str(PY), "-X", "utf8", str(RAIZ / "scripts" / script)]),
            cwd=str(RAIZ), capture_output=True, text=True, timeout=plazo,
            creationflags=SIN_VENTANA | PRIORIDAD_BAJA)
        if k.returncode != 0:
            cola = (k.stdout or k.stderr or "").strip().splitlines()
            print(f"  {que} no se renovó (queda el archivo anterior): "
                  f"{cola[-1][:150] if cola else '(sin mensaje)'}")
    except Exception as e:  # noqa: BLE001 — un exportador nunca tumba el servidor
        print(f"  {que} no se renovó ({type(e).__name__}); queda el archivo anterior")


def _exportar_personas() -> None:
    """Las dos listas con datos de personas: los clientes de Kommo (hoja."""
    if not _EXPORTANDO.acquire(blocking=False):
        return
    try:
        _correr_exportador("exportar_clientes.py", "la lista de clientes")
        _correr_exportador("exportar_morosos.py", "la lista de morosos")
        _correr_exportador("exportar_stock_vivo.py", "el stock en vivo", plazo=300)
        if not EN_LA_NUBE:
            _correr_exportador("exportar_crm_detalle.py", "los nombres del CRM")
    finally:
        _EXPORTANDO.release()


def _refrescar_stock_cada_tanto() -> None:
    """Lee el stock cada `STOCK_REFRESCO_MIN` minutos, aparte del tablero."""
    time.sleep(30)                      # que el arranque termine primero
    while True:
        t0 = time.monotonic()
        try:
            if not (_REGENERANDO.locked() or _CICLO.locked()):
                if _EXPORTANDO.acquire(blocking=False):
                    try:
                        _correr_exportador("exportar_stock_vivo.py", "el stock en vivo", plazo=180)
                    finally:
                        _EXPORTANDO.release()
        except Exception as e:  # noqa: BLE001 — nunca tumba el servidor
            print(f"  stock en vivo: el ciclo falló ({type(e).__name__}: {e})")
        time.sleep(max(30.0, STOCK_REFRESCO_MIN * 60 - (time.monotonic() - t0)))


_VERIF_VECES: dict = {}
_VERIF_CANDADO = threading.Lock()
VERIF_POR_MINUTO = 20          # por cuenta
VERIF_GLOBAL_MINUTO = 120      # entre todas


def _verif_permitida(quien: str) -> bool:
    ahora = time.monotonic()
    with _VERIF_CANDADO:
        todas = [t for lista in _VERIF_VECES.values() for t in lista if ahora - t < 60]
        propias = [t for t in _VERIF_VECES.get(quien, []) if ahora - t < 60]
        if len(propias) >= VERIF_POR_MINUTO or len(todas) >= VERIF_GLOBAL_MINUTO:
            return False
        propias.append(ahora)
        _VERIF_VECES[quien] = propias
        for k in [k for k, v in _VERIF_VECES.items() if not v or ahora - max(v) >= 60]:
            if k != quien:
                _VERIF_VECES.pop(k, None)
        return True


def _hora_huancayo(iso: str) -> str:
    from datetime import datetime, timedelta
    try:
        return (datetime.fromisoformat(str(iso)[:26]) - timedelta(hours=5)).strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return ""


def _consultar_unidad(uid: str) -> dict:
    """La unidad `uid` tal como está AHORA en AXION, o {} si no existe."""
    import urllib.error
    import urllib.request
    from urllib.parse import urlencode
    base = (os.getenv("AXION_API_BASE_URL") or "").rstrip("/")
    token = (os.getenv("AXION_API_TOKEN") or "").strip()
    vieja = (os.getenv("AXION_API_KEY") or "").strip()
    if not base or not (token or vieja):
        raise RuntimeError("faltan las credenciales de AXION")
    cab = {"Content-Type": "application/json"}
    if token:
        cab["Authorization"] = "Bearer " + token
    else:
        cab["api_key"] = vieja
    params = urlencode({"limit": 1, "q": json.dumps({"id": uid})})

    def _pedir(raiz: str):
        req = urllib.request.Request(f"{raiz}/entities/Unit?{params}", headers=cab)
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode("utf-8"))

    try:
        filas = _pedir(base)
    except urllib.error.HTTPError as e:
        if e.code != 403:
            raise
        try:
            app_id = ((json.loads(e.read().decode("utf-8")) or {}).get("extra_data") or {}).get("app_id")
        except (ValueError, OSError):
            app_id = None
        if not app_id:
            raise
        filas = _pedir(f"https://app.base44.com/api/apps/{app_id}")
    if not isinstance(filas, list) or not filas:
        return {}
    return filas[0] if isinstance(filas[0], dict) else {}


def _regenerar_una_vez() -> bool:
    """Corre `generar_tablero.py` una vez y, si sale bien, COMPRUEBA QUE LAS."""
    if not _REGENERANDO.acquire(blocking=False):
        return False
    _INICIO[0] = time.time()
    publicado = [False]
    ciclo = [False]
    try:
        ciclo[0] = _CICLO.acquire(timeout=1800)
        r = subprocess.run(
            _de_fondo([str(PY), "-X", "utf8",
                       str(RAIZ / "scripts" / "generar_tablero.py")]),
            cwd=str(RAIZ), capture_output=True, text=True, timeout=2400,
            creationflags=SIN_VENTANA | PRIORIDAD_BAJA)
        if r.returncode != 0:
            txt = (r.stderr or r.stdout or "").strip()
            cola = txt.splitlines()[-40:]
            print(f"  la regeneración falló (código {r.returncode}) — "
                  f"traceback completo:")
            for linea in cola:
                print(f"    | {linea[:220]}")
            if not cola:
                print("    | (el proceso no escribió nada en stderr ni stdout)")
            _ULT_ERROR[0] = ("generar_tablero salió con código "
                             f"{r.returncode}: " + " · ".join(cola[-3:])[:400])
            return False
        _ULT_ERROR[0] = None
        publicado[0] = True
        return True
    except subprocess.TimeoutExpired as e:
        _ULT_ERROR[0] = (f"la corrida superó el tope de {e.timeout:.0f}s "
                         "y se mató; el payload anterior quedó sirviendo")
        print(f"  !! {_ULT_ERROR[0]}")
        return False
    except Exception as e:  # noqa: BLE001 — el refresco nunca tumba el servidor
        _ULT_ERROR[0] = f"{type(e).__name__}: {str(e)[:300]}"
        print(f"  !! la regeneración reventó: {_ULT_ERROR[0]}")
        return False
    finally:
        _INICIO[0] = None
        _REGENERANDO.release()
        threading.Thread(target=_despues_de_publicar, args=(publicado[0], ciclo[0]),
                         daemon=True).start()


_POSPUBLICAR = threading.Lock()


def _despues_de_publicar(publicado: bool, soltar_ciclo: bool = False) -> None:
    """Los pasos de después y, pase lo que pase en ellos, el fin del ciclo."""
    try:
        _despues_cuerpo(publicado)
    finally:
        if soltar_ciclo:
            _CICLO.release()


def _despues_cuerpo(publicado: bool) -> None:
    """LO QUE CORRE DESPUÉS DE PUBLICAR LA DATA, SIN HACER ESPERAR AL BOTÓN."""
    with _POSPUBLICAR:
        if publicado:
            try:
                a = subprocess.run(
                    _de_fondo([str(PY), "-X", "utf8",
                               str(RAIZ / "scripts" / "armar_cockpit.py")]),
                    cwd=str(RAIZ), capture_output=True, text=True, timeout=300,
                    creationflags=SIN_VENTANA | PRIORIDAD_BAJA)
                if a.returncode != 0:
                    cola = (a.stderr or a.stdout or "").strip().splitlines()
                    print(f"  el cockpit no se rearmó (la data sí se publicó): "
                          f"{cola[-1][:150] if cola else '(sin mensaje)'}")
            except Exception as e:  # noqa: BLE001
                print(f"  el cockpit no se rearmó ({type(e).__name__}); "
                      f"la data sí se publicó")
            try:
                v = subprocess.run(
                    _de_fondo([str(PY), "-X", "utf8",
                               str(RAIZ / "scripts" / "verificar.py")]),
                    cwd=str(RAIZ), capture_output=True, text=True, timeout=600,
                    creationflags=SIN_VENTANA | PRIORIDAD_BAJA)
                if v.returncode != 0:
                    print("  !! LA VERIFICACIÓN FALLÓ — el tablero se publicó igual:")
                    for linea in (v.stdout or "").strip().splitlines():
                        print(f"     {linea}")
            except Exception as e:  # noqa: BLE001 — un control nunca tumba el servidor
                print(f"  los controles no corrieron ({type(e).__name__})")
    _exportar_personas()


def _regenerar_cada_tanto() -> None:
    """Corre `generar_tablero.py` en bucle mientras el servidor viva."""
    while True:
        t0 = time.monotonic()
        inicio = reloj.sello("%H:%M")
        bien = _regenerar_una_vez()
        dur = time.monotonic() - t0
        espera = max(60, REFRESCO_MIN * 60 - dur) if bien else 300
        if bien:
            print(f"[{inicio}] tablero regenerado en {dur / 60:.1f} min; "
                  f"el próximo en {espera / 60:.0f} min")
        else:
            print(f"[{inicio}] no se regeneró (corrida en marcha o falla) — "
                  f"se sigue sirviendo el anterior; se reintenta en "
                  f"{espera / 60:.0f} min")
        fin = time.time() + espera
        while True:
            resta = fin - time.time()
            if resta <= 0:
                break
            antes = time.time()
            time.sleep(min(60, resta))
            salto = time.time() - antes
            if salto > 300:
                print(f"[{reloj.sello('%H:%M')}] la máquina estuvo suspendida "
                      f"~{salto / 60:.0f} min — se regenera ahora, sin esperar "
                      f"el turno")
                break


_CONTROLANDO = threading.Lock()
_CONTROL_INICIO: list = [None]
CONTROL_JSON = RAIZ / "data" / "control_final.json"
_c = os.getenv("CONTROLES_CADA_HORAS")
CONTROLES_CADA_HORAS = int(_c) if (_c or "").strip().isdigit() else 24


def _correr_controles_una_vez() -> None:
    """verificar.py + el barrido de pantallas, y el veredicto a disco."""
    if not _CONTROLANDO.acquire(blocking=False):
        return
    _CONTROL_INICIO[0] = time.time()
    try:
        CONTROL_JSON.parent.mkdir(exist_ok=True)

        def _correr(script):
            r = subprocess.run(
                _de_fondo([sys.executable, "-X", "utf8",
                           str(RAIZ / "scripts" / script)]),
                cwd=RAIZ, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=1800,
                creationflags=SIN_VENTANA | PRIORIDAD_BAJA)
            return r.returncode, (r.stdout or "") + (r.stderr or "")

        rc1, out1 = _correr("verificar.py")
        rc2, out2 = _correr("verificar_pantallas.py")
        sin_chrome = "no encuentro Chrome" in out2
        if rc1 == 0 and rc2 == 0:
            veredicto = "VERDE"
        elif rc1 == 0 and sin_chrome:
            veredicto = "VERDE PARCIAL"
        else:
            veredicto = "ROJO"
        detalle = []
        if rc1 != 0:
            detalle += [l.strip() for l in out1.splitlines()
                        if l.strip().startswith(chr(183))][:8]
        if rc2 != 0 and not sin_chrome:
            detalle += [l.strip() for l in out2.splitlines() if "!!" in l][:8]
        if sin_chrome:
            detalle.append(
                "el barrido de pantallas NO corrio en este servidor: no hay "
                "Chrome instalado. Corrieron los controles de codigo y datos, "
                "nada mas.")
        CONTROL_JSON.write_text(json.dumps({
            "veredicto": veredicto,
            "cuando": reloj.sello("%Y-%m-%d %H:%M:%S"),
            "duracion_min": round((time.time() - _CONTROL_INICIO[0]) / 60, 1),
            "detalle": detalle,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
    finally:
        _CONTROLANDO.release()


def _controlar_cada_tanto() -> None:
    time.sleep(600)
    while True:
        _correr_controles_una_vez()
        time.sleep(max(1, CONTROLES_CADA_HORAS) * 3600)


_GZ: dict = {}                    # {ruta: (tamaño, mtime, bytes comprimidos)}
_GZ_CANDADO = threading.Lock()

SIN_COMPRIMIR = frozenset({
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".avif",
    ".woff", ".woff2", ".zip", ".gz", ".mp4", ".pdf",
})
GZIP_MINIMO = 1024                # por debajo de esto no vale la pena


def _comprimido(ruta: Path) -> bytes | None:
    """El archivo en gzip, cacheado por (tamaño, mtime). None si no conviene."""
    try:
        st = ruta.stat()
    except OSError:
        return None
    if st.st_size < GZIP_MINIMO or ruta.suffix.lower() in SIN_COMPRIMIR:
        return None
    clave = str(ruta)
    with _GZ_CANDADO:
        guardado = _GZ.get(clave)
        if guardado and guardado[0] == st.st_size and guardado[1] == st.st_mtime:
            return guardado[2]
    try:
        crudo = ruta.read_bytes()
    except OSError:
        return None
    z = gzip.compress(crudo, 6)   # 6 es el equilibrio de siempre: 9 tarda el
                                  # triple y baja menos del 1% en JSON
    with _GZ_CANDADO:
        _GZ.clear()               # un archivo a la vez, ver el comentario
        _GZ[clave] = (st.st_size, st.st_mtime, z)
    return z


class ConClave(SimpleHTTPRequestHandler):
    """Sirve la carpeta del proyecto, pero solo con la clave correcta."""

    cuentas: list = []
    quien = ""
    rol = ROL_HABITAT

    extensions_map = {
        **SimpleHTTPRequestHandler.extensions_map,
        ".html": "text/html; charset=utf-8",
        ".htm": "text/html; charset=utf-8",
        ".css": "text/css; charset=utf-8",
        ".js": "application/javascript; charset=utf-8",
        ".json": "application/json; charset=utf-8",
        ".md": "text/markdown; charset=utf-8",
        ".svg": "image/svg+xml; charset=utf-8",
    }

    def _autorizado(self) -> bool:
        self.quien = ""
        self.rol = ROL_ADMIN
        if not self.cuentas:
            return True
        self.rol = ROL_HABITAT
        ip = self.client_address[0] if self.client_address else "?"
        espera = _castigo(ip)
        if espera:
            time.sleep(espera)          # el freno de fuerza bruta
        galleta = self.headers.get("Cookie", "")
        for trozo in galleta.split(";"):
            k, _, v = trozo.strip().partition("=")
            if k == "sesion" and v:
                usuario = _usuario_de_cookie(v)
                if usuario:
                    for u, _c, rol in self.cuentas:
                        if u == usuario:
                            self.quien, self.rol = u, rol
                            return True
        if "text/html" in self.headers.get("Accept", ""):
            return False
        cab = self.headers.get("Authorization", "")
        if not cab.startswith("Basic "):
            return False
        try:
            crudo = base64.b64decode(cab[6:]).decode("utf-8")
        except Exception:  # noqa: BLE001 — cabecera malformada = no pasa
            _anotar_fallo(ip)
            return False
        ok = False
        for u, c, rol in self.cuentas:
            if _igual(crudo, f"{u}:{c}"):
                ok, self.quien, self.rol = True, u, rol
        if ok:
            _limpiar_fallos(ip)
        else:
            _anotar_fallo(ip)
        return ok

    def _ruta(self) -> str:
        """La ruta pedida, sin `?query` ni `#fragmento`."""
        return urlsplit(self.path).path

    VEDADO_AL_EXTERNO = frozenset({
        "/data/crm_leads.json",
        "/tablero.html",
        "/tablero_revision.html",
    })

    def _entregable(self) -> bool:
        """Si esta ruta es de las que alguna página pide de verdad."""
        ruta = self._ruta()
        if posixpath.normpath(unquote(ruta)) != ruta:
            return False
        if self._con_archivo_propio() and ruta in self.VEDADO_AL_EXTERNO:
            return False
        if ".." in ruta:
            return False
        if ruta in RAIZ_PERMITIDA:
            return True
        # El harness que `verificar_pantallas.py` escribe al vuelo en la raíz.
        if ruta.startswith("/_barrido") and ruta.endswith(".html"):
            return True
        for carpeta, extensiones in CARPETAS_PERMITIDAS.items():
            if ruta.startswith(carpeta):
                return ruta.endswith(extensiones)
        return False

    def _pedir_clave(self) -> None:
        acepta = self.headers.get("Accept", "")
        if self.command in ("GET", "HEAD") and "text/html" in acepta:
            self._redirigir("/acceso")
            return
        crudo = json.dumps({"error": "hace falta iniciar sesion",
                            "acceso": "/acceso"}, ensure_ascii=False).encode("utf-8")
        self.send_response(401)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(crudo)))
        self.end_headers()
        self.wfile.write(crudo)

    def _responder_html(self, cuerpo: bytes, estado: int = 200,
                        cookie: str | None = None) -> None:
        self.send_response(estado)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        if cookie is not None:
            self.send_header("Set-Cookie", cookie)
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def _redirigir(self, a: str, cookie: str | None = None) -> None:
        self.send_response(302)
        self.send_header("Location", a)
        self.send_header("Cache-Control", "no-store")
        if cookie is not None:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()

    def _cookie_sesion(self, valor: str, borrar: bool = False) -> str:
        partes = [f"sesion={valor}", "Path=/", "HttpOnly", "SameSite=Lax",
                  "Max-Age=0" if borrar else f"Max-Age={SESION_DIAS * 86400}"]
        if EN_LA_NUBE:
            partes.append("Secure")
        return "; ".join(partes)

    def _acceso_post(self) -> None:
        """El formulario de `design/acceso.html`."""
        n = int(self.headers.get("Content-Length") or 0)
        crudo = self.rfile.read(min(n, 4096)).decode("utf-8", "replace")
        datos = parse_qs(crudo, keep_blank_values=True)
        usuario = (datos.get("usuario") or [""])[0].strip()
        clave = (datos.get("clave") or [""])[0]
        ip = self.client_address[0] if self.client_address else "?"
        espera = _castigo(ip)
        if espera:
            time.sleep(espera)          # el mismo freno que la cabecera Basic
        ok = False
        for u, c, _rol in self.cuentas:
            # compare_digest sobre la pareja entera, contra TODAS las cuentas
            if _igual(f"{usuario}:{clave}", f"{u}:{c}"):
                ok = True
        if not ok:
            _anotar_fallo(ip)
            self._responder_html(_pagina_acceso(
                "Usuario o contraseña incorrectos.", usuario), 200)
            return
        _limpiar_fallos(ip)
        self._redirigir("/", self._cookie_sesion(_cookie_nueva(usuario)))

    def do_POST(self) -> None:  # noqa: N802
        if self._ruta().rstrip("/") == "/acceso":
            if not self.cuentas:            # sin cuentas no hay puerta
                self._redirigir("/")
                return
            self._acceso_post()
            return
        if not self._autorizado():
            self._pedir_clave()
            return
        ruta = self.path.rstrip("/")
        if ruta == "/controles/correr" and not self._es_dueno():
            self._json_403("esa acción es del administrador del tablero")
            return
        if ruta == "/actualizar" and self._con_archivo_propio():
            self._json_403("esa acción no está disponible para este acceso")
            return
        if ruta == "/morosos/comentario":
            if self.rol not in ROLES_COMENTAN:
                self.rfile.read(max(0, min(int(self.headers.get("Content-Length") or 0), 8192)))
                self._json_403("esta acción es de Comercial y del administrador")
                return
            if not self.cuentas and not ESCUCHA_SOLO_LOCAL:
                self._json_403("sin cuentas configuradas no se guardan comentarios")
                return
            self._guardar_comentario()
            return
        if ruta == "/informes/guardar":
            if self.rol not in ROLES_INFORMES:
                self.rfile.read(max(0, min(int(self.headers.get("Content-Length") or 0), 65536)))
                self._json_403("esta acción es de las cuentas de Habitat")
                return
            if not self.cuentas and not ESCUCHA_SOLO_LOCAL:
                self._json_403("sin cuentas configuradas no se guardan informes")
                return
            self._guardar_informe()
            return
        if ruta in ("/informes/imagen", "/informes/imagen/borrar"):
            if self.rol not in ROLES_INFORMES:
                self.rfile.read(max(0, min(int(self.headers.get("Content-Length") or 0), INFORME_IMG_CUERPO_MAX)))
                self._json_403("esta acción es de las cuentas de Habitat")
                return
            if not self.cuentas and not ESCUCHA_SOLO_LOCAL:
                self._json_403("sin cuentas configuradas no se guardan informes")
                return
            if ruta == "/informes/imagen":
                self._guardar_imagen_informe()
            else:
                self._borrar_imagen_informe()
            return
        if ruta == "/actualizar":
            ocupado = _REGENERANDO.locked()
            if not ocupado:
                threading.Thread(target=_regenerar_una_vez, daemon=True).start()
            self._json_corto('{"estado": "ya habia una actualizacion en marcha"}'
                             if ocupado else '{"estado": "actualizando"}')
            return
        if ruta == "/controles/correr":
            ocupado = _CONTROLANDO.locked()
            if not ocupado:
                threading.Thread(target=_correr_controles_una_vez,
                                 daemon=True).start()
            self._json_corto('{"estado": "ya habia controles corriendo"}'
                             if ocupado else '{"estado": "corriendo"}')
            return
        self.send_error(404)


    def _servir_pwa(self, ruta0: str, solo_cabeceras: bool = False) -> bool:
        """Entrega uno de los archivos de la app instalable (ver `PWA_PUBLICA`)."""
        elegido = PWA_PUBLICA.get(ruta0)
        if elegido is None:
            return False
        nombre, tipo = elegido
        try:
            crudo = (RAIZ / "pwa" / nombre).read_bytes()
        except OSError:
            self.send_error(404)
            return True
        self.send_response(200)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(crudo)))
        self.send_header("Cache-Control", "no-cache" if not nombre.endswith(".png")
                         else "public, max-age=86400")
        self.end_headers()
        if not solo_cabeceras:
            self.wfile.write(crudo)
        return True

    def do_GET(self) -> None:  # noqa: N802 — nombre fijado por la stdlib
        ruta0 = self._ruta().rstrip("/")
        if self._servir_pwa(ruta0):
            return
        if ruta0 == "/acceso":
            if not self.cuentas:            # sin cuentas no hay puerta
                self._redirigir("/")
                return
            if self._autorizado():
                self._redirigir("/")
                return
            self._responder_html(_pagina_acceso())
            return
        if ruta0 == "/salir":
            self._redirigir("/acceso", self._cookie_sesion("", borrar=True))
            return
        if not self._autorizado():
            self._pedir_clave()
            return
        if self._ruta().rstrip("/") == "/quien":
            from urllib.parse import parse_qs, urlsplit
            _q = parse_qs(urlsplit(self.path).query).get("hojas", [""])[0]
            _todas = [x for x in _q.split(",") if x] or hojas_del_paquete()
            _ved = hojas_vedadas(self.rol, _todas)
            if not self._es_dueno():
                _ved = sorted(set(_ved) | {"clientes", "estado", "observaciones",
                                           "cambios-stock"})
            _resp = {
                "usuario": self.quien, "rol": self.rol,
                "vedadas": _ved,
                "puede_actualizar": not self._con_archivo_propio(),
                "version": version_viva(),
            }
            self._json_corto(json.dumps(_resp, ensure_ascii=False))
            return
        if self._ruta().rstrip("/") == "/generando":
            _ini = _INICIO[0]
            self._json_corto(json.dumps({
                "hay_datos": RUTA_DATOS().exists(),
                "generando": _REGENERANDO.locked(),
                "segundos": int(time.time() - _ini) if _ini else 0,
            }, ensure_ascii=False))
            return
        if self._ruta().rstrip("/") == "/clientes":
            if not self._es_dueno():
                self._json_403("esta información es solo del administrador")
                return
            if not self.cuentas and not ESCUCHA_SOLO_LOCAL:
                self._json_403("sin cuentas configuradas esta información no se entrega")
                return
            self._responder_clientes()
            return
        _rs = self._ruta().rstrip("/")
        if _rs in ("/stock-vivo", "/verificar-unidad"):
            if "stock" in hojas_vedadas(self.rol, hojas_del_paquete()):
                self._json_403("esta cuenta no ve el stock")
                return
            if _rs == "/stock-vivo":
                self._responder_archivo(RUTA_STOCK_VIVO(), "todavía no se generó el stock en vivo")
            else:
                self._responder_verificacion()
            return
        if self._ruta().rstrip("/") == "/cambios-inventario":
            if not self._es_dueno():
                self._json_403("esta información es solo del administrador")
                return
            if not self.cuentas and not ESCUCHA_SOLO_LOCAL:
                self._json_403("sin cuentas configuradas esta información no se entrega")
                return
            self._responder_archivo(RUTA_CAMBIOS(), "todavía no se generó el registro de cambios")
            return
        if self._ruta().rstrip("/") == "/morosos":
            if self.rol not in ROLES_MOROSOS:
                self._json_403("esta información es de Comercial y del administrador")
                return
            if not self.cuentas and not ESCUCHA_SOLO_LOCAL:
                self._json_403("sin cuentas configuradas esta información no se entrega")
                return
            self._responder_morosos()
            return
        if self._ruta().startswith("/informes/imagen/"):
            if self.rol not in ROLES_INFORMES:
                self._json_403("esta información es de las cuentas de Habitat")
                return
            if not self.cuentas and not ESCUCHA_SOLO_LOCAL:
                self._json_403("sin cuentas configuradas esta información no se entrega")
                return
            self._servir_imagen_informe(self._ruta()[len("/informes/imagen/"):])
            return
        if self._ruta().rstrip("/") == "/informes":
            if self.rol not in ROLES_INFORMES:
                self._json_403("esta información es de las cuentas de Habitat")
                return
            if not self.cuentas and not ESCUCHA_SOLO_LOCAL:
                self._json_403("sin cuentas configuradas esta información no se entrega")
                return
            self._responder_informes()
            return
        if self._ruta().rstrip("/") == "/estado":
            self._responder_estado()
            return
        if self._ruta().rstrip("/") == "/controles/estado":
            if not self._es_dueno():
                self._json_403("esta información es solo del administrador")
                return
            self._responder_controles()
            return
        if self._ruta() in ("", "/"):
            self.send_response(302)
            self.send_header("Location", "/design/cockpit.html")
            self.end_headers()
            return
        if not self._entregable():
            self.send_error(404)
            return
        if self._servir_comprimido():
            return
        super().do_GET()

    def _con_archivo_propio(self) -> bool:
        """¿Este rol recibe un archivo de datos recortado? El vendedor."""
        return getattr(self, "rol", ROL_HABITAT) in (ROL_EXTERNO, ROL_FINANZAS, ROL_OBRAS,
                                                     ROL_VENTAS)

    def _archivo_de_datos(self) -> Path:
        """Qué archivo sale por `/tablero_datos.json` para quien pide."""
        rol = getattr(self, "rol", ROL_HABITAT)
        if rol == ROL_EXTERNO:
            return RUTA_STOCK()
        if rol == ROL_FINANZAS:
            return RUTA_FINANZAS()
        if rol == ROL_OBRAS:
            return RUTA_OBRAS()
        if rol == ROL_VENTAS:
            return RUTA_VENTAS()
        return RUTA_DATOS()

    def _etag(self, destino: Path, mtime: int, largo: int) -> str:
        """La huella de ESTA respuesta, para ESTE rol."""
        return '"%s-%x-%x"' % (destino.name, mtime, largo)

    def _no_cambio(self, mtime: int, etag: str | None = None) -> bool:
        """¿El navegador ya tiene esta misma versión del archivo?."""
        vistos = self.headers.get("If-None-Match")
        if etag and vistos:
            iguales = any(x.strip().strip("W/") == etag for x in vistos.split(","))
            if not iguales:
                return False
            return True
        if etag and not vistos:
            return False
        cab = self.headers.get("If-Modified-Since")
        if not cab:
            return False
        try:
            from email.utils import parsedate_to_datetime
            visto = parsedate_to_datetime(cab)
        except (TypeError, ValueError):
            return False
        if visto is None:
            return False
        try:
            import datetime as _dt
            if visto.tzinfo is None:
                visto = visto.replace(tzinfo=_dt.timezone.utc)
            return int(visto.timestamp()) >= mtime
        except (OverflowError, OSError, ValueError):
            return False

    def _servir_comprimido(self) -> bool:
        """Manda el archivo en gzip si el navegador lo acepta. True si lo hizo."""
        acepta = self.headers.get("Accept-Encoding", "")
        if "gzip" not in acepta.lower():
            return False
        rel = self._ruta().lstrip("/")
        if not rel:
            return False
        if rel == "tablero_datos.json":
            destino = self._archivo_de_datos()
        else:
            try:
                destino = (RAIZ / rel).resolve()
                destino.relative_to(RAIZ.resolve())
            except (ValueError, OSError):
                return False
        if not destino.is_file():
            return False
        z = _comprimido(destino)
        if z is None:
            return False
        tipo = self.guess_type(str(destino))
        mtime = int(destino.stat().st_mtime)
        etag = self._etag(destino, mtime, len(z))
        if self._no_cambio(mtime, etag):
            self.send_response(304)
            self.send_header("ETag", etag)
            self.send_header("Last-Modified", self.date_time_string(mtime))
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Vary", "Accept-Encoding, Cookie")
            self.end_headers()
            return True
        self.send_response(200)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Encoding", "gzip")
        self.send_header("Content-Length", str(len(z)))
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Vary", "Accept-Encoding, Cookie")
        self.send_header("ETag", etag)
        self.send_header("Last-Modified", self.date_time_string(mtime))
        self.end_headers()
        self.wfile.write(z)
        return True

    def translate_path(self, path: str) -> str:  # noqa: N802 — stdlib
        """La URL `/tablero_datos.json` se sirve desde donde VIVE el archivo."""
        if urlsplit(path).path.rstrip("/") == "/tablero_datos.json":
            return str(self._archivo_de_datos())
        return super().translate_path(path)

    def _json_403(self, motivo: str) -> None:
        crudo = json.dumps({"error": motivo}, ensure_ascii=False).encode("utf-8")
        self.send_response(403)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(crudo)))
        self.end_headers()
        self.wfile.write(crudo)

    def _json_corto(self, cuerpo: str) -> None:
        crudo = cuerpo.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(crudo)))
        self.end_headers()
        self.wfile.write(crudo)

    def _responder_clientes(self) -> None:
        """`clientes_kommo.json`, sin caché del navegador y en gzip si lo pide."""
        self._responder_archivo(RUTA_CLIENTES(), "todavía no se generó la lista de clientes")

    def _responder_verificacion(self) -> None:
        """`/verificar-unidad?id=…`: la unidad como está AHORA en AXION."""
        uid = (parse_qs(urlsplit(self.path).query).get("id", [""])[0] or "").strip()
        if not re.fullmatch(r"[0-9a-f]{24}", uid):
            self.send_error(400)
            return
        if not _verif_permitida(self.quien or (self.client_address[0] if self.client_address else "?")):
            crudo = json.dumps({"ok": False, "motivo": "demasiadas consultas seguidas; espera unos segundos"},
                               ensure_ascii=False).encode("utf-8")
            self.send_response(429)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(crudo)))
            self.end_headers()
            self.wfile.write(crudo)
            return
        try:
            u = _consultar_unidad(uid)
        except Exception as e:  # noqa: BLE001 — AXION caído o sin respuesta
            self._json_corto(json.dumps(
                {"ok": False, "motivo": f"AXION no respondió ({type(e).__name__})"}, ensure_ascii=False))
            return

        def _num(x):
            try:
                v = float(x)
            except (TypeError, ValueError):
                return None
            return None if v != v else v

        self._json_corto(json.dumps({
            "ok": True, "existe": bool(u), "id": uid,
            "unidad": str(u.get("name") or ""), "proyecto": str(u.get("project") or ""),
            "estado": str(u.get("status") or "").strip().upper(),
            "precio": _num(u.get("real_price")), "area": _num(u.get("area_m2")),
            "editada": _hora_huancayo(u.get("updated_date")) if u else "",
            "consultado": reloj.sello("%H:%M:%S"),
        }, ensure_ascii=False))

    def _responder_archivo(self, ruta: Path, vacio: str) -> None:
        """Un JSON de la carpeta de datos, sin caché del navegador y en gzip si."""
        try:
            crudo = ruta.read_bytes()
        except OSError:
            self._json_corto(json.dumps({"hay": False, "motivo": vacio}, ensure_ascii=False))
            return
        gz = "gzip" in self.headers.get("Accept-Encoding", "").lower()
        cuerpo = gzip.compress(crudo, 6) if gz else crudo
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        if gz:
            self.send_header("Content-Encoding", "gzip")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def _es_dueno(self) -> bool:
        """¿Es la cuenta principal? Sin cuentas configuradas, el servidor es."""
        if not self.cuentas:
            return True
        dueno = usuario_dueno()
        return bool(dueno) and self.rol == ROL_ADMIN and self.quien == dueno

    def _leer_comentarios(self) -> dict:
        try:
            return json.loads(RUTA_COMENTARIOS().read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def _responder_morosos(self) -> None:
        """`morosos.json` con los comentarios de cada crédito pegados."""
        try:
            datos = json.loads(RUTA_MOROSOS().read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self._json_corto(json.dumps(
                {"hay": False, "motivo": "todavía no se generó la lista de morosos"},
                ensure_ascii=False))
            return
        datos["comentarios"] = self._leer_comentarios()
        datos["usuario"] = self.quien or "admin"
        datos["puede_escribir"] = self.rol in ROLES_COMENTAN
        crudo = json.dumps(datos, ensure_ascii=False).encode("utf-8")
        gz = "gzip" in self.headers.get("Accept-Encoding", "").lower()
        cuerpo = gzip.compress(crudo, 6) if gz else crudo
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        if gz:
            self.send_header("Content-Encoding", "gzip")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def _guardar_comentario(self) -> None:
        if "application/json" not in self.headers.get("Content-Type", ""):
            self.send_error(415)
            return
        n = int(self.headers.get("Content-Length") or 0)
        if n > 8192:
            self.send_error(413)
            return
        try:
            cuerpo = json.loads(self.rfile.read(n).decode("utf-8"))
            cid = str(cuerpo.get("id") or "").strip()
            texto = str(cuerpo.get("texto") or "").strip()
        except (ValueError, AttributeError):
            self.send_error(400)
            return
        if not cid or not texto or len(texto) > COMENTARIO_MAX:
            self.send_error(400)
            return
        try:
            ids = {f.get("id") for f in json.loads(
                RUTA_MOROSOS().read_text(encoding="utf-8")).get("filas", [])}
        except (OSError, json.JSONDecodeError):
            ids = set()
        if cid not in ids:
            self.send_error(404)
            return
        nota = {"texto": texto, "autor": self.quien or "admin",
                "fecha": reloj.sello("%Y-%m-%d %H:%M")}
        with _COMENTARIOS_CANDADO:
            todos = self._leer_comentarios()
            todos.setdefault(cid, []).append(nota)
            ruta = RUTA_COMENTARIOS()
            ruta.parent.mkdir(parents=True, exist_ok=True)
            tmp = ruta.with_suffix(".tmp")
            tmp.write_text(json.dumps(todos, ensure_ascii=False, indent=1), encoding="utf-8")
            tmp.replace(ruta)
            lista = todos[cid]
        self._json_corto(json.dumps({"id": cid, "comentarios": lista}, ensure_ascii=False))

    def _leer_informes(self) -> dict:
        try:
            d = json.loads(RUTA_INFORMES().read_text(encoding="utf-8"))
            return d if isinstance(d, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _responder_informes(self) -> None:
        datos = {"informes": self._leer_informes(), "usuario": self.quien or "admin",
                 "puede_escribir": self.rol in ROLES_INFORMES}
        crudo = json.dumps(datos, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(crudo)))
        self.end_headers()
        self.wfile.write(crudo)

    def _guardar_informe(self) -> None:
        if "application/json" not in self.headers.get("Content-Type", ""):
            self.send_error(415)
            return
        n = int(self.headers.get("Content-Length") or 0)
        if n > 65536:
            self.send_error(413)
            return
        try:
            cuerpo = json.loads(self.rfile.read(n).decode("utf-8"))
            area = str(cuerpo.get("area") or "").strip()
            q = str(cuerpo.get("q") or "").strip()
            campos = cuerpo.get("campos") or {}
            if not isinstance(campos, dict):
                raise ValueError("campos")
        except (ValueError, AttributeError):
            self.send_error(400)
            return
        if area not in INFORME_AREAS or not _periodo_valido(q):
            self.send_error(400)
            return
        proyecto = ""
        if area in INFORME_AREAS_PROYECTO:
            proyecto = str(cuerpo.get("proyecto") or "").replace("|", "/").strip()
            if not proyecto or len(proyecto) > INFORME_PROYECTO_MAX:
                self.send_error(400)
                return
        nuevos = {}
        for k in INFORME_CAMPOS:
            if k not in campos:
                continue
            v = str(campos.get(k) or "").replace(chr(13) + chr(10), chr(10)).strip()
            if len(v) > INFORME_CAMPO_MAX:
                self.send_error(400)
                return
            nuevos[k] = v
        ahora = reloj.sello("%Y-%m-%d %H:%M")
        autor = self.quien or "admin"
        clave = _clave_informe(area, proyecto, q)
        with _INFORMES_CANDADO:
            todos = self._leer_informes()
            previo = todos.get(clave) or {}
            limpios = {k: "" for k in INFORME_CAMPOS}
            limpios.update(previo.get("campos") or {})
            limpios.update(nuevos)
            reg = dict(previo)
            reg.update({"campos": limpios, "autor": autor, "fecha": ahora,
                        "historial": self._historial(previo, autor, ahora)})
            todos[clave] = reg
            self._escribir_informes(todos)
            guardado = todos[clave]
        self._json_corto(json.dumps({"clave": clave, "informe": guardado}, ensure_ascii=False))

    @staticmethod
    def _historial(previo: dict, autor: str, ahora: str) -> list:
        hist = (previo.get("historial") or [])[-9:]
        if not (hist and hist[-1].get("autor") == autor and hist[-1].get("fecha") == ahora):
            hist.append({"autor": autor, "fecha": ahora})
        return hist

    @staticmethod
    def _escribir_informes(todos: dict) -> None:
        ruta = RUTA_INFORMES()
        ruta.parent.mkdir(parents=True, exist_ok=True)
        tmp = ruta.with_suffix(".tmp")
        tmp.write_text(json.dumps(todos, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(ruta)

    def _contexto_informe(self, cuerpo: dict):
        """(area, q, proyecto, clave) de un POST de imagen, o None tras contestar."""
        area = str(cuerpo.get("area") or "").strip()
        q = str(cuerpo.get("q") or "").strip()
        if area not in INFORME_AREAS or area == "ventas" or not _periodo_valido(q):
            self.send_error(400)
            return None
        proyecto = ""
        if area in INFORME_AREAS_PROYECTO:
            proyecto = str(cuerpo.get("proyecto") or "").replace("|", "/").strip()
            if not proyecto or len(proyecto) > INFORME_PROYECTO_MAX:
                self.send_error(400)
                return None
        return area, q, proyecto, _clave_informe(area, proyecto, q)

    def _leer_cuerpo_json(self, tope: int):
        n = int(self.headers.get("Content-Length") or 0)
        if "application/json" not in self.headers.get("Content-Type", ""):
            self.rfile.read(max(0, min(n, tope)))
            self.send_error(415)
            return None
        if n > tope:
            self.send_error(413)
            return None
        try:
            c = json.loads(self.rfile.read(n).decode("utf-8"))
            if not isinstance(c, dict):
                raise ValueError("cuerpo")
            return c
        except (ValueError, AttributeError):
            self.send_error(400)
            return None

    def _guardar_imagen_informe(self) -> None:
        import base64
        import hashlib
        cuerpo = self._leer_cuerpo_json(INFORME_IMG_CUERPO_MAX)
        if cuerpo is None:
            return
        ctx = self._contexto_informe(cuerpo)
        if ctx is None:
            return
        area, q, proyecto, clave = ctx
        m = re.fullmatch(r"data:image/(jpeg|png);base64,([A-Za-z0-9+/=]+)", str(cuerpo.get("data") or ""))
        if not m:
            self.send_error(400)
            return
        try:
            crudo = base64.b64decode(m.group(2), validate=True)
        except ValueError:
            self.send_error(400)
            return
        if len(crudo) > INFORME_IMG_MAX_BYTES:
            self.send_error(413)
            return
        if crudo[:3] == b"\xff\xd8\xff":
            ext = "jpg"
        elif crudo[:8] == b"\x89PNG\r\n\x1a\n":
            ext = "png"
        else:
            self.send_error(415)
            return
        nombre = hashlib.sha1(crudo).hexdigest()[:24] + "." + ext
        ahora = reloj.sello("%Y-%m-%d %H:%M")
        autor = self.quien or "admin"
        with _INFORMES_CANDADO:
            todos = self._leer_informes()
            previo = todos.get(clave) or {}
            imgs = list(previo.get("imagenes") or [])
            if nombre not in imgs:
                if len(imgs) >= INFORME_IMG_MAX_N:
                    crudo_err = json.dumps({"error": f"un informe lleva hasta {INFORME_IMG_MAX_N} imágenes"},
                                           ensure_ascii=False).encode("utf-8")
                    self.send_response(409)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Content-Length", str(len(crudo_err)))
                    self.end_headers()
                    self.wfile.write(crudo_err)
                    return
                carpeta = RUTA_INFORMES_IMAGENES()
                carpeta.mkdir(parents=True, exist_ok=True)
                destino = carpeta / nombre
                if not destino.exists():
                    tmp = destino.with_suffix(".tmp")
                    tmp.write_bytes(crudo)
                    tmp.replace(destino)
                imgs.append(nombre)
            reg = dict(previo)
            reg.setdefault("campos", {k: "" for k in INFORME_CAMPOS})
            reg.update({"imagenes": imgs, "autor": autor, "fecha": ahora,
                        "historial": self._historial(previo, autor, ahora)})
            todos[clave] = reg
            self._escribir_informes(todos)
            guardado = todos[clave]
        self._json_corto(json.dumps({"clave": clave, "informe": guardado}, ensure_ascii=False))

    def _borrar_imagen_informe(self) -> None:
        cuerpo = self._leer_cuerpo_json(65536)
        if cuerpo is None:
            return
        ctx = self._contexto_informe(cuerpo)
        if ctx is None:
            return
        area, q, proyecto, clave = ctx
        nombre = str(cuerpo.get("id") or "")
        if not _INFORME_IMG_ID.fullmatch(nombre):
            self.send_error(400)
            return
        ahora = reloj.sello("%Y-%m-%d %H:%M")
        autor = self.quien or "admin"
        with _INFORMES_CANDADO:
            todos = self._leer_informes()
            previo = todos.get(clave) or {}
            imgs = [i for i in (previo.get("imagenes") or []) if i != nombre]
            reg = dict(previo)
            reg.setdefault("campos", {k: "" for k in INFORME_CAMPOS})
            reg.update({"imagenes": imgs, "autor": autor, "fecha": ahora,
                        "historial": self._historial(previo, autor, ahora)})
            todos[clave] = reg
            self._escribir_informes(todos)
            if not any(nombre in (r.get("imagenes") or []) for r in todos.values() if isinstance(r, dict)):
                try:
                    (RUTA_INFORMES_IMAGENES() / nombre).unlink()
                except OSError:
                    pass
            guardado = todos[clave]
        self._json_corto(json.dumps({"clave": clave, "informe": guardado}, ensure_ascii=False))

    def _servir_imagen_informe(self, nombre: str) -> None:
        """GET `/informes/imagen/<nombre>`. El nombre se valida con una lista."""
        if not _INFORME_IMG_ID.fullmatch(nombre):
            self.send_error(404)
            return
        try:
            crudo = (RUTA_INFORMES_IMAGENES() / nombre).read_bytes()
        except OSError:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", "image/png" if nombre.endswith(".png") else "image/jpeg")
        self.send_header("Content-Length", str(len(crudo)))
        self.send_header("Cache-Control", "private, max-age=86400")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(crudo)

    def _responder_controles(self) -> None:
        """El ultimo veredicto de los controles, mas si estan corriendo AHORA."""
        base = {}
        if CONTROL_JSON.exists():
            try:
                base = json.loads(CONTROL_JSON.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001 — archivo a medio escribir
                base = {}
        base["corriendo"] = _CONTROLANDO.locked()
        base["va_min"] = (round((time.time() - _CONTROL_INICIO[0]) / 60)
                          if (base["corriendo"] and _CONTROL_INICIO[0]) else None)
        base["cada_horas"] = CONTROLES_CADA_HORAS
        base.setdefault("veredicto", None)
        crudo = json.dumps(base, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(crudo)))
        self.end_headers()
        self.wfile.write(crudo)

    def _responder_estado(self) -> None:
        """Qué está pasando AHORA con la actualización."""
        corriendo = _REGENERANDO.locked()
        arranco = _INICIO[0]
        datos = RUTA_DATOS()
        mtime = datos.stat().st_mtime if datos.exists() else None
        cuerpo = {
            "corriendo": corriendo,
            "va_min": (round((time.time() - arranco) / 60)
                       if (corriendo and arranco) else None),
            "publicado": (reloj.de_marca(mtime).strftime("%Y-%m-%d %H:%M:%S")
                          if mtime else None),
            "ultimo_error": _ULT_ERROR[0],
        }
        crudo = json.dumps(cuerpo, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(crudo)))
        self.end_headers()
        self.wfile.write(crudo)

    def do_HEAD(self) -> None:  # noqa: N802
        if self._servir_pwa(self._ruta().rstrip("/"), solo_cabeceras=True):
            return
        if not self._autorizado():
            self._pedir_clave()
            return
        if not self._entregable():
            self.send_error(404)
            return
        super().do_HEAD()

    def log_message(self, formato: str, *args) -> None:  # noqa: A002
        pass


def _cuentas_de_env() -> list[tuple[str, str, str]]:
    """Las cuentas activas, cada una con su ROL: (usuario, clave, rol)."""
    cuentas: list[tuple[str, str, str]] = []
    u = (os.getenv("TABLERO_USUARIO") or "habitat").strip()
    c = (os.getenv("TABLERO_CLAVE") or "").strip()
    if u and c:
        cuentas.append((u, c, ROL_ADMIN))
    for pedazo in (os.getenv("TABLERO_USUARIOS") or "").split(","):
        pedazo = pedazo.strip()
        if not pedazo or ":" not in pedazo:
            continue
        partes = pedazo.split(":")
        nu = partes[0].strip()
        nc = partes[1].strip() if len(partes) > 1 else ""
        rol = (partes[2].strip().lower() if len(partes) > 2 else "") or ROL_HABITAT
        if rol not in (ROL_ADMIN, ROL_HABITAT, ROL_COMERCIAL, ROL_EXTERNO, ROL_FINANZAS,
                       ROL_OBRAS, ROL_VENTAS):
            rol = ROL_HABITAT          # falla cerrado
        if nu and nc:
            cuentas.append((nu, nc, rol))
    return cuentas


def main() -> int:
    cuentas = _cuentas_de_env()
    ConClave.cuentas = cuentas
    _SECRETO[0] = _secreto_de(cuentas)

    if not RUTA_DATOS().exists():
        print("no hay tablero_datos.json — se genera en segundo plano "
              "(la primera corrida tarda unos minutos; el cockpit avisa "
              "mientras tanto)")
        threading.Thread(target=_regenerar_una_vez, daemon=True).start()

    manejador = partial(ConClave, directory=str(RAIZ))
    servidor = ThreadingHTTPServer((INTERFAZ, PUERTO), manejador)

    print(f"cockpit en http://localhost:{PUERTO}/design/cockpit.html")
    print(f"tablero en http://localhost:{PUERTO}/tablero.html")
    if INTERFAZ in ("127.0.0.1", "localhost", "::1"):
        print(f"escuchando SOLO en {INTERFAZ} — ninguna otra máquina de la red "
              f"lo alcanza (TABLERO_INTERFAZ en .env lo cambia)")
    else:
        print(f"!! ATENCIÓN: escuchando en {INTERFAZ} — el tablero es "
              f"alcanzable desde OTRAS máquinas de la red. Con TABLERO_CLAVE "
              f"vacía queda abierto a cualquiera; y sin HTTPS la clave viaja "
              f"en texto plano.")
    print("entrega solo el cockpit, el tablero y su data — el resto (.env, "
          "src/, scripts/, data/) responde 404")
    if cuentas:
        nombres = " · ".join(f"«{u}» ({rol})" for u, _, rol in cuentas)
        print(f"con clave · {len(cuentas)} usuario(s): {nombres} (definidos en .env)")
        print(f"   las hojas Estado y Clientes y los controles son solo de la "
              f"cuenta principal («{usuario_dueno() or '—'}»); regenerar puede "
              f"cualquier usuario logueado menos el externo, el de finanzas y "
              f"el de obras, que además reciben su propio archivo de datos")
    else:
        print("SIN CLAVE — no hay ninguna cuenta con clave en .env "
              "(TABLERO_CLAVE y las de TABLERO_USUARIOS están vacías). "
              "Para exigir clave, escribirlas ahí y reiniciar este servidor.")
    if REFRESCO_MIN:
        print(f"refresco automático cada {REFRESCO_MIN} min "
              f"(TABLERO_REFRESCO_MIN en .env · 0 lo apaga)")
        threading.Thread(target=_regenerar_cada_tanto, daemon=True).start()
    else:
        print("REFRESCO AUTOMÁTICO APAGADO (TABLERO_REFRESCO_MIN=0 en .env). "
              "El tablero solo se actualiza con el botón «Actualizar ahora».")
    if STOCK_REFRESCO_MIN:
        print(f"stock en vivo cada {STOCK_REFRESCO_MIN} min, aparte del tablero "
              f"(TABLERO_STOCK_MIN en .env · 0 apaga)")
        threading.Thread(target=_refrescar_stock_cada_tanto, daemon=True).start()
    else:
        print("STOCK EN VIVO APAGADO (TABLERO_STOCK_MIN=0): el stock se actualiza "
              "solo con el tablero completo.")
    if CONTROLES_CADA_HORAS:
        print(f"controles automáticos cada {CONTROLES_CADA_HORAS} h, primera "
              f"corrida a los 10 min (CONTROLES_CADA_HORAS en .env · 0 apaga)")
        threading.Thread(target=_controlar_cada_tanto, daemon=True).start()
    else:
        print("CONTROLES AUTOMÁTICOS APAGADOS (CONTROLES_CADA_HORAS=0). "
              "Quedan el botón de la hoja Estado y CONTROL_FINAL.bat.")
    
    def _iniciar_tiempo_real() -> None:
        """Inicia WebSocket para actualización en tiempo real."""
        try:
            from src import websocket_server
            websocket_server.iniciar_tiempo_real(puerto_ws=5000)
        except ImportError as e:
            print(f"  Advertencia: módulos de realtime no disponibles: {e}")
        except Exception as e:
            print(f"  Error iniciando tiempo real: {e}")
    
    threading.Thread(target=_iniciar_tiempo_real, daemon=True).start()
    
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
