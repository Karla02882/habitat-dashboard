"""HOJAS 11 y 12."""
from __future__ import annotations

import pandas as pd

from . import atribucion, contasis, ingest, periodo
from . import lectura_excel as lx

ANIO_CIERRE = 2026

POR_CREAR = [
    ("Inventario físico",
     "un conteo cargado en la tabla Inventory, que existe y está vacía",
     None),     # <- lo mide `por_crear()`
    ("Carga de costos por obra",
     "que la tabla Gasto tenga columna de proyecto",
     None),     # <- lo mide `por_crear()`
    ("Módulo de reclamos",
     "registro de reclamos de clientes",
     "Solicitado por Gerencia; hoy no hay tabla"),
    ("Origen comercial en la venta",
     "que la venta registre de dónde vino el cliente, y que el CRM "
     "alimente la tabla de interesados",
     None),
    ("Avance de obra",
     "conectar el cuaderno de obras",
     "4 indicadores de Procesos Internos sin fuente"),
    ("Si el indicador sube o baja",
     "llenar la columna kpi_type de la tabla KPI",
     None),     # <- lo mide `por_crear()`
]


def _num(s) -> pd.Series:
    return pd.to_numeric(s, errors="coerce").fillna(0)


def por_crear() -> list[tuple]:
    """Lo que falta crear en AXION, con las cifras MEDIDAS en el momento."""
    from . import areas as _ar
    from . import scorecard as _sc
    out = []
    for nom, que, porque in POR_CREAR:
        if porque is None and nom.startswith("Origen comercial"):
            porque = _sc._hueco_origen() + " Y Lead sigue en cero."
        elif porque is None and nom.startswith("Inventario"):
            n = {e: len(_ar._log(e)) for e in
                 ("OrdenCompra", "Proveedor", "Material", "Inventory")}
            sin = [c.etiqueta for c in _ar.logistica() if c.valor is None]
            porque = (f"el módulo de compras ya existe —OrdenCompra {n['OrdenCompra']}, "
                      f"Proveedor {n['Proveedor']}, Material {n['Material']}—, "
                      f"pero Inventory tiene {n['Inventory']} filas. "
                      f"{len(sin)} indicador(es) de Logística siguen sin fuente"
                      + (": " + " y ".join(sin) if sin else ""))
        elif porque is None and nom.startswith("Si el indicador"):
            kpi = ingest.fetch_axion_entity("KPI", None, 200)
            llenos = int(kpi["kpi_type"].astype(str).str.strip().ne("").sum()) \
                if "kpi_type" in kpi.columns else 0
            con_meta = int(pd.to_numeric(kpi.get("target"), errors="coerce").notna().sum())
            porque = (f"la columna existe y está llena en {llenos} de {len(kpi)} "
                      f"filas. Sin ella el tablero muestra la cifra y la meta "
                      f"pero no puede decir si cumple: no sabe si conviene subir "
                      f"o bajar. Son {con_meta} indicadores con meta cargada los "
                      f"que pasarían a tener verdicto, y no requiere desarrollo")
        elif porque is None and nom.startswith("Carga de costos"):
            from . import movimientos as _mv
            gt = _mv.gasto_total(None)
            con_obra = [c for c in _ar.obra()
                        if c.etiqueta == "Costo de obra registrado"]
            v = con_obra[0].valor if con_obra else None
            porque = (f"solo el {gt['pct_atribuido']:.1f}% del gasto lleva "
                      f"proyecto cargado. De S/ {gt['monto']:,.2f} registrados "
                      f"en el año, S/ {float(v):,.2f} se pudieron atribuir a "
                      f"una obra" if v else
                      f"ninguno de los {gt['filas']:,} movimientos de gasto "
                      f"lleva un proyecto que empareje con una obra: sin eso "
                      f"no hay rentabilidad")
        out.append((nom, que, porque or ""))
    return out


def metas() -> pd.DataFrame:
    """Los indicadores con su objetivo y meta, DICIENDO DE DÓNDE SALEN."""
    k = ingest.fetch_axion_opcional(
        "KPI", ["indicator", "objective", "target", "unit", "category",
                "monthly_values", "kpi_type"])
    if k.empty:
        return pd.DataFrame(columns=["perspectiva", "objetivo", "indicador",
                                     "meta", "unidad", "iniciativa", "origen"])
    caida = ingest.DEGRADADAS.get("KPI")
    origen = ("catálogo propio del proyecto — la tabla KPI ya no existe en "
              "AXION" if caida else "cargado en AXION (KPI)")
    return pd.DataFrame([{
        "perspectiva": str(r["category"]).strip(),
        "objetivo": str(r["objective"]).strip(),
        "indicador": str(r["indicator"]).strip(),
        "meta": pd.to_numeric(r["target"], errors="coerce"),
        "unidad": str(r["unit"]).strip(),
        "iniciativa": "",
        "origen": origen,
    } for _, r in k.sort_values(["category", "order"]).iterrows()])


def origen_metas() -> dict:
    """De dónde salen realmente las metas."""
    m = metas()
    caida = ingest.DEGRADADAS.get("KPI")
    con_meta = int(pd.to_numeric(m["meta"], errors="coerce").notna().sum()) \
        if len(m) else 0
    return {"filas": int(len(m)), "con_meta": con_meta,
            "en_axion": not bool(caida), "motivo": str(caida or "")}


def ingresos() -> list[dict]:
    s = ingest.fetch_axion_entity("Sale", None, 5000)
    f = pd.to_datetime(s["date"], errors="coerce")
    v = s[(s["status"] == "Vendido") & f.dt.year.eq(ANIO_CIERRE)
          & f.dt.month.le(6)]
    er = contasis.estados_de_resultados()
    ing = er[er["partida"].str.strip().str.startswith(
        "Ingresos de actividades ordinarias")] if not er.empty else er
    filas = [{
        "fuente": "AXION · lo vendido",
        "monto": float(_num(v["sale_price"]).sum()),
        "detalle": f"{len(v)} ventas con estado «Vendido», enero–junio 2026 "
                   f"(la misma ventana que declara ContaSis)",
    }]
    if not ing.empty:
        for _, r in ing.iterrows():
            filas.append({"fuente": str(r["_empresa"])[:44],
                          "monto": float(r["monto"] or 0),
                          "detalle": f'reconocido · {r["_periodo"]}'})
        filas.append({"fuente": "CONTASIS · total del grupo",
                      "monto": float(_num(ing["monto"]).sum()),
                      "detalle": "suma aritmética de las 4 empresas: no elimina "
                                 "operaciones entre ellas"})
    return filas


def utilidad_declarada() -> list[dict]:
    er = contasis.estados_de_resultados()
    if er.empty:
        return []
    u = er[er["partida"].str.strip().str.startswith(
        "Ganancia (Pérdida) Neta del Ejercicio")]
    return [{"empresa": str(r["_empresa"])[:44], "monto": float(r["monto"] or 0),
             "periodo": str(r["_periodo"])} for _, r in u.iterrows()]


def gasto_contable_por_obra() -> pd.DataFrame:
    """Gasto 6x del contador, solo lo que cae en una obra de AXION."""
    may = contasis.tablas("LIBRO MAYOR")
    if may.empty:
        return pd.DataFrame()
    # UNA presentación por empresa. Sin esto, el mismo asiento entra 2 o 3 veces.
    var = may["_archivo"].str.upper()
    may = may[var.str.contains("COMBINADO")]
    if may.empty:
        return pd.DataFrame()
    det = may[may["_clase"] == "detalle"]
    cd = next((c for c in det.columns if lx.normalizar(c) == "DESCRIPCION"), None)
    cc = next((c for c in det.columns if lx.normalizar(c) == "CUENTA"), None)
    if not cd or not cc:
        return pd.DataFrame()
    deb = pd.Series(0.0, index=det.index)
    for c in det.columns:
        if lx.normalizar(c) in ("DEBE", "DEBITO"):
            deb = deb.add(_num(det[c]), fill_value=0)
    g = det.assign(_d=deb, _c=det[cc].astype(str).str.strip(),
                   _s=det[cd].astype(str).str.rsplit(" - ", n=1).str[-1].str.strip())
    g = g[g["_c"].str.startswith("6")]
    obras = list(atribucion.obras_axion().query("declarada_en_Project")["obra"])
    g["_o"] = g["_s"].map(
        lambda x: (lambda o, c: o if c in ("exacta", "contenida") else None)(
            *atribucion._emparejar(x, obras)))
    total = float(g["_d"].sum())
    con = float(g[g["_o"].notna()]["_d"].sum())
    out = pd.DataFrame([{"obra": o,
                         "gasto": float(g[g["_o"] == o]["_d"].sum())}
                        for o in obras])
    out.attrs["total_6x"] = total
    out.attrs["atribuido"] = con
    todos = contasis.tablas("LIBRO MAYOR")
    sin_leer = sorted({
        str(e)[:44] for e in
        todos.loc[todos["_archivo"].str.upper().str.contains("ANALITICO"),
                  "_empresa"].unique()}) if not todos.empty else []
    out.attrs["variante"] = "Combinado"
    out.attrs["no_leidos"] = sin_leer
    return out


def gasto_administradora_por_obra() -> pd.DataFrame:
    eq = atribucion.equivalencias()
    m = eq[(eq["fuente"] == "Administración")
           & (eq["como"].isin(["exacta", "contenida"]))]
    obras = list(atribucion.obras_axion().query("declarada_en_Project")["obra"])
    filas = []
    for o in obras:
        r = m[m["obra_axion"] == o]
        filas.append({
            "obra": o,
            "monto": float(r["monto"].sum()) if len(r) and r["monto"].notna().any() else None,
            "hoja": " · ".join(r["etiqueta"]) if len(r) else "",
            "nota": ("la hoja llama MATERIALES a su columna de importe"
                     if len(r) and r["monto"].isna().all() else ""),
        })
    return pd.DataFrame(filas)


def _banda_ingresos_junio() -> dict:
    """La banda de resumen que el propio Excel de la administradora escribe."""
    from pathlib import Path
    p = (Path(__file__).resolve().parent.parent / "data" / "raw_exports"
         / "gastos_manuales" / "CONTROL DE INGRESOS Y GASTOS.xlsx")
    try:
        raw = pd.read_excel(p, sheet_name="JUNIO", header=None)
    except Exception:  # noqa: BLE001
        return {}
    out = {}
    for _, fila in raw.head(10).iterrows():
        vals = list(fila)
        for i, v in enumerate(vals[:-1]):
            r = str(v).strip()
            if r.lower() in ("venta al detalle", "venta mayoreo",
                             "total ingresos", "otros ingresos"):
                m = pd.to_numeric(pd.Series([vals[i + 1]]), errors="coerce")
                if m.notna().iloc[0]:
                    out[r] = float(m.iloc[0])
    return out


def _cobrado_axion_junio() -> float:
    cre = ingest.fetch_axion_entity("Credit", None, 5000)
    cxc = ingest.fetch_axion_entity("CxCPayment", None, 5000)
    f = pd.to_datetime(cxc["fecha"], errors="coerce")
    jun = f.dt.year.eq(ANIO_CIERRE) & f.dt.month.eq(6)
    total = float(_num(cxc.loc[jun, "monto"]).sum())
    for l in cre["iniciales"]:
        if not isinstance(l, list):
            continue
        for e in l:
            if not isinstance(e, dict):
                continue
            if "pendiente" in str(e.get("tipo") or "").lower():
                continue
            d = pd.to_datetime(e.get("fecha"), errors="coerce")
            if pd.notna(d) and d.year == ANIO_CIERRE and d.month == 6:
                total += float(str(e.get("monto") or 0).replace(",", "") or 0)
    return round(total, 2)


def _incongruencia_cobranza() -> dict:
    """Cobros que el Excel registra y AXION no."""
    ax = _cobrado_axion_junio()
    b = _banda_ingresos_junio()
    det = b.get("Venta al detalle")
    tot = b.get("Total Ingresos")
    if det is None:
        return {"n": 3, "titulo": "Cobros que el Excel registra y AXION no",
                "cifra": f"junio en AXION: S/ {ax:,.2f}",
                "detalle": ("no se pudo leer la banda de ingresos de la hoja "
                            "JUNIO del Excel de la administradora")}
    return {
        "n": 3,
        "titulo": "Cobros que el Excel registra y AXION no",
        "cifra": (f"junio · AXION S/ {ax:,.2f} (iniciales cobradas + cuotas) "
                  f"· Excel S/ {det:,.2f} («Venta al detalle»)"),
        "detalle": (f"**Las dos cifras no se restan**: miden cosas distintas "
                    f"y ninguna está mal. La de AXION es el cobro pegado a un "
                    f"crédito; la del Excel es la caja del mes, e incluye "
                    f"venta mayoreo hasta S/ {tot:,.2f} de «Total Ingresos». "
                    f"Lo que importa es el CONCEPTO: hay cobros que la "
                    f"administradora anota y que no llegan a AXION, y por eso "
                    f"hoy hacen falta las dos fuentes. Ese es el argumento "
                    f"para que AXION reemplace ese Excel — no la resta")}


def incongruencias() -> list[dict]:
    """Las cinco más resaltantes, con su cifra. Nada granular."""
    cont = gasto_contable_por_obra()
    adm = gasto_administradora_por_obra()
    con_cont = int((cont["gasto"] > 0).sum()) if not cont.empty else 0
    con_adm = int(adm["monto"].notna().sum()) if not adm.empty else 0
    eq = atribucion.equivalencias()
    sin = eq[(eq["fuente"].str.startswith("Administración")) & (eq["como"] == "—")]
    t6 = cont.attrs.get("total_6x", 0)
    atr = cont.attrs.get("atribuido", 0)

    def _m(o):
        r = cont[cont["obra"] == o]["gasto"]
        return float(r.iloc[0]) if len(r) else 0.0

    def _a(o):
        r = adm[adm["obra"] == o]["monto"]
        return float(r.iloc[0]) if len(r) and pd.notna(r.iloc[0]) else 0.0

    return [
        {"n": 1, "titulo": "Obras que aparecen en una fuente y no en la otra",
         "cifra": (f"ALAMEDA: S/ {_a('ALAMEDA'):,.2f} en el Excel de la "
                   f"administradora y S/ {_m('ALAMEDA'):,.2f} en lo que "
                   f"leemos de la contabilidad"),
         "detalle": (f"ese cero es NUESTRO, no del contador: el mayor "
                     f"ANALÍTICO de {len(cont.attrs.get('no_leidos', []))} "
                     f"empresas no tiene columna de cuenta —el número va en "
                     f"una fila separadora— y el lector lo descarta entero. "
                     f"ALAMEDA está ahí, en la cuenta 60310251 de Habitat "
                     f"EIRL. TORRE BLANCA sí está en las dos que leemos, con "
                     f"cifras distintas: S/ {_m('TORRE BLANCA'):,.2f} "
                     f"contable contra S/ {_a('TORRE BLANCA'):,.2f} del "
                     f"Excel — y el Excel llega al 18-jul mientras el libro "
                     f"cierra en junio, así que tampoco cubren la misma "
                     f"ventana")},
        {"n": 2, "titulo": "El contador casi no separa por obra",
         "cifra": f"{con_cont} obras con gasto identificable contra {con_adm} "
                  f"en el Excel de la administradora",
         "detalle": f"del gasto 6x total (S/ {t6:,.2f}) solo se atribuye "
                    f"S/ {atr:,.2f} ({100 * atr / t6:.1f}%)" if t6 else ""},
        _incongruencia_cobranza(),
        {"n": 4, "titulo": "JARDINES sale en cero y no es cero",
         "cifra": "137 movimientos en su hoja",
         "detalle": "esa hoja llama MATERIALES a la columna que las otras 20 "
                    "llaman MONTO. Es data de Habitat: se reporta, no se corrige"},
        {"n": 5, "titulo": "Obras del Excel que no existen en AXION",
         "cifra": f"{len(sin)} obras con "
                  f"S/ {float(sin['monto'].sum(skipna=True)):,.2f} de movimiento",
         "detalle": "MIAMI, CHANCAY, LOS MAGNOLIAS, PALIAN… Si Habitat quiere "
                    "verlas en el tablero, las sube a AXION"},
    ]
