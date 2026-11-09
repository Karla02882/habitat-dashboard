"""HOJA 2 · SCORECARD."""
from __future__ import annotations

import copy
from dataclasses import dataclass, field

import pandas as pd

from . import ingest, periodo


@dataclass
class Indicador:
    perspectiva: str
    objetivo: str
    indicador: str
    meta: float | None
    unidad: str
    valor: float | None = None
    formula: str = ""
    alcance: str = ""
    motivo: str = ""            # por qué no se puede calcular
    area: str = ""              # quién puede destrabarlo
    area_bsc: str = "Otros"
    necesita: str = ""
    iniciativa: str = ""        # SIEMPRE en blanco: lo carga Habitat
    tipeado: dict = field(default_factory=dict)   # su monthly_values, al lado
    avisos: list[str] = field(default_factory=list)
    desglose: list[dict] = field(default_factory=list)
    propio: bool = False
    es_porcentaje: bool | None = None

    @property
    def estado(self) -> str:
        if self.valor is None:
            return "sin fuente"
        a = self.alcance.lower()
        return "parcial" if a.startswith("parcial") or "incompleto" in a \
            or "pero mide" in a else "calculado"

    @property
    def unidad_valor(self) -> str:
        """LA UNIDAD DE LA CIFRA, que no siempre es la del indicador."""
        if self.es_porcentaje is False and self.unidad in ("%", "índice"):
            return "N°"
        return self.unidad

    @property
    def unidad_no_cuadra(self) -> str:
        """La meta y la cifra tienen que medir lo mismo."""
        if self.valor is None:
            return ""
        _sin_meta = self.meta is None or (isinstance(self.meta, float)
                                          and self.meta != self.meta)
        _de = (f"este indicador está declarado en «{self.unidad}»"
               if _sin_meta else f"la meta está en «{self.unidad}»")
        if self.unidad in ("%", "índice") and float(self.valor) > 100:
            return (f"{_de}, y la cifra calculada es un conteo: no son "
                    f"comparables")
        if self.unidad in ("%", "índice") and self.es_porcentaje is False:
            return (f"{_de}, y lo que hoy se puede calcular es un conteo — por "
                    f"eso la cifra de arriba va sin el signo de porcentaje: "
                    f"son unidades, no puntos porcentuales")
        return ""


def _num(s) -> pd.Series:
    return pd.to_numeric(s, errors="coerce").fillna(0)


def _doc(s: pd.Series) -> pd.Series:
    """El DNI normalizado, y los vacíos como cadena vacía."""
    x = (s.astype(str).str.upper()
         .str.replace(r"[^0-9A-Z]", "", regex=True))
    return x.where(~x.isin(["NAN", "NONE", "NAT", ""]), "")


def _clientes(df: pd.DataFrame) -> int:
    """Clientes distintos POR DNI, no por nombre."""
    d = _doc(df["dni"])
    return int(d[d != ""].nunique())


def _nombres_por_doc(df: pd.DataFrame) -> dict[str, set]:
    """Los DNI cargados con más de un nombre. Es data de Habitat: se reporta."""
    t = df.assign(_d=_doc(df["dni"]))
    t = t[t["_d"] != ""]
    g = t.groupby("_d")["client"].apply(lambda s: set(map(str, s)))
    return {k: v for k, v in g.items() if len(v) > 1}


def _vacio(s: pd.Series) -> pd.Series:
    """True donde el campo está vacío de verdad."""
    return s.map(lambda x: not str(x).strip()
                 or str(x).strip().lower() == "nan").astype(bool)


def _unidades() -> pd.DataFrame:
    return ingest.fetch_axion_entity("Unit", None, 5000)


def _leads_negativos() -> int:
    try:
        from . import crm as _crm
        a = (_crm.hoja(None, periodo.ANIO) or {}).get("atencion") or {}
        return int(a.get("negativas") or 0)
    except Exception:  # noqa: BLE001
        return 0


_AREA_CANON = {
    "cobranzas": "Cobranza",
    "comercial": "Marketing y Comercial",
    "marketing": "Marketing y Comercial",
}


def _area_limpia(a: str | None) -> str:
    """El área, sin coletillas y con un solo nombre por área."""
    base = str(a or "").split("·")[0].strip()
    if not base:
        return ""
    return _AREA_CANON.get(base.lower(), base)


def _flujo_entradas(mes: int | None = None) -> dict:
    """El lado de las ENTRADAS del flujo: cronograma contra cobrado."""
    def _n(s):
        return pd.to_numeric(s, errors="coerce").fillna(0)

    try:
        _pa, _pm = periodo.partes(mes)
    except (TypeError, ValueError):
        _pa, _pm = periodo.ANIO, None
    mes = _pm if _pa == periodo.ANIO else None

    inst = ingest.fetch_axion_entity("Installment", None, 5000)
    pagos = ingest.fetch_axion_entity("CxCPayment", None, 5000)
    cred = ingest.fetch_axion_entity("Credit", None, 5000)
    hoy = pd.Timestamp.today().normalize()

    venc = pd.to_datetime(inst["fecha_vencimiento"], errors="coerce")
    dele = venc.dt.year.eq(periodo.ANIO)
    if mes:
        dele &= venc.dt.month.eq(mes)
    proy = float(_n(inst["monto_cuota"])[dele].sum())

    f_p = pd.to_datetime(pagos["fecha"], errors="coerce")
    del_anio = f_p.dt.year.eq(periodo.ANIO)
    if mes:
        del_anio &= f_p.dt.month.eq(mes)
    real = float(_n(pagos["monto"])[del_anio].sum())

    # cada pago con la cuota que salda, para no mezclar años
    venc_de = dict(zip(inst["id"], venc))
    p = pagos[del_anio].copy()
    p["_v"] = p["installment_id"].map(venc_de)
    _pv = pd.to_datetime(p["_v"], errors="coerce")
    dentro = _pv.dt.year.eq(periodo.ANIO)
    if mes:
        dentro &= _pv.dt.month.eq(mes)
    cobr_venc = float(_n(p["monto"])[dentro].sum())

    pend = inst["estado"].astype(str).str.lower() == "pendiente"
    falta = (_n(inst["monto_cuota"]) - _n(inst["monto_pagado"])).clip(lower=0)
    vencido_total = float(_n(inst["monto_cuota"])[dele & (venc < hoy)].sum())
    por_entrar = float(falta[pend & (venc >= hoy) & dele].sum())

    ini = 0.0
    for xs in cred.get("iniciales", pd.Series(dtype=object)):
        for x in (xs or []) if isinstance(xs, list) else []:
            f = str(x.get("fecha") or "")
            if f[:4] == str(periodo.ANIO) and (not mes or f[5:7] == f"{mes:02d}"):
                m = pd.to_numeric(x.get("monto"), errors="coerce")
                ini += 0.0 if pd.isna(m) else float(m)

    return {
        "proy": proy, "n_proy": int(dele.sum()),
        "real": real, "n_real": int(del_anio.sum()),
        "venc": vencido_total, "cobr_venc": cobr_venc,
        "cumpl": (100 * cobr_venc / vencido_total) if vencido_total else 0.0,
        "por_entrar": por_entrar,
        "n_por_entrar": int((pend & (venc >= hoy) & dele).sum()),
        "iniciales": ini,
    }


def _sin_cronograma() -> int:
    """Créditos sin ninguna cuota cargada en Installment."""
    try:
        cr = ingest.fetch_axion_entity("Credit", None, 5000)
        ins = ingest.fetch_axion_entity("Installment", None, 5000)
        return int((~cr["id"].isin(set(ins["credit_id"].dropna()))).sum())
    except Exception:  # noqa: BLE001
        return 0


def _motivo_costo() -> str:
    from . import areas, movimientos
    obras = ingest.fetch_axion_entity("Project", None, 5000)
    gt = movimientos.gasto_total(None)
    c = [x for x in areas.obra() if x.etiqueta == "Costo de obra registrado"]
    val = c[0].valor if c else None
    if val:
        return (f"el costo existe pero está incompleto: S/ {float(val):,.2f} "
                f"atribuidos a obra, que es el {gt['pct_atribuido']:.1f}% del "
                f"gasto del año (S/ {gt['monto']:,.2f}), repartido en "
                f"{gt['obras']} de las {len(obras)} obras declaradas. El resto "
                f"no lleva proyecto cargado en el movimiento. Sin el costo "
                f"completo por obra no hay margen que medir")
    return (f"no hay costo atribuido a ninguna obra: ninguno de los "
            f"{gt['filas']:,} movimientos de gasto lleva un proyecto que "
            f"empareje con una obra de AXION")


def _hueco_origen() -> str:
    """Cuántas ventas no declaran de dónde vino el cliente."""
    s = ingest.fetch_axion_entity("Sale", None, 5000)
    v = s[s["status"] == "Vendido"]
    va = periodo.recortar(v, "date", None)
    hoy_vac = int(_vacio(va["marketing_source"]).sum())
    viejas = int(_vacio(v["marketing_source"]).sum())
    if not len(va):
        return f"Hoy ese dato está vacío en {viejas} de {len(v)} ventas cerradas."
    if hoy_vac == 0:
        return (f"En {periodo.ANIO} ya está completo: las {len(va)} ventas del "
                f"año declaran su origen. Lo que falta es el histórico — "
                f"{viejas} ventas de {len(v)} sin origen, todas anteriores a "
                f"{periodo.ANIO}, y por eso cualquier cifra que cruce años es "
                f"un piso.")
    return (f"En {periodo.ANIO} está vacío en {hoy_vac} de {len(va)} ventas del "
            f"año ({viejas} de {len(v)} contando todos los años), así que el "
            f"porcentaje es un piso.")


def _mes(df: pd.DataFrame, col: str, mes) -> pd.DataFrame:
    """El Scorecard SIEMPRE mide el año, porque las metas son del año: acá."""
    return periodo.recortar(df, col, None if periodo.es_historico(mes) else mes)


NECESITA = {
    "% incremento ventas":
        "que cada venta quede registrada con su crédito y sus pagos al día. "
        "Con eso el tablero sabe cuánto de lo firmado ya entró a caja. Hoy 6 "
        "ventas no tienen crédito registrado y su cobro no se puede contar.",
    "N° de unidades vendidas":
        "nada adicional: se genera solo, con cada venta que Comercial "
        "registra. Solo hay que mantener las ventas al día.",
    "% de cobranza efectiva":
        "lo mismo que el de ventas: créditos y pagos al día. Cada pago que "
        "Cobranzas registre mueve este porcentaje.",
    "% de reducción de costos":
        "que carguen el presupuesto de verdad: cuánto planea gastar cada obra "
        "cada mes, ANTES de gastarlo. Lo que hoy figura como presupuesto son "
        "movimientos entre cuentas del banco, no un plan — por eso coincide "
        "con el gasto real al céntimo y no sirve para comparar.",
    "Flujo de caja real vs proyectado":
        "nada nuevo para lo que ya se ve: sale de los pagos y gastos que "
        "registran. Para que la PROYECCIÓN sea completa falta una casilla: la "
        "fecha estimada en que el banco desembolsa cada hipoteca. Hoy hay "
        "S/ 4.7 millones esperando desembolso sin fecha conocida.",
    "Morosidad de la cartera":
        "que todos los créditos tengan su cronograma de cuotas cargado. Hoy "
        "{SIN_CRONOGRAMA} créditos no lo tienen y su deuda no aparece en "
        "ningún vencimiento.",
    "% de recuperación de lo vencido":
        "cronogramas al día y pagos registrados apenas se cobran. Mide "
        "cuánto de lo que ya venció se logró cobrar.",
    "Saldo vencido a más de 90 días":
        "lo mismo: cronogramas y pagos al día. Es la deuda más vieja, la que "
        "primero hay que perseguir.",
    "Créditos sin cronograma cargado":
        "que Cobranzas cargue las cuotas de los {SIN_CRONOGRAMA} créditos que "
        "hoy no las tienen. La meta es cero —la cargó Habitat en AXION— y "
        "quiere decir: toda deuda con su fecha de cobro.",
    "N° de créditos hipotecarios":
        "confirmar con Administración si la meta de 3 es mensual o anual: el "
        "año ya lleva {VALOR} y contra 3 el indicador pierde sentido.",
    "Leads captados":
        "nada adicional: el CRM ya lo registra solo con cada interesado que "
        "escribe o llama.",
    "Tasa de conversión de lead a venta":
        "que los asesores muevan cada lead a su etapa final —vendido o "
        "desestimado— en el CRM. Un lead que se queda a medio camino no "
        "cuenta ni como ganado ni como perdido.",
    "Tiempo de atención al lead":
        "que la primera llamada quede registrada en el CRM con su fecha "
        "real. Hoy {LEADS_NEGATIVOS} leads tienen la llamada anotada antes de "
        "que el lead existiera, y quedan fuera del cálculo.",
    "% incremento de clientes nuevos":
        "que AXION registre la fecha de alta de cada cliente. Sin ella no se "
        "distingue un cliente nuevo de uno recurrente.",
    "% ventas por referidos":
        "que al registrar cada venta se llene de dónde vino el cliente. "
        "{ORIGEN_HUECO}",
    "Órdenes de compra emitidas":
        "nada adicional: cada orden que Logística emita en AXION cuenta "
        "sola. El módulo arrancó el 4 de agosto.",
    "Concentración de proveedores":
        "que toda compra pase por una orden en AXION, con su proveedor. "
        "Mientras se compre por fuera, este porcentaje mira solo una parte.",
    "N° de proveedores nuevos":
        "registrar cada proveedor nuevo en AXION al primer trato.",
    "Lead time de compra":
        "que cada orden registre dos fechas: cuándo se pidió y cuándo llegó. "
        "Hoy la recepción no se registra.",
    "Exactitud de inventario":
        "un inventario físico contado y cargado en AXION para comparar "
        "contra lo que el sistema cree que hay. Hoy el inventario está "
        "vacío.",
    "Avance físico vs gasto ejecutado":
        "el presupuesto de cada obra. Los dos datos sueltos ya están —el "
        "avance físico lo carga Obra y el gasto sale del registro de "
        "movimientos— pero uno es un porcentaje y el otro son soles: sin el "
        "presupuesto no hay forma de ponerlos en la misma escala.",
    "Costo por m² ejecutado":
        "el gasto de años anteriores, o el presupuesto por obra. La cifra ya "
        "se calcula, pero solo con el gasto de este año: las obras que se "
        "construyeron antes de que existiera el registro salen baratísimas y "
        "no es que lo sean. También ayuda que cada movimiento lleve su obra: "
        "hoy la mayoría no la lleva.",
    "Avance promedio de obra":
        "que Obra actualice el porcentaje de avance de cada proyecto en "
        "AXION. Es un dato que se escribe a mano: vale lo que valga esa "
        "actualización.",
    "Cumplimiento cronograma":
        "cargar el cronograma de cada obra en algún sistema: fechas "
        "planeadas contra fechas reales. Hoy no existe en ninguno.",
    "N° de incidencias":
        "un registro de incidencias de obra. Hoy no existe: hay que crear "
        "el módulo o llevarlo en el cuaderno de obra digital.",
    "Rentabilidad por obra":
        "tres cosas: los costos de cada obra completos, la regla del margen "
        "que defina Gerencia (¿contratado o cobrado contra el costo?), y "
        "aprobar los nombres de obra que hoy no emparejan.",
    "Rentabilidad por razón social":
        "lo mismo que por obra, más completar la razón social de las 5 "
        "obras que no la tienen declarada.",
}


_YA: dict = {}


def limpiar_cache() -> None:
    """Olvida lo calculado. Para pruebas."""
    _YA.clear()


def construir(mes: int | None = None) -> list[Indicador]:
    clave = str(mes)
    if clave in _YA:
        return copy.deepcopy(_YA[clave])
    out = _construir(mes)
    _YA[clave] = copy.deepcopy(out)
    return out


def _construir(mes: int | None = None) -> list[Indicador]:
    kpi = ingest.fetch_axion_opcional(
        "KPI", ["indicator", "objective", "target", "unit", "category",
                "monthly_values", "kpi_type"])
    sale = ingest.fetch_axion_entity("Sale", None, 5000)
    prop = ingest.fetch_axion_entity("Property", None, 5000)
    cred = ingest.fetch_axion_entity("Credit", None, 5000)

    # SOLO `Vendido`. Separación y Devolución no son venta.
    vend_todo = sale[sale["status"] == "Vendido"]
    f_v = pd.to_datetime(vend_todo["date"], errors="coerce")
    viejas = vend_todo[~f_v.dt.year.eq(periodo.ANIO)]
    vend = _mes(vend_todo, "date", mes)
    vend_2026 = _mes(vend_todo, "date", None)
    n_sale = len(sale)

    def cerrar(ind: Indicador, valor, formula, alcance,
               pct: bool | None = None) -> Indicador:
        """`pct` declara si la cifra ES un porcentaje. Sin eso, el control de."""
        ind.valor, ind.formula, ind.alcance = valor, formula, alcance
        if pct is not None:
            ind.es_porcentaje = pct
        elif (ind.es_porcentaje is None and ind.unidad in ("%", "índice")
              and isinstance(valor, float) and 0 < valor < 100
              and abs(valor - round(valor)) > 1e-9):
            ind.es_porcentaje = True
        return ind

    salida: list[Indicador] = []
    if kpi.empty:
        return salida
    tiene_area = "area" in kpi.columns
    for _, r in kpi.sort_values(["category", "order"]).iterrows():
        nombre = str(r["indicator"]).strip()
        mv = r["monthly_values"] if isinstance(r["monthly_values"], dict) else {}
        ind = Indicador(
            perspectiva=str(r["category"]).strip(),
            objetivo=str(r["objective"]).strip(),
            indicador=nombre,
            meta=pd.to_numeric(r["target"], errors="coerce"),
            unidad=str(r["unit"]).strip(),
            tipeado={k: v for k, v in mv.items() if v},
        )
        ind.area_bsc = (str(r["area"]).strip() if tiene_area
                        and str(r.get("area") or "").strip() else "Otros")
        ind.necesita = (NECESITA.get(str(r["indicator"]).strip(), "")
                        .replace("{LEADS_NEGATIVOS}", f"{_leads_negativos():,}")
                        .replace("{SIN_CRONOGRAMA}", f"{_sin_cronograma():,}")
                        .replace("{ORIGEN_HUECO}", _hueco_origen()))

        n = nombre.lower()
        if n.startswith("n° de unidades vendidas"):
            cerrar(ind, len(vend),
                   "ventas marcadas como «Vendido», con fecha de 2026"
                   + (f", mes {mes}" if mes else " (acumulado del año)"),
                   f"completo: las {n_sale} ventas registradas traen su estado y su fecha")
            if len(viejas):
                ind.avisos.append(
                    f"AXION registra además {len(viejas)} ventas de años "
                    f"anteriores: quedan en Resultados (corte histórico), no "
                    f"acá, porque la meta es del año")
            ind.area = "Finanzas"
        elif n.startswith("% incremento ventas"):
            from . import estructura_ingreso as _ei
            e = _ei.calcular(mes)
            if e.get("hay"):
                cerrar(ind, e["entro"],
                       f"lo que REALMENTE entró a caja de las ventas del "
                       f"período: las cuotas iniciales cobradas más las cuotas pagadas. Lo "
                       f"firmado con crédito cargado fue S/ "
                       f"{e.get('base_comparable') or 0:,.2f} y de eso entró "
                       + (f"el {e['pct_entro']:.1f}%" if e['pct_entro'] is not None
                          else "una parte que no se puede medir: ninguna venta "
                               "del período tiene crédito cargado"),
                       (f"parcial: {e['sin_credito']} de {e['ventas']} ventas "
                        f"no tienen crédito registrado, así que su cobro no "
                        f"está contado — la cifra es un piso"
                        if e['sin_credito'] else
                        "completo: todas las ventas del período tienen su "
                        "crédito, y su cobro está contado"))
                ind.avisos.append(
                    f"La meta de S/ {ind.meta:,.0f} se mide contra la CAJA, no "
                    f"contra lo firmado. Firmado: S/ {e['contratado']:,.2f} · "
                    f"Entró: S/ {e['entro']:,.2f}. La diferencia está en "
                    f"hipotecas sin desembolsar y cuotas por vencer.")
            else:
                cerrar(ind, None, "lo que entró a caja de las ventas del "
                       "período", "sin ventas en el período")
            if len(viejas):
                ind.avisos.append(
                    f"AXION registra además {len(viejas)} ventas de años "
                    f"anteriores por "
                    f"S/ {float(_num(viejas['sale_price']).sum()):,.2f}: "
                    f"están en Resultados (corte histórico), no en esta cifra "
                    f"que se compara contra la meta 2026")
            ind.avisos.append(
                "El rótulo dice «%» y la meta viene en soles (16,000,000 S/.): "
                "la cifra que se muestra son soles, no un porcentaje. "
                "Confirmar el nombre con Habitat.")
            ind.area = "Finanzas"
        elif n.startswith("n° de captaciones"):
            cap = _mes(prop, "sale_date", mes) if mes else prop
            cerrar(ind, len(cap),
                   "cantidad de registros en Property (propiedades captadas)",
                   f"parcial: Property tiene {len(prop)} registros pero está "
                   f"marcada como no conectada para cifras "
                   f"(config/fuentes_ignoradas.json): sus precios contradicen "
                   f"a los de Unit, que tiene {len(_unidades())} unidades")
            ind.area = "Comercial"
            ind.avisos.append(
                "Property no tiene fecha de CAPTACIÓN propia: el acumulado "
                "es histórico (no se puede recortar a 2026) y el filtro de "
                "mes usa la fecha de venta de la propiedad, que es otra cosa")
        elif n.startswith("n° de créditos hipotecarios"):
            hip = vend[vend["modality"] == "Hipoteca"]
            _vac_p = int(_vacio(vend["modality"]).sum())
            _vac_t = int(_vacio(sale["modality"]).sum())
            cerrar(ind, len(hip),
                   f"ventas cuya modalidad de pago es «Hipoteca», entre las {len(vend)} "
                   f"cerradas del período",
                   (f"completo sobre las {len(vend)} ventas del período: todas "
                    f"declaran su modalidad"
                    if not _vac_p else
                    f"parcial: la modalidad de pago viene vacía en {_vac_p} de las "
                    f"{len(vend)} ventas del período"))
            if _vac_t and not _vac_p:
                ind.avisos.append(
                    f"AXION tiene {_vac_t} filas de venta sin modalidad "
                    f"cargada, de {n_sale} en total, pero ninguna es del "
                    f"período que mide esta cifra: son de años anteriores o "
                    f"de registros que no son venta cerrada. Por eso no la "
                    f"vuelven parcial.")
            ind.area = "Cobranzas"
            n_acum = int((vend_2026["modality"] == "Hipoteca").sum())
            if ind.meta is not None and n_acum > float(ind.meta):
                ind.avisos.append(
                    f"la meta dice {ind.meta:.0f} y el acumulado 2026 ya va "
                    f"en {n_acum}: confirmar con Habitat si la meta es "
                    f"mensual o si quedó desactualizada")
        elif "habitat concept" in n:
            ind.motivo = ("«Habitat Concept» no es ninguno de los 18 proyectos "
                          "declarados en Project ni aparece en Sale.project: no "
                          "hay con qué separar esas unidades del resto")
            ind.area = "Comercial"
        elif "reducción de costos" in n:
            from . import movimientos as _mv
            try:
                _c = _mv.crudo()
                _f = pd.to_datetime(_c["fecha"], errors="coerce")
                _ant = int(_f.dt.year.eq(periodo.ANIO - 1).sum())
                _act = int(_f.dt.year.eq(periodo.ANIO).sum())
                ind.motivo = (
                    f"una reducción se mide contra algo, y ese algo no existe "
                    f"todavía. El registro de movimientos arrancó este año: "
                    f"tiene {_act:,} movimientos de {periodo.ANIO} y solo "
                    f"{_ant} de {periodo.ANIO - 1}, así que no hay año "
                    f"anterior con el cual comparar. Y presupuesto tampoco: lo "
                    f"que figura cargado como tal son transferencias entre "
                    f"cuentas del grupo, no un plan de gasto. Con cualquiera "
                    f"de los dos —el cierre de un año completo, o el "
                    f"presupuesto por obra y por mes— este indicador se "
                    f"calcula solo")
            except Exception:  # noqa: BLE001
                ind.motivo = ("no hay contra qué comparar: ni año anterior "
                              "cerrado ni presupuesto cargado")
            ind.area = "Administración · cargar el presupuesto por obra y por mes"
            ind.avisos.append(
                "la meta dice 100%: reducir los costos en 100% es tener "
                "costo cero. Confirmar el número con Habitat")
        elif "rentabilidad" in n:
            ind.motivo = _motivo_costo()
            ind.area = "Gerencia · carga de costos en AXION"
        elif "flujo de caja" in n:
            e = _flujo_entradas(mes)
            cerrar(ind, e["real"],
                   f"lo cobrado de cuotas en {periodo.ANIO} — "
                   f"S/ {e['real']:,.2f} en {e['n_real']} pagos — contra el "
                   f"cronograma del año: S/ {e['proy']:,.2f} en {e['n_proy']} "
                   f"cuotas",
                   "parcial: es SOLO el lado de las entradas. Las salidas no "
                   "tienen proyección: ninguna tabla de AXION guarda "
                   "presupuesto, así que la mitad del flujo no se puede "
                   "comparar")
            _MES = ["", "enero", "febrero", "marzo", "abril", "mayo", "junio",
                    "julio", "agosto", "setiembre", "octubre", "noviembre",
                    "diciembre"]
            try:
                _pa2, _m = periodo.partes(mes)
                if _pa2 != periodo.ANIO:
                    _m = None
            except (TypeError, ValueError):
                _m = None
            _rot = f"en {_MES[_m]}" if _m else "en el año"
            _av = (f"De lo que YA venció {_rot} se cobró el "
                   f"{e['cumpl']:.2f}% — S/ {e['cobr_venc']:,.2f} de "
                   f"S/ {e['venc']:,.2f}, emparejando cada pago con la cuota "
                   f"que salda.")
            if e["por_entrar"] > 0:
                _av += (f" Quedan por entrar S/ {e['por_entrar']:,.2f} en "
                        f"{e['n_por_entrar']} cuotas con vencimiento futuro.")
            if e["iniciales"] > 0:
                _av += (f" Aparte, y sin proyección enfrente porque no son "
                        f"cuotas: cuotas iniciales cobradas {_rot} por "
                        f"S/ {e['iniciales']:,.2f}.")
            ind.avisos.append(_av)
            ind.necesita = (
                "el presupuesto de gasto por obra y por mes, que hoy no existe "
                "en ninguna tabla de AXION. Las ENTRADAS ya están completas: "
                "el cronograma de cuotas está cargado y es contra lo que se "
                "compara arriba.")
            ind.area = "Finanzas"
        elif "clientes nuevos" in n:
            cerrar(ind, _clientes(vend),
                   f"clientes distintos —contados por DNI— con al menos una "
                   f"venta cerrada en {periodo.ANIO}",
                   f"completo para contar, incompleto para «nuevos»: no hay "
                   f"fecha de alta de cliente, así que no se distingue nuevo "
                   f"de recurrente sin fijar un período de corte",
                   pct=False)
            ind.area = "Comercial"
        elif "referidos" in n:
            ref = vend[vend["marketing_subsource"].astype(str).str.strip()
                       == "Referido"]
            vac_anio = int(_vacio(vend["marketing_subsource"]).sum())
            pct_ref = (100 * len(ref) / len(vend)) if len(vend) else None
            cerrar(ind, pct_ref,
                   f"{len(ref)} de las {len(vend)} ventas cerradas del período "
                   f"tienen origen «Referido» — numerador y denominador salen "
                   f"de la misma población",
                   (f"parcial: {vac_anio} de {len(vend)} ventas del período no "
                    f"declaran subcanal, así que el porcentaje es un piso"
                    if vac_anio else
                    f"completo sobre las {len(vend)} ventas del período: todas "
                    f"declaran su subcanal"))
            ind.area = "Marketing"
        elif "retención de clientes" in n:
            d_ = _doc(vend_todo["dni"])
            veces = d_[d_ != ""].value_counts()
            sin_dni = int((d_ == "").sum())
            cerrar(ind, int((veces > 1).sum()),
                   "clientes con más de una venta cerrada, de TODOS los años, "
                   "contados por DNI (la recompra cruza años a propósito)",
                   f"completo sobre las {len(vend_todo)} ventas cerradas"
                   + (f" menos {sin_dni} sin DNI" if sin_dni else "")
                   + ", pero mide recompra, no retención: sin postventa ni "
                     "contratos renovables no hay a qué llamarle retención",
                   pct=False)
            mezcla = _nombres_por_doc(vend_todo)
            if mezcla:
                ej = " · ".join(f"{k}: " + " / ".join(sorted(vs)[:3])
                                for k, vs in list(mezcla.items())[:3])
                ind.avisos.append(
                    f"{len(mezcla)} DNI están cargados con más de un nombre, "
                    f"así que el mismo comprador figura como varias personas: "
                    f"{ej}. Contado por nombre, la recompra salía a la mitad. "
                    f"Lo revisa Comercial")
            ind.area = "Comercial"
        elif "reclamos" in n:
            ind.motivo = ("no hay tabla de reclamos en AXION. Gerencia pidió "
                          "explícitamente que los reclamos entren al tablero: "
                          "hay que crear el módulo")
            ind.area = "Gerencia · módulo por crear"
        elif "visibilidad de marca" in n:
            ind.motivo = ("no hay data de alcance ni de audiencia. "
                          + _hueco_origen() + " Y Lead está en cero")
            ind.area = "Marketing"
        elif "cobranza efectiva" in n:
            from . import estructura_ingreso as _ei
            e = _ei.calcular(mes)
            if e.get("hay"):
                base = e.get("base_comparable") or 0
                cerrar(ind, e["pct_entro"],
                       f"de los S/ {base:,.2f} firmados CON crédito cargado "
                       f"entraron S/ {e['entro']:,.2f}",
                       (f"parcial: {e['sin_credito']} de {e['ventas']} ventas "
                        f"no tienen crédito en AXION (S/ "
                        f"{e['monto_sin_credito']:,.2f}) y quedan fuera de los "
                        f"dos lados de la división — no se sabe si cobraron"
                        if e["sin_credito"] else
                        "completo: las ventas del período tienen crédito cargado"))
            ind.area = "Cobranza"
        elif "morosidad de la cartera" in n or "recuperación de lo vencido" in n:
            inst = ingest.fetch_axion_entity("Installment", None, 5000)
            cr_ = ingest.fetch_axion_entity("Credit", None, 5000)
            _vivos = (set(cr_.loc[~cr_["estado"].astype(str).str.lower()
                                  .eq("cancelado"), "id"])
                      if "estado" in cr_.columns else set(cr_["id"]))
            _viva = inst["credit_id"].isin(_vivos)
            venc_ = pd.to_datetime(inst["fecha_vencimiento"], errors="coerce")
            falta_ = (_num(inst["monto_cuota"])
                      - _num(inst["monto_pagado"])).clip(lower=0)
            pend_ = falta_.gt(0) & _viva
            ayer_ = pd.Timestamp.today().normalize()
            vencido = float(falta_[pend_ & (venc_ < ayer_)].sum())
            cartera = float(_num(cr_.loc[cr_["id"].isin(_vivos),
                                          "saldo_pendiente"]).sum())
            if "morosidad" in n:
                cerrar(ind, 100 * vencido / cartera if cartera else None,
                       f"S/ {vencido:,.2f} vencido sobre S/ {cartera:,.2f} de "
                       f"cartera total",
                       "completo: sale de las cuotas y los créditos de AXION")
            else:
                ya_ = (venc_ < ayer_) & _viva
                total_v = float(_num(inst.loc[ya_, "monto_cuota"]).sum())
                cob = float(_num(inst.loc[ya_, "monto_pagado"]).sum())
                cerrar(ind, 100 * cob / total_v if total_v else None,
                       f"de S/ {total_v:,.2f} que ya vencieron se cobraron "
                       f"S/ {cob:,.2f} — sumando lo que se pagó en cada cuota, no restando saldos",
                       "completo sobre las cuotas con cronograma de créditos "
                       "VIVOS — la misma cartera que Resultados y Cobranza; los cancelados y los que ya no existen quedan fuera")
            ind.area = "Cobranza"
        elif "sin cronograma cargado" in n:
            inst = ingest.fetch_axion_entity("Installment", None, 5000)
            cr_ = ingest.fetch_axion_entity("Credit", None, 5000)
            sin_ = cr_[~cr_["id"].isin(set(inst["credit_id"]))]
            _canc = sin_["estado"].astype(str).str.strip().str.lower().eq("cancelado") \
                if "estado" in sin_.columns else pd.Series(False, index=sin_.index)
            _saldo = _num(sin_["saldo_pendiente"])
            vivos = sin_[~_canc & _saldo.gt(0)]
            cerrar(ind, int(len(vivos)),
                   f"créditos ACTIVOS y con saldo que no tienen ninguna cuota "
                   f"cargada · su deuda de "
                   f"S/ {float(_num(vivos['saldo_pendiente']).sum()):,.2f} no "
                   f"aparece en ningún vencimiento, así que no se puede cobrar "
                   f"a fecha",
                   "completo: se cuentan los créditos sin ninguna cuota cargada, "
                   "descontando los cancelados")
            _fuera = int(len(sin_) - len(vivos))
            if _fuera:
                ind.avisos.append(
                    f"Sin cronograma hay {len(sin_)} créditos en total, pero "
                    f"{_fuera} están cancelados y con saldo S/ 0.00: a una "
                    f"deuda ya saldada no le falta fecha de cobro. La cifra de "
                    f"arriba cuenta solo los {len(vivos)} que siguen debiendo, "
                    f"que son los que Cobranzas puede accionar.")
            ind.area = "Cobranza"
        elif "vencido a más de 90" in n:
            inst = ingest.fetch_axion_entity("Installment", None, 5000)
            _cr90 = ingest.fetch_axion_entity("Credit", None, 5000)
            _vivos90 = (set(_cr90.loc[~_cr90["estado"].astype(str).str.lower()
                                      .eq("cancelado"), "id"])
                        if "estado" in _cr90.columns else set(_cr90["id"]))
            venc_ = pd.to_datetime(inst["fecha_vencimiento"], errors="coerce")
            falta_ = (_num(inst["monto_cuota"])
                      - _num(inst["monto_pagado"])).clip(lower=0)
            pend_ = falta_.gt(0) & inst["credit_id"].isin(_vivos90)
            corte = pd.Timestamp.today().normalize() - pd.Timedelta(days=90)
            cerrar(ind,
                   float(falta_[pend_ & (venc_ < corte) & falta_.gt(0)].sum()),
                   "cuotas pendientes vencidas hace más de 90 días, restando "
                   "lo ya pagado",
                   "completo sobre las cuotas con cronograma de créditos VIVOS — la misma cartera que Resultados y Cobranza")
            ind.area = "Cobranza"
        elif "leads captados" in n or "conversión de lead" in n \
                or "atención al lead" in n:
            try:
                from . import crm as _crm
                _pm3 = periodo.partes(mes)[1] if periodo.partes(mes)[0] == periodo.ANIO else None
                h_ = _crm.hoja(_pm3 if isinstance(_pm3, int) else None,
                               periodo.ANIO)
                a_ = h_.get("atencion") or {}
                if "leads captados" in n:
                    cerrar(ind, a_.get("leads"),
                           "leads creados en el embudo «Ventas - Habitat "
                           "Inmobiliaria» del CRM",
                           "completo: el CRM registra todos los leads")
                elif "conversión" in n:
                    et = {x["valor"]: x["leads"] for x in (h_.get("etapas") or [])}
                    v_ = et.get("VENDIDO", 0)
                    t_ = a_.get("leads") or 0
                    cerrar(ind, 100 * v_ / t_ if t_ else None,
                           f"{v_} leads en etapa VENDIDO sobre {t_} del embudo",
                           "completo dentro del CRM. NO se compara con las "
                           "ventas de AXION: son definiciones distintas")
                else:
                    cerrar(ind, a_.get("mediana"),
                           "MEDIANA de horas entre la creación del lead y su "
                           "primera llamada",
                           f"parcial: {a_.get('negativas', 0)} leads tienen la "
                           f"llamada antes de crearse y quedan fuera")
            except Exception:  # noqa: BLE001
                ind.motivo = "el CRM no respondió en esta lectura"
            ind.area = "Marketing y Comercial"
        elif "órdenes de compra" in n or "concentración de proveedores" in n \
                or "proveedores nuevos" in n:
            try:
                from . import areas as _ar
                oc = _ar._log_o_error("OrdenCompra")
                pv = _ar._log_o_error("Proveedor")

                oc = periodo.recortar(oc, "created_date", mes) \
                    if "created_date" in oc.columns else oc
                pv = periodo.recortar(pv, "created_date", mes) \
                    if "created_date" in pv.columns else pv
                _corte = (f", mes {mes}" if mes else " (acumulado del año)")

                if "órdenes" in n:
                    cerrar(ind, int(len(oc)),
                           f"órdenes de compra emitidas en AXION{_corte}",
                           f"parcial: el módulo se estrenó el 04-ago-2026, así "
                           f"que solo cubre desde entonces")
                elif "concentración" in n:
                    if len(oc) and "proveedor" in oc.columns:
                        tot = _num(oc["total"]).sum()
                        rucs = oc["proveedor"].map(
                            lambda x: (x or {}).get("ruc") if isinstance(x, dict)
                            else None)
                        top = _num(oc.assign(_r=rucs).groupby("_r")["total"]
                                   .sum()).max() if tot else 0
                        cerrar(ind, 100 * top / tot if tot else None,
                               f"porcentaje del monto comprado que se lleva el "
                               f"proveedor más grande, sobre {len(oc)} órdenes",
                               "parcial: son las primeras órdenes del módulo")
                else:
                    cerrar(ind, int(len(pv)), "proveedores registrados en AXION",
                           "parcial: el módulo se estrenó el 04-ago-2026")
                    _alta = pd.to_datetime(pv.get("created_date"),
                                           errors="coerce")
                    if _alta is not None and _alta.notna().any():
                        ind.avisos.append(
                            f"Hoy «nuevos» equivale a TODOS los proveedores: "
                            f"las {len(pv)} altas se registraron entre el "
                            f"{_alta.min():%d-%b} y el {_alta.max():%d-%b}, "
                            f"al estrenarse el módulo. El indicador empieza a "
                            f"distinguir nuevos de antiguos con el tiempo, "
                            f"solo.")
            except Exception:  # noqa: BLE001
                ind.motivo = ("el módulo de logística no respondió o todavía "
                              "no existe en AXION")
            ind.area = "Logística"
        elif "avance promedio de obra" in n:
            proj = ingest.fetch_axion_entity("Project", None, 5000)
            av = _num(proj["construction_progress"])
            _et = proj["project_stage"].astype(str).str.strip()
            _ej = _et == "Ejecución"
            _det = " · ".join(
                f"{e}: {float(av[_et == e].mean()):.1f}% ({int((_et == e).sum())})"
                for e in sorted(set(_et)) if (_et == e).any())
            cerrar(ind, float(av[_ej].mean()) if _ej.any() else None,
                   f"promedio de avance de las {int(_ej.sum())} obras en "
                   f"ejecución, de {len(proj)}. Por etapa: {_det}",
                   "parcial: lo escribe Habitat a mano; el tablero lo muestra, "
                   "no lo mide")
            _ult = pd.to_datetime(proj["updated_date"], errors="coerce").max()
            _dias = (pd.Timestamp.today().normalize()
                     - _ult.normalize()).days if pd.notna(_ult) else None
            ind.avisos.append(
                "Es un número TIPEADO por Obra en AXION, sin documento que lo "
                "respalde —no hay valorización ni acta conectada—"
                + (f", y nadie lo toca desde el {_ult:%d-%b-%Y}"
                   f" ({_dias} días)" if _dias is not None else "")
                + ". El promedio cubre solo las obras en etapa Ejecución: "
                  "mezclar un Anteproyecto con una Entrega inmediata no mide "
                  "nada.")
            ind.area = "Obra"
        elif "costo por m²" in n:
            from . import movimientos as _mv2
            _u2 = _unidades()
            _g2 = _mv2.gasto_por_obra(None).set_index("obra")["gasto"]
            _m22 = (_u2.assign(_a=_num(_u2["area_m2"]))
                    .groupby("project")["_a"].sum())
            _pr2 = ingest.fetch_axion_entity("Project", None, 5000)
            _av2 = dict(zip(_pr2["name"], _num(_pr2["construction_progress"])))
            _pares = [(o, float(_g2.get(o, 0)), float(_m22.get(o, 0)))
                      for o in _pr2["name"]]
            _con = [(o, g_, m_) for o, g_, m_ in _pares if g_ > 0 and m_ > 0]
            _sg = sum(g_ for _, g_, _ in _con)
            _sm = sum(m_ for _, _, m_ in _con)
            _gt2 = _mv2.gasto_total(None)
            if _sm > 0:
                cerrar(ind, _sg / _sm,
                       f"S/ {_sg:,.2f} de gasto atribuido a obra dividido "
                       f"entre {_sm:,.1f} m² de las {len(_con)} obras que tienen las dos cifras "
                       f"(área de sus unidades en AXION)",
                       f"parcial, y por dos motivos que hay que leer juntos: "
                       f"{len(_con)} de {len(_pr2)} obras tienen las dos "
                       f"cifras, y el gasto atribuido es el "
                       f"{_gt2['pct_atribuido']:.1f}% del gasto del año "
                       f"(S/ {_gt2['atribuido']:,.2f} de "
                       f"S/ {_gt2['monto']:,.2f}) — el resto no lleva obra "
                       f"cargada en el movimiento",
                       pct=False)
                _raros = sorted(
                    [(o, g_ / m_, _av2.get(o, 0)) for o, g_, m_ in _con
                     if _av2.get(o, 0) >= 90 and (g_ / m_) < 60],
                    key=lambda x: x[1])[:4]
                ind.avisos.append(
                    "NO es el costo de construir un metro cuadrado. La cifra "
                    "divide el gasto de " + str(periodo.ANIO) + " entre TODOS "
                    "los metros de la obra, estén construidos o no, porque el "
                    "registro de movimientos arrancó este año y no guarda lo "
                    "gastado antes. Las obras ya entregadas salen "
                    "artificialmente baratas: "
                    + (" · ".join(f"{o} S/ {c:,.2f}/m² con {a:.0f}% de avance"
                                  for o, c, a in _raros)
                       if _raros else "ninguna en este corte")
                    + ". Para el costo real de construcción hace falta cargar "
                      "el gasto histórico de cada obra, o su presupuesto.")
            else:
                ind.motivo = ("no hay ninguna obra con gasto atribuido y área "
                              "cargada a la vez")
            ind.area = "Obra · carga de costos por obra"
        elif "avance físico vs gasto" in n:
            from . import movimientos as _mv3
            _pr3 = ingest.fetch_axion_entity("Project", None, 5000)
            _g3 = _mv3.gasto_por_obra(None).set_index("obra")["gasto"]
            _et3 = _pr3["project_stage"].astype(str).str.strip()
            _ej3 = _pr3[_et3.eq("Ejecución")]
            _lista = sorted(
                [(r["name"], float(_num(pd.Series([r["construction_progress"]])).iloc[0]),
                  float(_g3.get(r["name"], 0))) for _, r in _ej3.iterrows()],
                key=lambda x: -x[2])
            ind.motivo = (
                f"el avance físico es un porcentaje de la obra y el gasto son "
                f"soles: para compararlos hace falta el presupuesto de cada "
                f"obra, que es lo que convertiría los soles en porcentaje. "
                f"AXION no lo guarda en ninguna tabla. Los dos datos sueltos "
                f"sí están —el avance en las {len(_pr3)} obras, el gasto en "
                f"{int((_g3 > 0).sum())}— y van abajo, sin dividirlos")
            if _lista:
                ind.avisos.append(
                    "Las obras en ejecución, con sus dos cifras sin dividir: "
                    + " · ".join(f"{o} {a:.0f}% de avance y "
                                 f"S/ {g_:,.0f} gastados en {periodo.ANIO}"
                                 for o, a, g_ in _lista)
                    + ". El gasto es solo del año en curso: el registro de "
                      "movimientos no tiene lo anterior.")
            ind.area = "Obra · carga de costos por obra"
        elif "flujo de caja" in n:
            from . import flujo_caja as _fc
            try:
                fl = _fc.por_mes()
            except Exception:  # noqa: BLE001
                fl = {"hay": False}
            if fl.get("hay"):
                a_ = fl["acumulado"]
                hip_ = fl.get("hipotecas") or {}
                cerrar(ind, a_["neto"],
                       f"lo que entró a caja (S/ {a_['entro']:,.2f}) menos lo "
                       f"que salió (S/ {a_['salio']:,.2f}) en el año, mes a "
                       f"mes. El detalle está en la hoja Cobranza",
                       f"parcial: la proyección de entradas es un PISO — "
                       f"{hip_.get('ventas', 0)} hipotecas por "
                       f"S/ {hip_.get('monto', 0):,.2f} no tienen fecha de "
                       f"desembolso registrada")
                ind.avisos.append(
                    f"Por entrar según cronograma: "
                    f"S/ {a_['por_entrar']:,.2f}. No incluye las hipotecas: "
                    f"AXION no registra cuándo desembolsa el banco.")
            else:
                ind.motivo = "no se pudo calcular el flujo en esta lectura"
            ind.area = "Administración"
        elif "reducción de costos" in n:
            ind.motivo = (
                "lo que hoy está cargado como «presupuesto» no es un plan de "
                "gastos: sus conceptos son transferencias entre cuentas del "
                "grupo y retiros. Por eso coincide con el gasto real al "
                "céntimo —en marzo difieren S/ 9 sobre S/ 648,000— y "
                "compararlos daría 100% siempre, sin medir nada. Hace falta "
                "cargar cuánto planea gastar cada obra cada mes, ANTES de "
                "gastarlo")
            ind.area = "Administración · cargar el presupuesto real por obra"
        elif any(x in n for x in ("cronograma", "incidencias", "retrabajos",
                                  "retrasos")):
            if "cronograma" in n:
                ind.motivo = (
                    "la ficha de la obra en AXION no guarda ninguna fecha: "
                    "trae el avance y la etapa, pero no cuándo se planeó "
                    "terminar ni cuándo se terminó de verdad. Sin esas dos "
                    "fechas por obra no hay cumplimiento que medir — y con "
                    "ellas cargadas, este indicador se calcula solo")
                ind.necesita = (
                    "dos casillas nuevas en la ficha de cada obra: fecha "
                    "planeada de entrega y fecha real. Las carga Obra y no "
                    "hace falta nada más.")
            else:
                ind.motivo = (
                    "no existe dónde anotar una incidencia: AXION no tiene "
                    "tabla de incidencias de obra y el cuaderno de obra digital "
                    "quedó fuera de alcance. No es que esté vacía — no está")
                ind.necesita = (
                    "crear el registro de incidencias, con fecha, obra, qué "
                    "pasó y cómo se resolvió. Mientras no exista, este "
                    "indicador no tiene de dónde salir.")
            ind.area = "Obra"
        elif "proveedores" in n:
            ind.motivo = ("el módulo de compras existe y ya tiene data: falta "
                          "que cada orden registre QUÉ material compró, para "
                          "poder medir contra el catálogo de precios")
            ind.area = "Logística · y la desarrolladora de AXION"
        elif "lead time" in n:
            ind.motivo = ("la orden de compra registra la fecha del pedido "
                          "pero no la de recepción. Falta esa casilla en la "
                          "ficha de la orden: con las dos fechas, este "
                          "indicador se calcula solo")
            ind.area = "Logística · y la desarrolladora de AXION"
        elif "inventario" in n:
            ind.motivo = ("la tabla de inventario existe en AXION y está "
                          "vacía: cero filas. Hace falta un conteo físico "
                          "cargado para comparar contra el sistema")
            ind.area = "Logística"
        else:
            ind.motivo = ("no tiene fuente en AXION ni en ningún sistema "
                          "conectado: se mide con encuestas y registros de "
                          "RR.HH. que hoy no existen como data")
            ind.area = "Gerencia"

        ind.area = _area_limpia(ind.area)

        if ind.necesita and "{VALOR}" in ind.necesita:
            v = ind.valor
            ind.necesita = ind.necesita.replace(
                "{VALOR}", "—" if v is None else f"{v:,.0f}")

        salida.append(ind)

    for nombre, objetivo in (
        ("Rentabilidad por obra",
         "Conocer el margen real de cada una de las 18 obras"),
        ("Rentabilidad por razón social",
         "Conocer el margen real de cada empresa del grupo"),
    ):
        ind = Indicador(perspectiva="Finanzas", objetivo=objetivo,
                        indicador=nombre, meta=None, unidad="%", propio=True)
        ind.motivo = (
            "la mitad de INGRESOS ya se mide en vivo: contratado y cobrado "
            "por obra y por empresa están en la hoja Rentabilidad. "
            + _motivo_costo())
        ind.area = _area_limpia("Gerencia")
        ind.area_bsc = "Finanzas"
        salida.append(ind)

    _fin = _finanzas_propuestos(vend, cred, mes)
    for ind in _fin:
        ind.area = _area_limpia("Finanzas")
        salida.append(ind)

    salida.extend(_marketing(mes))

    for ind in salida:
        if ind.area_bsc in ("", "Otros"):
            ind.area_bsc = _area_limpia(ind.area) or "Otros"
    return salida


_MK_NECESITA = {
    "I1": "nada para la cifra: sale de las mismas ventas que el resto del "
          "cockpit y coincide al céntimo. Lo que falta es la meta del año.",
    "I2": "que se cargue la inversión y los leads del mes apenas cierra. El "
          "costo por lead es una división: si un lado llega tarde, el "
          "indicador queda viejo sin avisar.",
    "I3": "nada adicional: se carga con cada campaña que Marketing lanza.",
    "I4": "confirmar con Marketing si la meta de S/ 10,000 es por mes o por "
          "año. Hoy está cargada en cada mes, y el acumulado contra ese "
          "número no significa nada.",
    "I6": "nada adicional: las tres redes ya reportan sus visualizaciones.",
    "I7": "definir qué se anota en esta casilla. En 2025 se cargaban los "
          "seguidores GANADOS en el mes y en 2026 se carga el total "
          "acumulado: son dos indicadores distintos con el mismo nombre.",
    "I8": "nada adicional: se carga con cada publicación.",
    "I9": "nada adicional: se carga con cada publicación.",
    "I10": "nada adicional: se carga con cada publicación.",
}

_MK_MES = ["", "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
           "agosto", "setiembre", "octubre", "noviembre", "diciembre"]


def _marketing(mes: int | None = None) -> list[Indicador]:
    """Los nueve indicadores de Marketing, como filas del scorecard."""
    from . import marketing_kpi as _mk

    try:
        filas = _mk.indicadores(mes)
        cob = _mk.cobertura()
        avs = _mk.avisos()
    except Exception as e:  # noqa: BLE001
        ind = Indicador(perspectiva="Clientes", objetivo="Medir el marketing",
                        indicador="Indicadores de Marketing", meta=None,
                        unidad="N°")
        ind.motivo = (f"la tabla de indicadores de marketing de AXION no "
                      f"respondió en esta lectura ({type(e).__name__})")
        ind.area, ind.area_bsc = "Marketing", "Marketing y Comercial"
        return [ind]
    if not filas:
        return []

    try:
        _pa, m = periodo.partes(mes)
        if _pa != periodo.ANIO:
            m = None
    except (TypeError, ValueError):
        m = None

    _hoy = pd.Timestamp.today()
    mes_hoy = _hoy.month if _hoy.year == periodo.ANIO else 12

    aviso_mensual = next((a for a in avs if "mensual" in a["titulo"]), None)
    aviso_seg = next((a for a in avs if "Seguidores" in a["titulo"]), None)
    aviso_tipo = next((a for a in avs if "criterio" in a["titulo"]), None)

    out: list[Indicador] = []
    for f in filas:
        cod = f["codigo"]
        meta = f["meta"] if (f["meta"] and m) else None
        ind = Indicador(
            perspectiva=f["perspectiva"], objetivo=f["objetivo"],
            indicador=f["indicador"], meta=meta, unidad=f["unidad"])
        ind.area, ind.area_bsc = "Marketing", "Marketing y Comercial"
        ind.es_porcentaje = False
        ind.necesita = _MK_NECESITA.get(cod, "")

        if f["valor"] is None:
            ind.motivo = (
                f"Marketing todavía no cargó {_MK_MES[m] if m else 'este período'}. "
                f"Lo cargado llega hasta {_MK_MES[cob['hasta']]} "
                f"({cob['filas']} registros de {cob['indicadores']} indicadores)")
            out.append(ind)
            continue

        _COMO = {
            "suma": f"suma de los {f['n_meses']} meses cargados",
            "media": f"promedio de los {f['n_meses']} meses cargados — es un "
                     f"cociente y no se suma; así lo totaliza también la ficha "
                     f"de Habitat",
            "ultimo": f"el ÚLTIMO mes cargado, porque es un saldo y no un "
                      f"flujo: sumar los {f['n_meses']} meses contaría a cada "
                      f"seguidor una vez por mes",
        }
        como = (f"lo cargado para {_MK_MES[m]}" if m else _COMO[f["agrega"]])
        ind.valor = f["valor"]
        ind.formula = (f"{como}, tal como Marketing lo registró en AXION. El "
                       f"tablero no lo recalcula: lo muestra")

        faltan = [x for x in range(1, mes_hoy + 1)
                  if x not in (cob.get("completos") or [])]
        ind.alcance = (
            f"completo para {_MK_MES[m]}" if m else
            (f"parcial: están cargados {len(cob['completos'])} meses del año "
             f"—hasta {_MK_MES[cob['hasta']]}— y el año va por "
             f"{_MK_MES[mes_hoy]}. Falta "
             f"{', '.join(_MK_MES[x] for x in faltan)}: la cifra es un piso"
             if faltan else
             f"completo: los {len(cob['completos'])} meses del año están "
             f"cargados"))

        if f["desglose"]:
            ind.desglose = f["desglose"]
            det = " · ".join(f"{d['dimension']} {d['valor']:,.0f}"
                             for d in f["desglose"])
            tot = sum(d["valor"] for d in f["desglose"])
            cuadra = abs(tot - float(f["valor"])) < 0.02
            ind.avisos.append(
                f"Desglose: {det}." +
                ("" if cuadra else
                 f" OJO: el desglose suma {tot:,.2f} y la cifra publicada dice "
                 f"{float(f['valor']):,.2f} — los dos números los cargó "
                 f"Marketing y no cuadran entre sí."))

        if cod == "I4" and aviso_mensual:
            ind.avisos.append(aviso_mensual["detalle"])
        if cod == "I7" and aviso_seg:
            ind.avisos.append(aviso_seg["detalle"])
        if cod == "I1":
            _s = ingest.fetch_axion_entity("Sale", None, 5000)
            _s = _s[_s["status"] == "Vendido"]
            _s = _s[pd.to_datetime(_s["date"], errors="coerce")
                    .dt.year.eq(periodo.ANIO)]
            _fv = pd.to_datetime(_s["date"], errors="coerce")
            _pv = _num(_s["sale_price"])
            _hasta = max(f["meses"]) if f["meses"] else 0
            _post = _fv.dt.month.gt(_hasta)
            _dif = float(_pv[_post].sum())
            if not m and _dif > 0:
                ind.avisos.append(
                    f"Es la MISMA venta que mide «Venta firmada del año» "
                    f"(S/ {float(_pv.sum()):,.2f}), con otra ventana: acá "
                    f"llega hasta {_MK_MES[_hasta]} porque hasta ahí cargó "
                    f"Marketing. La diferencia —S/ {_dif:,.2f} en "
                    f"{int(_post.sum())} ventas— es exactamente lo firmado "
                    f"después de {_MK_MES[_hasta]}. No son dos cifras que se "
                    f"contradicen: es la misma, con un mes de carga de "
                    f"diferencia.")
            c = _mk.contra_axion()
            if c.get("hay"):
                ind.avisos.append(
                    f"Se contrastó contra las ventas de AXION mes por mes: "
                    f"{c['meses'] - c['difieren']} de {c['meses']} coinciden "
                    f"al céntimo y en cantidad de ventas."
                    if not c["difieren"] else
                    f"Se contrastó contra las ventas de AXION mes por mes y "
                    f"{c['difieren']} de {c['meses']} NO coinciden: "
                    + " · ".join(f"{x['nombre']} difiere en "
                                 f"S/ {x['dif']:,.2f}"
                                 for x in c['filas'] if abs(x['dif']) >= 0.01)
                    + ". Las dos cifras salen de AXION, así que una de las dos "
                      "se cargó a mano y quedó vieja. Lo revisa Marketing.")
        if aviso_tipo and cod in ("I2", "I3", "I6", "I7", "I8", "I10"):
            ind.avisos.append(
                "AXION no guarda de forma consistente si para este indicador "
                "conviene subir o bajar: el criterio cambia entre meses del "
                "mismo indicador. Por eso el tablero muestra la cifra y no un "
                "semáforo.")
        out.append(ind)
    return out


def _finanzas_propuestos(vend: pd.DataFrame, cred: pd.DataFrame,
                         mes: int | None) -> list[Indicador]:
    """Los cinco saldos de Finanzas, calculados desde AXION."""
    def _n(s):
        return pd.to_numeric(s, errors="coerce").fillna(0)

    inst = ingest.fetch_axion_entity("Installment", None, 5000)
    hoy = pd.Timestamp.today().normalize()
    activos = cred[cred["estado"].astype(str).str.lower() != "cancelado"] \
        if "estado" in cred.columns else cred
    cartera = float(_n(activos["saldo_pendiente"]).sum())

    venc = pd.to_datetime(inst["fecha_vencimiento"], errors="coerce")
    falta = (_n(inst["monto_cuota"]) - _n(inst["monto_pagado"])).clip(lower=0)
    _vivos = (set(cred.loc[~cred["estado"].astype(str).str.lower()
                           .eq("cancelado"), "id"])
              if "estado" in cred.columns else set(cred["id"]))
    pend = falta.gt(0) & inst["credit_id"].isin(_vivos)
    vencido = float(falta[pend & (venc < hoy)].sum())
    n_venc = int((pend & (venc < hoy)).sum())
    por_venir = float(falta[pend & (venc >= hoy) & venc.dt.year.eq(periodo.ANIO)].sum())
    n_venir = int((pend & (venc >= hoy) & venc.dt.year.eq(periodo.ANIO)).sum())

    precios = _n(vend["sale_price"])
    firmado = float(precios.sum())
    prom = float(precios.mean()) if len(precios) else 0.0
    medi = float(precios.median()) if len(precios) else 0.0
    corte = f", mes {mes}" if mes else " (acumulado del año)"

    out: list[Indicador] = []

    def nuevo(nombre, objetivo, unidad, valor, formula, alcance, ojo=None):
        i = Indicador(perspectiva="Finanzas", objetivo=objetivo,
                      indicador=nombre, meta=None, unidad=unidad, propio=True)
        i.valor, i.formula, i.alcance = valor, formula, alcance
        i.es_porcentaje = (unidad == "%")
        i.necesita = ("nada: se calcula solo desde AXION. Falta que Gerencia "
                      "fije la meta del año.")
        if ojo:
            i.avisos.append(ojo)
        out.append(i)

    nuevo("Venta firmada del año",
          "Cuánta plata se firmó en contratos de venta este año", "S/.",
          firmado,
          f"suma del precio de las ventas marcadas «Vendido», con fecha "
          f"{periodo.ANIO}{corte} · {len(vend)} ventas",
          f"completo: las {len(vend)} ventas del período traen precio")

    nuevo("Ticket promedio de venta",
          "Cuánto vale, en promedio, cada venta del año", "S/.",
          prom,
          f"el precio de las {len(vend)} ventas del año, sumado y dividido "
          f"entre {len(vend)}",
          f"completo: entran las {len(vend)} ventas del año, ninguna queda afuera",
          ojo=(f"El promedio es S/ {prom:,.2f} y la MEDIANA es S/ {medi:,.2f}: "
               f"unas pocas ventas grandes lo arrastran hacia arriba. La venta "
               f"típica se parece más a la mediana. Los dos salen de las mismas "
               f"{len(vend)} ventas."))

    nuevo("Cartera por cobrar",
          "Cuánta plata falta que entre de las ventas ya firmadas", "S/.",
          cartera,
          f"suma del saldo que queda por pagar en los {len(activos)} créditos que no están "
          f"cancelados",
          f"completo sobre todos los créditos; NO es del período: es el saldo vivo a hoy, "
          f"de créditos de todos los años")

    _con_cro = activos[activos["id"].isin(set(inst["credit_id"].dropna()))]         if "id" in activos.columns else activos
    _cart_cro = float(_n(_con_cro["saldo_pendiente"]).sum())
    _sin_cro = cartera - _cart_cro
    _n_sin = len(activos) - len(_con_cro)
    nuevo("Morosidad de la cartera", "Cuánto de lo que ya venció sigue sin cobrarse",
          "%", (100 * vencido / cartera) if cartera else None,
          f"cuotas pendientes ya vencidas (S/ {vencido:,.2f}) sobre la cartera "
          f"por cobrar completa (S/ {cartera:,.2f})",
          f"parcial, y hay que leer los dos lados: arriba solo pueden estar "
          f"cuotas, y abajo está la cartera entera — que incluye "
          f"S/ {_sin_cro:,.2f} de {_n_sin} créditos sin ninguna cuota cargada, "
          f"que no pueden vencer y por eso nunca suben al numerador",
          ojo=(f"Son S/ {vencido:,.2f} en {n_venc} cuotas ya vencidas y sin "
               f"cobrar. La cifra es alta pero NO es una pérdida: es deuda "
               f"atrasada, no perdida. "
               + (f"Medida solo contra lo que SÍ puede vencer "
                  f"—S/ {_cart_cro:,.2f} de {len(_con_cro)} créditos con "
                  f"cronograma— la morosidad es "
                  f"{100 * vencido / _cart_cro:.2f}%, no "
                  f"{100 * vencido / cartera:.2f}%. La de arriba usa la cartera "
                  f"completa porque es la que cuadra con AXION; esta otra es "
                  f"la comparable."
                  if _cart_cro else "")))

    nuevo("Cuotas por vencer en lo que resta del año",
          "Cuánto entraría de acá a fin de año si se cobra a tiempo",
          "S/.", por_venir,
          f"cuotas pendientes con vencimiento entre hoy y el 31-dic-{periodo.ANIO} "
          f"· {n_venir} cuotas",
          f"parcial: solo los créditos con cronograma cargado")

    return out


def resumen(mes: int | None = None) -> pd.DataFrame:
    """La tabla de la hoja 2, tal como se muestra."""
    filas = []
    for i in construir(mes):
        filas.append({
            "Perspectiva": i.perspectiva,
            "Objetivo": i.objetivo,
            "Indicador": i.indicador,
            "Meta": i.meta,
            "Avance real": i.valor,
            "Iniciativa": i.iniciativa,
            "Alcance": i.alcance or i.motivo,
            "estado": i.estado,
            "unidad_no_cuadra": i.unidad_no_cuadra,
            "area": i.area,
            "tipeado_por_habitat": sum(i.tipeado.values()) if i.tipeado else None,
        })
    return pd.DataFrame(filas)
