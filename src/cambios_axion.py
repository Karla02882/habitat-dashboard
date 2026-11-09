"""VIGILANTE DE CAMBIOS EN AXION."""
from __future__ import annotations

import json
from pathlib import Path

from . import ingest, reloj

RAIZ = Path(__file__).resolve().parent.parent
HUELLA = RAIZ / "data" / "forma_axion.json"

EN_CASTELLANO = {
    "Sale": "Ventas", "Unit": "Unidades", "Credit": "Créditos",
    "Installment": "Cuotas", "CxCPayment": "Pagos de cuotas",
    "Project": "Obras", "Gasto": "Gastos (tabla antigua)",
    "Ingreso": "Ingresos (tabla antigua)", "KPI": "Indicadores",
    "Advisor": "Asesores", "Moroso": "Morosos", "Property": "Propiedades",
    "Lead": "Leads", "MovimientoGasto": "Registro de movimientos",
    "OrdenCompra": "Órdenes de compra", "Proveedor": "Proveedores",
    "Material": "Materiales", "Inventory": "Inventario",
    "Proforma": "Proformas", "Promotion": "Promociones",
}


def _bonito(tabla: str) -> str:
    n = EN_CASTELLANO.get(tabla)
    return f"{n} ({tabla})" if n else tabla


def forma_actual() -> dict:
    """Qué tablas responden hoy y con cuántas filas. Solo lo que el tablero."""
    out = {}
    for ent in ingest.AXION_ENTITIES:
        try:
            out[ent] = int(len(ingest.fetch_axion_entity(ent, None, 5000)))
        except Exception:  # noqa: BLE001 — no responde = no está
            out[ent] = None
    return out


def _leer() -> dict:
    if HUELLA.exists():
        try:
            return json.loads(HUELLA.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def revisar(guardar: bool = True) -> list[dict]:
    """Compara la forma de hoy contra la última vista. Devuelve los cambios."""
    previo = _leer()
    antes = previo.get("tablas") or {}
    ahora = forma_actual()
    cuando_antes = previo.get("cuando", "—")

    cambios = []
    for t, n in ahora.items():
        habia = antes.get(t, "no-estaba")
        if habia == "no-estaba":
            if antes:                       # primera corrida: no es novedad
                cambios.append({
                    "grave": False, "tabla": t,
                    "titulo": f"Apareció {_bonito(t)}",
                    "texto": (f"No existía la última vez que miramos "
                              f"({cuando_antes}) y ahora tiene "
                              f"{n if n is not None else 0:,} filas. Habitat "
                              f"agregó este cuadro a AXION.")})
        elif habia is not None and n is None:
            cambios.append({
                "grave": True, "tabla": t,
                "titulo": f"DESAPARECIÓ {_bonito(t)}",
                "texto": (f"Tenía {habia:,} filas el {cuando_antes} y hoy "
                          f"AXION ya no la entrega. Puede que la hayan "
                          f"renombrado o borrado. Las pantallas que dependen "
                          f"de este cuadro salen vacías hasta que se aclare.")})
        elif habia is None and n is not None:
            cambios.append({
                "grave": False, "tabla": t,
                "titulo": f"Volvió {_bonito(t)}",
                "texto": (f"No respondía el {cuando_antes} y hoy entrega "
                          f"{n:,} filas.")})
        elif habia is not None and n is not None and n != habia:
            d = n - habia
            # El crecimiento normal no es noticia; la caída sí, siempre.
            if d < 0 or abs(d) >= max(50, habia * 0.2):
                cambios.append({
                    "grave": d < 0, "tabla": t,
                    "titulo": (f"{_bonito(t)}: "
                               + (f"bajó {abs(d):,} filas" if d < 0
                                  else f"subió {d:,} filas")),
                    "texto": (f"Tenía {habia:,} el {cuando_antes} y hoy tiene "
                              f"{n:,}."
                              + (" Que BAJE es lo que hay que mirar: puede ser "
                                 "un borrado."
                                 if d < 0 else " Es carga nueva."))})

    if guardar:
        HUELLA.parent.mkdir(parents=True, exist_ok=True)
        HUELLA.write_text(json.dumps(
            {"cuando": reloj.sello(),
             "tablas": ahora}, indent=1, ensure_ascii=False), encoding="utf-8")
    return cambios
