"""INDICADORES DE OPERACIÓN · lo que sale de AXION todos los días, por obra."""
from __future__ import annotations

import pandas as pd

from . import ingest, movimientos, reloj


def _t(v) -> str:
    return "" if v is None or (isinstance(v, float) and v != v) else str(v).strip()


def _n(s) -> pd.Series:
    return pd.to_numeric(s, errors="coerce").fillna(0.0)


def calcular() -> dict:
    hoy = pd.Timestamp(reloj.ahora().date())

    u = ingest.fetch_axion_entity("Unit", None, 5000)
    u = u.assign(obra=u["project"].apply(_t), st=u["status"].apply(_t).str.upper())
    stock = []
    for obra, g in u.groupby("obra"):
        stock.append({"obra": obra or "(sin obra)", "unidades": int(len(g)),
                      "vendidas": int(g["st"].eq("VENDIDO").sum()),
                      "libres": int(g["st"].eq("LIBRE").sum()),
                      "bloqueadas": int(g["st"].eq("BLOQUEADO").sum())})

    s = ingest.fetch_axion_entity("Sale", None, 5000)
    s = s[s["status"].apply(_t).eq("Vendido")].copy()
    s["f"] = pd.to_datetime(s["date"], errors="coerce")
    s = s[s["f"].notna()]
    s["mes"] = s["f"].dt.strftime("%Y-%m")
    s["obra"] = s["project"].apply(_t)
    s["monto"] = _n(s["sale_price"])
    ventas = [{"mes": m, "obra": o or "(sin obra)", "n": int(len(g)),
               "monto": round(float(g["monto"].sum()), 2)}
              for (m, o), g in s.groupby(["mes", "obra"])]

    i = ingest.fetch_axion_entity("Installment", None, 5000)
    c = ingest.fetch_axion_entity("Credit", None, 5000)
    c = c.assign(credit_id=c["id"], obra=c["project"].apply(_t))[["credit_id", "obra"]]
    i = i.merge(c, on="credit_id", how="left")
    i["obra"] = i["obra"].fillna("").apply(_t)
    i["v"] = pd.to_datetime(i["fecha_vencimiento"], errors="coerce")
    i["saldo"] = (_n(i["monto_cuota"]) - _n(i["monto_pagado"])).clip(lower=0)
    _borrada_vencida = ~ingest.con_credito(i) & (i["v"] < hoy)
    pend = i[i["estado"].apply(_t).eq("pendiente") & ~_borrada_vencida]
    cuotas = []
    for obra, g in pend.groupby("obra"):
        venc = g[g["v"] < hoy]
        cuotas.append({"obra": obra or "(sin obra)",
                       "pendientes": int(len(g)),
                       "saldo": round(float(g["saldo"].sum()), 2),
                       "vencidas": int(len(venc)),
                       "saldo_vencido": round(float(venc["saldo"].sum()), 2)})

    mv = movimientos.crudo()
    mv = mv[mv["clase"].isin(["venta", "gasto"]) & mv["fecha_n"].notna()].copy()
    mv["mes"] = mv["fecha_n"].dt.strftime("%Y-%m")
    mv["obra"] = mv["proyecto"].apply(_t)
    caja = []
    for (m, o), g in mv.groupby(["mes", "obra"]):
        caja.append({"mes": m, "obra": o or "(sin obra)",
                     "entradas": round(float(g.loc[g["clase"].eq("venta"), "monto_n"].sum()), 2),
                     "salidas": round(float(g.loc[g["clase"].eq("gasto"), "monto_n"].sum()), 2)})

    return {"hay": True, "hoy": str(hoy.date()), "stock": stock,
            "ventas": ventas, "cuotas": cuotas, "caja": caja}
