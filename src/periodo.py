"""EL PERÍODO, definido UNA sola vez."""
from __future__ import annotations

import re

import pandas as pd

ANIO = pd.Timestamp.today().year
HISTORICO = "hist"


def es_historico(periodo) -> bool:
    return str(periodo) == HISTORICO


def partes(periodo) -> tuple[int | None, int | None]:
    """(año, mes) del período. (None, None) = histórico, sin recorte."""
    if es_historico(periodo):
        return (None, None)
    if periodo is None:
        return (ANIO, None)
    m = re.fullmatch(r"(\d{4})(?:-(\d{1,2}))?", str(periodo))
    if m:
        return (int(m.group(1)), int(m.group(2)) if m.group(2) else None)
    return (ANIO, int(periodo))


def recortar(df: pd.DataFrame, col: str, periodo) -> pd.DataFrame:
    """El recorte de un DataFrame por su columna de fecha."""
    if es_historico(periodo):
        return df
    anio, mes = partes(periodo)
    f = pd.to_datetime(df[col], errors="coerce")
    en_anio = f.dt.year.eq(anio)
    if mes is None:
        return df[en_anio]
    return df[en_anio & f.dt.month.eq(mes)]


def contiene(fecha, periodo) -> bool:
    """Lo mismo para una fecha suelta (las iniciales viven en una lista."""
    if es_historico(periodo):
        return True
    d = pd.to_datetime(str(fecha), errors="coerce")
    if pd.isna(d):
        return False
    anio, mes = partes(periodo)
    if d.year != anio:
        return False
    return mes is None or d.month == mes


MES = {1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril", 5: "Mayo",
       6: "Junio", 7: "Julio", 8: "Agosto", 9: "Setiembre",
       10: "Octubre", 11: "Noviembre", 12: "Diciembre"}


def etiqueta(periodo) -> str:
    if es_historico(periodo):
        return "Todos los años"
    anio, mes = partes(periodo)
    if mes is None:
        return (f"{anio} · Acumulado del año" if anio == ANIO
                else f"{anio} · Año completo")
    return f"{anio} · {MES[mes]}"
