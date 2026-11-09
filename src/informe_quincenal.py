"""EL INFORME QUINCENAL."""
from __future__ import annotations

import calendar
import datetime as dt
import html
import json
import pathlib
import re

import pandas as pd

from . import crm, ingest, movimientos, reloj

RAIZ = pathlib.Path(__file__).resolve().parent.parent
INDICADORES = RAIZ / "config" / "indicadores.json"
MES3 = ["", "ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "set",
        "oct", "nov", "dic"]
MESES = ["", "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "setiembre", "octubre", "noviembre", "diciembre"]
INICIO = dt.date(2026, 10, 1)
TEXTO_ASIENTO = 600          # largo máximo de cada asiento de la bitácora
AREAS_CFG = RAIZ / "config" / "informe_areas.json"


def _f(x, nd: int = 2):
    """Número a float de JSON; NaN y vacíos a None (NaN no es JSON)."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return None if v != v else round(v, nd)


def _t(x) -> str:
    v = "" if x is None else str(x).strip()
    return "" if v.lower() in ("nan", "none", "nat") else v


def _meta_anual() -> float:
    """La meta anual de ventas, del mismo catálogo que usa el scorecard."""
    try:
        d = json.loads(INDICADORES.read_text(encoding="utf-8"))
        for i in d.get("indicadores", []):
            if i.get("indicador") == "% incremento ventas":
                return float(i.get("meta") or 0)
    except (OSError, ValueError):
        pass
    return 0.0


def _agrupar(x: pd.DataFrame, col: str) -> list[list]:
    """[clave, ventas, monto] por la columna, de mayor a menor monto."""
    if x.empty:
        return []
    g = x.assign(_k=x[col].fillna("").astype(str).str.strip().replace("", "(sin dato)"))
    filas = [[k, int(len(v)), _f(v["precio"].sum())] for k, v in g.groupby("_k")]
    return sorted(filas, key=lambda r: -(r[2] or 0))


def _var(actual: float, previo: float) -> float | None:
    """Variación porcentual contra la base, con UN decimal. Sin base (la."""
    if not previo:
        return None
    return round(100.0 * (actual - previo) / previo, 1)


def _meses_inf(hoy: dt.date) -> list[dict]:
    """Los meses del AÑO EN CURSO que ya empezaron desde INICIO, del más viejo al más nuevo."""
    out = []
    anio = hoy.year
    for mes in range(1, hoy.month + 1):
        ini = dt.date(anio, mes, 1)
        if ini < INICIO:
            continue
        fin = dt.date(anio, mes, calendar.monthrange(anio, mes)[1])
        out.append({"id": f"{anio}-{mes:02d}", "anio": anio, "mes": mes,
                    "desde": ini.isoformat(), "hasta": fin.isoformat(),
                    "rotulo": f"{MESES[mes]} {anio}",
                    "nro": (anio - INICIO.year) * 12 + (mes - INICIO.month) + 1,
                    "completa": fin < hoy})
    return out


def _ventas_mes(meses: list[dict], anio: int, meta: float, hoy: dt.date) -> dict:
    s = ingest.fetch_axion_entity("Sale", None, 5000)
    if s.empty or "date" not in s.columns:
        return {}
    s = s.copy()
    s["fd"] = pd.to_datetime(s["date"], errors="coerce").dt.normalize()
    s = s[s["status"].astype(str).str.strip().eq("Vendido")]
    s["precio"] = pd.to_numeric(s["sale_price"], errors="coerce").fillna(0.0)
    s["real"] = pd.to_numeric(s["real_income"], errors="coerce").fillna(0.0)
    ts = pd.Timestamp
    meta_mes = meta / 12.0 if meta else 0.0
    out = {}
    for m in meses:
        y, mo = m["anio"], m["mes"]
        ini = dt.date(y, mo, 1)
        fin_mes = dt.date.fromisoformat(m["hasta"])
        corte = fin_mes if m["completa"] else min(hoy, fin_mes)
        py, pm = (y - 1, 12) if mo == 1 else (y, mo - 1)
        ult_p = calendar.monthrange(py, pm)[1]
        pini = dt.date(py, pm, 1)
        pfin = dt.date(py, pm, ult_p if m["completa"] else min(corte.day, ult_p))
        x = s[(s["fd"] >= ts(ini)) & (s["fd"] <= ts(corte))].sort_values(
            ["fd", "precio"], ascending=[True, False])
        xp = s[(s["fd"] >= ts(pini)) & (s["fd"] <= ts(pfin))]
        acum_anio = s[(s["fd"] >= ts(dt.date(y, 1, 1))) & (s["fd"] <= ts(corte))]["precio"].sum()
        monto, real = float(x["precio"].sum()), float(x["real"].sum())
        out[m["id"]] = {
            "n": int(len(x)),
            "monto": _f(monto),
            "ingreso_real": _f(real),
            "completa": bool(m["completa"]),
            "corte": corte.isoformat(),
            "prev": {
                "rotulo": f"{pini.day}–{pfin.day} {MES3[pm]} {py}",
                "n": int(len(xp)),
                "monto": _f(xp["precio"].sum()),
                "ingreso_real": _f(xp["real"].sum()),
            },
            "var": {
                "n": _var(len(x), len(xp)),
                "monto": _var(monto, float(xp["precio"].sum())),
                "ingreso_real": _var(real, float(xp["real"].sum())),
            },
            "acum_mes": _f(monto),
            "meta_mes": _f(meta_mes),
            "pct_meta_mes": _f(100 * monto / meta_mes, 1) if meta_mes else None,
            "acum_anio": _f(acum_anio),
            "meta_anio": _f(meta),
            "pct_meta_anio": _f(100 * acum_anio / meta, 1) if meta else None,
            "ventas": [[r.fd.strftime("%Y-%m-%d"), _t(r.project), _t(r.unit),
                        _t(r.advisor), _t(r.modality), _f(r.precio), _f(r.real)]
                       for r in x.itertuples()],
            "por_vendedor": _agrupar(x, "advisor"),
            "por_modalidad": _agrupar(x, "modality"),
            "por_proyecto": _agrupar(x, "project"),
        }
    return out


def _responsables_mes(meses: list[dict], base) -> dict:
    """Los leads del mes por responsable, con su tiempo de atención (mediana de horas."""
    if base is None or base.empty or "creado" not in base.columns:
        return {}
    creado = pd.to_datetime(base["creado"], errors="coerce").dt.normalize()
    out = {}
    for m in meses:
        df = base[(creado >= pd.Timestamp(m["desde"])) & (creado <= pd.Timestamp(m["hasta"]))]
        if df.empty:
            out[m["id"]] = []
            continue
        out[m["id"]] = [[r["responsable"], int(r["leads"]), int(r["vendidos"]),
                         int(r["sin_gestionar"]), _f(r["horas_mediana"], 1)]
                        for r in crm.por_responsable(df=df)]
    return out


def _marketing_kpis(meses: list[tuple[int, int]]) -> dict:
    """Los KPIs de marketing de AXION (`MarketingKPI`: una fila por indicador y."""
    k = ingest.fetch_axion_entity("MarketingKPI", None, 5000)
    if k.empty or "kpi_code" not in k.columns:
        return {}
    k = k.copy()
    k["anio_n"] = pd.to_numeric(k["year"], errors="coerce")
    k["mes_n"] = pd.to_numeric(k["month"], errors="coerce")
    k = k.sort_values("updated_date") if "updated_date" in k.columns else k
    out = {}
    for anio, mes in meses:
        x = k[(k["anio_n"] == anio) & (k["mes_n"] == mes)]
        dup = int(x.duplicated("kpi_code").sum())
        x = x.drop_duplicates("kpi_code", keep="last")
        filas = []
        for r in sorted(x.itertuples(), key=lambda r: (len(str(r.kpi_code)), str(r.kpi_code))):
            bd = r.breakdown if isinstance(r.breakdown, list) else []
            filas.append([
                _t(r.kpi_code), _t(r.kpi_name), _f(r.value), _f(r.meta), _t(r.meta_type),
                [[_t(d.get("dimension")), _f(d.get("value")), _t(d.get("dimension_type"))]
                 for d in bd if isinstance(d, dict)],
            ])
        out[f"{anio}-{mes:02d}"] = {"hay": bool(filas), "duplicados": dup, "filas": filas}
    return out


def _oficina() -> list[str]:
    """Los proyectos que lleva Oficina técnica, de `config/informe_areas.json`."""
    try:
        d = json.loads(AREAS_CFG.read_text(encoding="utf-8"))
        return [str(p).strip() for p in (d.get("oficina_tecnica") or {}).get("proyectos", [])
                if str(p).strip()]
    except (OSError, ValueError):
        return []


def _obras(meses: list[dict]) -> dict:
    """La bitácora de obra por MES y proyecto: los asientos (cada uno es."""
    oficina = _oficina()
    b = ingest.fetch_axion_entity("BitacoraObra", None, 5000)
    if b.empty or "date" not in b.columns:
        return {"proyectos": [], "oficina": oficina, "por_mes": {}}
    b = b.copy()
    b["d"] = b["date"].astype(str).str[:10]
    b["proyecto"] = b["project_name"].map(_t).replace("", "(sin proyecto)")

    def limpio(h: str) -> str:
        """El asiento de la bitácora, listo para el informe. La mayoría de los."""
        t = re.sub(r"<[^>]+>", " ", str(h))
        t = re.sub(r"\s+", " ", html.unescape(t)).strip()
        n = re.search(r"ASIENTO\s*N?[°º]?\s*(\d+)", t, re.I)
        m = re.search(r"ACTIVIDADES REALIZADAS\s*:?\s*(.*?)"
                      r"(?=\s*(?:CONTROL DE SEGURIDAD|AVANCE A LA FECHA|OCURRENCIAS)\b|$)", t, re.I)
        if m:
            act = m.group(1).strip(" -:")
            if len(act) < 4 or act.upper() in ("NINGUNA", "NINGUNO"):
                av = re.search(r"AVANCE A LA FECHA\s*:?\s*(.*?)(?=\s*OCURRENCIAS\b|$)", t, re.I)
                act = av.group(1).strip(" -:") if av else ""
            if len(act) >= 4:
                t = (f"Asiento N° {n.group(1)}: " if n else "") + act
        return t if len(t) <= TEXTO_ASIENTO else t[:TEXTO_ASIENTO - 1].rstrip() + "…"

    por_mes = {}
    for m in meses:
        x = b[(b["d"] >= m["desde"]) & (b["d"] <= m["hasta"])].sort_values(["d", "id"])
        proy = {}
        for nombre, g in x.groupby("proyecto"):
            proy[nombre] = {
                "asientos": [[r.d, limpio(r.description), _t(r.reported_by)] for r in g.itertuples()],
            }
        por_mes[m["id"]] = proy
    return {"proyectos": sorted(set(b["proyecto"])), "oficina": oficina, "por_mes": por_mes}


_MES_NOMBRE = {n: i for i, n in enumerate(MESES) if n}
_MES_NOMBRE["septiembre"] = 9


def _corto(nombre: str) -> str:
    p = _t(nombre).split()
    if not p:
        return "(sin nombre)"
    return p[0].capitalize() + (f" {p[1][0].upper()}." if len(p) > 1 else "")


def _rrhh(meses: list[tuple[int, int]]) -> dict:
    """Las tardanzas del módulo Recursos Humanos > Remuneraciones de AXION."""
    r = ingest.fetch_axion_entity("Remuneracion", None, 5000)
    if r.empty or "mes" not in r.columns:
        return {}
    r = r.copy()
    r["anio_n"] = pd.to_numeric(r["anio"], errors="coerce")
    r["mes_n"] = r["mes"].map(lambda m: _MES_NOMBRE.get(_t(m).lower()))
    cols = ["tardanzas_s5", "tardanzas_s10", "faltas", "falta_x_tardanza",
            "total_descuento_tardanza"]
    for c in cols:
        r[c] = pd.to_numeric(r[c], errors="coerce").fillna(0.0) if c in r.columns else 0.0
    r["nom"] = r["nombre"].map(_t)
    r = r.sort_values("updated_date") if "updated_date" in r.columns else r
    out = {}
    for anio, mes in meses:
        x = r[(r["anio_n"] == anio) & (r["mes_n"] == mes)]
        dup = int(x.duplicated("nom").sum())
        x = x.drop_duplicates("nom", keep="last")
        con = x[(x[cols] != 0).any(axis=1)]
        out[f"{anio}-{mes:02d}"] = {
            "hay": bool(len(x)),
            "personal": int(len(x)),
            "duplicados": dup,
            "con_tardanza": int(((x["tardanzas_s5"] > 0) | (x["tardanzas_s10"] > 0)).sum()),
            "s5": _f(x["tardanzas_s5"].sum(), 0),
            "s10": _f(x["tardanzas_s10"].sum(), 0),
            "faltas": _f(x["faltas"].sum(), 0),
            "falta_x_tardanza": _f(x["falta_x_tardanza"].sum(), 0),
            "descuento": _f(x["total_descuento_tardanza"].sum()),
            "filas": [[_corto(g.nom), _t(g.area), _f(g.tardanzas_s5, 0), _f(g.tardanzas_s10, 0),
                       _f(g.faltas, 0), _f(g.falta_x_tardanza, 0), _f(g.total_descuento_tardanza)]
                      for g in con.itertuples()],
        }
    return out


def _marketing(meses: list[dict], base) -> dict:
    """Los leads de Kommo del MES (las mismas definiciones de la hoja CRM)."""
    if base is None or base.empty or "creado" not in base.columns:
        return {}
    creado = pd.to_datetime(base["creado"], errors="coerce").dt.normalize()
    out = {}
    for m in meses:
        ini, fin = pd.Timestamp(m["desde"]), pd.Timestamp(m["hasta"])
        df = base[(creado >= ini) & (creado <= fin)]
        bloque = {}
        if df.empty:
            bloque.update({"hay": False})
            out[m["id"]] = bloque
            continue
        emb = crm.embudo_decision(df=df, con_citas=False)
        camp = crm._conteo(df, "campana")
        propios = next((c["leads"] for c in camp
                        if str(c["valor"]).strip().lower() == "publicidad propia"), 0)
        bloque.update({
            "hay": True,
            "leads": int(emb["leads"]),
            "contactados": int(emb["contactados"]),
            "visitas": int(emb["visitas"]),
            "vendidos": int(emb["vendidos"]),
            "leads_por_venta": emb.get("leads_por_venta"),
            "propios": int(propios),
            "campanas": [[str(c["valor"]), int(c["leads"])] for c in camp],
        })
        out[m["id"]] = bloque
    return out


TOP_LOGISTICA = 10


def _logistica(meses: list[dict]) -> dict:
    oc = ingest.fetch_axion_entity("OrdenCompra", None, 5000)
    pp = ingest.fetch_axion_entity("PagoPersonal", None, 5000)
    ordenes = []
    if not oc.empty and "date" in oc.columns:
        for r in oc.itertuples():
            prov = r.proveedor if isinstance(r.proveedor, dict) else {}
            nombre = _t(prov.get("empresa")) or "(sin proveedor)"
            ordenes.append({
                "fecha": str(r.date)[:10], "nombre": nombre,
                "clave": _t(prov.get("ruc")) or nombre.upper(),
                "tipo": _t(r.tipo) or "(sin tipo)",
                "total": float(pd.to_numeric(r.total, errors="coerce") or 0.0),
                "items": r.items if isinstance(r.items, list) else []})
    pagos = []
    if not pp.empty and "payments" in pp.columns:
        for r in pp.itertuples():
            proy = _t(r.project_name) or "(sin proyecto)"
            for x in (r.payments if isinstance(r.payments, list) else []):
                if isinstance(x, dict) and x.get("fecha"):
                    pagos.append((str(x["fecha"])[:10], proy, float(pd.to_numeric(x.get("p_actual"), errors="coerce") or 0.0)))

    def top(lista, n, suma_penultima=True):
        lista = sorted(lista, key=lambda f: -f[-1])
        if len(lista) <= n + 1:
            return lista
        cab, resto = lista[:n], lista[n:]
        if resto:
            cab.append([f"(otros {len(resto)})"] + [""] * (len(resto[0]) - 3) +
                       [round(sum(f[-2] for f in resto), 2) if suma_penultima else None,
                        round(sum(f[-1] for f in resto), 2)])
        return cab

    pagos_mes = {}
    for m in meses:
        ps = [p for p in pagos if m["desde"] <= p[0] <= m["hasta"]]
        proys = {}
        for _, proy, monto in ps:
            n_, t_ = proys.get(proy, (0, 0.0))
            proys[proy] = (n_ + 1, t_ + monto)
        pagos_mes[m["id"]] = {
            "hay": bool(ps), "n": len(ps), "monto": _f(sum(p[2] for p in ps)),
            "por_proyecto": sorted(([k, v[0], _f(v[1])] for k, v in proys.items()), key=lambda f: -(f[2] or 0))}

    out = {}
    for q in meses:
        x = [o for o in ordenes if q["desde"] <= o["fecha"] <= q["hasta"]]
        prov, tipo, mat = {}, {}, {}
        for o in x:
            a = prov.setdefault(o["clave"], {"nombre": o["nombre"], "n": 0, "monto": 0.0})
            a["n"] += 1
            a["monto"] += o["total"]
            t = tipo.setdefault(o["tipo"], [0, 0.0])
            t[0] += 1
            t[1] += o["total"]
            for it in o["items"]:
                if not isinstance(it, dict):
                    continue
                k = (_t(it.get("producto")).upper() or "(sin producto)", _t(it.get("unidad")).upper())
                b = mat.setdefault(k, [0.0, 0.0])
                b[0] += float(pd.to_numeric(it.get("cantidad"), errors="coerce") or 0.0)
                b[1] += float(pd.to_numeric(it.get("total"), errors="coerce") or 0.0)
        out[q["id"]] = {
            "hay": bool(x),
            "n": len(x),
            "monto": _f(sum(o["total"] for o in x)),
            "n_proveedores": len(prov),
            "por_tipo": sorted(([k, v[0], _f(v[1])] for k, v in tipo.items()), key=lambda f: -(f[2] or 0)),
            "por_proveedor": top([[v["nombre"], v["n"], _f(v["monto"])] for v in prov.values()], TOP_LOGISTICA),
            "n_materiales": len(mat),
            "por_material": top([[k[0], k[1], _f(v[0]), _f(v[1])] for k, v in mat.items()],
                                TOP_LOGISTICA, suma_penultima=False),
            "pagos_personal": pagos_mes.get(q["id"], {"hay": False, "n": 0, "monto": 0.0, "por_proyecto": []}),
        }
    return out


_TRASPASO = r"se\s+(?:deposit[oó]|retir[oó])|retiro\s+de|traspaso"


def _administracion(meses: list[dict], anio: int) -> dict:
    """La caja del MES: entró, salió, traspasos nombrados aparte y detalle por cuenta."""
    df = movimientos.crudo()
    if df.empty:
        return {}
    d = df[df["fecha_n"].dt.year.eq(anio)].copy()
    con = d["concepto"].fillna("").astype(str)
    d = d[~(d["clase"].eq("presupuesto") & con.str.strip().str.upper().str.startswith("SALDO"))]
    con = d["concepto"].fillna("").astype(str)
    d["tr"] = con.str.contains(_TRASPASO, case=False, regex=True)
    d["cu"] = d["cuenta"].fillna("").astype(str).str.strip().replace("", "(sin cuenta)")
    d["fn"] = d["fecha_n"].dt.normalize()
    d["con_"] = con.str.strip()
    out = {}
    for q in meses:
        x = d[(d["fn"] >= pd.Timestamp(q["desde"])) & (d["fn"] <= pd.Timestamp(q["hasta"]))]
        ent = x[x["clase"].isin(["venta", "presupuesto"])]
        sal = x[x["clase"].eq("gasto")]

        def top(g):
            g = g.sort_values("monto_n", ascending=False).head(5)
            return [[r.fn.strftime("%Y-%m-%d"), r.con_[:160], r.cu, _f(r.monto_n), bool(r.tr)]
                    for r in g.itertuples()]

        cuentas = sorted(set(ent["cu"]) | set(sal["cu"]))
        por_cuenta = sorted(
            ([c, _f(ent[ent["cu"] == c]["monto_n"].sum()), _f(sal[sal["cu"] == c]["monto_n"].sum())]
             for c in cuentas), key=lambda r: -(r[2] or 0))
        out[q["id"]] = {
            "n": int(len(x)),
            "entro": _f(ent["monto_n"].sum()),
            "salio": _f(sal["monto_n"].sum()),
            "tr_entro": _f(ent[ent["tr"]]["monto_n"].sum()),
            "tr_entro_n": int(ent["tr"].sum()),
            "tr_salio": _f(sal[sal["tr"]]["monto_n"].sum()),
            "tr_salio_n": int(sal["tr"].sum()),
            "por_cuenta": por_cuenta,
            "mayores_ingresos": top(ent),
            "mayores_gastos": top(sal),
        }
    return out


def calcular() -> dict:
    """El bloque `informe_quincenal` del payload."""
    ahora = reloj.ahora()
    anio = ahora.year
    hoy = ahora.date()
    meses_inf = _meses_inf(hoy)
    if not meses_inf:
        return {"hay": False}
    meta = _meta_anual()
    meses = [(m["anio"], m["mes"]) for m in meses_inf]
    out = {"hay": True, "anio": anio, "generado": reloj.sello(), "inicio": INICIO.isoformat(),
           "meta_anual": _f(meta), "meses_inf": meses_inf, "ventas": {},
           "marketing": {}, "administracion": {}, "marketing_kpis": {}, "logistica": {},
           "obras": {"proyectos": [], "oficina": [], "por_mes": {}}, "rrhh": {}}
    base = None
    try:
        base = crm._base(None, anio)       # los leads de Kommo, una sola lectura para Ventas y Marketing
    except Exception as e:  # noqa: BLE001
        out["marketing_error"] = f"{type(e).__name__}: {e}"
    try:
        out["ventas"] = _ventas_mes(meses_inf, anio, meta, hoy)
    except Exception as e:  # noqa: BLE001 — una fuente caída no tumba la otra
        out["ventas_error"] = f"{type(e).__name__}: {e}"
    try:
        for mid, filas in _responsables_mes(meses_inf, base).items():
            if mid in out["ventas"]:
                out["ventas"][mid]["responsables"] = filas
    except Exception as e:  # noqa: BLE001
        out["ventas_error"] = out.get("ventas_error", "") + f" responsables: {type(e).__name__}: {e}"
    try:
        out["marketing"] = _marketing(meses_inf, base)
    except Exception as e:  # noqa: BLE001
        out["marketing_error"] = f"{type(e).__name__}: {e}"
    try:
        out["administracion"] = _administracion(meses_inf, anio)
    except Exception as e:  # noqa: BLE001
        out["administracion_error"] = f"{type(e).__name__}: {e}"
    try:
        out["marketing_kpis"] = _marketing_kpis(meses)
    except Exception as e:  # noqa: BLE001
        out["marketing_kpis_error"] = f"{type(e).__name__}: {e}"
    try:
        out["obras"] = _obras(meses_inf)
    except Exception as e:  # noqa: BLE001
        out["obras_error"] = f"{type(e).__name__}: {e}"
    try:
        out["rrhh"] = _rrhh(meses)
    except Exception as e:  # noqa: BLE001
        out["rrhh_error"] = f"{type(e).__name__}: {e}"
    try:
        out["logistica"] = _logistica(meses_inf)
    except Exception as e:  # noqa: BLE001
        out["logistica_error"] = f"{type(e).__name__}: {e}"
    return out
