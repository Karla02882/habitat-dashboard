"""ATENCIÓN AL CLIENTE · la tabla `Incident` de AXION."""
from __future__ import annotations

import re

import pandas as pd

from . import atribucion, ingest, periodo

_CACHE: dict[str, pd.DataFrame] = {}


def _quitar_html(s: object) -> str:
    """`description`/`observations` llegan con etiquetas <p> de AXION."""
    t = re.sub(r"<[^>]+>", " ", str(s or ""))
    return re.sub(r"\s+", " ", t).strip()


def crudo() -> pd.DataFrame:
    """`Incident` tal como llega, una vez por corrida."""
    if "df" not in _CACHE:
        try:
            df = ingest._fetch_base44_entity(
                "AXION_API_BASE_URL", "AXION_API_KEY", "Incident",
                ["Incident"], limit=5000)
        except Exception:  # noqa: BLE001 — módulo opcional, se degrada
            df = pd.DataFrame()
        _CACHE["df"] = df
    return _CACHE["df"]


def filas() -> list[dict]:
    """Una fila por incidencia, con la obra emparejada contra las 18 de AXION."""
    df = crudo()
    if df.empty:
        return []
    _oa = atribucion.obras_axion()
    obras = list(_oa[_oa["declarada_en_Project"]]["obra"])
    out = []
    for _, r in df.iterrows():
        etiqueta = str(r.get("project") or "").strip()
        obra, como = atribucion._emparejar(etiqueta, obras) if etiqueta else ("—", "—")
        fecha = str(r.get("registration_date") or "").strip()
        out.append({
            "fecha": fecha,
            "cliente": str(r.get("client") or "").strip(),
            "unidad": str(r.get("department") or "").strip(),
            "proyecto_declarado": etiqueta or "(sin dato)",
            "obra": obra,
            "obra_como": como,
            "tipo": str(r.get("type") or "").strip() or "(sin dato)",
            "incidencia": str(r.get("incident_type") or "").strip(),
            "prioridad": str(r.get("priority") or "").strip() or "(sin dato)",
            "estado": str(r.get("status") or "").strip() or "(sin dato)",
            "descripcion": _quitar_html(r.get("description")),
            "resultado": _quitar_html(r.get("observations")),
            "asignado": str(r.get("assigned_to") or "").strip(),
            "telefono": str(r.get("phone") or "").strip(),
            "reclamo": str(r.get("claim_date") or "").strip(),
            "visita": str(r.get("visit_date") or "").strip(),
            "creado": str(r.get("created_date") or "").strip()[:19],
        })
    return out


def resumen(periodo_token=None) -> dict:
    """Los conteos del período."""
    fs = filas()
    if not fs:
        return {"hay": False}
    an, m = periodo.partes(periodo_token)
    def _en_periodo(f: dict) -> bool:
        fx = pd.to_datetime(f["fecha"], errors="coerce")
        if pd.isna(fx):
            return False
        if an is None:
            return True
        if fx.year != an:
            return False
        return m is None or fx.month == m
    sel = [f for f in fs if _en_periodo(f)]
    sin_obra = [f for f in sel if f["obra"] == "—"]
    ambiguas = [f for f in sel if f["obra_como"] == "AMBIGUA"]
    return {
        "hay": True,
        "filas": sel,
        "total": len(sel),
        "resueltas": sum(1 for f in sel if f["estado"] == "Resuelto"),
        "en_curso": sum(1 for f in sel if f["estado"] == "En curso"),
        "sin_correccion": sum(1 for f in sel if f["estado"] == "No se corregirá"),
        "reclamos": sum(1 for f in sel if f["tipo"] == "Reclamo"),
        "consultas": sum(1 for f in sel if f["tipo"] == "Consulta"),
        "sin_obra": len(sin_obra),
        "sin_obra_lista": sorted({f["proyecto_declarado"] for f in sin_obra}),
        "ambiguas": len(ambiguas),
    }
