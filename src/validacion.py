"""HOJA 10 · VALIDACIÓN MENSUAL."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd

from . import administracion as adm
from . import contasis, ingest, periodo, reloj
from . import lectura_excel as lx

MESES = {1: "enero", 2: "febrero", 3: "marzo", 4: "abril", 5: "mayo",
         6: "junio", 7: "julio", 8: "agosto", 9: "septiembre",
         10: "octubre", 11: "noviembre", 12: "diciembre"}


@dataclass
class Bloque:
    fuente: str
    pregunta: str          # qué contesta esta fuente
    cifra: float | None
    detalle: str
    ventana: str           # qué período cubre de verdad
    resaltante: str = ""
    cols: list = field(default_factory=list)
    filas: list = field(default_factory=list)
    de_donde: str = ""     # el archivo o la tabla, con nombre y apellido


def _num(s) -> pd.Series:
    return pd.to_numeric(s, errors="coerce").fillna(0)


def axion(mes: int) -> Bloque:
    sale = ingest.fetch_axion_entity("Sale", None, 5000)
    f = pd.to_datetime(sale["date"], errors="coerce")
    v = sale[(sale["status"] == "Vendido") & f.dt.month.eq(mes)
             & f.dt.year.eq(periodo.ANIO)]
    return Bloque(
        "AXION", "cuánto se VENDIÓ (contrato firmado, cobrado o no)",
        float(_num(v["sale_price"]).sum()),
        f"{len(v)} ventas cerradas del mes, de {len(sale)} filas en la tabla "
        f"Sale ({int((sale['status'] == 'Vendido').sum())} con status "
        f"«Vendido» en toda la historia)",
        f"{MESES[mes]} {periodo.ANIO} exacto: se filtra por Sale.date",
        cols=["Fecha", "Obra", "Unidad", "Cliente", "Asesor", "Monto S/"],
        filas=[[str(r["date"])[:10], r["project"], r["unit"], r["client"],
                r["advisor"],
                f'{float(_num(pd.Series([r["sale_price"]])).iloc[0]):,.2f}']
               for _, r in v.sort_values("date").iterrows()],
        de_donde="tabla Sale de AXION, por API")


def contasis_mes(mes: int) -> Bloque:
    er = contasis.estados_de_resultados()
    if er.empty:
        return Bloque("CONTASIS", "cuánto se RECONOCIÓ", None,
                      "no hay Estados de Resultados cargados", "—")
    ing = er[er["partida"].str.strip().str.startswith(
        "Ingresos de actividades ordinarias")]
    total = float(_num(ing["monto"]).sum())
    periodos = sorted({str(p) for p in er["_periodo"].dropna()})
    empresas = sorted(ing["_empresa"].dropna().unique())
    return Bloque(
        "CONTASIS", "cuánto se RECONOCIÓ (va a SUNAT)", total,
        f"{len(empresas)} razones sociales del grupo con Estado de "
        f"Resultados cargado, sumando {len(ing)} partidas de ingreso de "
        f"{len(er)} filas de reporte leídas",
        " · ".join(periodos),
        resaltante=("es ACUMULADO enero–junio, no el mes suelto: no es "
                    "comparable contra el mes de AXION"),
        cols=["Razón social", "Partida", "Período", "Monto S/"],
        filas=[[r["_empresa"], str(r["partida"]).strip(),
                str(r.get("_periodo", "")),
                f'{float(_num(pd.Series([r["monto"]])).iloc[0]):,.2f}']
               for _, r in ing.iterrows()],
        de_donde="Estados de Resultados exportados de ContaSis (Excel)")


def administracion_mes(mes: int) -> Bloque:
    mov = adm.movimientos("control")
    if mov.empty:
        return Bloque("ADMINISTRACIÓN", "cuánto se COBRÓ y PAGÓ", None,
                      "no hay Excels cargados", "—")
    det = mov[mov["_clase"] == "detalle"]
    col_f = next((c for c in det.columns
                  if not c.startswith("_") and lx.normalizar(c) == "FECHA"), None)
    f = pd.to_datetime(det[col_f], errors="coerce")
    d = det[f.dt.month.eq(mes) & f.dt.year.eq(periodo.ANIO)]
    en_otra = det[(det["_hoja"].astype(str).str.strip().str.upper()
                   == MESES[mes].upper())
                  & ~(f.dt.month.eq(mes) & f.dt.year.eq(periodo.ANIO))
                  & f.notna()]
    # La columna `Movimiento` es la que separa: Venta* / Gasto* / Presup.*
    m = d["Movimiento"].astype(str).str.strip().str.upper()
    imp = _num(d["Importe"])
    cobros = float(imp[m.str.startswith("VENTA")].sum())
    gastos = float(imp[m.str.startswith("GASTO")].sum())
    ven = d[m.str.startswith("VENTA")]
    quiero = ("MOVIMIENTO", "TIPO DE GASTO/INGRESO", "DESCRIPCION", "IMPORTE")
    cols_ver = [c for q in quiero for c in ven.columns
                if not c.startswith("_") and lx.normalizar(c) == q]
    resalta = ("el presupuesto se excluye: la columna Movimiento tiene "
               "Venta*, Gasto* y Presup.*, y este último no es caja")
    if len(en_otra):
        m_f = _num(en_otra["Importe"]).sum()
        resalta += (f" · **{len(en_otra)} movimientos están escritos en la hoja "
                    f"{MESES[mes].upper()} pero fechados en otro mes** "
                    f"(S/ {float(m_f):,.2f}): cuentan en el mes de su fecha, "
                    f"que es cuando entró o salió la plata. Es dato para "
                    f"preguntarle a la administradora")
    return Bloque(
        "ADMINISTRACIÓN", "cuánto se COBRÓ y PAGÓ (caja real)", cobros,
        f"cobró S/ {cobros:,.2f} en {int(m.str.startswith('VENTA').sum())} "
        f"movimientos · pagó S/ {gastos:,.2f} en "
        f"{int(m.str.startswith('GASTO').sum())} · la cifra grande son los "
        f"COBROS. Salen de {len(d)} movimientos del mes, de {len(det)} filas "
        f"de detalle del archivo",
        f"{MESES[mes]} {periodo.ANIO} · por la FECHA de cada movimiento, no "
        f"por la hoja donde está escrito: para caja manda cuándo entró o "
        f"salió la plata",
        resaltante=resalta,
        cols=["Fecha", "Hoja"] + [c + " S/" if lx.normalizar(c) == "IMPORTE"
                                  else c for c in cols_ver],
        filas=[[str(r[col_f])[:10], str(r["_hoja"])]
               + [str(r[c])[:44] for c in cols_ver]
               for _, r in ven.iterrows()],
        de_donde="Excels de control de la administradora, una hoja por obra")


def ultimo_mes_cerrado() -> int:
    """El último mes que se puede validar: el más reciente que YA cerró y del."""
    hoy = pd.Timestamp.today()
    tope = 12 if hoy.year > periodo.ANIO else max(1, hoy.month - 1)
    try:
        hojas = {str(h).strip().upper()
                 for h in adm.movimientos()["_hoja"].dropna()}
    except Exception:  # noqa: BLE001 — sin Excels se valida el mes anterior
        return tope
    for m in range(tope, 0, -1):
        if MESES[m].upper() in hojas:
            return m
    return tope


def hoja(mes: int | None = None) -> dict:
    """El mes pedido, o el último cerrado si no se pide ninguno."""
    mes = ultimo_mes_cerrado() if mes is None else mes
    bloques = [axion(mes), contasis_mes(mes), administracion_mes(mes)]
    return {
        "mes": f"{MESES[mes]} {periodo.ANIO}",
        "congelado": reloj.sello(),
        "bloques": bloques,
        "por_que_una_sola_fuente": [
            "Las tres cifras son correctas y ninguna se puede restar de otra: "
            "firmar, reconocer y cobrar pasan en momentos distintos.",
            "Hoy hay que abrir tres sistemas y cruzarlos a mano para saber "
            "cómo va un mes. Ese cruce es el trabajo que este software elimina.",
            "AXION reemplaza los Excels de la administradora. El contador NO: "
            "sigue emitiendo su estado de resultados.",
        ],
    }
