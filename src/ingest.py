import json
import os
import re
import threading
import time
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

from . import reloj

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

AXION_ENTITIES = ["Ingreso", "Gasto", "Sale", "Installment", "Moroso",
                  "CxCPayment", "Unit", "Credit", "Project", "Lead",
                  "Property", "KPI", "Advisor",
                  "OrdenCompra",
                  "BitacoraObra", "Contrato", "Cotizacion",
                  "PagoPersonal",
                  "MarketingActivity",
                  "Incident",
                  "SaldoInicial",
                  "MarketingKPI", "Remuneracion"]
OBRA_ENTITIES = ["BudgetItem", "Partida", "Valuation", "PagoPersonal"]


def read_contasis_excel(filename: str) -> pd.DataFrame:
    # Columnas reales por confirmar una vez llegue la muestra de export de ContaSis.
    return pd.read_excel(DATA_DIR / filename)


def read_base44_json(filename: str) -> dict:
    """Lee un export de una app Base44 (AXION u Obra): un dump manual de las."""
    content = json.loads((DATA_DIR / filename).read_text(encoding="utf-8"))
    return content.get("data", content)


def base44_entity_df(data: dict, entity: str) -> pd.DataFrame:
    if entity not in AXION_ENTITIES and entity not in OBRA_ENTITIES:
        raise ValueError(f"Entidad desconocida: {entity}")
    return pd.DataFrame(data.get(entity, []))


def read_ventas_gastos_export(filename: str) -> dict:
    return read_base44_json(filename)


def read_obra_export(filename: str) -> dict:
    return read_base44_json(filename)


def read_ventas_sheet(filename: str, sheet: str = "Ventas Habitat") -> pd.DataFrame:
    return pd.read_excel(DATA_DIR / "raw_exports" / filename, sheet_name=sheet)


def read_axion_html_table(filename: str) -> pd.DataFrame:
    """Los exports por página de AXION (Gastos, Ingresos) descargan un HTML."""
    from bs4 import BeautifulSoup

    path = DATA_DIR / "raw_exports" / filename
    content = path.read_text(encoding="utf-8", errors="replace")
    soup = BeautifulSoup(content, "html.parser")
    table = soup.find("table")
    rows = table.find_all("tr")
    headers = [th.get_text(strip=True) for th in rows[0].find_all("th")]
    data = [[td.get_text(strip=True) for td in tr.find_all("td")] for tr in rows[1:]]
    return pd.DataFrame(data, columns=headers)


def find_latest_export(prefix: str) -> str | None:
    """Busca en data/raw_exports/ el archivo más reciente que empiece con."""
    folder = DATA_DIR / "raw_exports"
    if not folder.exists():
        return None
    matches = sorted(folder.glob(f"{prefix}*.xls")) + sorted(folder.glob(f"{prefix}*.xlsx"))
    return matches[-1].name if matches else None


def axion_api_available() -> bool:
    return (bool(os.getenv("AXION_API_TOKEN") or os.getenv("AXION_API_KEY"))
            and bool(os.getenv("AXION_API_BASE_URL")))


def obra_api_available() -> bool:
    return (bool(os.getenv("OBRA_API_TOKEN") or os.getenv("OBRA_API_KEY"))
            and bool(os.getenv("OBRA_API_BASE_URL")))


CONTASIS_DIR = "raw_exports/contasis"
CABIDAS_DIR = "raw_exports/cabidas"


def contasis_available() -> bool:
    folder = DATA_DIR / CONTASIS_DIR
    return (folder / "Estado de resultados.xlsx").exists() and (folder / "Estados financieros.xlsx").exists()


_MESES_ES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "setiembre": 9, "septiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}


def contasis_cierre() -> str | None:
    """Fecha DEL CIERRE contable, leída de la cabecera del documento."""
    ruta = DATA_DIR / CONTASIS_DIR / "Estado de resultados.xlsx"
    if not ruta.exists():
        return None
    try:
        cab = pd.read_excel(ruta, sheet_name=0, header=None, nrows=10)
    except Exception:  # noqa: BLE001 — un export ilegible no debe tumbar el arranque
        return None
    texto = " ".join(
        str(v) for _, fila in cab.iterrows() for v in fila if pd.notna(v)
    ).lower()
    m = re.search(r"al\s+(\d{1,2})\s+de\s+([a-záéíóú]+)\s+del?\s+(\d{4})", texto)
    if not m:
        return None
    dia, mes, anio = m.group(1), _MESES_ES.get(m.group(2)), m.group(3)
    if not mes:
        return None
    return f"{anio}-{mes:02d}-{int(dia):02d}"


def contasis_fecha() -> str | None:
    """Fecha del último export contable (ISO, hasta el minuto)."""
    folder = DATA_DIR / CONTASIS_DIR
    if not folder.exists():
        return None
    archivos = [f for f in folder.glob("*.xlsx") if f.is_file()]
    if not archivos:
        return None
    return reloj.de_marca(max(f.stat().st_mtime for f in archivos)).strftime("%Y-%m-%dT%H:%M")


def cabidas_dir() -> Path:
    """Carpeta con las cabidas (proyectados de factibilidad de Yan)."""
    return DATA_DIR / CABIDAS_DIR


def read_contasis_libro_mayor() -> pd.DataFrame | None:
    """Libro Mayor Analítico de ContaSis: asientos contables con cuenta."""
    path = DATA_DIR / CONTASIS_DIR / "Libro Mayor Analitico.xlsx"
    if not path.exists():
        return None
    df = pd.read_excel(path, sheet_name="DIARIO ANALITICO", header=None,
                       names=["x", "mes", "fecha", "cuenta", "descripcion", "debe", "haber", "glosa"])
    df["cuenta"] = df["cuenta"].astype(str).str.strip()
    df["debe"] = pd.to_numeric(df["debe"], errors="coerce")
    df["haber"] = pd.to_numeric(df["haber"], errors="coerce")
    return df


def read_contasis_statement(filename: str, sheet: str) -> pd.DataFrame:
    """Lee un estado financiero de ContaSis (Estado de Resultados, Estados."""
    path = DATA_DIR / CONTASIS_DIR / filename
    return pd.read_excel(path, sheet_name=sheet, header=None)


_RAIZ_OK: dict[str, str] = {}
_PLATAFORMA = "https://app.base44.com/api/apps"


_CREDENCIAL: dict[tuple, dict] = {}
_CREDENCIAL_CANDADO = threading.Lock()


def _nombre_token(api_key_env: str) -> str:
    return (api_key_env[:-4] if api_key_env.endswith("_KEY") else api_key_env) + "_TOKEN"


def _cabeceras(base_url_env: str, api_key_env: str, entity: str) -> dict:
    """Las cabeceras de autenticación de esta app: el token si está y AXION lo."""
    clave = (base_url_env, api_key_env)
    with _CREDENCIAL_CANDADO:
        if clave in _CREDENCIAL:
            return _CREDENCIAL[clave]["cab"]
        base = (os.getenv(base_url_env) or "").rstrip("/")
        token = (os.getenv(_nombre_token(api_key_env)) or "").strip()
        vieja = (os.getenv(api_key_env) or "").strip()
        json_ = {"Content-Type": "application/json"}
        if token:
            cab = {"Authorization": f"Bearer {token}", **json_}
            como = f"token personal ({_nombre_token(api_key_env)})"
            if vieja:
                app_id = (os.getenv(base_url_env.replace("_API_BASE_URL", "_APP_ID")) or "").strip()
                urls = [f"{base}/entities/{entity}"]
                if app_id:
                    urls.append(f"{_PLATAFORMA}/{app_id}/entities/{entity}")
                codigos = []
                for u in urls:
                    try:
                        codigos.append(requests.get(u, headers=cab, params={"limit": 1},
                                                    timeout=30).status_code)
                    except requests.RequestException as e:
                        codigos.append(type(e).__name__)
                if not any(c in (200, 404) for c in codigos):
                    cab = {"api_key": vieja, **json_}
                    como = (f"clave vieja ({api_key_env}) — el token fue rechazado "
                            f"{codigos}; la clave deja de funcionar el 15-oct-2026")
        else:
            cab = {"api_key": vieja, **json_}
            como = (f"clave vieja ({api_key_env}) — falta {_nombre_token(api_key_env)}; "
                    f"deja de funcionar el 15-oct-2026")
        _CREDENCIAL[clave] = {"cab": cab, "como": como}
        print(f"  {base_url_env.split('_')[0]}: se lee con {como}")
        return cab


def _raiz_que_responde(base_url: str, cab: dict, entity: str) -> str:
    """La raiz de API que contesta. Prueba la configurada; si da 403 por falta."""
    if base_url in _RAIZ_OK:
        return _RAIZ_OK[base_url]
    try:
        r = requests.get(
            f"{base_url}/entities/{entity}",
            headers=cab, params={"limit": 1}, timeout=30)
        if r.status_code != 403:
            _RAIZ_OK[base_url] = base_url
            return base_url
        app_id = ((r.json() or {}).get("extra_data") or {}).get("app_id")
    except (requests.RequestException, ValueError):
        _RAIZ_OK[base_url] = base_url
        return base_url
    if not app_id:
        _RAIZ_OK[base_url] = base_url
        return base_url
    alterna = f"{_PLATAFORMA}/{app_id}"
    try:
        r2 = requests.get(
            f"{alterna}/entities/{entity}",
            headers=cab, params={"limit": 1}, timeout=30)
        # 404 sirve: quiere decir que la RAIZ contesta y la entidad no existe.
        if r2.status_code in (200, 404):
            _RAIZ_OK[base_url] = alterna
            return alterna
    except requests.RequestException:
        pass
    _RAIZ_OK[base_url] = base_url          # que falle con su 403 de siempre
    return base_url


def _fetch_base44_entity(base_url_env: str, api_key_env: str, entity: str, valid_entities: list[str],
                          q: dict | None = None, limit: int = 5000, sort_by: str = "-created_date") -> pd.DataFrame:
    """Trae una entidad en vivo de la API oficial de una app Base44 (AXION u."""
    if entity not in valid_entities:
        raise ValueError(f"Entidad desconocida: {entity}")

    base_url = os.getenv(base_url_env)
    if not base_url or not (os.getenv(_nombre_token(api_key_env)) or os.getenv(api_key_env)):
        raise RuntimeError(f"Faltan {base_url_env} / {_nombre_token(api_key_env)} en .env")
    cab = _cabeceras(base_url_env, api_key_env, entity)

    t_ini = time.time()
    raiz = _raiz_que_responde(base_url, cab, entity)
    for intento in range(1, 4):
        filas, paginas, repetidas = _leer_paginas(raiz, cab, entity, q, limit)
        if not repetidas:
            break
    else:
        raise RuntimeError(
            f"{entity}: tres lecturas seguidas trajeron filas repetidas entre "
            f"páginas ({repetidas} la última) — a la tabla le faltarían filas")
    with _MEDICION_CANDADO:
        MEDICION.append({"tabla": entity, "segundos": round(time.time() - t_ini, 1),
                         "filas": len(filas), "paginas": paginas, "intentos": intento})
    return _ordenar(pd.DataFrame(filas), sort_by)


def _leer_paginas(raiz: str, cab: dict, entity: str, q: dict | None,
                  limit: int) -> tuple[list, int, int]:
    """Una lectura completa por páginas, en orden de `id`. Devuelve las filas."""
    paginas = repetidas = 0
    filas: list = []
    vistos: set = set()
    salto = 0
    TOPE_PAGINAS = 100          # 500,000 filas: un techo contra un bucle infinito
    for _ in range(TOPE_PAGINAS):
        params = {"limit": limit, "skip": salto, "sort_by": "id"}
        if q:
            params["q"] = json.dumps(q)
        resp = requests.get(
            f"{raiz}/entities/{entity}",
            headers=cab,
            params=params,
            timeout=60,
        )
        resp.raise_for_status()
        paginas += 1
        pagina = resp.json()
        if not isinstance(pagina, list) or not pagina:
            break
        for r in pagina:
            rid = r.get("id") if isinstance(r, dict) else None
            if rid and rid in vistos:
                repetidas += 1
                continue
            if rid:
                vistos.add(rid)
            filas.append(r)
        salto += len(pagina)
        if len(pagina) < limit:
            break
    else:
        raise RuntimeError(
            f"{entity}: se leyeron {salto:,} filas y la API sigue devolviendo "
            f"páginas completas. Se cortó por seguridad — revisar el lector "
            f"antes de publicar nada con esta tabla")
    return filas, paginas, repetidas


def _ordenar(df: pd.DataFrame, sort_by: str) -> pd.DataFrame:
    """El orden que pidió la llamada (`-campo` = de mayor a menor), con el `id`."""
    campo = (sort_by or "").lstrip("-")
    if df.empty or not campo or campo not in df.columns or "id" not in df.columns:
        return df
    try:
        return df.sort_values([campo, "id"], ascending=[not sort_by.startswith("-"), True],
                              kind="stable", na_position="last").reset_index(drop=True)
    except TypeError:           # tipos mezclados en el campo: se deja por id
        return df


MEDICION: list[dict] = []
_MEDICION_CANDADO = threading.Lock()

_CACHE: dict[tuple, pd.DataFrame] = {}

RESPALDO = DATA_DIR / "ultima_lectura_axion.json"


CATALOGO = DATA_DIR.parent / "config" / "catalogo_kpi.json"


def _respaldo_leer() -> dict:
    base: dict = {}
    if CATALOGO.exists():
        try:
            base = json.loads(CATALOGO.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            base = {}
    if RESPALDO.exists():
        try:
            base.update(json.loads(RESPALDO.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            pass
        return base
    return base


def _respaldo_guardar(entity: str, df: pd.DataFrame) -> None:
    """Guarda la foto SOLO de las entidades chicas y de catálogo. No se."""
    if entity not in ("KPI", "Project", "Advisor"):
        return
    try:
        with _RESPALDO_CANDADO:
            h = _respaldo_leer()
            h[entity] = {"cuando": reloj.sello(),
                         "filas": df.to_dict("records")}
            RESPALDO.parent.mkdir(parents=True, exist_ok=True)
            RESPALDO.write_text(json.dumps(h, indent=1, ensure_ascii=False,
                                           default=str), encoding="utf-8")
    except Exception:  # noqa: BLE001 — el respaldo nunca rompe la lectura
        pass


_RESPALDO_CANDADO = threading.Lock()


DEGRADADAS: dict[str, str] = {}


def fetch_axion_entity(entity: str, q: dict | None = None, limit: int = 5000,
                        sort_by: str = "-fecha") -> pd.DataFrame:
    """Trae una entidad de AXION, CON CACHÉ POR CORRIDA."""
    clave = (entity, json.dumps(q, sort_keys=True) if q else None, limit, sort_by)
    if clave not in _CACHE:
        try:
            df = _fetch_base44_entity(
                "AXION_API_BASE_URL", "AXION_API_KEY", entity, AXION_ENTITIES,
                q, limit, sort_by)
            _respaldo_guardar(entity, df)
        except Exception as e:  # noqa: BLE001
            prev = _respaldo_leer().get(entity)
            if not prev:
                raise
            DEGRADADAS[entity] = (
                f"{type(e).__name__} — se muestra la última lectura buena, "
                f"del {prev['cuando']}")
            df = pd.DataFrame(prev["filas"])
        _CACHE[clave] = df
    return _CACHE[clave].copy()


def con_credito(inst: pd.DataFrame) -> pd.Series:
    """¿La cuota cuelga de un crédito que EXISTE en AXION?."""
    ids = set(fetch_axion_entity("Credit", None, 5000)["id"].astype(str))
    return inst["credit_id"].astype(str).isin(ids)


def fetch_axion_opcional(entity: str, columnas: list[str]) -> pd.DataFrame:
    """Como `fetch_axion_entity`, pero si la tabla NO EXISTE devuelve un."""
    try:
        return fetch_axion_entity(entity, None, 5000)
    except Exception as e:  # noqa: BLE001
        DEGRADADAS[entity] = (
            f"{type(e).__name__}: la tabla no responde. ¿La renombraron o "
            f"borraron en AXION?")
        return pd.DataFrame(columns=columnas)


def limpiar_cache() -> None:
    """Para volver a leer la API dentro del mismo proceso."""
    _CACHE.clear()


def fetch_obra_entity(entity: str, q: dict | None = None, limit: int = 5000,
                       sort_by: str = "-start_date") -> pd.DataFrame:
    return _fetch_base44_entity("OBRA_API_BASE_URL", "OBRA_API_KEY", entity, OBRA_ENTITIES, q, limit, sort_by)


def clave_inicial(entrada: dict, credito) -> str:
    def _campo(obj, nombre):
        if hasattr(obj, "get"):
            return obj.get(nombre)
        return getattr(obj, nombre, None)

    return (f"{entrada.get('serie') or ''}|{entrada.get('tipo')}|"
            f"{entrada.get('monto')}|{entrada.get('fecha')}|"
            f"{_campo(credito, 'project')}|{_campo(credito, 'unit')}")
