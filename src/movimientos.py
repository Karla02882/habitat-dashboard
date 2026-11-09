"""INGESTA · `MovimientoGasto`."""
from __future__ import annotations

import pandas as pd

from . import atribucion, ingest, periodo

PRESUPUESTO = ("Presup. Administrativo", "Presup. Operativo")
VENTA = ("Venta al detalle", "Venta Mayoreo", "Otros ingresos")
GASTO = ("Gasto Admistrativo", "Gasto Operativo")

_CACHE: dict[str, pd.DataFrame] = {}


_SIN_RECORTE = object()


def crudo() -> pd.DataFrame:
    """Los movimientos tal como llegan, con `clase` agregada. Caché por corrida."""
    if "crudo" in _CACHE:
        return _CACHE["crudo"].copy()
    df = ingest._fetch_base44_entity(
        "AXION_API_BASE_URL", "AXION_API_KEY", "MovimientoGasto",
        ["MovimientoGasto"], limit=5000)
    if df.empty:
        _CACHE["crudo"] = df
        return df.copy()

    if "moneda" in df.columns and "tasa_cambio" in df.columns:
        es_usd = df["moneda"].fillna("").astype(str).str.strip().eq("USD")
        tasa = pd.to_numeric(df["tasa_cambio"], errors="coerce")
        con_tasa = es_usd & tasa.gt(0)
        df.loc[con_tasa, "monto"] = (
            pd.to_numeric(df.loc[con_tasa, "monto"], errors="coerce")
            * tasa[con_tasa])

    mov = df["movimiento"].fillna("").astype(str).str.strip()
    df["clase"] = "otro"
    df.loc[mov.isin(PRESUPUESTO), "clase"] = "presupuesto"
    df.loc[mov.isin(VENTA), "clase"] = "venta"
    df.loc[mov.isin(GASTO), "clase"] = "gasto"

    tipo = df["tipo_movimiento"].fillna("").astype(str).str.strip()
    df.loc[df["clase"].eq("venta") & tipo.eq("Egreso"), "clase"] = "gasto"
    df.loc[df["clase"].eq("gasto") & tipo.eq("Ingreso"), "clase"] = "venta"

    tipo = df["tipo_movimiento"].fillna("").astype(str).str.strip()
    vacio = mov.eq("")
    df.loc[vacio & tipo.eq("Egreso"), "clase"] = "gasto"
    df.loc[vacio & tipo.eq("Ingreso"), "clase"] = "venta"
    df["sin_categoria"] = vacio
    df["monto_n"] = pd.to_numeric(df["monto"], errors="coerce").fillna(0)
    df["fecha_n"] = pd.to_datetime(df["fecha"], errors="coerce")
    _CACHE["crudo"] = df
    return df.copy()


def aperturas() -> dict:
    """El saldo con que arranca cada cuenta, LEÍDO de AXION."""
    try:
        df = ingest.fetch_axion_entity("SaldoInicial", None, 5000)
    except Exception:  # noqa: BLE001 — sin la tabla, el tablero sigue
        return {}
    if df.empty or not {"banco", "anio", "mes", "saldo"} <= set(df.columns):
        return {}
    out: dict[str, dict] = {}
    for _, r in df.iterrows():
        cuenta = str(r["banco"] or "").strip()
        try:
            anio, mes = int(r["anio"]), int(r["mes"])
        except (TypeError, ValueError):
            continue
        if not cuenta or not (1 <= mes <= 12):
            continue
        out.setdefault(cuenta, {})[f"{anio}-{mes:02d}"] = round(float(r["saldo"] or 0), 2)
    return out


def _obras_axion() -> list[str]:
    return sorted({str(x).strip() for x in
                   ingest.fetch_axion_entity("Project", None, 5000)["name"]
                   if str(x).strip()})


def mapa_proyectos() -> pd.DataFrame:
    """Cada valor distinto de `proyecto`, con la obra de AXION que le."""
    df = crudo()
    if df.empty:
        return pd.DataFrame()
    obras = _obras_axion()
    g = (df.assign(proyecto=df["proyecto"].fillna("(vacío)").astype(str).str.strip())
           .groupby("proyecto")
           .agg(filas=("monto_n", "size"), monto=("monto_n", "sum"))
           .reset_index())
    empar = [atribucion._emparejar(p, obras) for p in g["proyecto"]]
    g["obra_axion"] = [o for o, _ in empar]
    g["como"] = [c for _, c in empar]
    return g.sort_values("monto", ascending=False)


def gasto_por_obra(mes=periodo.HISTORICO) -> pd.DataFrame:
    """El GASTO REAL por obra de AXION. Sin presupuesto, sin ventas."""
    df = crudo()
    if df.empty:
        return pd.DataFrame()
    mapa = mapa_proyectos().set_index("proyecto")["obra_axion"].to_dict()
    g = df[df["clase"] == "gasto"].copy()
    g = periodo.recortar(g, "fecha", mes)
    if g.empty:
        return pd.DataFrame(columns=["obra", "movimientos", "gasto"])
    g["obra"] = (g["proyecto"].fillna("").astype(str).str.strip().map(mapa)
                 .fillna("—"))
    con = g[g["obra"] != "—"]
    return (con.groupby("obra")
               .agg(movimientos=("monto_n", "size"), gasto=("monto_n", "sum"))
               .reset_index().sort_values("gasto", ascending=False))


def gasto_total(mes=periodo.HISTORICO) -> dict:
    """EL GASTO DEL PERÍODO, sin repartir por obra. Con obra y sin ella."""
    VACIO = {"hay": False, "filas": 0, "monto": 0.0, "atribuido": 0.0,
             "sin_atribuir": 0.0, "obras": 0, "pct_atribuido": 0.0}
    df = crudo()
    if df.empty:
        return dict(VACIO)
    g = periodo.recortar(df[df["clase"] == "gasto"], "fecha", mes)
    if g.empty:
        return dict(VACIO, hay=True)
    por_obra = gasto_por_obra(mes)
    atr = float(por_obra["gasto"].sum()) if not por_obra.empty else 0.0
    tot = float(g["monto_n"].sum())
    return {
        "hay": True,
        "filas": int(len(g)),
        "monto": tot,
        "atribuido": atr,
        "sin_atribuir": tot - atr,
        "obras": int(len(por_obra)),
        "pct_atribuido": (100 * atr / tot) if tot else 0.0,
    }


def resumen() -> dict:
    """Los totales, SEPARADOS. El presupuesto nunca se suma con la caja."""
    df = crudo()
    if df.empty:
        return {"hay": False}
    por_clase = df.groupby("clase")["monto_n"].agg(["size", "sum"])

    def _t(clase):
        if clase not in por_clase.index:
            return {"filas": 0, "monto": 0.0}
        return {"filas": int(por_clase.loc[clase, "size"]),
                "monto": float(por_clase.loc[clase, "sum"])}

    gasto = _t("gasto")
    venta = _t("venta")
    presu = _t("presupuesto")
    ga = gasto_por_obra()
    atribuido = float(ga["gasto"].sum()) if not ga.empty else 0.0

    mapa = mapa_proyectos().set_index("proyecto")["obra_axion"].to_dict()
    pr = df[df["clase"] == "presupuesto"].copy()
    if pr.empty:
        pr_atr_monto, pr_atr_filas, pr_obras = 0.0, 0, []
    else:
        obra_pr = (pr["proyecto"].fillna("").astype(str).str.strip().map(mapa)
                   .fillna("—"))
        con = pr[obra_pr != "—"]
        pr_atr_monto = float(con["monto_n"].sum())
        pr_atr_filas = int(len(con))
        pr_obras = sorted({str(o) for o in obra_pr[obra_pr != "—"]})

    f = df["fecha_n"].dropna()
    return {
        "hay": True,
        "filas": int(len(df)),
        "periodo": (f"{f.min():%Y-%m-%d} a {f.max():%Y-%m-%d}"
                    if len(f) else "sin fechas"),
        "gasto": gasto, "venta": venta, "presupuesto": presu,
        "otro": _t("otro"),
        "gasto_atribuido": atribuido,
        "gasto_sin_atribuir": gasto["monto"] - atribuido,
        "pct_atribuido": (100 * atribuido / gasto["monto"]
                          if gasto["monto"] else 0.0),
        "obras_con_gasto": int(len(ga)),
        "presupuesto_atribuido": pr_atr_monto,
        "presupuesto_atribuido_filas": pr_atr_filas,
        "presupuesto_obras": pr_obras,
    }


def sin_atribuir() -> pd.DataFrame:
    """Los valores de `proyecto` que NO son una obra de AXION, con su monto."""
    m = mapa_proyectos()
    if m.empty:
        return m
    return m[m["obra_axion"] == "—"].copy()


def desglose(anio: int | None = _SIN_RECORTE) -> dict:
    df = crudo()
    if df.empty:
        return {}
    if anio is not _SIN_RECORTE:
        _a = anio or periodo.ANIO
        _f = pd.to_datetime(df["fecha"], errors="coerce")
        df = df[_f.dt.year.eq(_a)]
        if df.empty:
            return {}
    mapa = mapa_proyectos().set_index("proyecto")["obra_axion"].to_dict()

    def _por(sub: pd.DataFrame, col: str) -> list[dict]:
        if sub.empty:
            return []
        g = (sub.groupby(sub[col].fillna("(vacío)").astype(str).str.strip())
                .agg(filas=("monto_n", "size"), monto=("monto_n", "sum"))
                .reset_index().rename(columns={col: "clave"}))
        g.columns = ["clave", "filas", "monto"]
        g = g.sort_values("monto", ascending=False)
        cima, resto = g.head(30), g.iloc[30:]
        out = cima.to_dict("records")
        if len(resto):
            out.append({"clave": f"(y {len(resto)} claves más)",
                        "filas": int(resto["filas"].sum()),
                        "monto": round(float(resto["monto"].sum()), 2)})
        return out

    gasto = df[df["clase"] == "gasto"].copy()
    gasto["_obra"] = gasto["proyecto"].fillna("").astype(str).str.strip().map(mapa)
    return {
        "gasto": _por(gasto, "proyecto"),
        "atribuido": _por(gasto[gasto["_obra"].notna() & (gasto["_obra"] != "—")],
                          "_obra"),
        "venta": _por(df[df["clase"] == "venta"], "movimiento"),
        "presupuesto": _por(df[df["clase"] == "presupuesto"], "movimiento"),
    }


def avisos() -> list[dict]:
    """Lo que hay que DECIR en pantalla sobre esta fuente, con su cifra."""
    df = crudo()
    if df.empty:
        return []
    r = resumen()
    out = [{
        "etiqueta": "El presupuesto viaja como «Ingreso»",
        "cifra": r["presupuesto"]["monto"],
        "texto": (f"AXION marca {r['presupuesto']['filas']:,} movimientos de "
                  f"presupuesto por S/ {r['presupuesto']['monto']:,.2f} con "
                  f"tipo_movimiento «Ingreso», junto a las ventas reales "
                  f"(S/ {r['venta']['monto']:,.2f}). Sumar la columna entera "
                  f"publica como cobrado un presupuesto que nadie cobró: es el "
                  f"{100 * r['presupuesto']['monto'] / (r['presupuesto']['monto'] + r['venta']['monto']):.1f}% "
                  f"del total. Acá van separados y no se suman."),
        "area": "Administración · corregir en AXION",
    }]
    sc = df[df.get("sin_categoria", False)]
    if len(sc):
        tipo_sc = sc["tipo_movimiento"].astype(str).str.strip()
        ing = float(sc[tipo_sc == "Ingreso"]["monto_n"].sum())
        egr = float(sc[tipo_sc == "Egreso"]["monto_n"].sum())

        def _t(v) -> str:
            return "" if v is None or (isinstance(v, float) and v != v) else str(v).strip()

        filas_sc = [{
            "fecha": _t(r_.get("fecha"))[:10],
            "cuenta": _t(r_.get("cuenta")),
            "concepto": _t(r_.get("concepto")),
            "tipo": _t(r_.get("tipo_movimiento")),
            "monto": round(float(r_["monto_n"]), 2),
        } for _, r_ in sc.sort_values("fecha_n", ascending=False).iterrows()]
        out.append({
            "etiqueta": "Movimientos sin categoría cargada",
            "cifra": float(sc["monto_n"].sum()),
            "texto": (f"{len(sc)} movimientos con «movimiento» vacío en AXION · "
                      f"S/ {egr:,.2f} tipo Egreso · S/ {ing:,.2f} tipo Ingreso · "
                      f"el tablero los cuenta por su tipo"),
            "filas": filas_sc,
            "area": "Administración · cargar el tipo de movimiento",
        })
    sa = sin_atribuir()
    if not sa.empty:
        top = " · ".join(f"{r_.proyecto} (S/ {r_.monto:,.0f})"
                         for r_ in sa.head(5).itertuples())
        out.append({
            "etiqueta": "«Proyecto» no siempre es una obra",
            "cifra": float(sa["monto"].sum()),
            "texto": (f"{len(sa)} valores del campo «proyecto» no corresponden "
                      f"a ninguna de las 18 obras de AXION, y mueven "
                      f"S/ {sa['monto'].sum():,.2f}. Los mayores: {top}. El "
                      f"campo se autodetecta del concepto y mezcla obras con "
                      f"centros de costo. Su monto NO se reparte entre las "
                      f"obras: se muestra acá."),
            "area": "Administración · revisar la tabla de equivalencias",
        })
    ncl = df["clasificacion_financiera"].nunique(dropna=True)
    if ncl <= 1:
        out.append({
            "etiqueta": "Los campos de clasificación están sin usar",
            "cifra": None,
            "texto": (f"«clasificacion_financiera» tiene un solo valor en las "
                      f"{len(df):,} filas y «es_gasto_real» está en True en "
                      f"todas —incluidos los {r['presupuesto']['filas']:,} de "
                      f"presupuesto—. Son los valores por defecto: nadie los "
                      f"clasificó. Mientras sigan así, no sirven para separar "
                      f"inversión de gasto ni caja real de presupuesto."),
            "area": "Administración · clasificar en AXION",
        })
    return out


def gasto_fuera_de_alcance(mes=periodo.HISTORICO) -> dict:
    """LA PLATA QUE SALIÓ A PROYECTOS QUE NO ESTÁN EN AXION."""
    import re as _re
    df = crudo()
    if df.empty:
        return {"hay": False}
    df = periodo.recortar(df[df["clase"] == "gasto"], "fecha", mes)
    if df.empty:
        return {"hay": False}
    obras = set(_obras_axion())
    con = df["concepto"].fillna("").astype(str)
    pro = df["proyecto"].fillna("").astype(str).str.strip()
    FUERA = _re.compile(r"miami|chancay|beeach|beach", _re.I)
    sel = con.str.contains(FUERA) | pro.str.contains(FUERA)
    g = df[sel]
    if not len(g):
        return {"hay": False}
    monto = float(g["monto_n"].sum())
    DESTINO = {"miami": "Miami Beach", "beach": "Miami Beach",
               "beeach": "Miami Beach", "chancay": "Chancay"}

    def _destino(txt_pro, txt_con):
        for campo in (txt_pro, txt_con):
            bajo = str(campo).lower()
            for clave, nombre in DESTINO.items():
                if clave in bajo:
                    return nombre
        return ""

    _dest = [_destino(a, b) for a, b in zip(pro[sel], con[sel])]
    _por = (g.assign(_p=_dest).groupby("_p")["monto_n"].sum()
            .sort_values(ascending=False))
    nombres = [x for x in _por.index if x and x not in obras]
    filas = [{"fecha": str(r["fecha"])[:10],
              "proyecto": str(r["proyecto"] or "—").strip() or "—",
              "concepto": str(r["concepto"] or "—"),
              "monto": float(r["monto_n"])}
             for _, r in g.iterrows()]
    filas.sort(key=lambda x: -x["monto"])
    _anios_prev = sorted(int(a) for a in pd.to_datetime(
        g["fecha"], errors="coerce").dt.year.dropna().unique()
        if int(a) != periodo.ANIO)
    return {"hay": True, "movimientos": int(len(g)), "monto": monto,
            "anios": _anios_prev,
            "proyectos": nombres, "filas": filas}
