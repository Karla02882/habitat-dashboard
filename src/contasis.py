"""INGESTA · CONTASIS."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from . import lectura_excel as lx

CARPETAS = ("contasis", "contasis_empresas")


def hojas() -> list[lx.Hoja]:
    """Todas las hojas de los 61 Excels del contador, sin filtrar."""
    out: list[lx.Hoja] = []
    for c in CARPETAS:
        carpeta = lx.CRUDOS / c
        if carpeta.exists():
            out += lx.leer_carpeta(carpeta)
    return out


def _con_origen(h: lx.Hoja) -> pd.DataFrame:
    """Pega empresa, RUC y período a cada fila. Sin eso, dos filas idénticas de."""
    df = h.datos.copy()
    df.insert(3, "_empresa", h.empresa)
    df.insert(4, "_ruc", h.ruc)
    df.insert(5, "_periodo", h.periodo)
    return df


def tablas(patron: str | None = None) -> pd.DataFrame:
    """Las hojas con forma de tabla —mayores, libros caja, registros de compras."""
    partes = [_con_origen(h) for h in hojas()
              if h.forma == "tabla" and not h.datos.empty
              and (patron is None or patron.lower() in h.archivo.lower())]
    if not partes:
        return pd.DataFrame()
    return pd.concat(partes, ignore_index=True)


def reportes(patron: str | None = None) -> pd.DataFrame:
    """Los estados financieros como pares partida/monto, con su empresa."""
    partes = [_con_origen(h) for h in hojas()
              if h.forma == "reporte" and not h.datos.empty
              and (patron is None or patron.lower() in h.archivo.lower())]
    if not partes:
        return pd.DataFrame()
    return pd.concat(partes, ignore_index=True)


def estados_de_resultados() -> pd.DataFrame:
    """Los cuatro Estados de Resultados, uno por empresa."""
    return reportes("ESTADO DE RESULTADOS")


def inventario() -> pd.DataFrame:
    """Qué archivo es qué: una fila por hoja, con su forma y su corte."""
    return pd.DataFrame([{
        "archivo": h.archivo, "hoja": h.hoja, "forma": h.forma,
        "empresa": h.empresa, "ruc": h.ruc, "periodo": h.periodo,
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
