"""PASO 4 · LA FICHA DE UNA OBRA."""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from . import administracion as adm
from . import atribucion, contasis, ingest
from . import lectura_excel as lx


@dataclass
class Cifra:
    etiqueta: str
    valor: float | int | None
    formula: str
    origen: str
    motivo: str = ""          # por qué no se puede calcular, si valor es None
    area: str = ""            # a quién de Habitat le toca responderlo

    @property
    def hay(self) -> bool:
        return self.valor is not None

    def __repr__(self) -> str:                     # pragma: no cover
        if not self.hay:
            return f"{self.etiqueta}: SIN DATO — {self.motivo}"
        v = f"{self.valor:,.2f}" if isinstance(self.valor, float) else f"{self.valor:,}"
        return f"{self.etiqueta}: {v}"


@dataclass
class Vista:
    fuente: str
    periodo: str
    cifras: list[Cifra] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)


def _num(s) -> pd.Series:
    return pd.to_numeric(s, errors="coerce").fillna(0)


def vista_axion(obra: str) -> Vista:
    sale = ingest.fetch_axion_entity("Sale", None, 5000)
    unit = ingest.fetch_axion_entity("Unit", None, 5000)
    cred = ingest.fetch_axion_entity("Credit", None, 5000)
    s = sale[sale["project"] == obra]
    u = unit[unit["project"] == obra]
    c = cred[cred["project"] == obra]

    v = s[s["status"] == "Vendido"]
    fechas = pd.to_datetime(s["date"], errors="coerce").dropna()
    periodo = (f"acumulado desde {fechas.min():%Y-%m-%d} hasta "
               f"{fechas.max():%Y-%m-%d}" if len(fechas) else "sin fechas")

    vista = Vista("AXION · lo vendido", periodo)
    vista.cifras += [
        Cifra("Vendido", float(_num(v["sale_price"]).sum()),
              f"suma del precio de venta de las {len(v)} ventas con estado «Vendido»",
              "AXION · Sale"),
        Cifra("Ventas cerradas", len(v),
              "cantidad de filas con estado «Vendido»", "AXION · Sale"),
        Cifra("Unidades del proyecto", len(u),
              "filas de Unit con este proyecto", "AXION · Unit"),
    ]
    for estado in ("LIBRE", "VENDIDO", "SEPARADO", "BLOQUEADO"):
        n = int((u["status"] == estado).sum())
        if n:
            vista.cifras.append(
                Cifra(f"Unidades {estado}", n,
                      f"filas de Unit con estado «{estado}»", "AXION · Unit"))
    vista.cifras.append(
        Cifra("Saldo por cobrar",
              float(_num(c[~c["estado"].astype(str).str.lower()
                           .eq("cancelado")]["saldo_pendiente"]).sum()),
              f"suma del saldo por pagar de los créditos vivos de la obra, "
              f"de {len(c)} en total",
              "AXION · Credit"))

    # Lo que NO es venta se declara al lado, no se esconde ni se suma.
    for estado in ("Separación", "Devolución"):
        sub = s[s["status"] == estado]
        if len(sub):
            vista.avisos.append(
                f"{len(sub)} {estado.lower()}(es) por S/ "
                f"{_num(sub['sale_price']).sum():,.2f} NO están en «Vendido»: "
                f"no son venta.")
    con_interes = c[_num(c["tasa_interes"]) > 0]
    if len(con_interes):
        vista.avisos.append(
            f"{len(con_interes)} crédito(s) con interés: la identidad "
            f"inicial + cuotas + saldo = precio NO aplica.")
    return vista


def vista_contasis(obra: str) -> Vista:
    """Lo RECONOCIDO. Su período es el cierre que declara el contador."""
    eq = atribucion.equivalencias()
    mias = eq[(eq["fuente"] == "ContaSis")
              & (eq["obra_axion"] == obra)
              & (eq["como"].isin(["exacta", "contenida"]))]
    may = contasis.tablas("LIBRO MAYOR")
    det = may[may["_clase"] == "detalle"] if not may.empty else may
    periodos = sorted({p for p in det["_periodo"].dropna().unique()}) if len(det) else []
    vista = Vista("CONTASIS · lo reconocido",
                  " · ".join(periodos) if periodos else "sin período declarado")

    if mias.empty:
        vista.cifras.append(Cifra(
            "Gasto atribuido", None,
            "suma del DEBE de las cuentas cuyo nombre nombra a esta obra",
            "ContaSis · Libro Mayor",
            motivo="ninguna etiqueta del contador corresponde a esta obra; "
                   "la equivalencia no está declarada",
            area="Contabilidad"))
        return vista

    col = next((c for c in det.columns if lx.normalizar(c) == "DESCRIPCION"), None)
    total, movs = 0.0, 0
    for etq in mias["etiqueta"]:
        f = det[det[col].astype(str).str.strip() == etq]
        movs += len(f)
        for c in det.columns:
            if lx.normalizar(c) in ("DEBE", "DEBITO"):
                total += float(_num(f[c]).sum())
    vista.cifras.append(Cifra(
        "Gasto atribuido", total,
        f"suma del DEBE de {movs} movimientos en {len(mias)} cuenta(s): "
        + ", ".join(f"«{e}»" for e in mias["etiqueta"]),
        "ContaSis · Libro Mayor"))
    vista.avisos.append(
        "La atribución se apoya en el nombre de la cuenta del contador. Está "
        "propuesta, no aprobada por Habitat.")
    return vista


def vista_administracion(obra: str) -> Vista:
    """La CAJA. Su período es el de los Excels mensuales."""
    eq = atribucion.equivalencias()
    mias = eq[(eq["fuente"] == "Administración")
              & (eq["obra_axion"] == obra)
              & (eq["como"].isin(["exacta", "contenida"]))]
    vista = Vista("ADMINISTRACIÓN · la caja", "enero a julio 2026")

    if mias.empty:
        m = atribucion.menciones_sin_declarar(obra)
        vista.cifras.append(Cifra(
            "Movimiento de caja", None,
            "suma de las hojas de la administradora asignadas a esta obra",
            "Administración · Excels",
            motivo=(f"sin correspondencia declarada · {m['movimientos']} "
                    f"movimientos la mencionan · S/ {m['monto_rotulado']:,.2f} "
                    f"sin atribuir"),
            area="Administración"))
        return vista

    mov = adm.movimientos()
    det = mov[mov["_clase"] == "detalle"]
    hojas = set(mias["etiqueta"])
    f = det[det["_hoja"].astype(str).str.strip().isin(hojas)]
    cols_imp = [c for c in f.columns
                if lx.normalizar(c).startswith(("MONTO", "IMPORTE", "MATERIALES"))]
    total = sum(float(_num(f[c]).sum()) for c in cols_imp)

    vista.cifras += [
        Cifra("Movimiento de caja", total,
              f"suma de {', '.join(cols_imp)} en {len(f)} filas de "
              f"{', '.join(sorted(hojas))}, excluyendo las filas de TOTAL",
              "Administración · Excels"),
        Cifra("Movimientos", len(f),
              "filas de detalle de esas hojas", "Administración · Excels"),
        # ESTA es la que espera respuesta. No se inventa un reparto.
        Cifra("Cobrado", None,
              "suma de los movimientos que son cobro",
              "Administración · Excels",
              motivo="no se puede separar cobro de gasto: falta confirmar si "
                     "«Tipo de Gasto/Ingreso» alcanza para distinguirlos. El "
                     "total de arriba mezcla las dos cosas.",
              area="Administración"),
        Cifra("Pagado", None, "suma de los movimientos que son gasto",
              "Administración · Excels",
              motivo="mismo motivo que «Cobrado».", area="Administración"),
    ]
    return vista


def vista_comparado(obra: str) -> Vista:
    """QUÉ EXISTE en cada fuente. **Nunca cuánto difieren**: mostrar una."""
    vista = Vista("COMPARADO · qué existe en cada fuente", "cada bloque el suyo")
    eq = atribucion.equivalencias()
    for fuente in ("ContaSis", "Administración"):
        n = len(eq[(eq["fuente"] == fuente) & (eq["obra_axion"] == obra)
                   & (eq["como"].isin(["exacta", "contenida"]))])
        vista.cifras.append(Cifra(
            f"Etiquetas en {fuente}", n,
            f"filas de la tabla de equivalencias con esta obra y "
            f"correspondencia declarada", "docs/equivalencias_obras.md"))
    vista.avisos.append(
        "Los montos de las tres vistas NO son comparables entre sí: responden "
        "preguntas distintas y cubren períodos distintos.")
    return vista


def ficha(obra: str) -> list[Vista]:
    return [vista_axion(obra), vista_contasis(obra),
            vista_administracion(obra), vista_comparado(obra)]
