"""INGESTA · ADMINISTRACIÓN."""
from __future__ import annotations

import pandas as pd

from . import lectura_excel as lx

CARPETA = "gastos_manuales"

ARCHIVOS = {
    "proyectos": "GASTOS POR PROYECTOS - 2026.xlsx",
    "control": "CONTROL DE INGRESOS Y GASTOS.xlsx",
    "caja": "CONTROL DE GASTOS - LISBETH 2026.xlsx",
}

FECHA_MIN = pd.Timestamp("1900-01-01")
FECHA_MAX = pd.Timestamp("2100-12-31")


def hojas() -> list[lx.Hoja]:
    carpeta = lx.CRUDOS / CARPETA
    return lx.leer_carpeta(carpeta) if carpeta.exists() else []


def movimientos(archivo: str | None = None) -> pd.DataFrame:
    """Todas las hojas con forma de tabla, apiladas, con su origen."""
    if archivo in ARCHIVOS:
        archivo = ARCHIVOS[archivo]
    partes = []
    for h in hojas():
        if h.forma != "tabla" or h.datos.empty:
            continue
        if archivo and archivo.lower() not in h.archivo.lower():
            continue
        df = h.datos.copy()
        df.insert(3, "_periodo_hoja", h.periodo)
        partes.append(df)
    return pd.concat(partes, ignore_index=True) if partes else pd.DataFrame()


def columnas_por_hoja() -> pd.DataFrame:
    """Qué columnas trae cada hoja. La forma cambia mes a mes y esta tabla es."""
    filas = []
    for h in hojas():
        if h.forma != "tabla":
            continue
        cols = [c for c in h.datos.columns if not c.startswith("_")]
        filas.append({
            "archivo": h.archivo, "hoja": h.hoja,
            "columnas": len(cols),
            "nombres": " · ".join(cols[:12]) + ("…" if len(cols) > 12 else ""),
        })
    return pd.DataFrame(filas)


def fechas_imposibles() -> pd.DataFrame:
    """Las filas cuya fecha no puede existir. Se DETECTAN y se reportan; no se."""
    mov = movimientos()
    if mov.empty:
        return pd.DataFrame()
    cols_fecha = [c for c in mov.columns
                  if not c.startswith("_") and "FECHA" in lx.normalizar(c)]
    salida = []
    for col in cols_fecha:
        f = pd.to_datetime(mov[col], errors="coerce")
        mala = f.notna() & ((f < FECHA_MIN) | (f > FECHA_MAX))
        if not mala.any():
            continue
        sub = mov.loc[mala, ["_archivo", "_hoja", "_fila", "_clase"]].copy()
        sub["columna"] = col
        sub["valor_leido"] = f[mala].dt.strftime("%Y-%m-%d")
        salida.append(sub)
    return pd.concat(salida, ignore_index=True) if salida else pd.DataFrame()


def inventario() -> pd.DataFrame:
    """Una fila por hoja: forma, período declarado y cuántas filas de cada."""
    return pd.DataFrame([{
        "archivo": h.archivo, "hoja": h.hoja, "forma": h.forma,
        "periodo": h.periodo,
        "fila_encabezado": h.fila_encabezado,
        "filas_crudas": len(h.crudo),
        "filas_leidas": len(h.datos),
        "detalle": int((h.datos["_clase"] == "detalle").sum())
                   if "_clase" in h.datos.columns else None,
        "total": int((h.datos["_clase"] == "total").sum())
                 if "_clase" in h.datos.columns else None,
        "separador": int((h.datos["_clase"] == "separador").sum())
                     if "_clase" in h.datos.columns else None,
    } for h in hojas()])
