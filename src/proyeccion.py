"""LA PROYECCIÓN DE COBRANZA · de hoy a fin de año, mes por mes."""
from __future__ import annotations

import pandas as pd

from . import flujo_caja, ingest

DIAS_MADURO = 180

MES = {1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril", 5: "Mayo",
       6: "Junio", 7: "Julio", 8: "Agosto", 9: "Setiembre", 10: "Octubre",
       11: "Noviembre", 12: "Diciembre"}


def _n(s) -> pd.Series:
    return pd.to_numeric(s, errors="coerce").fillna(0)


def calcular(anio: int | None = None) -> dict:
    hoy = pd.Timestamp.today().normalize()
    anio = anio or hoy.year

    inst = ingest.fetch_axion_entity("Installment", None, 5000)
    cred = ingest.fetch_axion_entity("Credit", None, 5000)
    sale = ingest.fetch_axion_entity("Sale", None, 5000)
    if inst.empty:
        return {"hay": False}

    vivos = (set(cred.loc[~cred["estado"].astype(str).str.lower()
                          .eq("cancelado"), "id"])
             if "estado" in cred.columns else set(cred["id"]))
    fv = pd.to_datetime(inst["fecha_vencimiento"], errors="coerce")
    falta = (_n(inst["monto_cuota"]) - _n(inst["monto_pagado"])).clip(lower=0)
    viva = inst["credit_id"].isin(vivos)

    dias = (hoy - fv).dt.days
    mad = viva & fv.lt(hoy) & dias.ge(DIAS_MADURO)
    venc_mad = float(_n(inst.loc[mad, "monto_cuota"]).sum())
    pag_mad = float(_n(inst.loc[mad, "monto_pagado"]).sum())
    efec = (pag_mad / venc_mad) if venc_mad else 0.0

    tod = viva & fv.lt(hoy)
    venc_tod = float(_n(inst.loc[tod, "monto_cuota"]).sum())
    pag_tod = float(_n(inst.loc[tod, "monto_pagado"]).sum())
    efec_apar = (pag_tod / venc_tod) if venc_tod else 0.0

    ix_cred = cred.set_index(cred["id"].astype(str)) if not cred.empty else cred

    def _quien(cid):
        try:
            r = ix_cred.loc[str(cid)]
        except (KeyError, TypeError):
            return ("—", "—", "—")
        if isinstance(r, pd.DataFrame):
            r = r.iloc[0]
        return (str(r.get("client_name") or "—"),
                str(r.get("project") or "—"),
                str(r.get("unit") or "—"))

    meses = []
    for m in range(hoy.month, 13):
        sel = viva & falta.gt(0) & fv.dt.year.eq(anio) & fv.dt.month.eq(m)
        if m == hoy.month:
            sel = sel & fv.ge(hoy)
        vence = float(falta[sel].sum())
        if not vence:
            continue
        det = []
        for i in inst.index[sel]:
            q, o, u = _quien(inst.at[i, "credit_id"])
            det.append({
                "fecha": str(pd.to_datetime(fv[i]).date()),
                "cliente": q, "obra": o, "unidad": u,
                "cuota": float(_n(pd.Series([inst.at[i, "monto_cuota"]])).iloc[0]),
                "pagado": float(_n(pd.Series([inst.at[i, "monto_pagado"]])).iloc[0]),
                "falta": float(falta[i]),
                "n": str(inst.at[i, "numero_cuota"]) if "numero_cuota" in inst.columns else "",
            })
        det.sort(key=lambda x: (x["fecha"], -x["falta"]))
        meses.append({
            "mes": m,
            "etiqueta": f"{MES[m]} {anio}" + (" · lo que resta" if m == hoy.month else ""),
            "cuotas": int(sel.sum()),
            "vence": vence,
            "en_fecha": vence,
            "al_ritmo": vence * efec,
            "detalle": det,
        })

    total_vence = sum(x["vence"] for x in meses)

    try:
        fl = flujo_caja.por_mes(anio)
    except Exception:  # noqa: BLE001 — el forecast no tumba el tablero
        fl = {"hay": False}
    ya_meses, ya_total, ya_futuro = [], 0.0, 0.0
    for f_ in (fl.get("meses") or []):
        if not f_.get("entro"):
            continue
        futuro = f_["mes"] > hoy.month
        ya_meses.append({
            "mes": f_["mes"],
            "etiqueta": f'{MES[f_["mes"]]} {anio}',
            "monto": float(f_["entro"]),
            "futuro": futuro,
        })
        if futuro:
            ya_futuro += float(f_["entro"])
        else:
            ya_total += float(f_["entro"])

    v = sale[sale["status"] == "Vendido"] if "status" in sale.columns else sale
    hip = v[v["modality"].astype(str).str.strip().str.lower().eq("hipoteca")]
    post = viva & falta.gt(0) & fv.dt.year.gt(anio)
    atras = viva & falta.gt(0) & fv.lt(hoy)

    return {
        "hay": bool(meses),
        "anio": anio,
        "desde": str(hoy.date()),
        "mes_hoy": int(hoy.month),
        "meses": meses,
        "ya": {
            "meses": ya_meses,
            "total": ya_total,
            "futuro": ya_futuro,            # cargado con fecha adelante
            "con_futuro": ya_total + ya_futuro,
        },
        "cierre": {
            "techo": ya_total + ya_futuro + total_vence,
            "al_ritmo": ya_total + ya_futuro + total_vence * efec,
        },
        "total": {
            "vence": total_vence,
            "en_fecha": total_vence,
            "al_ritmo": total_vence * efec,
            "cuotas": sum(x["cuotas"] for x in meses),
        },
        "efectividad": {
            "usada": 100 * efec,
            "aparente": 100 * efec_apar,
            "dias_maduro": DIAS_MADURO,
            "cuotas_maduras": int(mad.sum()),
            "vencio_maduro": venc_mad,
            "cobro_maduro": pag_mad,
        },
        "fuera": {
            "hipotecas": {"ventas": int(len(hip)),
                          "monto": float(_n(hip["sale_price"]).sum())},
            "despues": {"cuotas": int(post.sum()),
                        "monto": float(falta[post].sum())},
            "atrasado": {"cuotas": int(atras.sum()),
                         "monto": float(falta[atras].sum())},
        },
    }
