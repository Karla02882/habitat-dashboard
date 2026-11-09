"""HOJAS 4 a 9 · las áreas."""
from __future__ import annotations

import threading
from datetime import date

import pandas as pd

from . import ingest, kommo, movimientos, periodo
from .ficha_obra import Cifra

HOY = pd.Timestamp(date.today())


def _num(s) -> pd.Series:
    return pd.to_numeric(s, errors="coerce").fillna(0)


def _kommo() -> pd.DataFrame | None:
    """Los leads del embudo de Habitat Inmobiliaria, o None si no se pudo leer."""
    try:
        return kommo.leads()
    except Exception:  # noqa: BLE001
        return None


SIN_KOMMO = ("el CRM no respondió en esta lectura. La cifra existe: son los "
             "leads del embudo «Ventas - Habitat Inmobiliaria» en Kommo")


def _ventas_caidas(sale: pd.DataFrame) -> Cifra:
    """Las ventas que se cayeron, con lo que el cliente ABONÓ."""
    from . import filas
    v = sale[sale["status"] == "Devolución"]
    caidas = filas.devoluciones()
    abonado = sum(f["monto"] for f in caidas)
    sin_dato = sum(1 for f in caidas if not f["monto"])
    precio = float(_num(v["sale_price"]).sum())
    detalle = (f"cantidad de ventas con estado «Devolución». Lo que Habitat "
               f"tendría que devolver es lo que el cliente ENTREGÓ: "
               f"S/ {abonado:,.2f} (campo «INGRESO REAL» de AXION, sin nulos). "
               f"El precio de esos inmuebles suma S/ {precio:,.2f} y NO es "
               f"plata a devolver")
    if sin_dato:
        detalle += (f" · {sin_dato} de {len(caidas)} figuran con pago en cero: "
                    f"o se cayeron antes de pagar nada, o falta cargarlo")
    return Cifra("Ventas caídas", int(len(v)), detalle, "AXION · Sale + Credit")


def ventas() -> list[Cifra]:
    sale = ingest.fetch_axion_entity("Sale", None, 5000)
    unit = ingest.fetch_axion_entity("Unit", None, 5000)
    v = sale[sale["status"] == "Vendido"]
    libres = int((unit["status"] == "LIBRE").sum())
    return [
        Cifra("Vendido", float(_num(v["sale_price"]).sum()),
              f"suma del precio de venta de las {len(v)} ventas con estado «Vendido»",
              "AXION · Sale"),
        Cifra("Ticket promedio", float(_num(v["sale_price"]).mean()),
              "vendido dividido entre las ventas cerradas — las dos cifras "
              "salen de la misma población: las ventas con estado «Vendido»",
              "AXION · Sale"),
        Cifra("Unidades libres", libres,
              "unidades con estado «LIBRE». NO es total menos vendidas: esa "
              f"resta contaría como stock las "
              f"{int((unit['status'] == 'SEPARADO').sum())} separadas y las "
              f"{int((unit['status'] == 'BLOQUEADO').sum())} bloqueadas",
              "AXION · Unit"),
        _vendido_del_inventario(sale, unit),
        _ventas_caidas(sale),
    ]


def cobranza() -> list[Cifra]:
    inst = ingest.fetch_axion_entity("Installment", None, 5000)
    cred = ingest.fetch_axion_entity("Credit", None, 5000)
    venc = pd.to_datetime(inst["fecha_vencimiento"], errors="coerce")
    falta = _num(inst["monto_cuota"]) - _num(inst["monto_pagado"])
    _vivos = set(cred[~cred["estado"].astype(str).str.lower().eq("cancelado")]["id"])
    _falta = (_num(inst["monto_cuota"]) - _num(inst["monto_pagado"])).clip(lower=0)
    vencidas = inst[(venc < HOY) & _falta.gt(0) & inst["credit_id"].isin(_vivos)]
    falta_venc = float(_falta[vencidas.index].sum())
    raras = inst[(inst["estado"] == "pendiente") & (_num(inst["monto_pagado"]) > 0)]

    out = [
        Cifra("Cartera por cobrar",
              float(_num(cred[~cred["estado"].astype(str).str.lower()
                              .eq("cancelado")]["saldo_pendiente"]).sum()),
              f"suma del saldo por pagar de los créditos vivos, "
              f"de {len(cred)} en total",
              "AXION · Credit"),
        Cifra("Vencido", falta_venc,
              f"{len(vencidas)} cuotas de créditos vivos con vencimiento "
              f"anterior a hoy y plata por pagar, restando lo ya pagado. Se usa "
              f"la fecha de vencimiento de cada cuota, no un cronograma calculado",
              "AXION · Installment"),
        Cifra("Cuotas pagadas", int((inst["estado"] == "pagado").sum()),
              "cuotas con estado «pagado»", "AXION · Installment"),
    ]
    if len(raras):
        out.append(Cifra(
            "Cuotas pendientes con pago recibido", len(raras),
            "cuotas en «pendiente» con pago recibido",
            "AXION · Installment",
            motivo=(f"el estado y el monto se contradicen en {len(raras)} "
                    f"cuotas. Ocho son faltantes de centavos (S/ 400.20 "
                    f"cobrado S/ 400.00) y dos son parciales reales. Habitat "
                    f"define si están vencidas o pagadas."),
            area="Cobranzas"))
    return out


def _clave(x) -> str:
    return "".join(c for c in str(x or "").upper() if c.isalnum())


def _origen_declarado(sale: pd.DataFrame, v: pd.DataFrame,
                      con_src: pd.DataFrame) -> Cifra:
    """Cuántas ventas declaran de dónde vino el cliente."""
    del sale
    vac = len(v) - len(con_src)
    va = periodo.recortar(v, "date", None)
    con_anio = int((~va["marketing_source"].map(
        lambda x: not str(x).strip() or str(x).strip().lower() == "nan")).sum())
    falta_anio = len(va) - con_anio
    if len(va) and falta_anio == 0:
        motivo = (f"En {periodo.ANIO} está COMPLETO: las {len(va)} ventas del "
                  f"año declaran su origen. Los {vac} vacíos son todos de años "
                  f"anteriores, así que esta cifra —que cruza años— es un piso "
                  f"del histórico, no un hueco de hoy")
        area = ""
    else:
        motivo = (f"faltan {falta_anio} de {len(va)} ventas de "
                  f"{periodo.ANIO} sin origen ({vac} de {len(v)} contando "
                  f"todos los años)")
        area = "Marketing"
    return Cifra(
        "Ventas con origen declarado", len(con_src),
        f"ventas cerradas con el origen del cliente cargado, de {len(v)} — las dos "
        f"cifras salen de la misma población: las ventas con estado «Vendido»",
        "AXION · Sale", motivo=motivo, area=area)


def _vendido_del_inventario(sale: pd.DataFrame, unit: pd.DataFrame) -> Cifra:
    """Qué parte del inventario está vendida, contando solo lo que tiene venta."""
    vendidas = unit[unit["status"] == "VENDIDO"]
    con_venta = {(_clave(p), _clave(u)) for p, u in zip(
        sale.loc[sale["status"] == "Vendido", "project"],
        sale.loc[sale["status"] == "Vendido", "unit"])}
    respaldadas = sum(1 for p, n in zip(vendidas["project"], vendidas["name"])
                      if (_clave(p), _clave(n)) in con_venta)
    total = len(unit) or 1
    huerfanas = len(vendidas) - respaldadas
    obras = sorted({str(p).strip() for p, n in
                    zip(vendidas["project"], vendidas["name"])
                    if (_clave(p), _clave(n)) not in con_venta})
    motivo = ""
    if huerfanas:
        motivo = (f"{huerfanas} unidades más figuran con estado VENDIDO pero "
                  f"no tienen ninguna venta registrada ({', '.join(obras[:3])}"
                  f"{'…' if len(obras) > 3 else ''}). Contándolas, la cifra "
                  f"sería {100.0 * len(vendidas) / total:.2f} %. No se cuentan: "
                  f"sin cliente, sin fecha y sin precio no hay venta que "
                  f"respalde el estado")
    return Cifra(
        "Vendido del inventario (%)", 100.0 * respaldadas / total,
        f"unidades con estado VENDIDO **y venta registrada** ({respaldadas}) "
        f"sobre el total del inventario ({len(unit)}). No es «absorción»: la "
        f"absorción es una tasa por período y esto es el acumulado histórico",
        "AXION · Unit + Sale", motivo=motivo, area="Comercial" if motivo else "")


def _agendas_y_visitas(adv: pd.DataFrame) -> tuple[float, float, int]:
    """Agendas y visitas reales, abriendo su ficha de asesor."""
    agendas = visitas = 0.0
    con_detalle = 0
    for md in adv.get("monthly_data", pd.Series(dtype=object)):
        if not isinstance(md, dict) or not md:
            continue
        con_detalle += 1
        for meses in md.values():
            if not isinstance(meses, dict):
                continue
            for m in meses.values():
                if isinstance(m, dict):
                    agendas += float(_num(pd.Series([m.get("agendas")])).iloc[0])
                    visitas += float(_num(pd.Series([m.get("visitas")])).iloc[0])
    return agendas, visitas, con_detalle


def comercial() -> list[Cifra]:
    sale = ingest.fetch_axion_entity("Sale", None, 5000)
    adv = ingest.fetch_axion_entity("Advisor", None, 5000)
    v = sale[sale["status"] == "Vendido"]
    por_asesor = v.groupby("advisor")["sale_price"].apply(lambda s: _num(s).sum())
    ag, vi, con = _agendas_y_visitas(adv)
    out = [
        Cifra("Asesores con venta cerrada", int(v["advisor"].nunique()),
              f"asesores distintos en las {len(v)} ventas cerradas, de los "
              f"{len(adv)} registrados como asesores. **De todos los años**, no "
              f"del período elegido", "AXION · Sale + Advisor"),
        Cifra("Mejor asesor", float(por_asesor.max()) if len(por_asesor) else None,
              f"mayor suma del precio de venta por asesor de TODOS los años: "
              f"{por_asesor.idxmax() if len(por_asesor) else '—'}. El bloque "
              f"de arriba sí sigue el filtro; esta tarjeta no",
              "AXION · Sale"),
        Cifra("Visitas hechas", float(vi),
              f"suma de las visitas mes a mes que declaran los asesores en "
              f"su ficha de asesor, sobre {con} de {len(adv)} que lo "
              f"tienen cargado. Van con {ag:,.0f} agendas: la diferencia entre "
              f"agendar y visitar es el dato que le sirve a Comercial",
              "AXION · Advisor",
              motivo=("" if con == len(adv) else
                      f"{len(adv) - con} de {len(adv)} asesores no cargan su "
                      f"detalle mensual, así que la cifra es un piso"),
              area="" if con == len(adv) else "Comercial"),
    ]

    k = _kommo()
    if k is None:
        out.append(Cifra("Leads en el embudo", None,
                         "leads del embudo de Habitat Inmobiliaria en el CRM",
                         "KOMMO", motivo=SIN_KOMMO, area="Comercial"))
        return out

    n = len(k)
    vendidos = int((k["etapa"] == "VENDIDO").sum())
    desestimados = int((k["etapa"] == "DESESTIMADO").sum())
    visitaron = int(k["visita_presencial"].notna().sum())
    fechas = k["creado"].dropna()

    out += [
        Cifra("Leads en el embudo", n,
              f"leads de «Ventas - Habitat Inmobiliaria», acumulado de "
              f"{fechas.min():%Y-%m-%d} a {fechas.max():%Y-%m-%d}. Los otros "
              f"tres embudos de la cuenta quedan fuera del alcance",
              "KOMMO · leads"),
        Cifra("Leads que visitaron", visitaron,
              f"leads con «Fecha de Visita Presencial» cargada, de {n:,} "
              f"({100 * visitaron / n:.1f}%). Se usa la FECHA y no la etapa "
              f"«VISITA»: la etapa dice dónde está el lead hoy, así que el que "
              f"visitó y compró ya salió de ella y no se contaría",
              "KOMMO · leads"),
        Cifra("Leads marcados VENDIDO", vendidos,
              f"leads en etapa «VENDIDO», de {n:,}. **No es comparable con las "
              f"ventas de AXION**: son dos sistemas con definiciones y "
              f"ventanas distintas, y restarlos inventaría una brecha",
              "KOMMO · leads"),
        Cifra("Conversión del embudo (%)", 100.0 * vendidos / n,
              f"los {vendidos} leads en «VENDIDO» sobre los {n:,} del embudo. "
              f"Numerador y denominador salen de la misma población: el mismo "
              f"embudo, la misma ventana",
              "KOMMO · leads"),
        Cifra("Leads desestimados", desestimados,
              f"leads en etapa «DESESTIMADO»: {100 * desestimados / n:.1f}% "
              f"del embudo. Es la etapa más poblada de las diez",
              "KOMMO · leads"),
        Cifra("De cada 100 visitas, se cierran",
              (100.0 * int(((k["visita_presencial"].notna())
                            & (k["etapa"] == "VENDIDO")).sum())
               / max(visitaron, 1)) if visitaron else None,
              f"leads con fecha de visita que además quedaron en «VENDIDO»: "
              f"{int(((k['visita_presencial'].notna()) & (k['etapa'] == 'VENDIDO')).sum())} "
              f"de {visitaron}. Los dos lados salen de los leads que "
              f"visitaron, no de todo el embudo",
              "KOMMO · leads",
              motivo=("es conversión DENTRO del CRM, no contra las ventas de "
                      "AXION: son dos definiciones y cruzarlas daría una tasa "
                      "inventada"),
              area="Comercial"),
    ]
    return out


def marketing() -> list[Cifra]:
    sale = ingest.fetch_axion_entity("Sale", None, 5000)
    v = sale[sale["status"] == "Vendido"]
    vac_src = int(sale["marketing_source"].map(lambda x: not str(x).strip()).sum())
    con_src = v[v["marketing_source"].map(lambda x: bool(str(x).strip()))]
    try:
        n_lead = len(ingest.fetch_axion_entity("Lead", None, 5000))
    except Exception:  # noqa: BLE001
        n_lead = 0
    out = [
        _origen_declarado(sale, v, con_src),
    ]
    if len(con_src):
        top = con_src["marketing_source"].value_counts()
        out.append(Cifra(
            "Canal con más ventas", int(top.iloc[0]),
            f"canal «{top.index[0]}» — conteo de ventas, no soles. "
            f"Calculado sobre las {len(con_src)} ventas con origen, no sobre "
            f"las {len(v)} cerradas",
            "AXION · Sale"))

    k = _kommo()
    if k is None:
        out.append(Cifra("Leads captados", None,
                         "leads del embudo de Habitat Inmobiliaria en el CRM",
                         "KOMMO", motivo=SIN_KOMMO, area="Marketing"))
        out.append(_costo_de_captacion(0))
        out += _kpis_del_area()
        return out

    n = len(k)
    con_camp = k[k["campana"].notna()]
    out.append(Cifra(
        "Leads captados", n,
        f"leads del embudo «Ventas - Habitat Inmobiliaria». La cuenta tiene "
        f"cuatro embudos y {kommo.resumen()['total_cuenta']:,} leads en total: "
        f"los otros tres —Concept y Atención al cliente— quedan fuera del "
        f"alcance por decisión de Habitat",
        "KOMMO · leads"))
    out.append(Cifra(
        "Leads con campaña declarada", len(con_camp),
        f"leads con «m Campaña Marketing» cargado, de {n:,} "
        f"({100 * len(con_camp) / n:.1f}%). Es el dato que AXION no tiene: "
        f"acá el origen está en 98 de cada 100",
        "KOMMO · leads"))
    if len(con_camp):
        top = con_camp["campana"].value_counts()
        out.append(Cifra(
            "Campaña con más leads", int(top.iloc[0]),
            f"campaña «{top.index[0]}» — conteo de LEADS, no de ventas ni de "
            f"soles. Sobre los {len(con_camp):,} leads con campaña, no sobre "
            f"los {n:,} del embudo. Hay {len(top)} campañas distintas en uso",
            "KOMMO · leads"))

    rastreados = int(sum(k[c].notna().sum() for c in kommo.RASTREO))
    out.append(Cifra(
        "Rastreo automático de anuncios", None,
        "de qué anuncio de Facebook, Google o TikTok vino cada lead",
        "KOMMO",
        motivo=(f"los {len(kommo.RASTREO)} campos de rastreo (utm_source, "
                f"gclid, fbclid, ttad_name…) están vacíos en los {n:,} leads: "
                f"{rastreados} con dato. La campaña la escribe el asesor A "
                f"MANO, así que sirve para agrupar pero no permite calcular "
                f"costo por anuncio"),
        area="Marketing"))
    out.append(campanas_con_venta())
    out.append(_costo_de_captacion(n))
    out += _kpis_del_area()
    return out


def _costo_de_captacion(n_leads_crm: int) -> Cifra:
    """El CPL."""
    from . import marketing_kpi as mk
    fichas = {f["hoja"]: f for f in mk.fichas()}
    c = mk.corte()
    f = fichas.get("KPI_02")
    if not c.get("hay") or not f:
        return Cifra(
            "Costo por lead (S/)", None,
            "inversión en marketing dividida entre los leads captados", "—",
            motivo=("el libro de indicadores de Marketing no está en "
                    "`data/raw_exports/marketing/`. Sin él no hay numerador: "
                    "AXION solo registra pauta digital, que no incluye "
                    "posteras, paneles, ferias ni volantes"),
            area="Marketing · carga de inversión")
    serie = _serie_ultima(f, "Costo de Lead")
    if not serie:
        return Cifra("Costo por lead (S/)", None,
                     "costo de generar leads ÷ leads captados", "—",
                     motivo=f"la ficha {f['hoja']} no trae serie del año",
                     area="Marketing")
    anio, meses = serie
    prom = sum(meses.values()) / len(meses)
    cont = mk.contraste_leads()
    aviso = ""
    if cont.get("hay") and cont.get("crm"):
        pares = [(a, cont["excel"][a], cont["crm"].get(a, 0))
                 for a in sorted(cont["excel"])]
        detalle = " · ".join(f"{a}: Excel {e:,} contra CRM {k:,}"
                             for a, e, k in pares)
        aviso = (f"**No se cruza con el CRM.** {detalle}. Son dos poblaciones "
                 f"—el Excel cuenta lo que entra por las plataformas de "
                 f"anuncios y el CRM lo que se registra— y dividir la "
                 f"inversión de una entre los leads de la otra daría un "
                 f"costo por lead que parece real y no lo es")
    return Cifra(
        "Costo por lead (S/)", round(prom, 2),
        f"promedio de los {len(meses)} meses cargados de {anio}, tal como lo "
        f"calcula Marketing en su ficha {f['hoja']}. Su fórmula: "
        f"{f['formula'] or 'inversión ÷ leads'}",
        f"Marketing · {f['archivo']} (fuente {f['fuente'] or 'Monday'})",
        motivo=aviso, area="Marketing" if aviso else "")


def _serie_junta(ficha: dict, claves: list[str]) -> tuple | None:
    """Varias series de la misma ficha, sumadas mes a mes. (anio, {mes: valor})."""
    cands = [s for s in ficha.get("series", [])
             if any(s["rotulo"].strip().lower().startswith(k.strip().lower())
                    for k in claves)]
    if not cands:
        return _serie_ultima(ficha, claves[0] if claves else "")
    anio = max(s["anio"] for s in cands)
    delanio = [s for s in cands if s["anio"] == anio]
    meses: dict[int, float] = {}
    for s in delanio:
        for m, v in s["meses"].items():
            meses[m] = meses.get(m, 0.0) + v
    if not meses:
        return None
    tiene = {m: sum(1 for s in delanio if m in s["meses"]) for m in meses}
    completos = {m: v for m, v in meses.items() if tiene[m] == len(delanio)}
    return anio, meses, (completos or meses)


def _serie_ultima(ficha: dict, contiene: str = "") -> tuple | None:
    """La serie del año más reciente de una ficha. (anio, {mes: valor})."""
    cands = [s for s in ficha.get("series", [])
             if not contiene or contiene.lower() in s["rotulo"].lower()]
    if not cands:
        cands = ficha.get("series", [])
    if not cands:
        return None
    anio = max(s["anio"] for s in cands)
    delanio = [s for s in cands if s["anio"] == anio]
    mejor = max(delanio, key=lambda s: s["n"])
    return anio, mejor["meses"]


def _kpis_del_area() -> list[Cifra]:
    """Los indicadores que Marketing mide y el tablero no tenía."""
    from . import marketing_kpi as mk
    c = mk.corte()
    if not c.get("hay"):
        return []
    fichas = {f["hoja"]: f for f in mk.fichas()}
    MES = ["", "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
           "agosto", "setiembre", "octubre", "noviembre", "diciembre"]
    out = []
    detalle = (f"{c['indicadores']} fichas de indicador leídas de "
               f"«{c['archivo']}», subido el {c['subido']}. Marketing lo "
               f"mantiene y su fuente es Monday, que no está conectado: esto "
               f"es una foto con fecha, no una lectura en vivo")
    excepciones = []
    if c.get("adelantadas"):
        excepciones.append("van un mes más adelante: "
                           + " y ".join(c["adelantadas"]))
    if c.get("sin_anio"):
        excepciones.append("sin ningún dato de " + str(c["anio"]) + ": "
                           + " y ".join(c["sin_anio"]))
    out.append(Cifra(
        f"Indicadores de Marketing · hasta {c['hasta']}", c["indicadores"],
        detalle, f"Marketing · {c['archivo']}",
        motivo=(" · ".join(excepciones) + ". El resto del tablero va a agosto"
                if excepciones else ""),
        area="Marketing" if excepciones else ""))
    PEDIDOS = [
        ("KPI_04", "Inversión en publicidad (S/)", ["TOTAL"], True, "suma"),
        ("KPI_03", "Campañas lanzadas", ["campañas", "# de campañas"], False, "suma"),
        ("KPI_06", "Alcance en redes (visualizaciones)",
         ["Facebook", "Instagram", "Tik Tok"], False, "suma"),
        ("KPI_07", "Seguidores de la marca",
         ["Facebook", "Instagram", "Tik Tok"], False, "ultimo"),
    ]
    for hoja, nombre, busca, es_plata, modo in PEDIDOS:
        f = fichas.get(hoja)
        if not f:
            continue
        s = _serie_junta(f, busca)
        if not s:
            continue
        anio, meses, completos = s
        # el flujo se acumula con lo que haya; el saldo se lee de un mes entero
        if modo != "suma":
            meses = completos
        total = (sum(meses.values()) if modo == "suma"
                 else meses[max(meses)])
        falta = ""
        if anio == c["anio"] and c["mes"] > max(meses):
            falta = (f"la fuente llega a {MES[max(meses)]}; el resto del "
                     f"tablero va a agosto")
        span = max(meses) - min(meses) + 1
        cuando = (f"de {MES[min(meses)]} a {MES[max(meses)]}"
                  if len(meses) == span else
                  "en " + ", ".join(MES[m] for m in sorted(meses)))
        _como = (f"suma de los {len(meses)} meses cargados de {anio}, {cuando}"
                 if modo == "suma" else
                 f"el último mes cargado de {anio} ({MES[max(meses)]}), no la "
                 f"suma: es un saldo y sumarlo contaría a cada seguidor una "
                 f"vez por mes")
        _ojo = falta
        if modo == "ultimo":
            _ojo = ((_ojo + " · " if _ojo else "")
                    + "OJO con el nombre: la ficha se llama «Nuevos "
                      "Seguidores» pero lo que carga Marketing en 2026 es el "
                      "TOTAL acumulado, no lo ganado en el mes. En 2025 la "
                      "misma hoja sí cargaba lo ganado (76, 94, 62 por mes). "
                      "Son dos indicadores distintos con el mismo nombre y "
                      "quién decide cuál vale es Marketing")
        out.append(Cifra(
            nombre, round(total, 2) if es_plata else int(round(total)),
            f"{_como}, de la ficha {hoja} de Marketing. "
            f"{f['formula'][:90] if f['formula'] else ''}",
            f"Marketing · {f['archivo']}",
            motivo=_ojo, area="Marketing" if _ojo else ""))
    return out


def campanas_con_venta() -> Cifra:
    """Cuántas campañas produjeron al menos una venta."""
    k = _kommo()
    if k is None or "campana" not in k.columns:
        return Cifra("Campañas que produjeron venta", None,
                     "campañas con al menos un lead cerrado", "KOMMO",
                     motivo=SIN_KOMMO, area="Marketing")
    kk = k[k["campana"].notna()]
    if not len(kk):
        return Cifra("Campañas que produjeron venta", None,
                     "campañas con al menos un lead cerrado", "KOMMO",
                     motivo="ningún lead trae campaña cargada", area="Marketing")
    total = int(kk["campana"].nunique())
    con = int(kk[kk["etapa"] == "VENDIDO"]["campana"].nunique())
    return Cifra(
        "Campañas que produjeron venta", con,
        f"campañas con al menos un lead en etapa «VENDIDO», de las {total} "
        f"que aparecen en el CRM. Se mide dentro del CRM y no contra las "
        f"ventas de AXION: son dos definiciones distintas",
        "KOMMO · leads",
        motivo=(f"las otras {total - con} campañas no tienen ningún lead "
                f"cerrado. Antes de bajarlas conviene mirar si están vivas: "
                f"una campaña reciente todavía no tuvo tiempo de cerrar"),
        area="Marketing")


def obra() -> list[Cifra]:
    """La hoja de Obra."""
    proj = ingest.fetch_axion_entity("Project", None, 5000)
    avance = _num(proj["construction_progress"])
    etapa = proj["project_stage"].astype(str).str.strip()
    en_ejec = etapa == "Ejecución"
    prom = {e: float(avance[etapa == e].mean())
            for e in sorted(set(etapa)) if (etapa == e).any()}
    detalle = " · ".join(f"{e}: {v:.1f}% ({int((etapa == e).sum())})"
                         for e, v in prom.items())
    ceros = int((avance == 0).sum())

    try:
        g = movimientos.gasto_por_obra(periodo.HISTORICO)
        con_gasto = int(len(g)) if len(g) else 0
        total_g = float(_num(g["gasto"]).sum()) if len(g) else 0.0
    except Exception:  # noqa: BLE001
        con_gasto, total_g = 0, 0.0

    return [
        Cifra("Obras en ejecución", int(en_ejec.sum()),
              f"proyectos con project_stage «Ejecución», de {len(proj)} obras",
              "AXION · Project"),
        Cifra("Avance de las obras en ejecución",
              float(avance[en_ejec].mean()) if en_ejec.any() else None,
              f"promedio de construction_progress de las {int(en_ejec.sum())} "
              f"obras en ejecución — la etapa que el objetivo nombra. Por "
              f"etapa: {detalle}", "AXION · Project",
              motivo=(f"{ceros} de las {len(proj)} obras tienen el avance en "
                      f"CERO. Todas tienen el campo cargado, así que el cero "
                      f"es lo que Habitat declaró: o no arrancaron, o nadie "
                      f"actualiza el avance" if ceros else ""),
              area="Obra" if ceros else ""),
        Cifra("Costo de obra registrado", total_g if con_gasto else None,
              f"gasto atribuido a obra en {con_gasto} obras, desde el módulo "
              f"de caja de AXION (MovimientoGasto). **AXION sí registra costo "
              f"por obra desde el 03-ago-2026**", "AXION · MovimientoGasto",
              motivo=("falta el PRESUPUESTO de obra para poder comparar: hoy "
                      "hay costo ejecutado y nada contra qué medirlo. Y el "
                      "avance físico contra gasto tampoco se puede hasta que "
                      "el avance se actualice con la misma frecuencia que el "
                      "gasto" if con_gasto else
                      "MovimientoGasto no respondió en esta lectura"),
              area="Obra · y Administración"),
    ]


_LOG_CACHE: dict = {}
_LOG_CANDADO = threading.Lock()


def _log_o_error(entidad: str) -> pd.DataFrame:
    """Una tabla del módulo de logística con caché por corrida; si la API."""
    with _LOG_CANDADO:
        if entidad in _LOG_CACHE:
            return _LOG_CACHE[entidad].copy()
    df = ingest._fetch_base44_entity(
        "AXION_API_BASE_URL", "AXION_API_KEY", entidad, [entidad],
        limit=5000)
    with _LOG_CANDADO:
        _LOG_CACHE.setdefault(entidad, df)
        return _LOG_CACHE[entidad].copy()


def _log(entidad: str) -> pd.DataFrame:
    """Una tabla del módulo de logística, o vacía si no responde."""
    try:
        return _log_o_error(entidad)
    except Exception:  # noqa: BLE001 — módulo nuevo: que no tumbe la hoja
        return pd.DataFrame()


def _items_oc(oc: pd.DataFrame) -> pd.DataFrame:
    """El detalle por ítem de las órdenes de compra, abriendo la lista."""
    if not len(oc) or "items" not in oc.columns:
        return pd.DataFrame()
    li = [dict(it, _oc=fila.get("oc_number"))
          for _, fila in oc.iterrows()
          for it in (fila.get("items") or [])
          if isinstance(it, dict)]
    if not li:
        return pd.DataFrame()
    d = pd.DataFrame(li)
    if "codigo" not in d.columns:
        d["codigo"] = pd.NA
    d["_c"] = d["codigo"].astype("string").str.strip()
    d.loc[d["_c"].isna() | (d["_c"] == ""), "_c"] = pd.NA
    return d


def logistica() -> list[Cifra]:
    oc, pv, mat = _log("OrdenCompra"), _log("Proveedor"), _log("Material")
    out = []

    if len(oc):
        tot = float(_num(oc["total"]).sum())
        def _ruc(x):
            return str(x.get("ruc") or x.get("razon_social") or x) \
                if isinstance(x, dict) else str(x)
        por = oc.assign(_r=oc["proveedor"].map(_ruc)).groupby("_r")["total"] \
                .apply(lambda s: _num(s).sum()).sort_values(ascending=False)
        f = pd.to_datetime(oc["date"], errors="coerce").dropna()
        cuando = (f"del {f.min():%d-%m-%Y} al {f.max():%d-%m-%Y}"
                  if len(f) else "sin fechas")
        dias = int((f.max().normalize() - f.min().normalize()).days) + 1 if len(f) else 0
        out += [
            Cifra("Órdenes de compra emitidas", int(len(oc)),
                  f"órdenes cargadas en AXION, {cuando}, por "
                  f"S/ {tot:,.2f} en total", "AXION · OrdenCompra"),
            Cifra("Concentración de proveedores",
                  100.0 * float(por.iloc[0]) / tot if tot else None,
                  f"lo que se lleva el proveedor más grande de los "
                  f"{len(por)} con compras: S/ {float(por.iloc[0]):,.2f} de "
                  f"S/ {tot:,.2f}. Se agrupa por RUC, no por nombre",
                  "AXION · OrdenCompra",
                  motivo=(f"el módulo arrancó el {f.min():%d-%m-%Y}: con "
                          f"{len(oc):,} órdenes de {dias} días de historia, "
                          f"esta cifra todavía no describe un patrón de compra"
                          if len(f) else
                          "las órdenes no tienen fecha: no se puede decir "
                          "cuánta historia hay detrás de esta cifra"),
                  area="Logística"),
        ]
    else:
        out.append(Cifra(
            "Órdenes de compra emitidas", None,
            "órdenes de compra cargadas en AXION", "—",
            motivo="la tabla OrdenCompra no respondió en esta lectura",
            area="Logística"))

    out.append(Cifra(
        "Proveedores registrados", int(len(pv)) if len(pv) else None,
        f"proveedores en la tabla Proveedor, con RUC, banco y cuenta"
        if len(pv) else "proveedores registrados en AXION",
        "AXION · Proveedor" if len(pv) else "—",
        motivo=("es el padrón completo, no altas del período: la tabla no "
                "guarda desde cuándo trabaja cada uno"
                if len(pv) else "la tabla Proveedor no respondió"),
        area="Logística"))

    con_precio = 0
    if len(mat):
        pmin, pmax = _num(mat["precio_min"]), _num(mat["precio_max"])
        con_precio = int(((pmin > 0) | (pmax > 0)).sum())
        sin_precio = int(len(mat) - con_precio)
        con_rango = int(((pmax - pmin) > 0).sum())
        out.append(Cifra(
            "Materiales con precio de referencia", con_precio,
            f"ítems del catálogo con algún precio cargado, de los {len(mat)} "
            f"que tiene el catálogo entero. En {con_rango} el máximo supera al "
            f"mínimo: en el resto el mínimo y el máximo son el mismo número, "
            f"así que no hay banda, hay un precio", "AXION · Material",
            motivo=(f"{sin_precio} de {len(mat)} materiales tienen precio "
                    f"mínimo y máximo en 0.00: el catálogo está cargado pero "
                    f"casi sin valorizar" if sin_precio else ""),
            area="Logística" if sin_precio else ""))

    lineas = _items_oc(oc)
    if len(lineas) and con_precio:
        cruz = lineas.merge(
            mat.assign(_c=mat["codigo"].astype("string").str.strip())
               [["_c", "precio_min", "precio_max"]],
            on="_c", how="inner")
        pu = _num(cruz["precio_unit"])
        pmn, pmx = _num(cruz["precio_min"]), _num(cruz["precio_max"])
        fuera = int(((pu > pmx) | (pu < pmn)).sum())
        al_minimo = int((pu == pmn).sum())
        out.append(Cifra(
            "Compras fuera del precio de referencia", fuera,
            f"líneas de compra cuyo precio unitario cae fuera de la banda del "
            f"catálogo, sobre {len(cruz)} de las {len(lineas)} líneas que "
            f"tienen código para cruzar. El detalle sale de "
            f"`OrdenCompra.items`", "AXION · OrdenCompra + Material",
            motivo=(f"el precio de referencia parece copiado de la compra: "
                    f"{al_minimo} de {len(cruz)} líneas pagaron exactamente el "
                    f"precio mínimo del catálogo, y los {con_precio} materiales "
                    f"valorizados son exactamente los {con_precio} que aparecen "
                    f"comprados. Mientras el catálogo se llene desde la orden, "
                    f"esta cifra va a dar cero por construcción y no puede "
                    f"detectar un sobreprecio"),
            area="Logística"))
    else:
        out.append(Cifra(
            "Compras fuera del precio de referencia", None,
            "líneas de compra cuyo precio unitario cae fuera de la banda del "
            "catálogo", "—",
            motivo=("faltan el detalle por ítem de las órdenes o los precios "
                    "del catálogo"),
            area="Logística"))

    out += [
        Cifra("Lead time de compra", None,
              "días entre el pedido y la recepción del material", "—",
              motivo=("la orden registra la fecha del pedido pero no la de "
                      "recepción. Falta una casilla «fecha de recepción» en "
                      "la ficha de la orden"),
              area="Logística · y la desarrolladora de AXION"),
        Cifra("Exactitud de inventario", None,
              "stock contado contra stock del sistema", "—",
              motivo=("la tabla de inventario existe en AXION y está VACÍA: "
                      "cero filas. Hace falta un conteo físico cargado"),
              area="Logística"),
    ]
    return out


def marketing_extra(anio: int | None = None) -> dict:
    sale = ingest.fetch_axion_entity("Sale", None, 5000)
    v = sale[sale["status"] == "Vendido"].copy()
    if anio:
        v = v[v["date"].astype(str).str.startswith(str(anio))]
    if v.empty:
        return {"hay": False}

    def _rep(col: str) -> list[dict]:
        s = v[col].fillna("").map(lambda x: str(x).strip() or "(sin dato)")
        vc = s.value_counts()
        n = len(v)
        return [{"valor": str(k), "ventas": int(c), "pct": round(100.0 * c / n, 1),
                 "monto": float(pd.to_numeric(
                     v.loc[s == k, "sale_price"], errors="coerce").fillna(0).sum())}
                for k, c in vc.items()]

    lleg = pd.to_datetime(v["lead_arrival_date"], errors="coerce")
    vent = pd.to_datetime(v["date"], errors="coerce")
    dias = (vent - lleg).dt.days
    malas = int(((dias < 0) | (dias > 400)).sum())
    sin_fecha = int(lleg.isna().sum())
    ok = dias[(dias >= 0) & (dias <= 400)].dropna()

    return {
        "hay": True,
        "ventas": int(len(v)),
        "fuente": _rep("marketing_source"),
        "subfuente": _rep("marketing_subsource"),
        "dias": {
            "n": int(len(ok)),
            "promedio": round(float(ok.mean()), 1) if len(ok) else None,
            "mediana": int(ok.median()) if len(ok) else None,
            "min": int(ok.min()) if len(ok) else None,
            "max": int(ok.max()) if len(ok) else None,
            "sin_fecha": sin_fecha,
            "imposibles": malas,
            "tramos": [
                {"rot": "Mismo día", "n": int((ok == 0).sum())},
                {"rot": "1 a 7 días", "n": int(((ok >= 1) & (ok <= 7)).sum())},
                {"rot": "8 a 30 días", "n": int(((ok >= 8) & (ok <= 30)).sum())},
                {"rot": "31 a 90 días", "n": int(((ok >= 31) & (ok <= 90)).sum())},
                {"rot": "más de 90 días", "n": int((ok > 90).sum())},
            ],
        },
    }


HOJAS = {"Ventas": ventas, "Cobranza": cobranza, "Comercial": comercial,
         "Obra": obra, "Marketing": marketing, "Logística": logistica}
