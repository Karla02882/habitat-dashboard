"""VENCIMIENTOS MES A MES."""
from __future__ import annotations

import pandas as pd

from . import ingest

MES = {1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril", 5: "Mayo",
       6: "Junio", 7: "Julio", 8: "Agosto", 9: "Setiembre", 10: "Octubre",
       11: "Noviembre", 12: "Diciembre"}


def _n(s) -> pd.Series:
    return pd.to_numeric(s, errors="coerce").fillna(0)


def por_mes(desde: str | None = None, hasta: str | None = None) -> list[dict]:
    """Un renglón por mes de vencimiento, del más viejo al más nuevo."""
    inst = ingest.fetch_axion_entity("Installment", None, 5000)
    cred = ingest.fetch_axion_entity("Credit", None, 5000)
    if inst.empty:
        return []

    f = pd.to_datetime(inst["fecha_vencimiento"], errors="coerce")
    obra_de_credito = dict(zip(cred["id"], cred["project"]))

    _cancelados = set(cred.loc[
        cred["estado"].astype(str).str.strip().str.lower().eq("cancelado"),
        "id"].astype(str))
    _existentes = set(cred["id"].astype(str))
    _cid = inst["credit_id"].astype(str)
    _viva = _cid.isin(_existentes) & ~_cid.isin(_cancelados)

    d = inst.assign(
        _f=f,
        _obra=inst["credit_id"].map(obra_de_credito).fillna("(sin obra)"),
        _cuota=_n(inst["monto_cuota"]),
        _pagado=_n(inst["monto_pagado"]),
        _viva=_viva)
    d = d[d["_f"].notna() & d["_viva"]]
    if desde:
        d = d[d["_f"] >= pd.Timestamp(desde)]
    if hasta:
        d = d[d["_f"] <= pd.Timestamp(hasta)]
    if d.empty:
        return []

    hoy = pd.Timestamp(pd.Timestamp.today().date())
    out = []
    for (anio, mes), g in d.groupby([d["_f"].dt.year, d["_f"].dt.month]):
        vencia = float(g["_cuota"].sum())
        cobrado = float(g["_pagado"].sum())
        # `min(cobrado, vencia)` no: si pagaron de más, hay que VERLO.
        falta = vencia - cobrado
        fin_mes = pd.Timestamp(year=int(anio), month=int(mes), day=1) \
            + pd.offsets.MonthEnd(0)
        out.append({
            "anio": int(anio), "mes": int(mes),
            "etiqueta": f"{MES[int(mes)]} {int(anio)}",
            "cuotas": int(len(g)),
            "vencia": vencia,
            "cobrado": cobrado,
            "falta": falta,
            "pct": (100 * cobrado / vencia) if vencia else 0.0,
            "pasado": bool(fin_mes < hoy),
            "obras": sorted({str(x) for x in g["_obra"]}),
        })
    return sorted(out, key=lambda r: (r["anio"], r["mes"]))


def fuera_de_la_vista() -> dict:
    """Cuánta cartera NO aparece en esta vista, y por qué. Sin esto, la tabla."""
    cred = ingest.fetch_axion_entity("Credit", None, 5000)
    inst = ingest.fetch_axion_entity("Installment", None, 5000)
    sin = cred[~cred["id"].isin(set(inst["credit_id"]))]
    return {"creditos": int(len(sin)),
            "saldo": float(_n(sin["saldo_pendiente"]).sum()),
            "total_creditos": int(len(cred))}


def composicion() -> dict:
    """DE QUÉ ESTÁ HECHA LA CARTERA."""
    cred = ingest.fetch_axion_entity("Credit", None, 5000)
    inst = ingest.fetch_axion_entity("Installment", None, 5000)
    hoy = pd.Timestamp.today().normalize()

    vivos = cred[cred["estado"].astype(str).str.lower() != "cancelado"]
    ids_vivos = set(vivos["id"])
    ids_todos = set(cred["id"])
    con_cuota = set(inst["credit_id"].dropna())

    venc = pd.to_datetime(inst["fecha_vencimiento"], errors="coerce")
    falta = (_n(inst["monto_cuota"]) - _n(inst["monto_pagado"])).clip(lower=0)
    pend = falta > 0
    de_vivo = inst["credit_id"].isin(ids_vivos)
    huerf = ~inst["credit_id"].isin(ids_todos)
    cancel = inst["credit_id"].isin(ids_todos - ids_vivos)

    def _s(sel):
        return {"cuotas": int(sel.sum()), "monto": float(falta[sel].sum())}

    ya = pend & (venc < hoy)
    fut = pend & (venc >= hoy)
    cartera_total = float(_n(vivos["saldo_pendiente"]).sum())
    vencido = _s(de_vivo & ya)
    porvencer = _s(de_vivo & fut)
    sin_cro = vivos[~vivos["id"].isin(con_cuota)]
    sin_cronograma = {"creditos": int(len(sin_cro)),
                      "monto": float(_n(sin_cro["saldo_pendiente"]).sum())}
    cuadra = cartera_total - vencido["monto"] - porvencer["monto"]         - sin_cronograma["monto"]

    # los créditos CON cronograma cuyo saldo no coincide con sus cuotas
    pend_cred = (inst[pend & de_vivo].assign(_f=falta[pend & de_vivo])
                 .groupby("credit_id")["_f"].sum().to_dict())
    descuadres = []
    for _, c in vivos[vivos["id"].isin(con_cuota)].iterrows():
        sal = float(pd.to_numeric(c["saldo_pendiente"], errors="coerce") or 0)
        cuo = float(pend_cred.get(c["id"], 0.0))
        if abs(sal - cuo) > 0.01:
            descuadres.append({
                "cliente": str(c.get("client_name") or "—"),
                "obra": str(c.get("project") or "—"),
                "saldo": sal, "cuotas": cuo, "dif": sal - cuo})
    descuadres.sort(key=lambda x: -abs(x["dif"]))

    return {
        "cartera": cartera_total,
        "creditos": int(len(vivos)),
        "vencido": vencido,
        "por_vencer": porvencer,
        "sin_cronograma": sin_cronograma,
        "descuadre": cuadra,
        "descuadres": descuadres,
        "fuera_cartera": {
            "futuro_huerfano": _s(huerf & fut),
            "vencido_cancelado": _s(cancel & ya),
            "futuro_cancelado": _s(cancel & fut),
        },
        # la lista para el panel que se abre al hacer clic
        "detalle_sin_cronograma": sorted(
            [{"cliente": str(c.get("client_name") or "—"),
              "obra": str(c.get("project") or "—"),
              "unidad": str(c.get("unit") or "—"),
              "estado": str(c.get("estado") or "—"),
              "inicio": str(c.get("fecha_inicio") or "")[:10],
              "cuotas_pactadas": int(pd.to_numeric(c.get("numero_cuotas"),
                                                   errors="coerce") or 0),
              "precio": float(pd.to_numeric(c.get("precio_total"),
                                            errors="coerce") or 0),
              "saldo": float(pd.to_numeric(c.get("saldo_pendiente"),
                                           errors="coerce") or 0)}
             for _, c in sin_cro.iterrows()],
            key=lambda x: -x["saldo"]),
    }


SIN_RS = "— sin razón social declarada en AXION —"


def cartera() -> dict:
    """LA CARTERA CONSOLIDADA, por razón social y por obra."""
    cred = ingest.fetch_axion_entity("Credit", None, 5000).copy()
    inst = ingest.fetch_axion_entity("Installment", None, 5000).copy()
    pag = ingest.fetch_axion_entity("CxCPayment", None, 5000).copy()
    proy = ingest.fetch_axion_entity("Project", None, 5000)

    de_obra = {}
    for _, p in proy.iterrows():
        rs = str(p.get("company_name") or "").strip()
        de_obra[str(p.get("name") or "").strip()] = rs if rs and rs.lower() != "nan" else SIN_RS

    for c in ("precio_total", "saldo_pendiente", "monto_financiado"):
        cred[c] = _n(cred[c])
    inst["mc"] = _n(inst["monto_cuota"])
    inst["mp"] = _n(inst["monto_pagado"])
    inst["fv"] = pd.to_datetime(inst["fecha_vencimiento"], errors="coerce")
    hoy = pd.Timestamp.today().normalize()
    inst["vencido"] = ((inst["fv"] < hoy) * (inst["mc"] - inst["mp"])).clip(lower=0)
    _vivo = ~inst["credit_id"].astype(str).isin(
        set(cred[cred["estado"].astype(str).str.lower() == "cancelado"]["id"].astype(str)))
    venc_por_credito = (inst[_vivo].groupby(inst.loc[_vivo, "credit_id"].astype(str))
                        ["vencido"].sum())
    pag["m"] = _n(pag["monto"])
    pag_por_credito = pag.groupby(pag["credit_id"].astype(str))["m"].sum()

    cred["obra"] = cred["project"].astype(str).str.strip()
    cred["rs"] = cred["obra"].map(de_obra).fillna(SIN_RS)
    cred["venc"] = cred["id"].astype(str).map(venc_por_credito).fillna(0.0)
    cred["pagado"] = cred["id"].astype(str).map(pag_por_credito).fillna(0.0)

    cred["_vivo"] = ~cred["estado"].astype(str).str.strip().str.lower().eq("cancelado")

    def _fila(nombre, g):
        return {
            "nombre": nombre,
            "creditos": int(len(g)),
            "creditos_vivos": int(g["_vivo"].sum()),
            "cartera": float(g["precio_total"].sum()),
            "saldo": float(g["saldo_pendiente"].sum()),
            "vencido": float(g["venc"].sum()),
            "pagado_cuotas": float(g["pagado"].sum()),
        }

    por_rs = [_fila(k, g) for k, g in cred.groupby("rs")]
    por_rs.sort(key=lambda r: -r["saldo"])
    for r in por_rs:
        r["obras"] = sorted({o for o, e in de_obra.items() if e == r["nombre"]
                             and o in set(cred["obra"])})

    por_obra = [dict(_fila(k, g), razon_social=de_obra.get(k, SIN_RS))
                for k, g in cred.groupby("obra")]
    por_obra.sort(key=lambda r: -r["saldo"])

    ids = set(cred["id"].astype(str))
    _ven_h = (inst["fv"] < hoy) & ((inst["mc"] - inst["mp"]) > 0)
    ih = inst[~inst["credit_id"].astype(str).isin(ids) & ~_ven_h]
    ph = pag[~pag["credit_id"].astype(str).isin(ids)]
    return {
        "por_razon_social": por_rs,
        "por_obra": por_obra,
        "total": _fila("TOTAL", cred),
        "sin_razon_social": SIN_RS,
        "obras_sin_rs": sorted(o for o, e in de_obra.items() if e == SIN_RS),
        "huerfanos": {
            "cuotas": int(len(ih)), "monto_cuotas": float(_n(ih["monto_cuota"]).sum()),
            "pagos": int(len(ph)), "monto_pagos": float(_n(ph["monto"]).sum()),
        },
    }
