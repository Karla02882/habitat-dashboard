"""EL STOCK PARA EL PERSONAL EXTERNO DE VENTAS."""

from __future__ import annotations

import time

import pandas as pd

from . import ingest, reloj

COLUMNAS = ["Unidad", "Estado", "m²", "Precio"]

COLUMNAS_DEPA = ["N° dorm.", "N° baños"]

PISTAS_DORM = ("dorm", "bedroom", "habitac", "cuarto")
PISTAS_BANO = ("bano", "baño", "bathroom", "bath", "servicio_hig")

PISTAS_NO_DEPA = ("COCHERA", "OFICINA", "TIENDA")


def _es_no_depa(nombre_unidad: str) -> bool:
    n = str(nombre_unidad or "").strip().upper()
    return any(n.startswith(p) for p in PISTAS_NO_DEPA)

PROHIBIDOS = ("advisor", "client_name", "sale_date")

ESTADOS_CON_STOCK = ("LIBRE",)


def _num(serie: pd.Series) -> pd.Series:
    return pd.to_numeric(serie, errors="coerce")


def _val(x):
    """Un número de pandas a algo que JSON entienda, o None si no hay."""
    if x is None or pd.isna(x):
        return None
    return float(x)


def _local(ts) -> str:
    """Una marca de hora de AXION (UTC, sin zona) a hora de Huancayo."""
    t = pd.to_datetime(ts, errors="coerce")
    return "" if pd.isna(t) else (t - pd.Timedelta(hours=5)).strftime("%Y-%m-%d %H:%M")


def _entero(x):
    """Un conteo —dormitorios, baños— como entero, o None."""
    if x is None or pd.isna(x):
        return None
    try:
        return int(round(float(x)))
    except (TypeError, ValueError):
        return None


def _buscar_campo(u: pd.DataFrame, pistas: tuple) -> tuple:
    """El primer campo que case con las pistas Y traiga números."""
    candidatos = [c for c in u.columns
                  if any(k in c.lower() for k in pistas)]
    if not candidatos:
        return None, ""
    for c in candidatos:
        nums = pd.to_numeric(u[c], errors="coerce")
        if nums.notna().sum() > 0:
            return c, ""
    return None, ("el campo «%s» existe pero no trae números"
                  % candidatos[0])


def calcular() -> dict:
    """El stock por proyecto, con las cinco columnas y nada más."""
    u = ingest.fetch_axion_entity("Unit", None, 5000)
    if u is None or u.empty:
        return {"hay": False, "motivo": "AXION no devolvió unidades"}

    for c in ("name", "project", "status"):
        if c not in u.columns:
            return {"hay": False, "motivo": f"la tabla Unit no trae «{c}»"}

    u = u.copy()
    u["zproy"] = u["project"].fillna("(sin proyecto)").astype(str).str.strip()

    tipos = {}
    try:
        pr = ingest.fetch_axion_entity("Project", None, 500)
        if pr is not None and not pr.empty and "project_type" in pr.columns:
            for r in pr.itertuples():
                nom = str(getattr(r, "name", "") or "").strip().upper()
                tip = str(getattr(r, "project_type", "") or "").strip()
                if nom and tip:
                    tipos[nom] = tip
    except Exception:  # noqa: BLE001
        tipos = {}
    u["zest"] = u["status"].fillna("(sin estado)").astype(str).str.strip().str.upper()
    u["zarea"] = _num(u["area_m2"]) if "area_m2" in u.columns else None
    u["zprecio"] = _num(u["real_price"]) if "real_price" in u.columns else None
    u["zppm"] = _num(u["price_per_m2"]) if "price_per_m2" in u.columns else None
    u["zedit"] = (pd.to_datetime(u["updated_date"], errors="coerce")
                  if "updated_date" in u.columns else pd.NaT)

    # Dormitorios y baños: el campo se busca, no se escribe a mano
    cDorm, avDorm = _buscar_campo(u, PISTAS_DORM)
    cBano, avBano = _buscar_campo(u, PISTAS_BANO)
    u["zdorm"] = _num(u[cDorm]) if cDorm else None
    u["zbano"] = _num(u[cBano]) if cBano else None

    def _armar_tarjeta(nombre: str, tipo: str, g_sub, libs_sub) -> dict:
        """Una tarjeta de proyecto, a partir de su propio recorte de filas."""
        filas = []
        for r in libs_sub.sort_values("name").itertuples():
            fila = [
                str(getattr(r, "name", "") or "—"),
                str(r.zest),
                _val(r.zarea),
                _val(r.zprecio),
            ]
            fila.append(_entero(getattr(r, "zdorm", None)) if cDorm else None)
            fila.append(_entero(getattr(r, "zbano", None)) if cBano else None)
            fila.append(str(getattr(r, "id", "") or ""))
            filas.append(fila)
        pr = [x for x in libs_sub["zprecio"].tolist() if x == x and x is not None]
        ar = [x for x in libs_sub["zarea"].tolist() if x == x and x is not None]
        hay_dorm = any(f[4] is not None for f in filas)
        hay_bano = any(f[5] is not None for f in filas)
        return {
            "proyecto": nombre,
            "hay_dorm": hay_dorm,
            "hay_bano": hay_bano,
            "tipo": tipo,
            "unidades": int(len(g_sub)),
            "libres": int(len(filas)),
            # el rango que muestra la tarjeta del proyecto, como en AXION
            "precio_min": float(min(pr)) if pr else None,
            "precio_max": float(max(pr)) if pr else None,
            "area_min": float(min(ar)) if ar else None,
            "area_max": float(max(ar)) if ar else None,
            "edicion": _local(g_sub["zedit"].max()),
            "filas": filas,
        }

    proyectos = []
    sin_stock = 0
    sin_tipo_real = []
    for nombre, g in u.groupby("zproy", sort=True):
        libres = int((g["zest"].isin(ESTADOS_CON_STOCK)).sum())
        if libres == 0:
            sin_stock += 1
            continue
        if nombre.strip().upper() not in tipos:
            sin_tipo_real.append(nombre)
        tipo_proy = tipos.get(nombre.strip().upper(), "Otros")
        libs = g[g["zest"].isin(ESTADOS_CON_STOCK)]

        if tipo_proy == "Departamentos":
            es_otro = g["name"].apply(_es_no_depa)
            g_depa, g_otro = g[~es_otro], g[es_otro]
            libs_depa, libs_otro = libs[~es_otro.loc[libs.index]], libs[es_otro.loc[libs.index]]
        else:
            g_depa, g_otro = g, g.iloc[0:0]
            libs_depa, libs_otro = libs, libs.iloc[0:0]

        if len(libs_depa):
            proyectos.append(_armar_tarjeta(nombre, tipo_proy, g_depa, libs_depa))
        if len(libs_otro):
            proyectos.append(_armar_tarjeta(nombre, "Otros", g_otro, libs_otro))

    proyectos.sort(key=lambda p: -p["libres"])
    estados = sorted({f[1] for p in proyectos for f in p["filas"]})
    detectado = {"dorm": cDorm, "banos": cBano}
    avisos = [x for x in (avDorm, avBano) if x]
    return {
        "hay": True,
        "leido": reloj.sello("%Y-%m-%d %H:%M"),
        "leido_ts": int(time.time()),
        "ultima_edicion": _local(u["zedit"].max()),
        "cols": list(COLUMNAS),
        "cols_depa": list(COLUMNAS_DEPA),
        "detectado": detectado,
        "avisos_campos": avisos,
        "proyectos": proyectos,
        "estados": estados,
        "totales": {
            "proyectos": len(proyectos),
            "unidades": sum(p["unidades"] for p in proyectos),
            "libres": sum(len(p["filas"]) for p in proyectos),
        },
        "tipos": [x for x in ("Lotes", "Departamentos", "Casas", "Oficinas", "Otros")
                  if any(p["tipo"] == x for p in proyectos)],
        "sin_tipo": sorted(sin_tipo_real),
        "sin_stock": sin_stock,
    }


def sin_datos_de_personas(datos: dict) -> list[str]:
    """Control propio: que no se haya colado un dato de persona."""
    import json

    u = ingest.fetch_axion_entity("Unit", None, 5000)
    if u is None or u.empty:
        return ["no se pudo leer Unit para el control"]
    sellos = ("leido", "leido_ts", "ultima_edicion")
    copia = {k: v for k, v in datos.items() if k not in sellos}
    copia["proyectos"] = [{k: v for k, v in p.items() if k != "edicion"}
                          for p in datos.get("proyectos", [])]
    crudo = json.dumps(copia, ensure_ascii=False)
    fallas = []
    for campo in PROHIBIDOS:
        if campo not in u.columns:
            continue
        vistos = {str(x).strip() for x in u[campo].dropna().tolist()}
        vistos = {v for v in vistos if len(v) >= 6}
        colados = sorted(v for v in vistos if v in crudo)
        if colados:
            fallas.append(
                f"el stock del externo trae {len(colados)} valor(es) de "
                f"«{campo}»: {colados[:3]}")
    return fallas
