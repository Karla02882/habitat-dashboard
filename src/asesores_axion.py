"""INGESTA · LAS VISITAS QUE LLEVA COMERCIAL EN AXION."""
from __future__ import annotations

import unicodedata

from . import ingest, periodo

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
_ALIAS = {"setiembre": "septiembre"}


def _sin_tildes(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", str(s or ""))
                   if unicodedata.category(c) != "Mn").upper().strip()


def _del_anio(dic, anio: int, mes: int | None):
    """Lo que ese diccionario anidado guarda para el año y el mes pedidos."""
    if not isinstance(dic, dict):
        return []
    por_anio = dic.get(str(anio)) or dic.get(anio)
    if not isinstance(por_anio, dict):
        return []
    if mes is None:
        return [por_anio.get(m) for m in MESES if por_anio.get(m) is not None]
    nom = MESES[mes - 1]
    v = por_anio.get(nom)
    if v is None:
        v = por_anio.get(_ALIAS.get(nom, nom))
    return [] if v is None else [v]


def por_asesor(anio: int | None = None, mes: int | None = None) -> dict:
    """Agendas, visitas y leads propios por asesor, según AXION."""
    anio = anio or periodo.ANIO
    try:
        a = ingest.fetch_axion_entity("Advisor", None, 500)
    except Exception as e:  # noqa: BLE001 — sin AXION la hoja lo declara
        return {"hay": False, "motivo": f"no se pudo leer Advisor: {type(e).__name__}"}
    if a is None or a.empty:
        return {"hay": False, "motivo": "AXION no devolvió asesores"}

    filas = []
    for _, r in a.iterrows():
        nom = str(r.get("name") or "").strip()
        if not nom:
            continue
        md = _del_anio(r.get("monthly_data"), anio, mes)
        ag = sum(int(x.get("agendas") or 0) for x in md if isinstance(x, dict))
        vi = sum(int(x.get("visitas") or 0) for x in md if isinstance(x, dict))
        lp = _del_anio(r.get("own_leads_monthly"), anio, mes)
        filas.append({
            "asesor": nom,
            "clave": _sin_tildes(nom),
            "activo": bool(r.get("active")),
            "agendas": ag if md else None,
            "visitas": vi if md else None,
            "leads_propios": sum(int(x or 0) for x in lp) if lp else None,
            "pct_visitas": (round(100 * vi / ag, 1) if ag else None),
        })
    con = [f for f in filas if f["agendas"] is not None]
    return {
        "hay": bool(con),
        "anio": anio, "mes": mes,
        "asesores": sorted(filas, key=lambda x: -(x["agendas"] or 0)),
        "con_carga": len(con), "total": len(filas),
        "fuente": "AXION · módulo Comercial → Asesores (lo carga Comercial a mano)",
        "motivo": "" if con else "ningún asesor tiene visitas cargadas en AXION",
    }
