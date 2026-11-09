"""EL DETALLE DETRÁS DE CADA CIFRA."""
from __future__ import annotations

from datetime import date

import pandas as pd

from . import ingest, rentabilidad

HOY = pd.Timestamp(date.today())


def _n(s) -> pd.Series:
    return pd.to_numeric(s, errors="coerce").fillna(0)


def ventas_cerradas() -> tuple[str, list[str], list[list]]:
    s = ingest.fetch_axion_entity("Sale", None, 5000)
    v = s[s["status"] == "Vendido"].copy()
    v["_p"] = _n(v["sale_price"])
    v = v.sort_values("_p", ascending=False)
    return (f"Las {len(v)} ventas con estado «Vendido» que suman el vendido",
            ["Fecha", "Obra", "Unidad", "Cliente", "Asesor", "Precio"],
            [[str(r["date"])[:10], r["project"], r["unit"], r["client"],
              r["advisor"], f'{r["_p"]:,.2f}'] for _, r in v.iterrows()])


def no_son_venta() -> tuple[str, list[str], list[list]]:
    s = ingest.fetch_axion_entity("Sale", None, 5000)
    o = s[s["status"] != "Vendido"].copy()
    o["_p"] = _n(o["sale_price"])
    return (f"Las {len(o)} filas de Sale que NO son venta y quedan fuera del total",
            ["Estado", "Fecha", "Obra", "Unidad", "Cliente", "Monto"],
            [[r["status"], str(r["date"])[:10], r["project"], r["unit"],
              r["client"], f'{r["_p"]:,.2f}'] for _, r in
             o.sort_values(["status", "_p"], ascending=[True, False]).iterrows()])


def cuotas_vencidas() -> tuple[str, list[str], list[list]]:
    i = ingest.fetch_axion_entity("Installment", None, 5000)
    venc = pd.to_datetime(i["fecha_vencimiento"], errors="coerce")
    v = i[(i["estado"] == "pendiente") & (venc < HOY) & ingest.con_credito(i)].copy()
    v["_falta"] = _n(v["monto_cuota"]) - _n(v["monto_pagado"])
    v = v.sort_values("_falta", ascending=False)
    return (f"Las {len(v)} cuotas vencidas: pendientes con vencimiento anterior "
            f"a hoy, de créditos que existen en AXION, restando lo ya pagado",
            ["Vencimiento", "Cliente", "Cuota N°", "Monto cuota", "Pagado", "Falta"],
            [[str(r["fecha_vencimiento"])[:10], r["client_name"],
              f'{r["numero_cuota"]:.0f}', f'{float(r["monto_cuota"]):,.2f}',
              f'{float(r["monto_pagado"]):,.2f}', f'{r["_falta"]:,.2f}']
             for _, r in v.iterrows()])


def creditos_duplicados() -> tuple[str, list[str], list[list]]:
    """Las unidades con más de un crédito cargado."""
    c = ingest.fetch_axion_entity("Credit", None, 5000)
    k = ["project", "unit"]
    d = c[c.duplicated(k, keep=False)].sort_values(k + ["client_name"])
    grupos = int(d.groupby(k).ngroups) if len(d) else 0
    return (f"{grupos} unidades tienen su crédito cargado más de una vez: "
            f"{len(d)} créditos para {grupos} operaciones. Cada copia arrastra "
            f"su propia lista de pagos y su propio cronograma, así que infla "
            f"lo cobrado y lo vencido. Se agrupa por obra y unidad, NO por "
            f"nombre: los nombres difieren entre copias. "
            f"Data de Habitat — se reporta, no se corrige · responde Cobranzas",
            ["Obra", "Unidad", "Cliente", "Precio S/", "Inicial S/",
             "Saldo S/", "Estado"],
            [[r["project"], r["unit"], r["client_name"],
              f'{float(r["precio_venta"]):,.2f}',
              f'{float(r["monto_inicial"]):,.2f}',
              f'{float(r["saldo_pendiente"]):,.2f}', r["estado"]]
             for _, r in d.iterrows()])


def peso_duplicados() -> dict:
    """Cuánto de lo publicado es el MISMO recibo contado dos veces."""
    from . import periodo
    c = ingest.fetch_axion_entity("Credit", None, 5000)
    if not len(c):
        return {"grupos": 0, "creditos": 0, "cobrado": 0.0,
                "saldo_min": 0.0, "saldo_max": 0.0,
                "grupos_saldo": 0, "max_por_grupo": 0}

    _dni = c.get("client_document")
    clave = ["project", "unit"] + (["client_document"] if _dni is not None
                                   else [])
    d = c[c.duplicated(clave, keep=False)]
    if not len(d):
        return {"grupos": 0, "creditos": 0, "cobrado": 0.0,
                "saldo_min": 0.0, "saldo_max": 0.0,
                "grupos_saldo": 0, "max_por_grupo": 0}

    def _ini_del_anio(l) -> float:
        if not isinstance(l, list):
            return 0.0
        t = 0.0
        for e in l:
            if not isinstance(e, dict):
                continue
            if "pendiente" in str(e.get("tipo") or "").lower():
                continue
            if str(e.get("fecha") or "")[:4] != str(periodo.ANIO):
                continue
            t += float(str(e.get("monto") or 0).replace(",", "") or 0)
        return t

    exceso = 0.0
    for _, g in d.groupby(clave):
        ini = sorted((_ini_del_anio(x) for x in g["iniciales"]), reverse=True)
        exceso += sum(ini[1:])            # se deja la copia que más cobró

    # EL SALDO solo compite entre VIVOS: un cancelado no puede ser el vigente.
    vivo = ~d["estado"].astype(str).str.lower().eq("cancelado")
    dv = d[vivo]
    dv = dv[dv.duplicated(clave, keep=False)]   # los que siguen repetidos
    saldos_min = saldos_max = 0.0
    max_por_grupo = 0
    for _, g in dv.groupby(clave):
        sal = sorted(float(x or 0) for x in g["saldo_pendiente"])
        saldos_min += sum(sal[:-1])       # se deja la de MAYOR saldo
        saldos_max += sum(sal[1:])        # se deja la de MENOR saldo
        max_por_grupo = max(max_por_grupo, len(sal))
    return {"grupos": int(dv.groupby(clave).ngroups) if len(dv) else 0,
            "creditos": int(len(dv)), "cobrado": round(exceso, 2),
            "saldo_min": round(saldos_min, 2),
            "saldo_max": round(saldos_max, 2),
            "grupos_cobrado": int(d.groupby(clave).ngroups),
            "creditos_cobrado": int(len(d)),
            "max_por_grupo": int(max_por_grupo)}


def cobros() -> tuple[str, list[str], list[list]]:
    """Iniciales + cuotas. Las iniciales viven dentro de una celda con lista y."""
    cre = ingest.fetch_axion_entity("Credit", None, 5000)
    cxc = ingest.fetch_axion_entity("CxCPayment", None, 5000)
    filas = []
    for _, c in cre.iterrows():
        if isinstance(c["iniciales"], list):
            for e in c["iniciales"]:
                if isinstance(e, dict):
                    try:
                        m = float(str(e.get("monto", "0")).replace(",", ""))
                    except ValueError:
                        continue
                    filas.append(["inicial", str(e.get("fecha", ""))[:10],
                                  c["project"], c["client_name"],
                                  str(e.get("serie", "")), str(e.get("empresa", "")),
                                  f"{m:,.2f}", m])
    obra = dict(zip(cre["id"], cre["project"]))
    for _, p in cxc.iterrows():
        m = float(_n(pd.Series([p["monto"]])).iloc[0])
        filas.append(["cuota", str(p["fecha"])[:10], obra.get(p["credit_id"], "—"),
                      p["client_name"], "", str(p.get("notas", ""))[:40],
                      f"{m:,.2f}", m])
    filas.sort(key=lambda x: -x[7])
    total = sum(f[7] for f in filas)
    return (f"Los {len(filas)} cobros que suman S/ {total:,.2f}: "
            f"iniciales (dentro de Credit.iniciales) más cuotas (CxCPayment)",
            ["Tipo", "Fecha", "Obra", "Cliente", "Serie", "Caja / nota", "Monto"],
            [f[:7] for f in filas])


def obras() -> tuple[str, list[str], list[list]]:
    p = ingest.fetch_axion_entity("Project", None, 5000)
    return (f"Las {len(p)} obras que AXION declara. Es el universo del tablero: "
            f"lo que no está acá, no se calcula",
            ["Obra", "Razón social", "Etapa", "RUC", "Avance"],
            [[r["name"], str(r["company_name"]).strip() or rentabilidad.SIN_RAZON,
              r["project_stage"], str(r["ruc"]).strip() or "—",
              f'{float(r["construction_progress"]):.0f}%']
             for _, r in p.sort_values("name").iterrows()])


def inventario() -> tuple[str, list[str], list[list]]:
    u = ingest.fetch_axion_entity("Unit", None, 5000)
    g = u.groupby(["project", "status"]).size().unstack(fill_value=0)
    for c in ("LIBRE", "VENDIDO", "SEPARADO", "BLOQUEADO"):
        if c not in g.columns:
            g[c] = 0
    g["TOTAL"] = g.sum(axis=1)
    return (f"Las {len(u)} unidades por obra y estado. «Libre» son las LIBRE: "
            f"las SEPARADO y BLOQUEADO no son stock vendible",
            ["Obra", "Libre", "Vendido", "Separado", "Bloqueado", "Total"],
            [[i, int(r["LIBRE"]), int(r["VENDIDO"]), int(r["SEPARADO"]),
              int(r["BLOQUEADO"]), int(r["TOTAL"])]
             for i, r in g.sort_values("TOTAL", ascending=False).iterrows()])


DETALLES = {
    "ventas": ventas_cerradas,
    "no_venta": no_son_venta,
    "vencidas": cuotas_vencidas,
    "duplicados": creditos_duplicados,
    "cobros": cobros,
    "obras": obras,
    "inventario": inventario,
}
