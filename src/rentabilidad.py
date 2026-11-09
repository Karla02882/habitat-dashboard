"""HOJA 3 · RENTABILIDAD."""
from __future__ import annotations

import pandas as pd

from . import ingest, movimientos, periodo
from .ficha_obra import Cifra

SIN_RAZON = "— sin razón social declarada en AXION —"


def _num(s) -> pd.Series:
    return pd.to_numeric(s, errors="coerce").fillna(0)


def _mes(df: pd.DataFrame, col: str, mes) -> pd.DataFrame:
    return periodo.recortar(df, col, mes)


def por_obra(mes: int | None = None) -> pd.DataFrame:
    """Las 18 obras declaradas en `Project`. **Ninguna se omite por no tener."""
    proj = ingest.fetch_axion_entity("Project", None, 5000)
    sale = ingest.fetch_axion_entity("Sale", None, 5000)
    cred = ingest.fetch_axion_entity("Credit", None, 5000)
    cxc = ingest.fetch_axion_entity("CxCPayment", None, 5000)

    vend = _mes(sale[sale["status"] == "Vendido"], "date", mes)

    ini, vistos = [], set()
    for _, cr in cred.iterrows():
        if not isinstance(cr["iniciales"], list):
            continue
        for e in cr["iniciales"]:
            if not isinstance(e, dict):
                continue
            _k = ingest.clave_inicial(e, cr)
            if _k in vistos:
                continue
            vistos.add(_k)
            if "pendiente" in str(e.get("tipo") or "").lower():
                continue
            try:
                monto = float(str(e.get("monto", "")).replace(",", "") or 0)
            except ValueError:
                continue
            ini.append({"project": cr["project"], "monto": monto,
                        "fecha": e.get("fecha", "")})
    ini = pd.DataFrame(ini) if ini else pd.DataFrame(
        columns=["project", "monto", "fecha"])
    ini_mes = _mes(ini, "fecha", mes) if len(ini) else ini

    cxc_mes = _mes(cxc, "fecha", mes)
    # Los cobros no traen obra: viajan por el crédito.
    obra_de_credito = dict(zip(cred["id"], cred["project"]))
    cxc_mes = cxc_mes.assign(
        project=cxc_mes["credit_id"].map(obra_de_credito))
    sin_credito = int(cxc_mes["project"].isna().sum())

    try:
        g_obra = movimientos.gasto_por_obra(mes)
        costos = dict(zip(g_obra["obra"], g_obra["gasto"])) if len(g_obra) else {}
        n_mov = dict(zip(g_obra["obra"], g_obra["movimientos"])) if len(g_obra) else {}
        hay_movimientos = True
    except Exception:  # noqa: BLE001 — fuente nueva: que no tumbe la hoja
        costos, n_mov, hay_movimientos = {}, {}, False

    filas = []
    for _, p in proj.sort_values("name").iterrows():
        obra = str(p["name"]).strip()
        empresa = str(p["company_name"]).strip() or SIN_RAZON
        v = vend[vend["project"] == obra]
        c = cxc_mes[cxc_mes["project"] == obra]
        i = ini_mes[ini_mes["project"] == obra] if len(ini_mes) else ini_mes

        contratado = float(_num(v["sale_price"]).sum()) if len(v) else None
        cuotas = float(_num(c["monto"]).sum()) if len(c) else 0.0
        iniciales = float(_num(i["monto"]).sum()) if len(i) else 0.0
        cobrado = (cuotas + iniciales) if (len(c) or len(i)) else None

        motivo_ingreso = ""
        if contratado is None and cobrado is None:
            motivo_ingreso = (f"sin ventas cerradas ni cobros registrados en "
                              f"{periodo.etiqueta(mes)}"
                              + f" · etapa: {str(p['project_stage']).strip()}")

        costo = costos.get(obra)
        costo_nota = ""
        if costo is not None:
            costo_nota = (f"{n_mov.get(obra, 0):,} mov. · equivalencias "
                          f"por aprobar")
            motivo_costo = (f"{n_mov.get(obra, 0):,} movimientos de gasto en "
                            f"MovimientoGasto, {periodo.etiqueta(mes)} · "
                            f"emparejado por palabras completas, equivalencias "
                            f"pendientes de aprobar")
        elif hay_movimientos:
            motivo_costo = ("sin gasto atribuido — puede estar bajo un "
                            "rótulo sin emparejar (ver el pie)")
        else:
            motivo_costo = ("MovimientoGasto no respondió en esta lectura: "
                            "la columna vuelve a llenarse en la próxima")

        filas.append({
            "obra": obra,
            "razon_social": empresa,
            "etapa": str(p["project_stage"]).strip(),
            "ventas": len(v),
            "contratado": contratado,
            "cobros": len(c) + len(i),
            "iniciales": iniciales if (len(c) or len(i)) else None,
            "cuotas": cuotas if (len(c) or len(i)) else None,
            "cobrado": cobrado,
            "costo": costo,
            "costo_nota": costo_nota,
            "margen": None,
            "motivo_ingreso": motivo_ingreso,
            "motivo_costo": motivo_costo,
            "motivo_margen": ("ingreso y costo ya existen; falta que Gerencia "
                              "defina la regla —¿contratado o cobrado contra "
                              "el costo?— y no se elige en silencio"),
        })
    df = pd.DataFrame(filas)
    df.attrs["cobros_sin_obra"] = sin_credito
    df.attrs["mes"] = mes
    return df


def por_razon_social(mes: int | None = None) -> pd.DataFrame:
    """Agrupado por empresa. Las obras sin razón social se agrupan aparte y se."""
    d = por_obra(mes)
    g = (d.groupby("razon_social", dropna=False)
         .agg(obras=("obra", "size"),
              ventas=("ventas", "sum"),
              contratado=("contratado", "sum"),
              cobros=("cobros", "sum"),
              iniciales=("iniciales", "sum"),
              cuotas=("cuotas", "sum"),
              cobrado=("cobrado", "sum"),
              costo=("costo", lambda s: s.sum(min_count=1)))
         .reset_index()
         .sort_values("contratado", ascending=False))
    g["margen"] = None
    return g


def avisos(mes: int | None = None) -> list[Cifra]:
    """Lo que la hoja tiene que decir al lado de sus cifras."""
    proj = ingest.fetch_axion_entity("Project", None, 5000)
    d = por_obra(mes)

    sin_razon = d[d["razon_social"] == SIN_RAZON]
    sin_nada = d[d["contratado"].isna() & d["cobrado"].isna()]

    fuera = []
    # Empresas que emiten estado de resultados y NO tienen obra en AXION.
    rucs_axion = {str(r).strip() for r in proj["ruc"] if str(r).strip()}
    if "20611216565" not in rucs_axion:
        fuera.append("Escalar y Habitat Grupo Inmobiliario (RUC 20611216565)")

    try:
        r_mov = movimientos.resumen()
    except Exception:  # noqa: BLE001
        r_mov = {"hay": False}

    if r_mov.get("hay"):
        cifra_costo = Cifra(
            "Costo por obra", r_mov["gasto_atribuido"],
            "gasto real de MovimientoGasto emparejado a las obras de Project "
            "por palabras completas — acumulado de toda la tabla",
            "AXION · MovimientoGasto",
            motivo=(f"cubre el {r_mov['pct_atribuido']:.1f}% del gasto "
                    f"registrado (S/ {r_mov['gasto']['monto']:,.2f}): el resto "
                    f"lleva rótulos que no son obra y está listado abajo con "
                    f"su monto. Equivalencias pendientes de aprobar."),
            area="Administración · aprobar equivalencias")
        cifra_margen = Cifra(
            "Margen por obra", None,
            "ingreso menos costo", "AXION",
            motivo=("ingreso y costo ya existen. Falta la regla: ¿contratado "
                    "o cobrado contra el costo? La define Gerencia y no se "
                    "elige en silencio."),
            area="Gerencia · definir la regla del margen")
    else:
        cifra_costo = Cifra(
            "Costo por obra", None,
            "suma de los gastos de AXION atribuidos a cada obra",
            "AXION · Gasto",
            motivo=(f"esperando la carga de costos: Gasto tiene "
                    f"el resto de los movimientos sin proyecto cargado."),
            area="Gerencia · carga de costos en AXION")
        cifra_margen = Cifra(
            "Margen por obra", None, "ingreso menos costo",
            "AXION", motivo="sin costos no hay margen",
            area="Gerencia · carga de costos en AXION")

    out = [
        cifra_costo,
        cifra_margen,
        Cifra("Obras sin razón social", len(sin_razon),
              "obras de Project con company_name vacío",
              "AXION · Project",
              motivo=("no se pueden agrupar por empresa: "
                      + ", ".join(sin_razon["obra"])) if len(sin_razon) else "",
              area="Comercial"),
        Cifra("Obras sin ingreso registrado", len(sin_nada),
              "obras sin ventas cerradas ni cobros en el período",
              "AXION · Sale + CxCPayment",
              motivo=("se muestran vacías con su etapa, no en cero: "
                      + ", ".join(sin_nada["obra"])) if len(sin_nada) else "",
              area="Comercial"),
    ]
    if d.attrs.get("cobros_sin_obra"):
        out.append(Cifra(
            "Cobros sin obra", d.attrs["cobros_sin_obra"],
            "pagos de CxCPayment cuyo credit_id no existe en Credit",
            "AXION · CxCPayment",
            motivo="no se pueden atribuir a ninguna obra; quedan fuera del "
                   "detalle por obra pero siguen contados en el total",
            area="Cobranzas"))
    if fuera:
        out.append(Cifra(
            "Empresas sin obra en AXION", len(fuera),
            "razones sociales con estado de resultados propio y sin ningún "
            "proyecto declarado en Project",
            "ContaSis vs AXION · Project",
            motivo=("; ".join(fuera) + ". Su resultado aparece en la hoja 12 "
                    "y no tiene obra a la cual atribuirse en esta hoja."),
            area="Contabilidad"))
    return out
