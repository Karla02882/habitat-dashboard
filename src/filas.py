"""LAS FILAS CRUDAS que componen cada cifra de Resultados."""
from __future__ import annotations

from datetime import date

import pandas as pd

from . import ingest, periodo

HOY = pd.Timestamp(date.today())
SIN_OBRA = "— sin obra —"
SIN_ASESOR = "(sin asesor)"


def asesor(v) -> str:
    """El nombre del vendedor, o `(sin asesor)`."""
    s = str(v).strip()
    return SIN_ASESOR if s.lower() in ("", "nan", "none", "<na>", "nat") else s


def _n(s) -> pd.Series:
    return pd.to_numeric(s, errors="coerce").fillna(0)


def _f(v) -> str:
    """Fecha en ISO corto, o vacío. La pantalla filtra por los 7 primeros."""
    d = pd.to_datetime(str(v), errors="coerce")
    return "" if pd.isna(d) else f"{d:%Y-%m-%d}"


def vendido() -> list[dict]:
    s = ingest.fetch_axion_entity("Sale", None, 5000)
    v = s[s["status"] == "Vendido"]
    return [{"fecha": _f(r["date"]), "obra": str(r["project"]).strip(),
             "monto": float(_n(pd.Series([r["sale_price"]])).iloc[0]),
             "d": [str(r["unit"]), str(r["client"]), asesor(r["advisor"]),
                   str(r["modality"]) or "—"]}
            for _, r in v.iterrows()]


_REPETIDOS: list[dict] = []

_SIN_MONTO: list[dict] = []


def repetidos() -> list[dict]:
    """Los recibos que venían cargados dos veces. Vacío hasta que corra."""
    return list(_REPETIDOS)


def cobrado() -> list[dict]:
    """Lo que REALMENTE entró: iniciales cobradas más cuotas pagadas."""
    cred = ingest.fetch_axion_entity("Credit", None, 5000)
    cxc = ingest.fetch_axion_entity("CxCPayment", None, 5000)
    obra = dict(zip(cred["id"], cred["project"]))
    out = []
    vistos: set = set()
    _REPETIDOS.clear()
    _SIN_MONTO.clear()
    for _, c in cred.iterrows():
        if not isinstance(c["iniciales"], list):
            continue
        for e in c["iniciales"]:
            if not isinstance(e, dict):
                continue
            if "pendiente" in str(e.get("tipo") or "").lower():
                continue
            try:
                m = float(str(e.get("monto", "0")).replace(",", ""))
            except ValueError:
                _SIN_MONTO.append({"fecha": _f(e.get("fecha", "")),
                                   "obra": str(c["project"]).strip(),
                                   "unidad": str(c.get("unit") or "—")})
                continue
            k = ingest.clave_inicial(e, c)
            if k in vistos:
                _REPETIDOS.append({"fecha": _f(e.get("fecha", "")),
                                   "obra": str(c["project"]).strip(),
                                   "unidad": str(c.get("unit") or "—"),
                                   "monto": m})
                continue
            vistos.add(k)
            out.append({"fecha": _f(e.get("fecha", "")),
                        "obra": str(c["project"]).strip(), "monto": m,
                        "d": ["inicial", str(c["client_name"]),
                              str(e.get("serie", "")) or "—",
                              str(e.get("empresa", "")) or "—"]})
    for _, p in cxc.iterrows():
        out.append({"fecha": _f(p["fecha"]),
                    "obra": str(obra.get(p["credit_id"], SIN_OBRA)).strip(),
                    "monto": float(_n(pd.Series([p["monto"]])).iloc[0]),
                    "d": ["cuota", str(p["client_name"]), "—",
                          str(p.get("notas", ""))[:38]]})
    return out


def separaciones() -> list[dict]:
    """Las separaciones NO son venta —sumarlas infló el vendido en S/ 596k."""
    s = ingest.fetch_axion_entity("Sale", None, 5000)
    v = s[s["status"] == "Separación"]
    return [{"fecha": _f(r["date"]), "obra": str(r["project"]).strip(),
             "monto": float(_n(pd.Series([r["real_income"]])).iloc[0]),
             "d": [str(r["unit"]), str(r["client"]), asesor(r["advisor"]),
                   f'lote S/ {float(_n(pd.Series([r["sale_price"]])).iloc[0]):,.2f}',
                   f'entregó S/ {float(_n(pd.Series([r["real_income"]])).iloc[0]):,.2f}']}
            for _, r in v.iterrows()]


def _norm_doc(s) -> str:
    return "".join(ch for ch in str(s or "").upper() if ch.isalnum())


def _abono_por_dni() -> dict[str, float]:
    """{DNI: plata que el cliente REALMENTE puso}."""
    cred = ingest.fetch_axion_entity("Credit", None, 5000)
    cxc = ingest.fetch_axion_entity("CxCPayment", None, 5000)
    out: dict[str, float] = {}
    for _, cr in cred.iterrows():
        doc = _norm_doc(cr.get("client_document"))
        if not doc:
            continue
        tot = 0.0
        if isinstance(cr.get("iniciales"), list):
            for e in cr["iniciales"]:
                if not isinstance(e, dict):
                    continue
                if "pendiente" in str(e.get("tipo") or "").lower():
                    continue
                try:
                    tot += float(str(e.get("monto", "")).replace(",", "") or 0)
                except ValueError:
                    pass
        p = cxc[cxc["credit_id"] == cr["id"]] if "credit_id" in cxc.columns else cxc.iloc[0:0]
        if len(p):
            tot += float(_n(p["monto"]).sum())
        out[doc] = out.get(doc, 0.0) + tot
    return out


def devoluciones() -> list[dict]:
    """Las ventas que se cayeron. **El monto es lo que el cliente ABONÓ**, no."""
    s = ingest.fetch_axion_entity("Sale", None, 5000)
    v = s[s["status"] == "Devolución"]
    filas = []
    for _, r in v.iterrows():
        precio = float(_n(pd.Series([r["sale_price"]])).iloc[0])
        puesto = float(_n(pd.Series([r["real_income"]])).iloc[0])
        filas.append({
            "fecha": _f(r["date"]), "obra": str(r["project"]).strip(),
            "monto": puesto,
            "d": [str(r["unit"]), str(r["client"]),
                  f"precio S/ {precio:,.2f}",
                  f"abonó S/ {puesto:,.2f}",
                  str(r["detail"])[:46] or "—"]})
    return filas


def por_cobrar() -> list[dict]:
    c = ingest.fetch_axion_entity("Credit", None, 5000)
    c = c[_n(c["saldo_pendiente"]) > 0]
    return [{"fecha": _f(r["fecha_inicio"]), "obra": str(r["project"]).strip(),
             "monto": float(_n(pd.Series([r["saldo_pendiente"]])).iloc[0]),
             "d": [str(r["unit"]), str(r["client_name"]), str(r["estado"]),
                   f'{float(_n(pd.Series([r["precio_venta"]])).iloc[0]):,.2f}']}
            for _, r in c.iterrows()]


def vencido() -> list[dict]:
    i = ingest.fetch_axion_entity("Installment", None, 5000)
    cred = ingest.fetch_axion_entity("Credit", None, 5000)
    obra = dict(zip(cred["id"], cred["project"]))
    vivos = set(cred[~cred["estado"].astype(str).str.lower().eq("cancelado")]["id"])
    f = pd.to_datetime(i["fecha_vencimiento"], errors="coerce")
    falta = (_n(i["monto_cuota"]) - _n(i["monto_pagado"])).clip(lower=0)
    v = i[(f < HOY) & falta.gt(0) & i["credit_id"].isin(vivos)]
    return [{"fecha": _f(r["fecha_vencimiento"]),
             "obra": str(obra.get(r["credit_id"], SIN_OBRA)).strip(),
             "monto": float(_n(pd.Series([r["monto_cuota"]])).iloc[0]
                            - _n(pd.Series([r["monto_pagado"]])).iloc[0]),
             "d": [str(r["client_name"]), f'cuota {r["numero_cuota"]:.0f}',
                   f'{float(r["monto_cuota"]):,.2f}',
                   f'{float(r["monto_pagado"]):,.2f}']}
            for _, r in v.iterrows()]


def por_vencer() -> list[dict]:
    """El cronograma que viene: cuotas pendientes que TODAVÍA no vencieron."""
    i = ingest.fetch_axion_entity("Installment", None, 5000)
    cred = ingest.fetch_axion_entity("Credit", None, 5000)
    obra = dict(zip(cred["id"], cred["project"]))
    f = pd.to_datetime(i["fecha_vencimiento"], errors="coerce")
    v = i[(i["estado"] == "pendiente") & (f >= HOY)]
    return [{"fecha": _f(r["fecha_vencimiento"]),
             "obra": str(obra.get(r["credit_id"], SIN_OBRA)).strip(),
             "monto": float(_n(pd.Series([r["monto_cuota"]])).iloc[0]
                            - _n(pd.Series([r["monto_pagado"]])).iloc[0]),
             "d": [str(r["client_name"]), f'cuota {r["numero_cuota"]:.0f}',
                   f'{float(r["monto_cuota"]):,.2f}',
                   f'{float(r["monto_pagado"]):,.2f}']}
            for _, r in v.iterrows()]


def falta_vender() -> list[dict]:
    u = ingest.fetch_axion_entity("Unit", None, 5000)
    li = u[u["status"] == "LIBRE"]
    return [{"fecha": "", "obra": str(r["project"]).strip(),
             "monto": float(_n(pd.Series([r["real_price"]])).iloc[0]
                            or _n(pd.Series([r.get("catalog_price")])).iloc[0]),
             "asesor": asesor(r["advisor"]),
             "d": [str(r["name"]),
                   f'{float(_n(pd.Series([r["area_m2"]])).iloc[0]):,.2f} m²',
                   str(r["status"]), asesor(r["advisor"])]}
            for _, r in li.iterrows()]


def gasto() -> list[dict]:
    """El gasto real, del MÓDULO DE MOVIMIENTOS."""
    from . import movimientos
    try:
        df = movimientos.crudo()
    except Exception:  # noqa: BLE001 — si el módulo nuevo no responde, sin gasto
        return []
    if df.empty:
        return []
    g = df[df["clase"] == "gasto"]
    mapa = movimientos.mapa_proyectos().set_index("proyecto")["obra_axion"].to_dict()
    filas = []
    for _, r in g.iterrows():
        proy = str(r.get("proyecto") or "").strip()
        obra = mapa.get(proy, "—")
        filas.append({
            "fecha": _f(r["fecha"]),
            "obra": obra if obra and obra != "—" else SIN_OBRA,
            "monto": float(r["monto_n"]),
            "d": [str(r.get("concepto") or "—")[:60],
                  str(r.get("movimiento") or "—"),
                  proy or "—",
                  str(r.get("cuenta") or "—")]})
    return filas


CONCEPTOS = {
    "Vendido": {
        "fn": vendido, "unidad": "ventas", "mensual": True,
        "corta": "ventas con estado «Vendido» · tabla Sale",
        "regla": "solo las ventas con estado «Vendido», en soles. Las "
                 "separaciones y devoluciones no son venta y quedan fuera "
                 "(tabla Sale de AXION)",
        "cols": ["Fecha", "Obra", "Unidad", "Cliente", "Asesor", "Modalidad", "Monto"]},
    "Cobrado": {
        "fn": cobrado, "unidad": "cobros", "mensual": True,
        "corta": "iniciales + cuotas cobradas · tablas Credit y CxCPayment",
        "regla": "la cuota inicial de cada crédito más las cuotas cobradas, en "
                 "soles (tablas Credit y CxCPayment de AXION)",
        "cols": ["Fecha", "Obra", "Tipo", "Cliente", "Serie", "Caja / nota", "Monto"]},
    "Por cobrar": {
        "fn": por_cobrar, "unidad": "créditos", "mensual": False,
        "corta": "saldo pendiente de cada crédito · tabla Credit",
        "regla": "el saldo que falta pagar de cada crédito, en soles. Es un "
                 "saldo a hoy: el mes no lo cambia (tabla Credit de AXION)",
        "cols": ["Inicio", "Obra", "Unidad", "Cliente", "Estado", "Precio", "Saldo"]},
    "Vencido": {
        "fn": vencido, "unidad": "cuotas", "mensual": False,
        "corta": "cuotas ya vencidas, restando lo pagado · tabla Installment",
        "regla": "cuotas pendientes que ya vencieron, restando lo ya pagado, en "
                 "soles. Es un saldo a hoy (tabla Installment de AXION)",
        "cols": ["Vencimiento", "Obra", "Cliente", "Cuota", "Monto", "Pagado", "Falta"]},
    "Por vencer": {
        "fn": por_vencer, "unidad": "cuotas", "mensual": False,
        "corta": "lo que entra si todos pagan en fecha · tabla Installment",
        "regla": "cuotas pendientes cuyo vencimiento todavía NO llegó, en "
                 "soles: es lo que entra si todos pagan en fecha. Es un "
                 "cronograma a futuro, el filtro de mes no lo recorta "
                 "(tabla Installment de AXION)",
        "cols": ["Vence", "Obra", "Cliente", "Cuota", "Monto", "Pagado",
                 "Falta"]},
    "Falta vender": {
        "fn": falta_vender, "unidad": "unidades", "mensual": False,
        "corta": "precio de las unidades LIBRES · tabla Unit",
        "regla": "el precio de las unidades libres, en soles. Las separadas y "
                 "bloqueadas no son stock vendible (tabla Unit de AXION)",
        "cols": ["—", "Obra", "Unidad", "Área", "Estado", "Asesor", "Precio"]},
    "Separaciones": {
        "fn": separaciones, "unidad": "separaciones", "mensual": True,
        "corta": "apalabrado que aún NO es venta · tabla Sale",
        "regla": "ventas con estado «Separación», en soles: plata apalabrada "
                 "que aún NO es venta y por eso no está en «Vendido» (tabla "
                 "Sale de AXION)",
        "cols": ["Fecha", "Obra", "Unidad", "Cliente", "Asesor",
                 "Precio del lote", "Lo que entregó", "Monto"]},
    "Devoluciones": {
        "fn": devoluciones, "unidad": "ventas caídas", "mensual": True,
        "corta": "lo que el cliente ABONÓ · no el precio del inmueble",
        "regla": "ventas con estado «Devolución». El monto es lo que el "
                 "cliente REALMENTE puso —iniciales cobradas más cuotas, de "
                 "la tabla Credit cruzada por DNI—, no el precio de la "
                 "unidad. El precio pactado va en su propia columna, como "
                 "contexto. **Lo efectivamente devuelto no existe como dato "
                 "en AXION**: solo aparece escrito a mano en «Detalle»",
        "cols": ["Fecha", "Obra", "Unidad", "Cliente", "Precio pactado",
                 "Abonado", "Detalle", "Monto"]},
    "Gasto": {
        "fn": gasto, "unidad": "movimientos de gasto", "mensual": True,
        "corta": "lo que salió de caja · del módulo de movimientos de AXION",
        "regla": "los movimientos marcados como gasto en el módulo de "
                 "movimientos de AXION —el que Habitat empezó a cargar en "
                 "agosto—. NO incluye el presupuesto, que AXION guarda como "
                 "si fuera un ingreso y no es plata que salió. La obra sale "
                 "de emparejar el proyecto que escribieron con las obras "
                 "declaradas; lo que no empareja se muestra sin obra en vez "
                 "de repartirse",
        "cols": ["Fecha", "Obra", "Concepto", "Tipo", "Proyecto escrito",
                 "Banco", "Soles"]},
}


def todo() -> dict:
    out = {}
    for k, v in CONCEPTOS.items():
        filas_ = v["fn"]()
        regla = v["regla"]
        avisos: list[str] = []
        if v["mensual"]:
            viejas_ = [x for x in filas_
                       if x["fecha"]
                       and not x["fecha"].startswith(str(periodo.ANIO))]
            if viejas_:
                avisos.append(
                    f"AXION guarda además {len(viejas_)} operaciones de años "
                    f"anteriores por "
                    f"S/ {sum(x['monto'] for x in viejas_):,.2f}: NO entran "
                    f"en el acumulado del año. Para verlas, elegí «Todos los "
                    f"años» en el período")
        if k == "Vencido":
            i = ingest.fetch_axion_entity("Installment", None, 5000)
            cr = ingest.fetch_axion_entity("Credit", None, 5000)
            saldos = dict(zip(cr["id"], _n(cr["saldo_pendiente"])))
            venc = pd.to_datetime(i["fecha_vencimiento"], errors="coerce")
            hoy_ = pd.Timestamp(pd.Timestamp.today().date())
            v_ = i[(i["estado"] == "pendiente") & (venc < hoy_)].copy()
            v_["_falta"] = _n(v_["monto_cuota"]) - _n(v_["monto_pagado"])
            cerr = v_[v_["credit_id"].map(lambda x: saldos.get(x, -1) == 0)]
            m_c = float(cerr["_falta"].sum())
            if m_c:
                avisos.append(alerta(
                    f"S/ {m_c:,.2f} en cuotas «pendiente» de créditos "
                    f"cancelados",
                    f"{len(cerr)} cuotas siguen en «pendiente» dentro de un "
                    f"crédito que el propio AXION marca como cancelado y con "
                    f"saldo cero: o la cuota está impaga, o el crédito está "
                    f"cancelado, las dos cosas no. No entran en lo vencido.",
                    "Corregir la cuota o el crédito en AXION.",
                    "Cobranzas"))
        if k in ("Cobrado", "Por cobrar"):
            from . import auditoria
            dup = auditoria.peso_duplicados()
            if dup["grupos"]:
                if k == "Cobrado" and _REPETIDOS:
                    _r_tot = sum(x["monto"] for x in _REPETIDOS)
                    _r_an = [x for x in _REPETIDOS
                             if str(x["fecha"])[:4] == str(periodo.ANIO)]
                    _u = sorted({f'{x["obra"]} / {x["unidad"]}'
                                 for x in _REPETIDOS})
                    avisos.append(alerta(
                        f"S/ {_r_tot:,.2f} en {len(_REPETIDOS)} recibos "
                        f"venían cargados dos veces y NO se suman acá",
                        f"{len(_u)} unidades tienen su crédito cargado más de "
                        f"una vez en AXION, y cada copia arrastra su propia "
                        f"lista de pagos: el mismo recibo —misma serie, mismo "
                        f"monto, misma fecha— aparecía dos veces. Se cuenta "
                        f"una sola vez, y acá va lo que quedó afuera para que "
                        f"se vea"
                        + (f", de lo cual S/ {sum(x['monto'] for x in _r_an):,.2f} "
                           f"en {len(_r_an)} recibos son de {periodo.ANIO}"
                           if _r_an else "")
                        + f". Las unidades son: {', '.join(_u)}. Los nombres "
                        f"difieren entre copias («ROMARIO R. (COPIA)» contra "
                        f"«(2)»), así que a simple vista no se ven repetidas.",
                        "Decidir cuál de cada grupo queda y dar de baja el "
                        "otro en AXION. La cifra de esta tarjeta ya no los "
                        "cuenta dos veces; lo que sigue abierto es cuál de "
                        "las copias es la buena.",
                        "Cobranzas"))
                elif k == "Por cobrar" and dup["saldo_max"]:
                    avisos.append(alerta(
                        f"Entre S/ {dup['saldo_min']:,.2f} y "
                        f"S/ {dup['saldo_max']:,.2f} de la deuda está "
                        f"duplicada",
                        f"{dup['grupos']} unidades con crédito repetido "
                        f"arrastran "
                        + (f"hasta {dup['max_por_grupo']} saldos"
                           if dup.get('max_por_grupo', 2) > 2
                           else "dos saldos")
                        + f" por una sola "
                        f"operación. El rango sale de que las copias no "
                        f"traen el mismo saldo: según cuál sea la buena, lo "
                        f"duplicado es una cifra u otra. <b>Esa decisión es "
                        f"de Habitat, no del tablero</b>, y por eso acá va el "
                        f"rango y no un número. Solo entran créditos VIVOS: "
                        f"un cancelado no puede ser el vigente, y dos "
                        f"créditos de la misma unidad con DNI distinto son "
                        f"una reventa, no una copia.",
                        "Definir cuál de cada grupo es el crédito vigente y "
                        "dar de baja los otros. Con eso, la cifra deja de ser "
                        "un rango.",
                        "Cobranzas"))
        if k == "Cobrado" and _SIN_MONTO:
            _u = sorted({f'{x["obra"]} / {x["unidad"]}' for x in _SIN_MONTO})
            avisos.append(alerta(
                f"{len(_SIN_MONTO)} " + ("recibo cargado" if len(_SIN_MONTO) == 1
                                         else "recibos cargados") +
                " sin monto",
                f"En AXION hay {len(_SIN_MONTO)} "
                + ("pago inicial con el campo «monto» vacío"
                   if len(_SIN_MONTO) == 1
                   else "pagos iniciales con el campo «monto» vacío")
                + f": {', '.join(_u)}. No se cuentan como cobro —no se sabe "
                f"de cuánto son— ni se rellenan con cero, que los haría "
                f"desaparecer del hallazgo.",
                "Cargar el monto en AXION, o dar de baja el recibo si no "
                "corresponde.",
                "Cobranzas"))
        if k == "Cobrado":
            cr = ingest.fetch_axion_entity("Credit", None, 5000)
            px = ingest.fetch_axion_entity("CxCPayment", None, 5000)
            pagos = _n(px["monto"]).groupby(px["credit_id"]).sum()
            rotos = []
            for _, r in cr.iterrows():
                ini = 0.0
                if isinstance(r["iniciales"], list):
                    for e in r["iniciales"]:
                        if isinstance(e, dict):
                            if "pendiente" in str(e.get("tipo") or "").lower():
                                continue
                            try:
                                ini += float(str(e.get("monto", "0"))
                                             .replace(",", ""))
                            except ValueError:
                                pass
                precio = float(_n(pd.Series([r["precio_venta"]])).iloc[0])
                dif = (ini + float(pagos.get(r["id"], 0.0))
                       + float(_n(pd.Series([r["saldo_pendiente"]])).iloc[0])
                       - precio)
                if abs(dif) > 1:
                    rotos.append((dif, ini, precio, str(r["client_name"])))
            if rotos:
                rotos.sort(reverse=True)
                dif1, ini1, precio1, quien1 = rotos[0]
                tam = sum(abs(x[0]) for x in rotos)
                avisos.append(alerta(
                    f"En {len(rotos)} créditos las cuentas del cliente no "
                    f"cierran",
                    f"En {len(rotos)} de {len(cr)} créditos, lo que el cliente "
                    f"pagó de inicial, más sus cuotas, más lo que todavía debe, "
                    f"NO da el precio pactado. Entre todos el descuadre suma "
                    f"S/ {tam:,.2f} en valor absoluto (unos piden de más y "
                    f"otros de menos, así que no se compensan). El caso más "
                    f"grande es "
                    f"{quien1}: su precio es S/ {precio1:,.0f} y tiene "
                    f"S/ {ini1:,.0f} registrados como pago inicial — mucho más "
                    f"que el precio entero. Si ese monto está mal tipeado, el "
                    f"total cobrado que muestra el tablero está inflado.",
                    "Revisar esos créditos en AXION y corregir el monto que "
                    "esté mal cargado. Conviene empezar por el más grande, que "
                    "es el que más mueve la cifra.",
                    "Cobranzas"))
        if k == "Por cobrar":
            i = ingest.fetch_axion_entity("Installment", None, 5000)
            cr = ingest.fetch_axion_entity("Credit", None, 5000)
            pend = i["estado"] == "pendiente"
            cuotas_ = float((_n(i["monto_cuota"]) - _n(i["monto_pagado"]))[pend].sum())
            _v_ = cr[~cr["estado"].astype(str).str.lower().eq("cancelado")]
            saldo_ = float(_n(_v_["saldo_pendiente"]).sum())
            sin_cuotas = cr[~cr["id"].isin(set(i["credit_id"]))]
            desc = []
            for _, cr_ in cr.iterrows():
                s_ = float(_n(pd.Series([cr_["saldo_pendiente"]])).iloc[0])
                q_ = float((_n(i["monto_cuota"]) - _n(i["monto_pagado"]))[
                    pend & (i["credit_id"] == cr_["id"])].sum())
                if q_ > 0 and abs(s_ - q_) > 1:
                    desc.append((abs(s_ - q_), str(cr_["client_name"]), s_, q_))
            if desc:
                desc.sort(reverse=True)
                d1, quien1_, s1_, q1_ = desc[0]
                avisos.append(alerta(
                    f"En {len(desc)} créditos las cuotas cargadas no suman lo "
                    f"que el cliente debe",
                    f"Estos créditos sí tienen cronograma, pero la suma de sus "
                    f"cuotas pendientes no coincide con su saldo. El caso "
                    f"mayor es {quien1_}: debe S/ {s1_:,.2f} y sus cuotas "
                    f"suman S/ {q1_:,.2f}. Por eso el reparto del saldo no "
                    f"cierra exacto: hay créditos con cuotas de más y otros "
                    f"con cuotas de menos, y se compensan entre sí.",
                    "Revisar esos cronogramas en AXION: o falta agregar "
                    "cuotas, o hay cuotas cargadas de más.",
                    "Cobranzas"))

            if abs(saldo_ - cuotas_) > 1:
                avisos.append(alerta(
                    f"{len(sin_cuotas)} créditos no tienen su cronograma de "
                    f"cuotas cargado",
                    f"El saldo que los clientes deben es S/ {saldo_:,.2f}, pero "
                    f"si se suman las cuotas pendientes una por una solo dan "
                    f"S/ {cuotas_:,.2f} — faltan "
                    f"S/ {saldo_ - cuotas_:,.2f}. El motivo: {len(sin_cuotas)} "
                    f"de {len(cr)} créditos no tienen ninguna cuota registrada, "
                    f"así que esa plata no aparece en ningún vencimiento y no "
                    f"se puede saber cuándo entra ni reclamarla a tiempo.",
                    "Cargar el cronograma de cuotas de esos créditos en AXION: "
                    "cuántas cuotas, de cuánto y con qué fecha de vencimiento.",
                    "Cobranzas"))
        if k == "Separaciones":
            avisos += _aviso_separaciones(filas_)
        if k == "Devoluciones" and filas_:
            avisos += _aviso_devoluciones(filas_)
        out[k] = {**{x: y for x, y in v.items() if x != "fn"},
                  "regla": regla, "avisos": avisos, "filas": filas_}
    return out


def alerta(titulo: str, que_paso: str, como_se_cierra: str, area: str) -> str:
    """Una alerta con las tres cosas que alguien necesita para actuar."""
    return f"{titulo}∷{que_paso}∷{como_se_cierra}∷{area}"


def _aviso_devoluciones(filas_: list[dict]) -> list[str]:
    """Lo que hay que decir al lado del monto de las ventas caídas."""
    abonado = sum(f["monto"] for f in filas_)
    precios = 0.0
    for f in filas_:
        try:
            precios += float(str(f["d"][2]).replace("precio", "")
                             .replace("S/", "").replace(",", "").strip())
        except ValueError:
            pass

    out = []
    sin_pago = [f for f in filas_ if not f["monto"]]
    if sin_pago:
        quienes = " · ".join(str(f["d"][1]) for f in sin_pago)
        out.append(alerta(
            f"{len(sin_pago)} de {len(filas_)} ventas caídas figuran con pago "
            f"en cero",
            f"Estas ventas se cayeron y AXION registra S/ 0.00 recibido: "
            f"{quienes}. Puede ser correcto —una venta que se cayó antes de "
            f"que el cliente pagara nada— o puede faltar cargar el pago. "
            f"Mientras tanto no hay nada que devolverles.",
            "Confirmar si esos clientes llegaron a pagar algo. Si pagaron, "
            "cargarlo en la venta; si no pagaron, no hay que hacer nada y el "
            "cero es el dato correcto.",
            "Comercial"))
    s_ = ingest.fetch_axion_entity("Sale", None, 5000)
    llenas = int((_n(s_["monto_devolucion"]) > 0).sum()) \
        if "monto_devolucion" in s_.columns else 0
    out.append(alerta(
        "La casilla del importe devuelto existe y está vacía",
        f"Cuando una venta se cae, el cliente recibe de vuelta parte o todo lo "
        f"que pagó. La ficha de venta de AXION tiene la casilla «monto "
        f"devolución» y **está vacía en las {len(filas_)} ventas caídas** "
        f"({llenas} ventas de toda la tabla la tienen con un importe mayor a "
        f"cero). Lo devuelto solo queda escrito a mano en el comentario: uno "
        f"de estos casos dice «SE LE DEVOLVIO EL 50% (100 SOLES)». Por eso el "
        f"tablero muestra lo ABONADO (S/ {abonado:,.2f}), que es el techo de "
        f"lo que podría devolverse, no lo que salió de caja.",
        "Llenar «monto devolución» en la ficha de cada venta caída con lo que "
        "efectivamente se devolvió. No hay que pedirle nada a la "
        "desarrolladora: el campo ya está. En cuanto se cargue, el tablero "
        "puede mostrar lo devuelto de verdad en vez del techo.",
        "Comercial"))
    return out


def _aviso_separaciones(filas_: list[dict]) -> list[str]:
    """El descuadre entre `Unit.status` y `Sale.status`, CON NOMBRE Y APELLIDO."""
    u = ingest.fetch_axion_entity("Unit", None, 5000)
    s = ingest.fetch_axion_entity("Sale", None, 5000)
    sep_u = u[u["status"] == "SEPARADO"]
    if len(sep_u) == len(filas_):
        return []

    def clave(obra, unidad) -> tuple[str, str]:
        return (str(obra).strip().upper(), str(unidad).strip().upper())

    con_separacion = {
        clave(r["project"], r["unit"])
        for _, r in s[s["status"] == "Separación"].iterrows()}

    detalle = []
    for _, r in sep_u.iterrows():
        k = clave(r["project"], r["name"])
        if k in con_separacion:
            continue
        otras = s[(s["project"].astype(str).str.strip().str.upper() == k[0])
                  & (s["unit"].astype(str).str.strip().str.upper() == k[1])]
        if len(otras):
            estados = ", ".join(sorted({str(x) for x in otras["status"]}))
            precios = ""
            pu = pd.to_numeric(pd.Series([r.get("real_price")]),
                               errors="coerce").iloc[0]
            ps = pd.to_numeric(otras["sale_price"], errors="coerce").iloc[0]
            if pd.notna(pu) and pd.notna(ps) and abs(pu - ps) > 0.01:
                precios = (f", y encima el precio no coincide: en la ficha de "
                           f"la unidad dice S/ {pu:,.2f} y en la de la venta "
                           f"S/ {ps:,.2f}")
            detalle.append(
                f"la obra {r['project']}, unidad {r['name']}: figura como "
                f"separada, pero su venta ya está «{estados}»{precios}")
        else:
            detalle.append(
                f"la obra {r['project']}, unidad {r['name']}: figura como "
                f"separada y no tiene ninguna venta registrada")

    if not detalle:
        return [alerta(
            "Las unidades separadas no cuadran con las separaciones",
            f"El sistema tiene {len(sep_u)} unidades marcadas como separadas, "
            f"pero solo {len(filas_)} separaciones registradas. Cada unidad "
            f"cruza con la suya, así que la diferencia viene por otro lado.",
            "Revisar con Comercial de dónde sale la diferencia.", "Comercial")]
    cuales = " · ".join(detalle)
    return [alerta(
        (f"Una unidad figura separada pero su venta ya está cerrada"
         if len(detalle) == 1 else
         f"{len(detalle)} unidades tienen dos estados distintos a la vez"),
        f"El sistema tiene {len(sep_u)} unidades marcadas como separadas, pero "
        f"solo {len(filas_)} tienen su separación registrada. La diferencia "
        f"está acá: {cuales}",
        "Entrar a AXION, buscar esa unidad y dejarle el estado que "
        "corresponde. Si además el precio no coincide entre la ficha de la "
        "unidad y la de la venta, decidir cuál manda y corregir el otro. Al "
        "quedar parejo, esta alerta desaparece sola.",
        "Comercial")]


def obras_disponibles() -> list[str]:
    """Las obras que aparecen en alguna de las filas. Se arma de los datos."""
    vistas = set()
    for v in CONCEPTOS.values():
        for f in v["fn"]():
            if f["obra"] and f["obra"] != SIN_OBRA:
                vistas.add(f["obra"])
    return sorted(vistas)
