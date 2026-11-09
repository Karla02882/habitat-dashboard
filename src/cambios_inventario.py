"""LOS CAMBIOS DE STOCK Y DE PRECIO."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from . import ingest, reloj

TOPE_EVENTOS = 5000
DIAS_VENTAS = 30
FRACCION_MINIMA = 0.5


def _t(x) -> str:
    v = "" if x is None else str(x).strip()
    return "" if v.lower() in ("nan", "none", "nat", "<na>") else v


def _precio(x):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return None if v != v else round(v, 2)


def foto_de(u: pd.DataFrame) -> dict:
    """{id: [unidad, proyecto, ESTADO, precio, m²]} de cada unidad."""
    out = {}
    for r in u.itertuples():
        uid = _t(getattr(r, "id", ""))
        if not uid:
            continue
        est = _t(getattr(r, "status", "")).upper() or "(SIN ESTADO)"
        out[uid] = [_t(getattr(r, "name", "")), _t(getattr(r, "project", "")), est,
                    _precio(getattr(r, "real_price", None)),
                    _precio(getattr(r, "area_m2", None))]
    return out


def comparar(antes: dict, ahora: dict, t: str) -> list[dict]:
    """Los cambios entre dos fotos, ordenados por proyecto y unidad."""
    ev = []
    for uid, d in ahora.items():
        a = antes.get(uid)
        if a is None:
            ev.append({"t": t, "id": uid, "u": d[0], "p": d[1], "k": "alta", "a": None, "d": d[2]})
            continue
        if a[2] != d[2]:
            ev.append({"t": t, "id": uid, "u": d[0], "p": d[1], "k": "estado", "a": a[2], "d": d[2]})
        pa, pd_ = a[3], d[3]
        if pa is None and pd_ is not None:
            ev.append({"t": t, "id": uid, "u": d[0], "p": d[1], "k": "precio_carga", "a": None, "d": pd_})
        elif pa is not None and pd_ is None:
            ev.append({"t": t, "id": uid, "u": d[0], "p": d[1], "k": "precio_quita", "a": pa, "d": None})
        elif pa is not None and pd_ is not None and abs(pa - pd_) >= 0.005:
            ev.append({"t": t, "id": uid, "u": d[0], "p": d[1], "k": "precio", "a": pa, "d": pd_})
    for uid, a in antes.items():
        if uid not in ahora:
            ev.append({"t": t, "id": uid, "u": a[0], "p": a[1], "k": "baja", "a": a[2], "d": None})
    ev.sort(key=lambda e: (e["p"], e["u"], e["k"]))
    return ev


def ventas_recientes(u: pd.DataFrame, hoy: pd.Timestamp) -> list[list]:
    """Las unidades VENDIDAS con fecha de venta en los últimos 30 días, que es."""
    if u.empty or "sale_date" not in u.columns:
        return []
    est = u["status"].fillna("").astype(str).str.strip().str.upper()
    sd = pd.to_datetime(u["sale_date"], errors="coerce").dt.normalize()
    ok = est.eq("VENDIDO") & sd.notna() & (sd >= hoy - pd.Timedelta(days=DIAS_VENTAS)) & (sd <= hoy)
    filas = []
    for r in u[ok].assign(fv=sd[ok]).sort_values("fv", ascending=False).itertuples():
        filas.append([r.fv.strftime("%Y-%m-%d"), _t(getattr(r, "project", "")),
                      _t(getattr(r, "name", "")), _precio(getattr(r, "real_price", None))])
    return filas


def _leer(ruta: Path) -> dict:
    try:
        d = json.loads(ruta.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def actualizar(ruta: Path, u: pd.DataFrame | None = None) -> dict:
    """Lee `Unit`, la compara contra la foto de `ruta` y reescribe `ruta`."""
    if u is None:
        u = ingest.fetch_axion_entity("Unit", None, 5000)
    if u is None or u.empty or "id" not in u.columns or "status" not in u.columns:
        raise ValueError("AXION no devolvió unidades")
    ahora = foto_de(u)
    if not ahora:
        raise ValueError("AXION devolvió unidades sin identificador")
    t = reloj.sello("%Y-%m-%d %H:%M")
    prev = _leer(ruta)
    antes = prev.get("foto") or {}
    eventos = list(prev.get("eventos") or [])
    base = prev.get("base") or t
    if antes:
        if len(ahora) < FRACCION_MINIMA * len(antes):
            raise ValueError(f"lectura incompleta: {len(ahora)} unidades contra {len(antes)} "
                             f"de la anterior; no se toca el registro")
        eventos = (eventos + comparar(antes, ahora, t))[-TOPE_EVENTOS:]
    estados = {}
    for v in ahora.values():
        estados[v[2]] = estados.get(v[2], 0) + 1
    datos = {
        "hay": True,
        "base": base,
        "ultima": t,
        "unidades": len(ahora),
        "estados": dict(sorted(estados.items())),
        "eventos": eventos,
        "ventas": ventas_recientes(u, pd.Timestamp(reloj.ahora().date())),
        "foto": ahora,
    }
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tmp = ruta.with_suffix(".tmp")
    tmp.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
    tmp.replace(ruta)
    return datos
