"""INGESTA · exports por página de AXION (los `.xls` que son HTML)."""
from __future__ import annotations

import pandas as pd

from . import ingest
from . import lectura_excel as lx

ARCHIVO_GASTOS = "gastos_2026-07-22.xls"


def gastos_snapshot() -> pd.DataFrame:
    """El export tal como está, sin convertir monedas ni renombrar columnas."""
    ruta = lx.CRUDOS / ARCHIVO_GASTOS
    if not ruta.exists():
        return pd.DataFrame()
    df = lx.leer_archivo(ruta)[0].datos.copy()
    col = next((c for c in df.columns if "monto" in c.lower()), None)
    if col:
        df["monto_num"] = pd.to_numeric(
            df[col].astype(str).str.replace(",", ""), errors="coerce")
    return df


def contraste_con_api() -> dict:
    """Vuelve a medir el solapamiento contra la API, ahora."""
    exp = gastos_snapshot()
    if exp.empty:
        return {"error": f"no está {ARCHIVO_GASTOS}"}
    api = ingest.fetch_axion_entity("Gasto", None, 5000)
    api_monto = pd.to_numeric(api["monto"], errors="coerce")
    api_fecha = api["fecha"].astype(str).str.strip()

    col_fecha = next(c for c in exp.columns if "fecha" in c.lower())
    exp_fecha = exp[col_fecha].astype(str).str.strip()

    pares_exp = set(zip(exp_fecha, exp["monto_num"].round(2)))
    pares_api = set(zip(api_fecha, api_monto.round(2)))
    return {
        "export_filas": len(exp),
        "export_suma_columna": round(float(exp["monto_num"].sum()), 2),
        "export_desde": exp_fecha.min(), "export_hasta": exp_fecha.max(),
        "api_filas": len(api),
        "api_desde": api_fecha.min(), "api_hasta": api_fecha.max(),
        "pares_distintos_en_export": len(pares_exp),
        "pares_que_ya_estan_en_la_api": len(pares_exp & pares_api),
        "pares_que_no_estan": len(pares_exp - pares_api),
        "fechas_del_export_cubiertas": len(set(exp_fecha) & set(api_fecha)),
        "fechas_del_export": len(set(exp_fecha)),
        "monedas_en_la_api": api["moneda"].value_counts().to_dict(),
    }


def filas_que_cambiaron() -> pd.DataFrame:
    """Las filas del export que la API ya no tiene igual: son las que Habitat."""
    exp = gastos_snapshot()
    if exp.empty:
        return pd.DataFrame()
    api = ingest.fetch_axion_entity("Gasto", None, 5000)
    pares_api = set(zip(api["fecha"].astype(str).str.strip(),
                        pd.to_numeric(api["monto"], errors="coerce").round(2)))
    col_fecha = next(c for c in exp.columns if "fecha" in c.lower())
    fuera = exp[[(str(f).strip(), round(m, 2)) not in pares_api
                 for f, m in zip(exp[col_fecha], exp["monto_num"])]]
    return fuera
