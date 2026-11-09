"""LA BITÁCORA DE OBRA."""

from __future__ import annotations

import html
import re

import pandas as pd

from . import ingest

CATEGORIAS = [
    ("workers_supervisor", "Supervisores"),
    ("workers_operarios", "Operarios"),
    ("workers_assistant", "Ayudantes"),
    ("workers_peon", "Peones"),
    ("workers_admin", "Administrativos"),
]


def _num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce").fillna(0)


_ETIQUETA = re.compile(r"<[^>]+>")
_SALTO = re.compile(r"</p\s*>|<br\s*/?>|</div\s*>|</li\s*>|</h[1-6]\s*>", re.I)


def _sin_html(x) -> str:
    v = "" if x is None else str(x)
    if "<" not in v and "&" not in v:
        return v
    t = _SALTO.sub("\n", v)
    t = _ETIQUETA.sub("", t)
    t = html.unescape(t).replace("\xa0", " ")
    lineas = [" ".join(l.split()) for l in t.split("\n")]
    return "\n".join(l for l in lineas if l)


def _txt(x, tope: int = 0) -> str:
    v = "" if x is None else str(x).strip()
    if v.lower() in ("nan", "none"):
        v = ""
    return v[:tope] if tope and len(v) > tope else v


def _val(x):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return None if pd.isna(v) else v


def _tipos_de_proyecto() -> dict:
    """El tipo de cada proyecto, de la tabla `Project`."""
    try:
        pr = ingest.fetch_axion_entity("Project", None, 500)
    except Exception:  # noqa: BLE001
        return {}
    if pr is None or pr.empty or "project_type" not in pr.columns:
        return {}
    out = {}
    for r in pr.itertuples():
        nom = _txt(getattr(r, "name", "")).upper()
        tip = _txt(getattr(r, "project_type", ""))
        if nom and tip:
            out[nom] = tip
    return out


def tipo_de(nombre: str, tipos: dict) -> str:
    nom = _txt(nombre).upper()
    if not nom or nom == "(SIN PROYECTO)":
        return ""
    if nom in tipos:
        return tipos[nom]
    primera = re.split(r"[\s\-]+", nom, maxsplit=1)[0]
    if primera in ("CASA", "CASAS"):
        return "Casas"
    return "Otros"


def _plata(df: pd.DataFrame, proyecto: str, cols: list) -> list:
    """Las filas de `df` que son de ese proyecto, ya recortadas."""
    if df is None or df.empty or "project_name" not in df.columns:
        return []
    sub = df[df["project_name"].fillna("").astype(str).str.strip() == proyecto]
    return [[f(r) for _, f in cols] for r in sub.itertuples()]


def calcular() -> dict:
    """La bitácora por proyecto, con sus contratos y cotizaciones."""
    try:
        b = ingest.fetch_axion_entity("BitacoraObra", None, 5000)
    except Exception as e:  # noqa: BLE001
        return {"hay": False, "motivo": f"no se pudo leer BitacoraObra: {type(e).__name__}"}
    if b is None or b.empty:
        return {"hay": False, "motivo": "AXION no devolvió partes de obra"}

    b = b.copy()
    b["zproy"] = b["project_name"].fillna("").astype(str).str.strip()
    b.loc[b["zproy"].eq(""), "zproy"] = "(sin proyecto)"
    b["zfecha"] = b["date"].fillna("").astype(str).str.slice(0, 10)
    for c, _rot in CATEGORIAS:
        b["z_" + c] = _num(b[c]) if c in b.columns else 0
    b["ztrab"] = sum(b["z_" + c] for c, _ in CATEGORIAS)

    try:
        con = ingest.fetch_axion_entity("Contrato", None, 2000)
    except Exception:  # noqa: BLE001
        con = None
    try:
        cot = ingest.fetch_axion_entity("Cotizacion", None, 2000)
    except Exception:  # noqa: BLE001
        cot = None

    COLS_CON = [
        ("Contratista", lambda r: _txt(getattr(r, "contractor", ""), 46) or "—"),
        ("Estado", lambda r: _txt(getattr(r, "status", ""), 20) or "—"),
        ("Acordado", lambda r: _txt(getattr(r, "agreement_date", ""))[:10] or "—"),
        ("Días", lambda r: _val(getattr(r, "duration_days", None))),
        ("Monto S/", lambda r: _val(getattr(r, "amount_soles", None))),
        ("Adelanto S/", lambda r: _val(getattr(r, "advance_soles", None))),
    ]
    COLS_COT = [
        ("Partida", lambda r: (_txt(getattr(r, "partida", ""), 40)
                               or _txt(getattr(r, "description", ""), 40) or "—")),
        ("Proveedor", lambda r: _txt(getattr(r, "provider", ""), 34) or "—"),
        ("Estado", lambda r: _txt(getattr(r, "status", ""), 20) or "—"),
        ("F. Inicio", lambda r: _txt(getattr(r, "start_date", ""))[:10] or "—"),
        ("F. Fin", lambda r: _txt(getattr(r, "end_date", ""))[:10] or "—"),
        ("Servicios", lambda r: _txt(getattr(r, "servicios_incluidos", ""), 60) or "—"),
        ("Monto S/", lambda r: _val(getattr(r, "amount_soles", None))),
    ]
    iMontoCon = [c for c, _ in COLS_CON].index("Monto S/")
    iMontoCot = [c for c, _ in COLS_COT].index("Monto S/")

    tipos = _tipos_de_proyecto()
    proyectos = []
    for nombre, g in b.groupby("zproy", sort=True):
        dias = []
        for r in g.sort_values("zfecha", ascending=False).itertuples():
            porcat = [int(getattr(r, "z_" + c, 0) or 0) for c, _ in CATEGORIAS]
            dias.append({
                "fecha": r.zfecha,
                "que": _txt(_sin_html(getattr(r, "description", "")), 900) or "—",
                "quien": _txt(getattr(r, "reported_by", ""), 44) or "—",
                "clima": _txt(getattr(r, "weather", ""), 20),
                "trab": int(getattr(r, "ztrab", 0) or 0),
                "cat": porcat,
                "fotos": len(getattr(r, "photo_urls", None) or []),
                "urls": [u for u in (getattr(r, "photo_urls", None) or [])
                         if isinstance(u, str) and u.startswith("http")],
                "nota": _txt(getattr(r, "notes", ""), 300),
            })
        fechas = [d["fecha"] for d in dias if d["fecha"]]
        conT = _plata(con, nombre, COLS_CON)
        cotT = _plata(cot, nombre, COLS_COT)
        proyectos.append({
            "proyecto": nombre,
            "tipo": tipo_de(nombre, tipos),
            "partes": len(dias),
            "desde": min(fechas) if fechas else "",
            "hasta": max(fechas) if fechas else "",
            "trab_max": max((d["trab"] for d in dias), default=0),
            "trab_prom": round(sum(d["trab"] for d in dias) / len(dias), 1) if dias else 0,
            "con_gente": sum(1 for d in dias if d["trab"] > 0),
            "fotos": sum(d["fotos"] for d in dias),
            "dias": dias,
            "contratos": conT,
            "cotizaciones": cotT,
            "con_monto": sum(x[iMontoCon] or 0 for x in conT),
            "cot_monto": sum(x[iMontoCot] or 0 for x in cotT),
        })

    proyectos.sort(key=lambda p: -p["partes"])
    fechas = [f for p in proyectos for f in (p["desde"], p["hasta"]) if f]
    conocidos = {p["proyecto"] for p in proyectos}
    def _fuera(df):
        if df is None or df.empty or "project_name" not in df.columns:
            return 0
        n = df["project_name"].fillna("").astype(str).str.strip()
        return int((~n.isin(conocidos)).sum())
    return {
        "hay": True,
        "proyectos": proyectos,
        "categorias": [rot for _c, rot in CATEGORIAS],
        "tipos": [x for x in ("Lotes", "Departamentos", "Casas", "Oficinas", "Otros")
                  if any(p["tipo"] == x for p in proyectos)],
        "totales": {
            "proyectos": len(proyectos),
            "partes": sum(p["partes"] for p in proyectos),
            "desde": min(fechas) if fechas else "",
            "hasta": max(fechas) if fechas else "",
            "contratos": sum(len(p["contratos"]) for p in proyectos),
            "cotizaciones": sum(len(p["cotizaciones"]) for p in proyectos),
        },
        "cols_contrato": [r for r, _f in COLS_CON],
        "cols_cotizacion": [r for r, _f in COLS_COT],
        "contratos_fuera": _fuera(con),
        "cotizaciones_fuera": _fuera(cot),
    }


def pagos_personal() -> dict:
    try:
        df = ingest.fetch_axion_entity("PagoPersonal", None, 5000)
    except Exception as e:  # noqa: BLE001
        return {"hay": False, "motivo": f"no se pudo leer PagoPersonal: {type(e).__name__}"}
    if df is None or df.empty:
        return {"hay": False, "motivo": "AXION no devolvió partidas de Pagos a Personal"}

    tipos = _tipos_de_proyecto()
    contratistas = {_txt(x).upper() for x in df.get("contractor", pd.Series(dtype=str))
                    if _txt(x)}
    proyectos: dict[str, dict] = {}
    for r in df.itertuples():
        proy = _txt(getattr(r, "project_name", "")) or "(sin proyecto)"
        total = _val(getattr(r, "monto_total", None)) or 0.0
        pagos = []
        for x in (getattr(r, "payments", None) or []):
            if not isinstance(x, dict):
                continue
            pagos.append([_txt(x.get("fecha"))[:10],
                          _val(x.get("p_anterior")), _val(x.get("p_actual")),
                          _val(x.get("p_acumulado")), _val(x.get("saldo"))])
        pagos.sort(key=lambda q: q[0])
        pagado = round(sum(q[2] or 0 for q in pagos), 2)
        partida = _txt(getattr(r, "partida", ""), 80) or "—"
        obs = []
        if pagado - total > 0.005:
            obs.append(f"pagado supera el total en S/ {pagado - total:,.2f}")
        mal_saldo = sum(1 for q in pagos
                        if q[3] is not None and q[4] is not None
                        and abs(total - q[3] - q[4]) > 0.005)
        if mal_saldo:
            obs.append(f"{mal_saldo} pago{'s' if mal_saldo != 1 else ''} con saldo "
                       f"distinto de total − acumulado")
        ult = max((q[3] or 0 for q in pagos), default=0.0)
        if pagos and abs(ult - pagado) > 0.005:
            obs.append(f"los pagos suman S/ {pagado:,.2f} y el acumulado dice "
                       f"S/ {ult:,.2f}")
        if partida.upper() in contratistas:
            obs.append("la partida trae el nombre de un contratista")
        p = proyectos.setdefault(proy, {"proyecto": proy, "tipo": tipo_de(proy, tipos),
                                        "partidas": []})
        p["partidas"].append({
            "partida": partida,
            "contratista": _txt(getattr(r, "contractor", ""), 60) or "—",
            "estado": _txt(getattr(r, "estado", "")) or "sin estado",
            "total": round(total, 2),
            "pagado": pagado,
            "saldo": round(total - pagado, 2),
            "pagos": pagos,
            "obs": obs,
        })
    out = []
    for nom in sorted(proyectos):
        p = proyectos[nom]
        p["partidas"].sort(key=lambda x: x["partida"])
        p["total"] = round(sum(x["total"] for x in p["partidas"]), 2)
        p["pagado"] = round(sum(x["pagado"] for x in p["partidas"]), 2)
        p["saldo"] = round(p["total"] - p["pagado"], 2)
        out.append(p)
    estados = sorted({x["estado"] for p in out for x in p["partidas"]})
    return {
        "hay": True,
        "proyectos": out,
        "estados": estados,
        "totales": {
            "proyectos": len(out),
            "partidas": sum(len(p["partidas"]) for p in out),
            "pagos": sum(len(x["pagos"]) for p in out for x in p["partidas"]),
            "total": round(sum(p["total"] for p in out), 2),
            "pagado": round(sum(p["pagado"] for p in out), 2),
            "saldo": round(sum(p["saldo"] for p in out), 2),
            "con_obs": sum(1 for p in out for x in p["partidas"] if x["obs"]),
        },
    }
