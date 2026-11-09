"""PANTALLA · RESULTADOS AL CORTE."""
from __future__ import annotations

from datetime import date

import pandas as pd

from . import ingest, movimientos, periodo
from .ficha_obra import Cifra

HOY = pd.Timestamp(date.today())

MARKETING = ("FB ", "TIK", "GOOGLE", "META", "CAP CUT", "ADS")


def _n(s) -> pd.Series:
    return pd.to_numeric(s, errors="coerce").fillna(0)


def _a_soles(g: pd.DataFrame) -> pd.Series:
    """El monto en soles. AXION guarda el importe en su moneda original y el."""
    m = _n(g["monto"])
    tc = _n(g["tasa_cambio"]).replace(0, 1)
    return m.where(g["moneda"].astype(str) != "USD", m * tc)


def cifras() -> list[Cifra]:
    sale = ingest.fetch_axion_entity("Sale", None, 5000)
    unit = ingest.fetch_axion_entity("Unit", None, 5000)
    cred = ingest.fetch_axion_entity("Credit", None, 5000)
    cxc = ingest.fetch_axion_entity("CxCPayment", None, 5000)
    inst = ingest.fetch_axion_entity("Installment", None, 5000)
    _gt = movimientos.gasto_total(None)

    v = periodo.recortar(sale[sale["status"] == "Vendido"], "date", None)
    vendido = float(_n(v["sale_price"]).sum())

    # Cobrado = inicial + cuotas. La inicial vive dentro de Credit.iniciales.
    ini = 0.0
    n_ini = 0
    _vistos: set = set()
    for _idx, lista in enumerate(cred["iniciales"]):
        _cr = cred.iloc[_idx]
        if isinstance(lista, list):
            for e in lista:
                if isinstance(e, dict) and periodo.contiene(e.get("fecha", ""),
                                                            None):
                    if "pendiente" in str(e.get("tipo") or "").lower():
                        continue
                    _k = ingest.clave_inicial(e, _cr)
                    if _k in _vistos:
                        continue
                    _vistos.add(_k)
                    try:
                        ini += float(str(e.get("monto", "")).replace(",", ""))
                    except ValueError:
                        continue
                    n_ini += 1
    _cxc_per = periodo.recortar(cxc, "fecha", None)
    n_cuo = int(len(_cxc_per))
    cuotas = float(_n(_cxc_per["monto"]).sum())

    venc = pd.to_datetime(inst["fecha_vencimiento"], errors="coerce")
    _vivos = set(cred[cred["estado"].astype(str).str.lower() != "cancelado"]["id"])         if "estado" in cred.columns else set(cred["id"])
    _falta = (_n(inst["monto_cuota"]) - _n(inst["monto_pagado"])).clip(lower=0)
    vencidas = inst[(venc < HOY) & _falta.gt(0)
                    & inst["credit_id"].isin(_vivos)]
    vencido = float((_n(vencidas["monto_cuota"])
                     - _n(vencidas["monto_pagado"])).clip(lower=0).sum())

    libres = unit[unit["status"] == "LIBRE"]
    precio = _n(libres["real_price"]).where(
        _n(libres["real_price"]) > 0,
        _n(libres.get("catalog_price", pd.Series(0.0, index=libres.index))))
    sin_precio = int((precio == 0).sum())


    _est_r = cred["estado"].astype(str).str.lower()
    _vivos_r = cred[~_est_r.eq("cancelado")]
    _cancelados_r = cred[_est_r.eq("cancelado")]
    _saldo_canc = float(_n(_cancelados_r["saldo_pendiente"]).sum())
    _canc_cero = int((_n(_cancelados_r["saldo_pendiente"]) <= 0.005).sum())
    return [
        Cifra("Vendido", vendido,
              f"suma del precio de venta de las {len(v)} ventas con estado «Vendido». "
              f"Las {len(sale) - len(v)} separaciones y devoluciones no entran",
              "AXION · Sale"),
        Cifra("Cobrado", ini + cuotas,
              f"inicial + cuotas: {n_ini} pagos iniciales (S/ {ini:,.2f}) más "
              f"{n_cuo} cuotas (S/ {cuotas:,.2f}) — solo los que tienen fecha "
              f"dentro del período",
              "AXION · Credit.iniciales + CxCPayment"),
        Cifra("Por cobrar", float(_n(_vivos_r["saldo_pendiente"]).sum()),
              f"suma del saldo por pagar de los {len(_vivos_r)} créditos "
              f"vivos, de {len(cred)} en total"
              + ((lambda _n_: f". OJO: {_n_} crédito{'s' if _n_ != 1 else ''} "
                  f"CANCELADO{'S' if _n_ != 1 else ''} aún "
                  f"{'muestran' if _n_ != 1 else 'muestra'} "
                  f"S/ {_saldo_canc:,.2f} de saldo — un cancelado está "
                  f"saldado, eso lo responde Cobranzas")
                 (len(cred) - len(_vivos_r) - _canc_cero)
                 if _saldo_canc > 0.005 else ""),
              "AXION · Credit"),
        Cifra("De eso, ya vencido", vencido,
              f"{len(vencidas)} cuotas que ya vencieron y a las que todavía "
              f"les falta plata — se mide el faltante, no el estado de la "
              f"casilla — y solo de créditos vivos, que son los que forman la "
              f"cartera de arriba. Misma regla que la hoja Cobranza",
              "AXION · Installment"),
        Cifra("Falta vender", float(precio.sum()),
              f"precio de las {len(libres)} unidades LIBRE"
              + (f" · {sin_precio} sin precio cargado quedan en cero"
                 if sin_precio else ""),
              "AXION · Unit"),
        Cifra("Ticket promedio", vendido / len(v) if len(v) else None,
              f"vendido dividido entre las {len(v)} ventas cerradas — mismo "
              f"universo arriba y abajo", "AXION · Sale"),
        Cifra("Gasto registrado", _gt["monto"],
              f"{_gt['filas']:,} movimientos de gasto del año, del Registro de "
              f"Movimientos de AXION — donde Administración carga la caja",
              "AXION · Registro de Movimientos"),
        Cifra("De eso, atribuido a una obra", _gt["atribuido"],
              f"el {_gt['pct_atribuido']:.1f}% del gasto dice de qué obra es, "
              f"repartido en {_gt['obras']} obras. El resto no lleva proyecto "
              f"cargado y por eso el margen por obra sale incompleto",
              "AXION · Registro de Movimientos"),
    ]


def cifras_del_mes(mes: int) -> list[Cifra]:
    sale = ingest.fetch_axion_entity("Sale", None, 5000)
    cred = ingest.fetch_axion_entity("Credit", None, 5000)
    cxc = ingest.fetch_axion_entity("CxCPayment", None, 5000)
    _gtm = movimientos.gasto_total(mes)

    def _del_mes(df, col):
        return periodo.recortar(df, col, mes)

    v = _del_mes(sale[sale["status"] == "Vendido"], "date")
    vendido = float(_n(v["sale_price"]).sum())

    _vistos_m: set = set()
    ini, n_ini = 0.0, 0
    for _, c in cred.iterrows():
        if isinstance(c["iniciales"], list):
            for e in c["iniciales"]:
                if isinstance(e, dict) and periodo.contiene(e.get("fecha", ""),
                                                            mes):
                    if "pendiente" in str(e.get("tipo") or "").lower():
                        continue
                    _k = ingest.clave_inicial(e, c)
                    if _k in _vistos_m:
                        continue
                    _vistos_m.add(_k)
                    try:
                        ini += float(str(e.get("monto", "")).replace(",", ""))
                    except ValueError:
                        continue
                    n_ini += 1
    cuo = _del_mes(cxc, "fecha")
    cuotas = float(_n(cuo["monto"]).sum())


    _est_m = cred["estado"].astype(str).str.lower()
    saldo = float(_n(cred[~_est_m.eq("cancelado")]["saldo_pendiente"]).sum())
    return [
        Cifra("Vendido en el mes", vendido,
              f"{len(v)} ventas con estado «Vendido» y fecha en el mes",
              "AXION · Sale"),
        Cifra("Cobrado en el mes", ini + cuotas,
              f"{n_ini} iniciales (S/ {ini:,.2f}) + {len(cuo)} cuotas "
              f"(S/ {cuotas:,.2f}) con fecha en el mes",
              "AXION · Credit.iniciales + CxCPayment"),
        Cifra("Por cobrar", saldo,
              "saldo de los créditos A HOY. No es del mes: es un saldo, y "
              "filtrarlo por mes no significaría nada", "AXION · Credit"),
        Cifra("Ticket promedio del mes", vendido / len(v) if len(v) else None,
              f"vendido del mes entre sus {len(v)} ventas", "AXION · Sale"),
        # Mismo cambio que en el acumulado: Registro de Movimientos.
        Cifra("Gasto del mes", _gtm["monto"],
              f"{_gtm['filas']:,} movimientos de gasto con fecha en el mes, del "
              f"Registro de Movimientos", "AXION · Registro de Movimientos"),
        Cifra("De eso, atribuido a una obra", _gtm["atribuido"],
              f"el {_gtm['pct_atribuido']:.1f}% del gasto del mes dice de qué "
              f"obra es", "AXION · Registro de Movimientos"),
    ]


def lo_que_axion_no_contesta() -> list[Cifra]:
    """La otra mitad de la validación: qué NO se puede sacar de la API hoy."""
    return [
        Cifra("Gasto de Comercial", None,
              "comisiones y gastos del área comercial", "AXION",
              motivo="AXION no los registra. Las comisiones están en el libro "
                     "del contador, en cuentas «COMISIONES - VTAS»",
              area="Gerencia · carga de gastos en AXION"),
        _costo_de_obra(),
        Cifra("Planilla", None, "sueldos y cargas del personal", "AXION",
              motivo="no hay módulo de personal",
              area="Administración"),
        _compras(),
    ]


def _costo_de_obra() -> Cifra:
    from . import areas
    gt = movimientos.gasto_total(None)
    obra = [c for c in areas.obra() if c.etiqueta == "Costo de obra registrado"]
    val = obra[0].valor if obra else None
    if val:
        return Cifra("Costo de obra", float(val),
                     "gasto del libro de caja que se pudo atribuir a una obra",
                     "AXION · Registro de Movimientos",
                     motivo=(f"es el {gt['pct_atribuido']:.1f}% del gasto del "
                             f"año (S/ {gt['monto']:,.2f}): el resto no lleva "
                             f"proyecto cargado en el movimiento, así que no se "
                             f"puede repartir por obra sin inventarlo"),
                     area="Administración · cargar el proyecto en cada gasto")
    return Cifra("Costo de obra", None, "materiales, mano de obra, contratistas",
                 "AXION · Registro de Movimientos",
                 motivo=(f"ninguno de los {gt['filas']:,} movimientos de gasto "
                         f"del período lleva un proyecto que empareje con una "
                         f"obra de AXION"),
                 area="Administración · cargar el proyecto en cada gasto")


def _compras() -> Cifra:
    from . import areas
    oc, pv = areas._log("OrdenCompra"), areas._log("Proveedor")
    if not len(oc):
        return Cifra("Compras y proveedores", None,
                     "órdenes de compra, inventario, proveedores", "AXION",
                     motivo="la tabla OrdenCompra no respondió en esta lectura",
                     area="Logística")
    from .areas import _num
    tot = float(_num(oc["total"]).sum())
    return Cifra("Compras y proveedores", tot,
                 f"comprado en las {len(oc)} órdenes cargadas, con "
                 f"{len(pv)} proveedores", "AXION · OrdenCompra",
                 motivo=("el módulo arrancó el 03-ago: son tres días de "
                         "compras, todavía no un histórico"),
                 area="Logística")
