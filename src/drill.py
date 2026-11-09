"""DRILL-THROUGH."""
from __future__ import annotations

from datetime import date

import pandas as pd

from . import ingest, periodo


def _txt(v, vacio: str = "") -> str:
    s = str(v).strip()
    return vacio if s.lower() in ("", "nan", "none", "nat", "<na>") else s

HOY = pd.Timestamp(date.today())


def _n(s) -> pd.Series:
    return pd.to_numeric(s, errors="coerce").fillna(0)


def _mes(df: pd.DataFrame, col: str, mes) -> pd.DataFrame:
    return periodo.recortar(df, col, mes)


_DESCARTES: list[dict] = []


def _iniciales(cred: pd.DataFrame) -> pd.DataFrame:
    """Las iniciales de todos los creditos, UNA VEZ CADA UNA."""
    filas = []
    vistos: set = set()
    _DESCARTES.clear()
    for _, c in cred.iterrows():
        if not isinstance(c["iniciales"], list):
            continue
        for e in c["iniciales"]:
            if not isinstance(e, dict):
                continue
            if "pendiente" in str(e.get("tipo") or "").lower():
                continue
            try:
                m = float(str(e.get("monto", "0")).replace(",", ""))
            except ValueError:
                continue
            k = ingest.clave_inicial(e, c)
            if k in vistos:
                _DESCARTES.append({"fecha": str(e.get("fecha", ""))[:10],
                                   "obra": _txt(c["project"]),
                                   "unidad": _txt(c.get("unit"), "—"),
                                   "monto": m})
                continue
            vistos.add(k)
            filas.append({"tipo": "inicial", "fecha": str(e.get("fecha", ""))[:10],
                          "obra": c["project"], "quien": c["client_name"],
                          "unidad": _txt(c.get("unit"), "—"),
                          "ref": str(e.get("serie", "")) or str(e.get("empresa", "")),
                          "monto": m})
    return pd.DataFrame(filas)


def vendido(mes=None) -> dict:
    s = ingest.fetch_axion_entity("Sale", None, 5000)
    v = _mes(s[s["status"] == "Vendido"], "date", mes).copy()
    v["monto"] = _n(v["sale_price"])
    return {
        "titulo": "Qué incluye «Vendido»",
        "regla": "solo Sale con estado «Vendido». Separación y Devolución no "
                 "son venta y quedan fuera",
        "por": ("Obra", v.groupby("project")["monto"].agg(["size", "sum"])),
        "cols": ["Fecha", "Obra", "Unidad", "Cliente", "Asesor", "Monto"],
        "filas": [[str(r["date"])[:10], r["project"], r["unit"], r["client"],
                   r["advisor"], r["monto"]]
                  for _, r in v.sort_values("monto", ascending=False).iterrows()],
        "total": float(v["monto"].sum()),
    }


def cobrado(mes=None) -> dict:
    """Lo cobrado, fila por fila."""
    cred = ingest.fetch_axion_entity("Credit", None, 5000)
    cxc = ingest.fetch_axion_entity("CxCPayment", None, 5000)
    proy = ingest.fetch_axion_entity("Project", None, 5000)
    obra = dict(zip(cred["id"], cred["project"]))
    unid = dict(zip(cred["id"], cred["unit"]))
    tipo_obra = {_txt(n): _txt(t) for n, t in zip(proy["name"], proy["project_type"])}

    CORTO = {"Departamentos": "Depto", "Lotes": "Lote", "Casas": "Casa",
             "Oficinas": "Oficina"}

    def _tipo(o) -> str:
        t = tipo_obra.get(_txt(o), "")
        return CORTO.get(t, t) or "—"

    def _cap(v, n: int) -> str:
        t = _txt(v, "—")
        return t if len(t) <= n else t[:n - 1].rstrip() + "…"

    ini = _iniciales(cred)
    ini = _mes(ini, "fecha", mes) if len(ini) else ini
    cu = _mes(cxc, "fecha", mes).copy()
    cu["monto"] = _n(cu["monto"])
    filas = [["inicial", r["fecha"], r["obra"], _cap(r["unidad"], 28),
              _tipo(r["obra"]), _cap(r["quien"], 34), _cap(r["ref"], 24), r["monto"]]
             for _, r in ini.iterrows()] if len(ini) else []
    filas += [["cuota", str(r["fecha"])[:10], obra.get(r["credit_id"], "—"),
               _cap(unid.get(r["credit_id"]), 28), _tipo(obra.get(r["credit_id"], "")),
               _cap(r["client_name"], 34), _cap(r.get("notas", ""), 24), r["monto"]]
              for _, r in cu.iterrows()]
    filas.sort(key=lambda x: -x[-1])
    df = pd.DataFrame(filas, columns=["tipo", "fecha", "obra", "unidad",
                                      "tipo_unidad", "quien", "ref", "monto"])
    sin_u = int((df["unidad"].astype(str).str.strip().isin(("", "—", "nan"))).sum()) if len(df) else 0
    regla = ("la inicial de cada crédito (dentro de Credit.iniciales) más "
             "las cuotas de CxCPayment. Sin las iniciales, la cifra es "
             "una décima parte. La unidad la hereda del crédito; el tipo "
             "—departamento, casa, lote— es el de la OBRA, porque AXION no "
             "lo guarda en la unidad")
    if sin_u:
        regla += (f". {sin_u} de {len(df)} filas salen sin unidad: son cuotas "
                  f"cuyo crédito no está en Credit, así que no tienen de dónde "
                  f"heredarla — no se rellena, se muestra con raya")
    quitados = [x for x in _DESCARTES if periodo.contiene(x["fecha"], mes)]
    if quitados:
        obras = sorted({x["obra"] for x in quitados})
        regla += (f". Se descartaron {len(quitados)} recibos repetidos por "
                  f"S/ {sum(x['monto'] for x in quitados):,.2f} — mismo cliente, "
                  f"misma serie, mismo monto y misma fecha, en créditos que "
                  f"Habitat cargó dos veces ({', '.join(obras[:3])}"
                  f"{'…' if len(obras) > 3 else ''}). Cada uno cuenta UNA vez; "
                  f"cuál de los dos créditos vale lo decide Cobranzas")
    return {
        "titulo": "Qué incluye «Cobrado»",
        "regla": regla,
        "por": ("Concepto", df.groupby("tipo")["monto"].agg(["size", "sum"])
                if len(df) else None),
        "cols": ["Concepto", "Fecha", "Obra", "Unidad", "Tipo",
                 "Cliente", "Serie / caja", "Monto"],
        "filas": filas,
        "total": float(df["monto"].sum()) if len(df) else 0.0,
    }


def por_cobrar(mes=None) -> dict:
    c = ingest.fetch_axion_entity("Credit", None, 5000).copy()
    c["monto"] = _n(c["saldo_pendiente"])
    c = c[c["monto"] > 0]
    return {
        "titulo": "Qué incluye «Por cobrar»",
        "regla": "saldo_pendiente de cada crédito. Es un SALDO a hoy: el "
                 "filtro de mes no lo cambia",
        "por": ("Obra", c.groupby("project")["monto"].agg(["size", "sum"])),
        "cols": ["Obra", "Unidad", "Cliente", "Precio", "Estado", "Saldo"],
        "filas": [[r["project"], r["unit"], r["client_name"],
                   float(_n(pd.Series([r["precio_venta"]])).iloc[0]),
                   r["estado"], r["monto"]]
                  for _, r in c.sort_values("monto", ascending=False).iterrows()],
        "total": float(c["monto"].sum()),
    }


def vencido(mes=None) -> dict:
    i = ingest.fetch_axion_entity("Installment", None, 5000)
    cr = ingest.fetch_axion_entity("Credit", None, 5000)
    vivos = set(cr[~cr["estado"].astype(str).str.lower().eq("cancelado")]["id"])
    f = pd.to_datetime(i["fecha_vencimiento"], errors="coerce")
    falta = (_n(i["monto_cuota"]) - _n(i["monto_pagado"])).clip(lower=0)
    v = i[(f < HOY) & falta.gt(0) & i["credit_id"].isin(vivos)].copy()
    v["monto"] = falta[v.index]
    return {
        "titulo": "Qué incluye «De eso, ya vencido»",
        "regla": "cuotas de créditos vivos con fecha_vencimiento anterior a "
                 "hoy y plata por pagar, restando lo ya pagado. Es un saldo: "
                 "no depende del mes",
        "por": ("Cliente", v.groupby("client_name")["monto"].agg(["size", "sum"])),
        "cols": ["Vencimiento", "Cliente", "Cuota", "Monto cuota", "Pagado", "Falta"],
        "filas": [[str(r["fecha_vencimiento"])[:10], r["client_name"],
                   f'{r["numero_cuota"]:.0f}', float(r["monto_cuota"]),
                   float(r["monto_pagado"]), r["monto"]]
                  for _, r in v.sort_values("monto", ascending=False).iterrows()],
        "total": float(v["monto"].sum()),
    }


def falta_vender(mes=None) -> dict:
    u = ingest.fetch_axion_entity("Unit", None, 5000)
    li = u[u["status"] == "LIBRE"].copy()
    li["monto"] = _n(li["real_price"]).where(_n(li["real_price"]) > 0,
                                             _n(li.get("catalog_price", pd.Series(0.0, index=li.index))))
    return {
        "titulo": "Stock de unidades disponibles",
        "por": ("Obra", li.groupby("project")["monto"].agg(["size", "sum"])),
        "cols": ["Obra", "Unidad", "Área m²", "Precio"],
        "filas": [[r["project"], r["name"],
                   float(_n(pd.Series([r["area_m2"]])).iloc[0]), r["monto"]]
                  for _, r in li.sort_values("monto", ascending=False).iterrows()],
        "total": float(li["monto"].sum()),
    }


def gasto(mes=None) -> dict:
    from . import movimientos
    g = movimientos.crudo()
    g = g[g["clase"] == "gasto"]
    g = periodo.recortar(g, "fecha", mes).copy()
    if g.empty:
        return {"titulo": "Qué incluye «Gasto registrado»",
                "regla": "sin movimientos de gasto en el período",
                "por": None,
                "cols": [], "filas": [], "total": 0.0}
    g["obra_txt"] = g["proyecto"].fillna("").astype(str).str.strip()
    return {
        "titulo": "Qué incluye «Gasto registrado»",
        "regla": "los movimientos de gasto del Registro de Movimientos de "
                 "AXION, donde Administración carga la caja. No incluye "
                 "presupuesto: eso es una previsión, no plata que salió.",
        "por": ("Categoría", g.groupby(
            g["categoria"].fillna("").astype(str).str.strip()
             .replace("", "(sin categoría)"))["monto_n"].agg(["size", "sum"])),
        "cols": ["Fecha", "Tipo", "Categoría", "Proyecto", "Cuenta",
                 "Concepto", "Monto"],
        "filas": [[f"{r.fecha_n:%Y-%m-%d}" if pd.notna(r.fecha_n) else "",
                   _txt(r.movimiento, "(sin tipo)"),
                   _txt(r.categoria, "(sin categoría)"),
                   _txt(r.obra_txt, "—"),
                   _txt(r.cuenta, "—"),
                   _txt(r.concepto, "")[:70],
                   float(r.monto_n)]
                  for r in g.sort_values("monto_n", ascending=False).itertuples()],
        "total": float(g["monto_n"].sum()),
    }


DRILLS = {
    "Vendido": vendido,
    "Cobrado": cobrado,
    "Por cobrar": por_cobrar,
    "De eso, ya vencido": vencido,
    "Falta vender": falta_vender,
    "Gasto registrado": gasto,
}


def verificar_cuadre(mes=None) -> list[str]:
    """El detalle tiene que sumar EXACTO la cifra que abre."""
    fallas = []
    for nombre, fn in DRILLS.items():
        d = fn(mes)
        suma = sum(f[-1] for f in d["filas"]) if d["filas"] else 0.0
        if abs(suma - d["total"]) > 0.01:
            fallas.append(f"{nombre}: las filas suman {suma:,.2f} y la cifra "
                          f"dice {d['total']:,.2f}")
    return fallas
