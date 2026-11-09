"""ENTRE CUENTAS DEL GRUPO · la plata que se movió de bolsillo, con TODO el."""
from __future__ import annotations

import re

import pandas as pd

from . import movimientos

SALDO = re.compile(r"\bsaldo\b", re.I)


def _n(s) -> pd.Series:
    return pd.to_numeric(s, errors="coerce").fillna(0)


def _limpio(x) -> str:
    s = str(x).strip()
    return "" if s.lower() in ("", "nan", "none", "nat") else s


def calcular(anio: int | None = None) -> dict:
    df = movimientos.crudo()
    if df.empty:
        return {"hay": False}
    f = pd.to_datetime(df["fecha"], errors="coerce")
    anio = anio or int(pd.Timestamp.today().year)
    tipo = df["tipo_movimiento"].fillna("").astype(str).str.strip()

    sel = df[f.dt.year.eq(anio) & tipo.eq("Ingreso") & df["clase"].eq("presupuesto")].copy()
    if not len(sel):
        return {"hay": False, "anio": anio}
    sel["f"] = pd.to_datetime(sel["fecha"], errors="coerce")
    sel["m"] = _n(sel["monto"])
    sel["es_saldo"] = sel["concepto"].fillna("").astype(str).str.contains(SALDO)

    MES = {1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril", 5: "Mayo",
           6: "Junio", 7: "Julio", 8: "Agosto", 9: "Setiembre", 10: "Octubre",
           11: "Noviembre", 12: "Diciembre"}

    filas = []
    for _, r in sel.sort_values("m", ascending=False).iterrows():
        filas.append({
            "fecha": str(r["f"].date()) if pd.notna(r["f"]) else "",
            "mes": int(r["f"].month) if pd.notna(r["f"]) else 0,
            "mes_nom": MES.get(int(r["f"].month), "") if pd.notna(r["f"]) else "",
            "monto": float(r["m"]),
            "concepto": _limpio(r.get("concepto")) or "—",
            "cuenta": _limpio(r.get("cuenta")),
            "rotulo": _limpio(r.get("movimiento")) or "—",
            "obra": _limpio(r.get("proyecto")),
            "tipo": "saldo de apertura" if r["es_saldo"] else "transferencia",
        })

    def _tot(sub):
        return {"filas": int(len(sub)), "monto": float(sub["m"].sum())}

    por_mes = []
    for mm in sorted(sel["f"].dt.month.dropna().unique()):
        g = sel[sel["f"].dt.month.eq(mm)]
        por_mes.append({
            "mes": int(mm), "etiqueta": f"{MES[int(mm)]} {anio}",
            "filas": int(len(g)), "monto": float(g["m"].sum()),
            "saldos": float(g.loc[g["es_saldo"], "m"].sum()),
            "transferencias": float(g.loc[~g["es_saldo"], "m"].sum()),
        })

    cuentas = []
    con = sel[sel["cuenta"].apply(_limpio).ne("")] if "cuenta" in sel.columns else sel.iloc[0:0]
    if len(con):
        for k, g in con.groupby(con["cuenta"].apply(_limpio)):
            cuentas.append({"cuenta": k, "filas": int(len(g)),
                            "monto": float(g["m"].sum())})
        cuentas.sort(key=lambda x: -x["monto"])

    sin_cuenta = _tot(sel[~sel["cuenta"].apply(_limpio).ne("")])

    uni = sel["concepto"].fillna("").astype(str).str.contains(
        r"dpto|depto|lote|casa|cochera", case=False, regex=True, na=False)
    sospechosas = [{
        "fecha": str(r["f"].date()) if pd.notna(r["f"]) else "",
        "monto": float(r["m"]),
        "concepto": _limpio(r.get("concepto")) or "—",
    } for _, r in sel[uni].sort_values("m", ascending=False).iterrows()]

    return {
        "hay": True,
        "anio": anio,
        "total": _tot(sel),
        "saldos": _tot(sel[sel["es_saldo"]]),
        "transferencias": _tot(sel[~sel["es_saldo"]]),
        "por_mes": por_mes,
        "cuentas": cuentas,
        "sin_cuenta": sin_cuenta,
        "sospechosas": sospechosas,
        "detalle": filas,
    }
