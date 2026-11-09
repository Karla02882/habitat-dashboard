"""LAS FILAS de las hojas de área, para que respondan a los filtros."""
from __future__ import annotations

from datetime import date

import pandas as pd

from . import filas, ingest

HOY = pd.Timestamp(date.today())
SIN_OBRA = "— sin obra —"


def _n(s) -> pd.Series:
    return pd.to_numeric(s, errors="coerce").fillna(0)


def _f(v) -> str:
    d = pd.to_datetime(str(v), errors="coerce")
    return "" if pd.isna(d) else f"{d:%Y-%m-%d}"


def _obra_de_credito() -> dict:
    c = ingest.fetch_axion_entity("Credit", None, 5000)
    return dict(zip(c["id"], c["project"]))


def ventas_cerradas() -> list[dict]:
    """Cada venta lleva además su asesor y su modalidad como campos aparte."""
    s = ingest.fetch_axion_entity("Sale", None, 5000)
    v = s[s["status"] == "Vendido"]
    return [{"fecha": _f(r["date"]), "obra": str(r["project"]).strip(),
             "monto": float(_n(pd.Series([r["sale_price"]])).iloc[0]),
             "asesor": filas.asesor(r["advisor"]),
             "modalidad": str(r["modality"]).strip() or "(sin declarar)",
             "d": [str(r["unit"]), str(r["client"]), filas.asesor(r["advisor"]),
                   str(r["modality"]).strip() or "(sin declarar)"]}
            for _, r in v.iterrows()]


def _puesto(r) -> float:
    """Lo que el cliente ENTREGÓ, de `Sale.real_income`."""
    return float(_n(pd.Series([r.get("real_income")])).iloc[0])


def ventas_caidas() -> list[dict]:
    """Las ventas caídas, con lo ABONADO como monto."""
    s = ingest.fetch_axion_entity("Sale", None, 5000)
    d = s[s["status"] == "Devolución"]
    filas_ = []
    for _, r in d.iterrows():
        precio = float(_n(pd.Series([r["sale_price"]])).iloc[0])
        ab = _puesto(r)
        filas_.append({
            "fecha": _f(r["date"]), "obra": str(r["project"]).strip(),
            "monto": ab,
            "asesor": filas.asesor(r["advisor"]),
            "d": [str(r["unit"]), str(r["client"]), f"S/ {precio:,.2f}"]})
    return filas_


def _unidades(u) -> list[dict]:
    return [{"fecha": "", "obra": str(r["project"]).strip(), "monto": 1.0,
             "asesor": filas.asesor(r["advisor"]),
             "d": [str(r["name"]), str(r["status"]),
                   f'{float(_n(pd.Series([r["area_m2"]])).iloc[0]):,.2f} m²']}
            for _, r in u.iterrows()]


def unidades(estado: str) -> list[dict]:
    u = ingest.fetch_axion_entity("Unit", None, 5000)
    return _unidades(u[u["status"] == estado])


def unidades_todas() -> list[dict]:
    return _unidades(ingest.fetch_axion_entity("Unit", None, 5000))


def creditos() -> list[dict]:
    c = ingest.fetch_axion_entity("Credit", None, 5000)
    c = c[_n(c["saldo_pendiente"]) > 0]
    return [{"fecha": _f(r["fecha_inicio"]), "obra": str(r["project"]).strip(),
             "monto": float(_n(pd.Series([r["saldo_pendiente"]])).iloc[0]),
             "d": [str(r["unit"]), str(r["client_name"]), str(r["estado"])]}
            for _, r in c.iterrows()]


def _antiguedad(dias: float) -> str:
    """El tramo de mora. Los cortes son los de siempre —30/60/90— y sirven."""
    if dias <= 30:
        return "1 a 30 días"
    if dias <= 60:
        return "31 a 60 días"
    if dias <= 90:
        return "61 a 90 días"
    return "más de 90 días"


def cuotas(cuales: str) -> list[dict]:
    i = ingest.fetch_axion_entity("Installment", None, 5000)
    obra = _obra_de_credito()
    f = pd.to_datetime(i["fecha_vencimiento"], errors="coerce")
    _falta = (_n(i["monto_cuota"]) - _n(i["monto_pagado"]))
    if cuales == "vencidas":
        sel = i[_falta.gt(0) & (f < HOY) & ingest.con_credito(i)]
        monto = (_n(sel["monto_cuota"]) - _n(sel["monto_pagado"])).tolist()
    elif cuales == "por_vencer":
        sel = i[_falta.gt(0) & (f >= HOY)]
        monto = (_n(sel["monto_cuota"]) - _n(sel["monto_pagado"])).tolist()
    elif cuales == "pagadas":
        sel = i[i["estado"] == "pagado"]
        monto = _n(sel["monto_pagado"]).tolist()
    else:
        sel = i[(i["estado"] == "pendiente") & (_n(i["monto_pagado"]) > 0)]
        monto = _n(sel["monto_pagado"]).tolist()
    dias = (HOY - pd.to_datetime(sel["fecha_vencimiento"], errors="coerce")).dt.days

    _cr = ingest.fetch_axion_entity("Credit", None, 5000)
    _vivos = set(_cr[_cr["estado"].astype(str).str.lower() != "cancelado"]["id"])
    _todos = set(_cr["id"])

    def _fuera(cid):
        if cid in _vivos:
            return ""
        return "cancelado" if cid in _todos else "sin crédito"

    _unidad = dict(zip(_cr["id"], _cr["unit"]))
    _asesor = (dict(zip(_cr["id"], _cr["advisor"]))
               if "advisor" in _cr.columns else {})

    def _txt(d, cid):
        v = d.get(cid)
        if v is None or str(v).strip().lower() in ("", "nan", "none"):
            return "—"
        return str(v).strip()

    return [{"fecha": _f(r["fecha_vencimiento"]),
             "obra": str(obra.get(r["credit_id"], SIN_OBRA)).strip(),
             "monto": float(monto[k]),
             "antig": _antiguedad(float(dias.iloc[k])) if cuales == "vencidas" else "",
             "fuera": _fuera(r["credit_id"]),
             "d": [str(r["client_name"]), f'cuota {r["numero_cuota"]:.0f}',
                   f'{float(r["monto_cuota"]):,.2f}',
                   f'{float(r["monto_pagado"]):,.2f}',
                   _txt(_unidad, r["credit_id"]),
                   _txt(_asesor, r["credit_id"])]}
            for k, (_, r) in enumerate(sel.iterrows())]


def cobrado() -> list[dict]:
    """Lo cobrado de verdad: la inicial más los pagos de cuota."""
    return filas.cobrado()


def _por_asesor(estado: str) -> list[dict]:
    """Las ventas de un estado, agrupadas por asesor."""
    s = ingest.fetch_axion_entity("Sale", None, 5000)
    v = s[s["status"] == estado]
    puesto_ = estado in ("Devolución", "Separación")
    filas_ = []
    for _, r in v.iterrows():
        precio = float(_n(pd.Series([r["sale_price"]])).iloc[0])
        monto = _puesto(r) if puesto_ else precio
        det = [filas.asesor(r["advisor"]), str(r["unit"]),
               str(r["client"])]
        if puesto_:
            det.append(f"S/ {precio:,.2f}")
        filas_.append({
            "fecha": _f(r["date"]), "obra": str(r["project"]).strip(),
            "monto": monto,
            "grupo": filas.asesor(r["advisor"]),
            "asesor": filas.asesor(r["advisor"]),
            "d": det})
    return filas_


def ventas_por_origen() -> list[dict]:
    """Una fila por venta cerrada, con el origen que declaro el cliente."""
    s = ingest.fetch_axion_entity("Sale", None, 5000)
    if s.empty:
        return []
    v = s[s["status"].astype(str).str.strip() == "Vendido"]

    def _txt(x):
        x = str(x or "").strip()
        return "" if x.lower() in ("", "nan", "none") else x

    filas_ = []
    for _, r in v.iterrows():
        fuente = _txt(r.get("marketing_source"))
        canal = _txt(r.get("capture_channel"))
        sub = _txt(r.get("marketing_subsource"))
        filas_.append({
            "fecha": _f(r["date"]),
            "obra": str(r.get("project") or "—").strip(),
            "monto": float(_n(pd.Series([r.get("sale_price")])).iloc[0]),
            "grupo": fuente or "— sin origen declarado —",
            "llegada": _f(r.get("lead_arrival_date")),
            "d": [_txt(r.get("unit")) or "—",
                  fuente or "— sin declarar —", canal or "—", sub or "—",
                  _txt(r.get("client")) or "—",
                  filas.asesor(r.get("advisor"))]})
    return filas_

def ventas_por_asesor() -> list[dict]:
    return _por_asesor("Vendido")


def separaciones_por_asesor() -> list[dict]:
    """OJO: el monto es lo ENTREGADO (real_income), no el precio del lote."""
    """El otro lado del trabajo comercial. Una separación no es venta y nunca
    se suma con ellas, pero es lo que el asesor SÍ movió: dejarla fuera mide
    a medias a quien está trabajando el embudo."""
    return _por_asesor("Separación")


def devoluciones_por_asesor() -> list[dict]:
    return _por_asesor("Devolución")


CIFRAS = {
    "Ventas": [
        {"nombre": "Vendido", "modo": "suma", "unidad": "ventas", "mensual": True,
         "fn": ventas_cerradas,
         "calculo": "suma del precio de venta de las ventas con estado «Vendido»",
         "cols": ["Fecha", "Obra", "Unidad", "Cliente", "Asesor", "Modalidad", "Monto"]},
        {"nombre": "Ticket promedio", "modo": "promedio", "unidad": "ventas", "mensual": True,
         "fn": ventas_cerradas,
         "calculo": "vendido dividido entre las ventas cerradas — las dos "
                    "cifras salen de la MISMA población",
         "cols": ["Fecha", "Obra", "Unidad", "Cliente", "Asesor", "Modalidad", "Monto"]},
        {"nombre": "Separaciones", "modo": "suma", "unidad": "separaciones",
         "mensual": True, "fn": separaciones_por_asesor,
         "calculo": "ventas con estado «Separación»: plata apalabrada que aún "
                    "NO es venta. Nunca se suma dentro de «Vendido» —hacerlo "
                    "lo infló S/ 596k una vez— pero es el embudo",
         "cols": ["Fecha", "Obra", "Asesor", "Unidad", "Cliente", "Pactado",
                  "Entregado"]},
        {"nombre": "Devoluciones", "modo": "suma", "unidad": "devoluciones", "mensual": True,
         "fn": ventas_caidas,
         "calculo": "ventas con estado «Devolución». **El monto es lo que el "
                    "cliente ABONÓ**, cruzado por DNI contra Credit — no el "
                    "precio del inmueble. Nadie devuelve el precio del "
                    "departamento. Donde no hay DNI o no hay crédito, el "
                    "abono no se puede cruzar y la fila va en cero: la cifra "
                    "es un piso. Mismo número que la tarjeta de Resultados",
         "cols": ["Fecha", "Obra", "Unidad", "Cliente", "Precio", "Abonado"]},
        {"nombre": "Falta vender", "modo": "suma", "unidad": "unidades", "mensual": False,
         "fn": filas.falta_vender,
         "calculo": "el precio de las unidades con estado «LIBRE». NO es total "
                    "menos vendidas: esa resta contaría como stock las "
                    "SEPARADO y BLOQUEADO. Mismas filas que la tarjeta de "
                    "Resultados",
         "cols": ["—", "Obra", "Unidad", "Área", "Estado", "Asesor", "Precio"]},
        {"nombre": "Unidades vendidas", "modo": "cuenta", "unidad": "unidades", "mensual": False,
         "fn": lambda: unidades("VENDIDO"),
         "calculo": "unidades con estado «VENDIDO»",
         "cols": ["—", "Obra", "Unidad", "Estado", "Área", "—"]},
        {"nombre": "Inventario total", "modo": "cuenta", "unidad": "unidades", "mensual": False,
         "fn": unidades_todas,
         "calculo": "todas las unidades del proyecto. Es el DENOMINADOR de la "
                    "absorción: se muestra para que el cociente se pueda leer",
         "cols": ["—", "Obra", "Unidad", "Estado", "Área", "—"]},
    ],
    "Cobranza": [
        {"nombre": "Cobrado", "modo": "suma", "unidad": "cobros", "mensual": True,
         "fn": cobrado,
         "calculo": "la cuota inicial de cada crédito (Credit.iniciales) más "
                    "los pagos de cuota (CxCPayment). Es la MISMA fila que "
                    "suma la tarjeta «Cobrado» de Resultados",
         "cols": ["Fecha", "Obra", "Tipo", "Cliente", "Serie", "Caja / nota", "Monto"]},
        {"nombre": "Por cobrar", "modo": "suma", "unidad": "créditos", "mensual": False,
         "fn": creditos,
         "calculo": "suma del saldo por pagar de los créditos con saldo",
         "cols": ["Inicio", "Obra", "Unidad", "Cliente", "Estado", "Saldo"]},
        {"nombre": "Vencido", "modo": "suma", "unidad": "cuotas", "mensual": False,
         "fn": lambda: cuotas("vencidas"),
         "calculo": "cuotas pendientes con vencimiento anterior a hoy, "
                    "RESTANDO lo ya pagado. Se usa la fecha de vencimiento de cada cuota, "
                    "no un cronograma calculado",
         "cols": ["Vencimiento", "Obra", "Cliente", "Cuota", "Monto", "Pagado",
                   "Falta", "Unidad", "Asesor"]},
        {"nombre": "Por vencer", "modo": "suma", "unidad": "cuotas", "mensual": False,
         "fn": lambda: cuotas("por_vencer"),
         "calculo": "cuotas pendientes cuyo vencimiento todavía no llegó: el "
                    "cronograma que viene. El filtro de mes no lo recorta "
                    "porque no es un flujo del mes, es plata futura",
         "cols": ["Vence", "Obra", "Cliente", "Cuota", "Monto", "Pagado",
                   "Falta", "Unidad", "Asesor"]},
        {"nombre": "Cuotas cobradas", "modo": "suma", "unidad": "cuotas", "mensual": True,
         "fn": lambda: cuotas("pagadas"),
         "calculo": "monto_pagado de las cuotas con estado «pagado». Es la "
                    "parte de «Cobrado» que viene de cuotas, sin las iniciales",
         "cols": ["Vencimiento", "Obra", "Cliente", "Cuota", "Monto", "Pagado", "Cobrado"]},
        {"nombre": "Pendientes con pago recibido", "modo": "suma", "mensual": False,
         "unidad": "cuotas", "fn": lambda: cuotas("raras"),
         "calculo": "cuotas en «pendiente» con pago recibido: "
                    "el estado y el monto se contradicen. Es data de Habitat, "
                    "se reporta y no se corrige",
         "cols": ["Vencimiento", "Obra", "Cliente", "Cuota", "Monto", "Pagado", "Recibido"]},
    ],
    "Comercial": [
        {"nombre": "Vendido por asesor", "modo": "suma", "unidad": "ventas", "mensual": True,
         "fn": ventas_por_asesor, "agrupa": "asesor",
         "calculo": "suma del precio de venta de las ventas cerradas, agrupada por "
                    "Sale.advisor",
         "cols": ["Fecha", "Obra", "Asesor", "Unidad", "Cliente", "Monto"]},
        {"nombre": "Ticket promedio por venta", "modo": "promedio", "unidad": "ventas",
         "mensual": True, "fn": ventas_por_asesor, "agrupa": "asesor",
         "calculo": "vendido dividido entre las ventas cerradas. Las dos cifras "
                    "salen de la MISMA población: el mismo filtro las mueve a "
                    "las dos",
         "cols": ["Fecha", "Obra", "Asesor", "Unidad", "Cliente", "Monto"]},
        {"nombre": "Ventas cerradas", "modo": "cuenta", "unidad": "ventas",
         "mensual": True, "fn": ventas_por_asesor, "agrupa": "asesor",
         "calculo": "cuántas ventas con estado «Vendido» cerró cada asesor. Es "
                    "un conteo, no soles: un asesor puede cerrar más ventas y "
                    "menos plata",
         "cols": ["Fecha", "Obra", "Asesor", "Unidad", "Cliente", "Monto"]},
        {"nombre": "Origen declarado de la venta", "modo": "cuenta", "unidad": "ventas",
         "mensual": False, "fn": ventas_por_origen, "agrupa": "grupo",
         "calculo": "una fila por venta con estado «Vendido», de TODOS los años, "
                    "con el campo «Fuente de marketing» que declaró el cliente. "
                    "Agrupadas por ese origen: la fila «— sin origen declarado —» "
                    "es el hueco que publica la tarjeta de cobertura",
         "cols": ["Fecha", "Obra", "Unidad", "Origen declarado", "Canal",
                  "Subfuente", "Cliente", "Asesor", "Monto"]},
        {"nombre": "Ventas por canal", "modo": "cuenta", "unidad": "ventas",
         "mensual": False, "fn": ventas_por_origen, "agrupa": "grupo",
         "calculo": "las mismas filas, para poder ver TODOS los canales y no "
                    "solo el más frecuente: cada grupo es un origen y su conteo",
         "cols": ["Fecha", "Obra", "Unidad", "Origen declarado", "Canal",
                  "Subfuente", "Cliente", "Asesor", "Monto"]},
        {"nombre": "Separaciones por asesor", "modo": "suma", "unidad": "separaciones",
         "mensual": True, "fn": separaciones_por_asesor, "agrupa": "asesor",
         "calculo": "ventas con estado «Separación», agrupadas por asesor. "
                    "NO se suman con las cerradas: todavía no son venta",
         "cols": ["Fecha", "Obra", "Asesor", "Unidad", "Cliente", "Pactado",
                  "Entregado"]},
        {"nombre": "Devoluciones por asesor", "modo": "suma", "unidad": "devoluciones",
         "mensual": True, "fn": devoluciones_por_asesor, "agrupa": "asesor",
         "calculo": "ventas con estado «Devolución», agrupadas por "
                    "Sale.advisor: lo que se cerró y después se cayó. **El "
                    "monto es lo ABONADO por el cliente**, no el precio del "
                    "inmueble — el precio va en el detalle, al lado",
         "cols": ["Fecha", "Obra", "Asesor", "Unidad", "Cliente", "Pactado",
                  "Entregado"]},
    ],
}


def todo() -> dict:
    out = {}
    for hoja, cifras in CIFRAS.items():
        out[hoja] = []
        for c in cifras:
            out[hoja].append({
                "nombre": c["nombre"], "modo": c["modo"], "unidad": c["unidad"],
                "mensual": c["mensual"],
                "calculo": c["calculo"], "cols": c["cols"],
                "agrupa": c.get("agrupa", ""),
                "filas": c["fn"](),
            })
    return out
