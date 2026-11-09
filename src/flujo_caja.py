"""FLUJO DE CAJA."""
from __future__ import annotations

import pandas as pd

from . import ingest, movimientos, periodo


def _n(s) -> pd.Series:
    return pd.to_numeric(s, errors="coerce").fillna(0)


MES_NOMBRE = {1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril", 5: "Mayo",
              6: "Junio", 7: "Julio", 8: "Agosto", 9: "Setiembre",
              10: "Octubre", 11: "Noviembre", 12: "Diciembre"}


def _entradas_reales() -> pd.DataFrame:
    """Iniciales cobradas + cuotas pagadas, con la fecha en que entraron."""
    cred = ingest.fetch_axion_entity("Credit", None, 5000)
    cxc = ingest.fetch_axion_entity("CxCPayment", None, 5000)
    filas, sin_fecha, sin_monto = [], 0.0, 0
    vistos: set = set()
    for _, cr in cred.iterrows():
        for e in (cr.get("iniciales") or []):
            if not isinstance(e, dict):
                continue
            if "pendiente" in str(e.get("tipo") or "").lower():
                continue
            _k = ingest.clave_inicial(e, cr)
            if _k in vistos:
                continue
            vistos.add(_k)
            _bruto = str(e.get("monto", "")).replace(",", "").strip()
            try:
                monto = float(_bruto)
            except ValueError:
                sin_monto += 1
                continue
            f = pd.to_datetime(str(e.get("fecha") or ""), errors="coerce")
            if pd.isna(f):
                sin_fecha += monto
                continue
            filas.append({"fecha": f, "monto": monto, "tipo": "inicial",
                          "quien": str(cr.get("client_name") or
                                       cr.get("client_document") or "—"),
                          "unidad": str(cr.get("unit") or "—"),
                          "obra": str(cr.get("project") or "—")})
    _ix = cred.set_index(cred["id"].astype(str)) if not cred.empty else cred

    def _de_quien(cid):
        try:
            r = _ix.loc[str(cid)]
        except (KeyError, TypeError):
            return ("—", "—", "—")
        if isinstance(r, pd.DataFrame):
            r = r.iloc[0]
        return (str(r.get("client_name") or "—"), str(r.get("unit") or "—"),
                str(r.get("project") or "—"))

    f_cxc = pd.to_datetime(cxc["fecha"], errors="coerce")
    _cid = (cxc["credit_id"] if "credit_id" in cxc.columns
            else pd.Series([None] * len(cxc), index=cxc.index))
    for f, m, ci in zip(f_cxc, _n(cxc["monto"]), _cid):
        if pd.isna(f):
            sin_fecha += float(m)
            continue
        q, u, o = _de_quien(ci)
        filas.append({"fecha": f, "monto": float(m), "tipo": "cuota",
                      "quien": q, "unidad": u, "obra": o})
    df = pd.DataFrame(filas) if filas else pd.DataFrame(
        columns=["fecha", "monto", "tipo"])
    df.attrs["sin_fecha"] = sin_fecha
    df.attrs["sin_monto"] = sin_monto
    return df


def _sin_dato(df, col: str, anio: int) -> dict:
    """Cuanta plata del gasto del año viene sin ese campo cargado."""
    if df is None or df.empty or col not in df.columns:
        return {"monto": 0.0, "filas": 0}
    f = pd.to_datetime(df["fecha"], errors="coerce")
    sel = df[f.dt.year.eq(anio)]
    if sel.empty:
        return {"monto": 0.0, "filas": 0}
    k = sel[col].fillna("").astype(str).str.strip().str.lower()
    v = k.isin(("", "nan", "none", "\u2014", "-"))
    campo = "monto" if "monto" in sel.columns else "monto_n"
    return {"monto": float(_n(sel.loc[v, campo]).sum()), "filas": int(v.sum())}


def por_mes(anio: int | None = None) -> dict:
    """Un renglón por mes: entró, salió, por entrar y presupuesto."""
    anio = anio or periodo.ANIO
    ent = _entradas_reales()
    sal = movimientos.crudo()
    inst = ingest.fetch_axion_entity("Installment", None, 5000)

    def _plan_real(df, an: int, mes: int) -> float:
        if df is None or df.empty:
            return 0.0
        f = pd.to_datetime(df["fecha"], errors="coerce")
        sel = df[f.dt.year.eq(an) & f.dt.month.eq(mes)]
        if sel.empty:
            return 0.0
        c = sel["concepto"].astype(str).str.strip().str.upper()
        es_saldo = (c.str.startswith("SALDO") | c.str.startswith("RETIRO")
                    | c.str.startswith("SE RETIR") | c.str.startswith("SE DEPOSIT"))
        return float(_n(sel.loc[~es_saldo, "monto"]).sum())

    # Salidas reales: solo `gasto`. El presupuesto va aparte, en su columna.
    gastos = sal[sal["clase"] == "gasto"] if not sal.empty else sal
    presup = sal[sal["clase"] == "presupuesto"] if not sal.empty else sal
    cobros_lib = sal[sal["clase"] == "venta"] if not sal.empty else sal
    otros = sal[sal["clase"] == "otro"] if not sal.empty else sal

    venc = pd.to_datetime(inst["fecha_vencimiento"], errors="coerce")
    falta = (_n(inst["monto_cuota"]) - _n(inst["monto_pagado"])).clip(lower=0)
    _cred_fc = ingest.fetch_axion_entity("Credit", None, 5000)
    _vivos_fc = set(_cred_fc.loc[~_cred_fc["estado"].astype(str).str.lower()
                                 .eq("cancelado"), "id"].astype(str))         if "estado" in _cred_fc.columns else set(_cred_fc["id"].astype(str))
    _viva_fc = inst["credit_id"].astype(str).isin(_vivos_fc)
    proy = pd.DataFrame({"fecha": venc, "monto": falta})[_viva_fc & falta.gt(0)]

    _base_fc = _viva_fc & falta.gt(0)
    _hoy_fc = pd.Timestamp(pd.Timestamp.today().date())
    _del_anio = _base_fc & venc.dt.year.eq(anio)
    _fuera = _base_fc & venc.notna() & ~venc.dt.year.eq(anio)
    _por_anio = []
    for _a in sorted(set(venc[_fuera].dt.year.dropna().astype(int))):
        _s = _base_fc & venc.dt.year.eq(_a)
        _por_anio.append({"anio": int(_a), "cuotas": int(_s.sum()),
                          "monto": float(falta[_s].sum())})
    _sin_venc = _base_fc & venc.isna()
    _canc = (~_viva_fc) & falta.gt(0)
    composicion_por_entrar = {
        "del_anio": {"cuotas": int(_del_anio.sum()),
                     "monto": float(falta[_del_anio].sum())},
        "vencido": {"cuotas": int((_del_anio & venc.lt(_hoy_fc)).sum()),
                    "monto": float(falta[_del_anio & venc.lt(_hoy_fc)].sum())},
        "por_vencer": {"cuotas": int((_del_anio & venc.ge(_hoy_fc)).sum()),
                       "monto": float(falta[_del_anio & venc.ge(_hoy_fc)].sum())},
        "otros_anios": {"cuotas": int(_fuera.sum()),
                        "monto": float(falta[_fuera].sum()),
                        "por_anio": _por_anio},
        "sin_vencimiento": {"cuotas": int(_sin_venc.sum()),
                            "monto": float(falta[_sin_venc].sum())},
        "cancelados": {"cuotas": int(_canc.sum()),
                       "monto": float(falta[_canc].sum())},
        "cartera_con_cronograma": {"cuotas": int(_base_fc.sum()),
                                   "monto": float(falta[_base_fc].sum())},
        "al_dia": str(_hoy_fc.date()),
    }

    CORTE_PRESUPUESTO = 8
    hoy = pd.Timestamp(pd.Timestamp.today().date())
    filas = []
    for m in range(1, 13):
        def _suma(df, col="fecha"):
            if df is None or df.empty or col not in df.columns:
                return 0.0
            f = pd.to_datetime(df[col], errors="coerce")
            sel = f.dt.year.eq(anio) & f.dt.month.eq(m)
            campo = "monto" if "monto" in df.columns else "monto_n"
            return float(_n(df.loc[sel, campo]).sum())

        entro = _suma(ent)
        _ei = ent[ent["tipo"] == "inicial"] if not ent.empty else ent
        _ec = ent[ent["tipo"] == "cuota"] if not ent.empty else ent
        entro_ini = _suma(_ei)
        entro_cuo = _suma(_ec)
        salio = _suma(gastos)
        sin_clase = _suma(otros)
        porent = _suma(proy)
        presu = _suma(presup)
        fin_mes = pd.Timestamp(year=anio, month=m, day=1) + pd.offsets.MonthEnd(0)
        # Un mes sin NADA no se dibuja: los meses futuros vacíos serían ruido.
        if not any((entro, salio, porent, presu, sin_clase)):
            continue
        plan = _plan_real(presup, anio, m)
        mide = bool(m >= CORTE_PRESUPUESTO and presu and plan / presu >= 0.5)
        cob_lib = _suma(cobros_lib)

        def _top(df, col_fecha, campos, tope=10):
            if df is None or df.empty or col_fecha not in df.columns:
                return {"filas": 0, "monto": 0.0, "detalle": [], "resto": 0.0,
                        "resto_filas": 0}
            fx = pd.to_datetime(df[col_fecha], errors="coerce")
            sel = df[fx.dt.year.eq(anio) & fx.dt.month.eq(m)]
            if not len(sel):
                return {"filas": 0, "monto": 0.0, "detalle": [], "resto": 0.0,
                        "resto_filas": 0}
            campo = "monto" if "monto" in sel.columns else "monto_n"
            sel = sel.assign(_m=_n(sel[campo])).sort_values("_m", ascending=False)
            top = sel.head(tope)
            det = []
            for _, r in top.iterrows():
                fila = {"fecha": str(pd.to_datetime(r[col_fecha]).date()),
                        "monto": float(r["_m"])}
                for k, orig in campos.items():
                    val = r.get(orig)
                    fila[k] = ("" if val is None or str(val).strip().lower()
                               in ("", "nan", "none") else str(val).strip())
                det.append(fila)
            return {"filas": int(len(sel)), "monto": float(sel["_m"].sum()),
                    "detalle": det,
                    "resto": float(sel["_m"].sum() - top["_m"].sum()),
                    "resto_filas": int(len(sel) - len(top))}

        def _ultimo(df):
            if df is None or df.empty or "fecha" not in df.columns:
                return None
            f = pd.to_datetime(df["fecha"], errors="coerce")
            f = f[f.dt.year.eq(anio) & f.dt.month.eq(m)]
            return None if f.empty or pd.isna(f.max()) else f"{f.max():%Y-%m-%d}"

        corte = {"cobro": _ultimo(ent), "gasto": _ultimo(gastos)}

        top_cobros = _top(ent, "fecha",
                          {"quien": "quien", "unidad": "unidad", "tipo": "tipo",
                           "obra": "obra"})
        top_gastos = _top(gastos, "fecha",
                          {"concepto": "concepto", "obra": "proyecto",
                           "cuenta": "cuenta", "rotulo": "movimiento"})

        def _filas_todas(df, col_fecha, campos):
            if df is None or df.empty or col_fecha not in df.columns:
                return []
            fx = pd.to_datetime(df[col_fecha], errors="coerce")
            sel = df[fx.dt.year.eq(anio) & fx.dt.month.eq(m)]
            if not len(sel):
                return []
            campo = "monto" if "monto" in sel.columns else "monto_n"
            out = []
            for _, r in sel.iterrows():
                fila = {"fecha": str(pd.to_datetime(r[col_fecha]).date()),
                        "monto": float(_n(pd.Series([r[campo]])).iloc[0])}
                for k, orig in campos.items():
                    val = r.get(orig)
                    fila[k] = ("" if val is None or str(val).strip().lower()
                               in ("", "nan", "none") else str(val).strip())
                out.append(fila)
            return out

        filas_cobro = _filas_todas(ent, "fecha",
                                   {"quien": "quien", "unidad": "unidad",
                                    "tipo": "tipo", "obra": "obra"})
        filas_gasto = _filas_todas(gastos, "fecha",
                                   {"concepto": "concepto", "obra": "proyecto",
                                    "cuenta": "cuenta", "rotulo": "movimiento"})

        def _reparto(df, col, tope=8, vacio="(sin dato)"):
            if df is None or df.empty or col not in df.columns:
                return []
            fx = pd.to_datetime(df["fecha"], errors="coerce")
            sel = df[fx.dt.year.eq(anio) & fx.dt.month.eq(m)]
            if not len(sel):
                return []
            campo = "monto" if "monto" in sel.columns else "monto_n"
            k = sel[col].fillna("").astype(str).str.strip()
            k = k.mask(k.str.lower().isin(("", "nan", "none", "—")), vacio)
            g = (sel.assign(_k=k, _m=_n(sel[campo]))
                 .groupby("_k")["_m"].agg(["sum", "count"])
                 .sort_values("sum", ascending=False))
            out = [{"que": str(i), "monto": float(r["sum"]),
                    "filas": int(r["count"])} for i, r in g.head(tope).iterrows()]
            if len(g) > tope:
                r = g.iloc[tope:]
                out.append({"que": f"otros {len(r)}", "monto": float(r["sum"].sum()),
                            "filas": int(r["count"].sum())})
            return out

        reparto_gasto = {
            "rotulo": _reparto(gastos, "movimiento", 8, "(sin rótulo en AXION)"),
            "obra": _reparto(gastos, "proyecto", 8, "(sin obra cargada)"),
            "cuenta": _reparto(gastos, "cuenta", 8, "(sin cuenta cargada)"),
        }

        filas.append({
            "mes": m, "etiqueta": f"{MES_NOMBRE[m]} {anio}",
            "entro": entro, "salio": salio,
            "entro_inicial": entro_ini, "entro_cuota": entro_cuo,
            "top_cobros": top_cobros, "top_gastos": top_gastos,
            "reparto_gasto": reparto_gasto,
            "filas_cobro": filas_cobro, "filas_gasto": filas_gasto,
            # Hasta que dia esta cargado cada lado — ver `_ultimo`.
            "corte": corte,
            "neto": entro - salio,
            # el neto que SÍ se puede restar: los dos lados del mismo libro
            "cobros_libro": cob_lib,
            "neto_libro": cob_lib - salio,
            "por_entrar": porent, "presupuesto": presu,
            "sin_clasificar": sin_clase,
            "plan_real": plan,
            "ejecucion": (100 * salio / presu) if mide else None,
            "mide_presupuesto": mide,
            "pasado": bool(fin_mes < hoy),
            "en_curso": bool(fin_mes >= hoy and
                             pd.Timestamp(year=anio, month=m, day=1) <= hoy),
        })

    # Las hipotecas sin fecha de desembolso: el hueco que hay que declarar.
    sale = ingest.fetch_axion_entity("Sale", None, 5000)
    v = periodo.recortar(sale[sale["status"] == "Vendido"], "date", None)
    hip = v[v["modality"].astype(str).str.strip().str.lower() == "hipoteca"]
    fut = ent[pd.to_datetime(ent["fecha"], errors="coerce") > hoy] \
        if not ent.empty else ent
    futuros = {
        "n": int(len(fut)),
        "monto": float(_n(fut["monto"]).sum()) if len(fut) else 0.0,
        "detalle": [
            {"fecha": str(pd.to_datetime(r["fecha"]).date()),
             "monto": float(r["monto"]), "quien": r.get("quien") or "—",
             "unidad": r.get("unidad") or "—", "obra": r.get("obra") or ""}
            for _, r in fut.iterrows()] if len(fut) else [],
    }

    acum_e = sum(f["entro"] for f in filas)
    acum_s = sum(f["salio"] for f in filas)

    def _filas_del_anio(df):
        if df is None or df.empty or "fecha" not in df.columns:
            return 0
        return int(pd.to_datetime(df["fecha"], errors="coerce")
                   .dt.year.eq(anio).sum())

    _fv = pd.to_datetime(inst["fecha_vencimiento"], errors="coerce")
    _falta_all = _n(inst["monto_cuota"]) - _n(inst["monto_pagado"])
    _borr_ven = ~ingest.con_credito(inst) & (_fv < pd.Timestamp(pd.Timestamp.today().date()))
    _pend = (inst["estado"] == "pendiente") & _falta_all.gt(0) & ~_borr_ven
    _post = _pend & _fv.dt.year.gt(anio)
    _prev = _pend & _fv.dt.year.lt(anio)
    fuera_del_anio = {
        "despues": {"cuotas": int(_post.sum()),
                    "monto": float(_falta_all[_post].sum()),
                    "hasta": (f"{_fv[_post].max():%Y}" if _post.any() else "")},
        "antes": {"cuotas": int(_prev.sum()),
                  "monto": float(_falta_all[_prev].sum())},
        "total_pendiente": float(_falta_all[_pend].sum()),
    }
    return {
        "futuros": futuros,
        "fuera_del_anio": fuera_del_anio,
        "hay": bool(filas),
        "anio": anio,
        "meses": filas,
        "acumulado": {"entro": acum_e, "salio": acum_s, "neto": acum_e - acum_s,
                      "por_entrar": sum(f["por_entrar"] for f in filas),
                      "presupuesto": sum(f["presupuesto"] for f in filas),
                      "sin_clasificar": sum(f["sin_clasificar"] for f in filas),
                      # del AÑO, no de siempre — ver `_filas_del_anio`
                      "filas_salio": _filas_del_anio(gastos),
                      "filas_entro": _filas_del_anio(ent),
                      "filas_presupuesto": _filas_del_anio(presup),
                      "sin_obra": _sin_dato(gastos, "proyecto", anio),
                      "sin_cuenta": _sin_dato(gastos, "cuenta", anio),
                      "composicion_por_entrar": composicion_por_entrar},
        "desglose_entro": [
            {"clave": ("Iniciales de crédito" if k == "inicial"
                       else "Cuotas cobradas (CxCPayment)"),
             "filas": int(len(g)), "monto": float(g["monto"].sum())}
            for k, g in (ent.assign(
                _a=pd.to_datetime(ent["fecha"], errors="coerce").dt.year)
                .query("_a == @anio").groupby("tipo"))
        ] if not ent.empty else [],
        "cobros_del_libro": (
            float(_n(sal.loc[
                sal["clase"].eq("venta")
                & pd.to_datetime(sal["fecha"], errors="coerce").dt.year.eq(anio),
                "monto"]).sum())
            if not sal.empty else 0.0),
        "sin_fecha": float(ent.attrs.get("sin_fecha") or 0),
        "sin_monto": int(ent.attrs.get("sin_monto") or 0),
        "pagos_futuros": [
            {"fecha": f"{r.fecha:%Y-%m-%d}", "monto": float(r.monto),
             "tipo": str(r.tipo), "quien": str(r.quien),
             "unidad": str(r.unidad)}
            for r in ent.itertuples()
            if r.fecha > pd.Timestamp.today().normalize()
        ] if not ent.empty else [],
        "hipotecas": {"ventas": int(len(hip)),
                      "monto": float(_n(hip["sale_price"]).sum())},
        "arrastre": _arrastre_anterior(sal, anio),
    }


def _arrastre_anterior(sal: pd.DataFrame, anio: int) -> dict:
    """La caja de los años ANTERIORES al año en curso, con la vara del libro."""
    vacio = {"hay": False, "anios": [], "entro": 0.0, "salio": 0.0,
             "monto": 0.0, "miami_chancay": 0.0}
    if sal.empty:
        return vacio
    f = pd.to_datetime(sal["fecha"], errors="coerce")
    prev = sal[f.dt.year.lt(anio)]
    if prev.empty:
        return vacio
    fp = pd.to_datetime(prev["fecha"], errors="coerce")
    entro = float(_n(prev.loc[prev["clase"].eq("venta"), "monto"]).sum())
    salio = float(_n(prev.loc[prev["clase"].eq("gasto"), "monto"]).sum())
    txt = (prev["proyecto"].fillna("").astype(str) + " | " +
           prev["concepto"].fillna("").astype(str)).str.upper()
    mc = prev[prev["clase"].eq("gasto") &
              txt.str.contains("MIAMI|MIAMY|MAIMI|CHANCAY|CHANCAI|CHANKAY",
                               regex=True, na=False)]
    return {
        "hay": True,
        "anios": sorted(int(a) for a in fp.dt.year.dropna().unique()),
        "entro": entro, "salio": salio, "monto": entro - salio,
        "miami_chancay": float(_n(mc["monto"]).sum()),
    }


def diagnostico_presupuesto() -> dict | None:
    f = por_mes()
    if not f.get("hay"):
        return None
    casi_iguales = [m for m in f["meses"]
                    if m["presupuesto"] > 1000 and m["salio"] > 1000
                    and abs(m["salio"] - m["presupuesto"]) / m["presupuesto"] < 0.005]
    if len(casi_iguales) < 3:
        return None
    peor = min(casi_iguales,
               key=lambda m: abs(m["salio"] - m["presupuesto"]))
    df = movimientos.crudo()
    p = df[df["clase"] == "presupuesto"]
    conceptos = [str(c) for c in p["concepto"].dropna().head(3)]
    proy = p["proyecto"].fillna("").astype(str).str.strip()
    _mapa = movimientos.mapa_proyectos()
    _obra_de = (_mapa.set_index("proyecto")["obra_axion"].to_dict()
                if not _mapa.empty else {})
    _clave = p["proyecto"].fillna("(vacío)").astype(str).str.strip()
    sin_obra = int(sum(1 for x in _clave if _obra_de.get(x, "—") == "—"))
    return {
        "meses": len(casi_iguales),
        "ejemplo_mes": peor["etiqueta"],
        "ejemplo_presu": peor["presupuesto"],
        "ejemplo_gasto": peor["salio"],
        "ejemplo_dif": abs(peor["salio"] - peor["presupuesto"]),
        "conceptos": conceptos,
        "sin_obra": sin_obra,
        "total_filas": int(len(p)),
    }


def alertas_presupuesto() -> list[dict]:
    """Meses donde el gasto real superó al presupuesto. Es literalmente lo que."""
    f = por_mes()
    if not f.get("hay"):
        return []
    out = []
    for m in f["meses"]:
        if not m.get("mide_presupuesto"):
            continue
        if m["presupuesto"] and m["salio"] > m["presupuesto"]:
            out.append({
                "mes": m["etiqueta"],
                "presupuesto": m["presupuesto"],
                "gasto": m["salio"],
                "exceso": m["salio"] - m["presupuesto"],
                "pct": m["ejecucion"],
            })
    return out
