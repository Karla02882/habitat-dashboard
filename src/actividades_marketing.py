"""LAS ACTIVIDADES DEL EQUIPO DE MARKETING."""
from __future__ import annotations

import pandas as pd

from . import ingest


def _t(x, tope: int = 0) -> str:
    v = "" if x is None else str(x).strip()
    if v.lower() in ("nan", "none", "nat"):
        v = ""
    return v[:tope] if tope and len(v) > tope else v


def calcular() -> dict:
    try:
        df = ingest.fetch_axion_entity("MarketingActivity", None, 5000)
    except Exception as e:  # noqa: BLE001
        return {"hay": False, "motivo": f"no se pudo leer MarketingActivity: {type(e).__name__}"}
    if df is None or df.empty:
        return {"hay": False, "motivo": "AXION no devolvió actividades de Marketing"}

    df = df.copy()
    df["zfecha"] = df["start_date"].map(lambda x: _t(x)[:10])
    df = df[df["zfecha"].str.match(r"^\d{4}-\d{2}-\d{2}$")]
    cuenta = df["responsible"].map(_t).replace("", "(sin responsable)").value_counts()

    dic: dict[str, list] = {"resp": list(cuenta.index), "tipo": [], "cont": [], "emp": []}
    idx = {k: {v: i for i, v in enumerate(dic[k])} for k in dic}

    def _i(campo: str, valor: str) -> int:
        if valor not in idx[campo]:
            idx[campo][valor] = len(dic[campo])
            dic[campo].append(valor)
        return idx[campo][valor]

    filas = []
    for r in df.sort_values(["zfecha", "time_from"], ascending=[False, True],
                            na_position="last").itertuples():
        filas.append([
            r.zfecha,
            _i("resp", _t(getattr(r, "responsible", "")) or "(sin responsable)"),
            _t(getattr(r, "name", ""), 140),
            _i("tipo", _t(getattr(r, "activity_type", ""))),
            _i("cont", _t(getattr(r, "content_type", ""))),
            _i("emp", _t(getattr(r, "company", ""))),
            _t(getattr(r, "time_from", ""), 5),
            _t(getattr(r, "time_to", ""), 5),
        ])
    fechas = [f[0] for f in filas]
    return {"hay": True, **dic, "f": filas, "total": len(filas),
            "desde": min(fechas) if fechas else "", "hasta": max(fechas) if fechas else ""}
