"""INGESTA · KOMMO."""
from __future__ import annotations

import os
import threading
import time
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests
from dotenv import load_dotenv

from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
load_dotenv(RAIZ / ".env")

EMBUDO_HABITAT = 11714440
EMBUDO_CONCEPT = 11990195

POR_PAGINA = 250
PAUSA = 0.2
TOPE_PAGINAS = 200

CAMPOS = {
    "m Campaña Marketing:": "campana",
    "v Proyecto de interés:": "proyecto",
    "m Género:": "genero",
    "v Contactabilidad:": "contactabilidad",
    "v Producto:": "producto",
    "v Nivel de Interés:": "nivel_interes",
    "m Ciudad donde vive:": "ciudad",
    "v Uso:": "uso",
    "m Lugar de Trabajo:": "lugar_trabajo",
    "m Rango de edad:": "rango_edad",
    "v Medidas:": "medidas",
    "v Dormitorios:": "dormitorios",
    "v Llamada Lead Nuevo:": "primera_llamada",
    "Llamada Seguimiento 1:": "seguimiento_1",
    "Llamada Seguimiento 2:": "seguimiento_2",
    "Llamada Seguimiento 3:": "seguimiento_3",
    "v Fecha de Reunión Virtual:": "reunion_virtual",
    "v Fecha de Visita Presencial:": "visita_presencial",
    "v Proyecto adicional de interés:": "proyecto_adicional",
}
FECHAS = {"primera_llamada", "visita_presencial", "seguimiento_1",
          "seguimiento_2", "seguimiento_3", "reunion_virtual"}

RASTREO = ["utm_source", "utm_medium", "utm_campaign", "utm_term",
           "utm_content", "referrer", "gclid", "fbclid", "ttad_name"]


class KommoNoResponde(RuntimeError):
    """Para que quien llame decida qué mostrar, en vez de recibir un cero."""


def _credenciales() -> tuple[str, str]:
    sub = (os.getenv("KOMMO_SUBDOMINIO") or "").strip()
    token = (os.getenv("KOMMO_TOKEN") or "").strip()
    sub = sub.replace("https://", "").replace("http://", "")
    sub = sub.split("/")[0].split(".kommo.com")[0].strip(". /")
    if not sub or not token:
        raise KommoNoResponde("faltan KOMMO_SUBDOMINIO / KOMMO_TOKEN en .env")
    return sub, token


def disponible() -> bool:
    try:
        _credenciales()
        return True
    except KommoNoResponde:
        return False


_SESION: requests.Session | None = None


def _sesion() -> tuple[requests.Session, str]:
    global _SESION
    sub, token = _credenciales()
    if _SESION is None:
        _SESION = requests.Session()
        _SESION.headers.update({"Authorization": f"Bearer {token}"})
    return _SESION, f"https://{sub}.kommo.com"


MEDICION: dict = {"por_ruta": {}, "pausas": 0.0}


def _pedir(ruta: str, params: dict | None = None) -> dict | None:
    """`_pedir_sin_medir`, anotando en `MEDICION` cuánto tardó."""
    t_ini = time.time()
    try:
        return _pedir_sin_medir(ruta, params)
    finally:
        m = MEDICION["por_ruta"].setdefault(ruta, [0, 0.0])
        m[0] += 1
        m[1] += time.time() - t_ini


def _pedir_sin_medir(ruta: str, params: dict | None = None) -> dict | None:
    """Un pedido a Kommo, con reintento ante el 429 Y ante un corte de red."""
    ses, base = _sesion()
    ultimo: Exception | None = None
    for intento in range(4):
        try:
            r = ses.get(f"{base}{ruta}", params=params, timeout=30)
        except requests.RequestException as e:
            ultimo = e
            if intento == 3:
                break
            time.sleep(2 ** intento)
            continue
        if r.status_code == 429:
            time.sleep(2 ** intento)
            continue
        if r.status_code == 204:
            return None
        if r.status_code == 401:
            raise KommoNoResponde("HTTP 401 — el token no es válido")
        if r.status_code != 200:
            raise KommoNoResponde(f"HTTP {r.status_code} en {ruta}")
        return r.json()
    if ultimo is not None:
        raise KommoNoResponde(
            f"{type(ultimo).__name__} en {ruta}, tras cuatro intentos: "
            f"{str(ultimo)[:70]}") from ultimo
    raise KommoNoResponde(f"429 — límite de tasa en {ruta}, tras cuatro reintentos")


def _coleccion(cuerpo: dict) -> list:
    """La lista de `_embedded`, sin asumir su nombre. Buscar la clave literal."""
    emb = cuerpo.get("_embedded")
    if not isinstance(emb, dict):
        return []
    for valor in emb.values():
        if isinstance(valor, list):
            return valor
    return []


_CACHE: dict[str, object] = {}


def embudos() -> dict[int, str]:
    """{id: nombre} de los cuatro embudos."""
    if "embudos" not in _CACHE:
        cuerpo = _pedir("/api/v4/leads/pipelines")
        _CACHE["embudos"] = {p["id"]: p.get("name")
                             for p in _coleccion(cuerpo or {})}
    return _CACHE["embudos"]                                   # type: ignore


def _etapas() -> dict[tuple[int, int], str]:
    """{(embudo, etapa): nombre}. La clave lleva el embudo porque Kommo reusa."""
    if "etapas" not in _CACHE:
        cuerpo = _pedir("/api/v4/leads/pipelines")
        mapa = {}
        for p in _coleccion(cuerpo or {}):
            for s in (p.get("_embedded", {}).get("statuses") or []):
                mapa[(p["id"], s["id"])] = s.get("name")
        _CACHE["etapas"] = mapa
    return _CACHE["etapas"]                                    # type: ignore


LIMA = timezone(timedelta(hours=-5))


def _momento(ts) -> pd.Timestamp | None:
    """Fecha Y HORA locales. Se guarda la hora porque el tiempo de atención se."""
    if not ts:
        return None
    try:
        return pd.Timestamp(datetime.fromtimestamp(int(ts), LIMA).replace(tzinfo=None))
    except (ValueError, TypeError, OSError, OverflowError):
        return None


def _fecha(ts) -> pd.Timestamp | None:
    m = _momento(ts)
    return None if m is None else m.normalize()


def usuarios() -> dict[int, str]:
    if "usuarios" not in _CACHE:
        try:
            cuerpo = _pedir("/api/v4/users", {"page": 1, "limit": POR_PAGINA})
            _CACHE["usuarios"] = {u["id"]: (u.get("name") or f"usuario {u['id']}")
                                  for u in _coleccion(cuerpo or {})}
        except KommoNoResponde:
            _CACHE["usuarios"] = {}
    return _CACHE["usuarios"]                                  # type: ignore


def motivos_perdida() -> dict[int, str]:
    """{id: nombre} del catálogo de motivos de descarte de Kommo."""
    if "motivos" not in _CACHE:
        try:
            cuerpo = _pedir("/api/v4/leads/loss_reasons")
            _CACHE["motivos"] = {m["id"]: (m.get("name") or f"motivo {m['id']}")
                                 for m in _coleccion(cuerpo or {})}
        except KommoNoResponde:
            _CACHE["motivos"] = {}
    return _CACHE["motivos"]                                   # type: ignore


_LEADS_CANDADO = threading.Lock()


def _leads_crudos() -> list:
    """Todas las páginas de /api/v4/leads, una vez por corrida."""
    with _LEADS_CANDADO:
        if "leads_crudos" in _CACHE:
            return _CACHE["leads_crudos"]                     # type: ignore
        crudos: list = []
        pagina = 1
        while pagina <= TOPE_PAGINAS:
            cuerpo = _pedir("/api/v4/leads",
                            {"page": pagina, "limit": POR_PAGINA, "with": "tags"})
            time.sleep(PAUSA)
            MEDICION["pausas"] += PAUSA
            if not cuerpo:
                break
            items = _coleccion(cuerpo)
            if not items:
                break
            crudos += items
            if not (cuerpo.get("_links") or {}).get("next"):
                break
            pagina += 1
        _CACHE["leads_crudos"] = crudos
        return crudos


def leads(embudo: int | None = EMBUDO_HABITAT) -> pd.DataFrame:
    """Los leads, uno por fila, con sus campos personalizados aplanados."""
    clave = f"leads:{embudo}"
    if clave in _CACHE:
        return _CACHE[clave].copy()                            # type: ignore

    etapas, crudos = _etapas(), _leads_crudos()

    filas = []
    for x in crudos:
        pid = x.get("pipeline_id")
        if embudo is not None and pid != embudo:
            continue
        fila = {
            # `name` NO se copia: en Kommo es el nombre del cliente.
            "id": x.get("id"),
            "embudo": embudos().get(pid, f"(embudo {pid})"),
            "etapa": etapas.get((pid, x.get("status_id")),
                                f"(etapa {x.get('status_id')})"),
            "precio": x.get("price") or 0,
            "creado": _momento(x.get("created_at")),
            "cerrado": _fecha(x.get("closed_at")),
            "motivo_perdida": motivos_perdida().get(x.get("loss_reason_id")),
            "responsable_id": x.get("responsible_user_id"),
            "responsable": usuarios().get(x.get("responsible_user_id"),
                                          "(sin responsable)"),
            "etiquetas": sorted(t.get("name") or "" for t in
                                (x.get("_embedded", {}).get("tags") or [])),
        }
        for c in (x.get("custom_fields_values") or []):
            nombre = c.get("field_name") or ""
            destino = CAMPOS.get(nombre) or (nombre if nombre in RASTREO else None)
            if not destino:
                continue
            vals = [v.get("value") for v in (c.get("values") or [])
                    if v.get("value") not in (None, "")]
            if not vals:
                continue
            if destino in FECHAS:
                fila[destino] = _momento(vals[0])
            else:
                fila[destino] = " · ".join(str(v) for v in vals)
        filas.append(fila)

    df = pd.DataFrame(filas)
    for col in list(CAMPOS.values()) + RASTREO:
        if col not in df.columns:
            df[col] = pd.NA
    _CACHE[clave] = df
    return df.copy()


def tareas() -> pd.DataFrame:
    """Las TAREAS de Kommo, una por fila."""
    if "tareas" in _CACHE:
        return _CACHE["tareas"].copy()                          # type: ignore

    crudos, pagina = [], 1
    while pagina <= TOPE_PAGINAS:
        cuerpo = _pedir("/api/v4/tasks", {"page": pagina, "limit": POR_PAGINA})
        time.sleep(PAUSA)
        MEDICION["pausas"] += PAUSA
        if not cuerpo:
            break
        items = _coleccion(cuerpo)
        if not items:
            break
        crudos += items
        if not (cuerpo.get("_links") or {}).get("next"):
            break
        pagina += 1

    filas = [{
        "id": t.get("id"),
        "entidad": t.get("entity_type"),
        "entidad_id": t.get("entity_id"),
        "creada": _momento(t.get("created_at")),
        "vence": _momento(t.get("complete_till")),
        "completada": bool(t.get("is_completed")),
        "tipo_id": t.get("task_type_id"),
        "responsable_id": t.get("responsible_user_id"),
        "responsable": usuarios().get(t.get("responsible_user_id"),
                                      "(sin responsable)"),
    } for t in crudos]

    df = pd.DataFrame(filas)
    for col in ("id", "entidad", "entidad_id", "creada", "vence", "completada",
                "tipo_id", "responsable_id", "responsable"):
        if col not in df.columns:
            df[col] = pd.NA
    _CACHE["tareas"] = df
    return df.copy()


def limpiar_cache() -> None:
    _CACHE.clear()


def resumen() -> dict:
    """Lo que la hoja Estado necesita: conteos por embudo y período leído."""
    todos = leads(None)
    del_embudo = todos[todos["embudo"] == embudos().get(EMBUDO_HABITAT)]
    fechas = del_embudo["creado"].dropna()
    return {
        "total_cuenta": int(len(todos)),
        "por_embudo": todos["embudo"].value_counts().to_dict(),
        "leidos": int(len(del_embudo)),
        "periodo": (f"leads de {fechas.min():%Y-%m-%d} a {fechas.max():%Y-%m-%d}"
                    if len(fechas) else "sin fechas"),
    }
