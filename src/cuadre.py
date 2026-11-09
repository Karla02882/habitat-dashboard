"""CONTROL DE NUESTRAS PROPIAS CIFRAS."""
from __future__ import annotations

import pandas as pd

TOLERANCIA = 0.01          # un céntimo: los flotantes no dan exacto


def _casi(a: float, b: float) -> bool:
    return abs(float(a) - float(b)) <= TOLERANCIA


def comprobar() -> list[str]:
    """Devuelve la lista de contradicciones. Vacía = el tablero cuadra."""
    from . import filas, movimientos, rentabilidad

    fallas: list[str] = []

    try:
        for nombre, v in filas.todo().items():
            suma = sum(f["monto"] for f in v["filas"])
            if not _casi(suma, sum(f["monto"] for f in v["filas"])):
                fallas.append(f"cifra «{nombre}»: no cuadra con sus filas")
    except Exception as e:  # noqa: BLE001
        fallas.append(f"no se pudieron leer las filas de Resultados: {e}")

    try:
        por_obra = rentabilidad.por_obra()
        por_emp = rentabilidad.por_razon_social()
        for col in ("contratado", "cobrado", "costo"):
            a = pd.to_numeric(por_obra[col], errors="coerce").sum()
            b = pd.to_numeric(por_emp[col], errors="coerce").sum()
            if not _casi(a, b):
                fallas.append(
                    f"Rentabilidad · «{col}»: por obra suma {a:,.2f} y por "
                    f"razón social {b:,.2f} — son el mismo dinero y difieren "
                    f"en {abs(a-b):,.2f}")
    except Exception as e:  # noqa: BLE001
        fallas.append(f"no se pudo comparar Rentabilidad: {e}")

    try:
        r = movimientos.resumen()
        if r.get("hay"):
            g = movimientos.gasto_por_obra()
            suma_obras = float(g["gasto"].sum()) if not g.empty else 0.0
            if not _casi(suma_obras, r["gasto_atribuido"]):
                fallas.append(
                    f"Costos: la tabla por obra suma {suma_obras:,.2f} y la "
                    f"tarjeta «atribuido a obra» dice "
                    f"{r['gasto_atribuido']:,.2f}")
            if r["gasto_atribuido"] > r["gasto"]["monto"] + TOLERANCIA:
                fallas.append(
                    f"Costos: lo atribuido a obra ({r['gasto_atribuido']:,.2f}) "
                    f"supera al gasto total ({r['gasto']['monto']:,.2f}), que "
                    f"es imposible")
            if not 0 <= r["pct_atribuido"] <= 100:
                fallas.append(
                    f"Costos: el porcentaje atribuido es "
                    f"{r['pct_atribuido']:.2f}%, fuera de 0-100")
            total = (r["gasto"]["monto"] + r["venta"]["monto"]
                     + r["presupuesto"]["monto"] + r["otro"]["monto"])
            if r["filas"] and not _casi(
                    total, r["gasto"]["monto"] + r["venta"]["monto"]
                    + r["presupuesto"]["monto"] + r["otro"]["monto"]):
                fallas.append("Costos: las clases no suman el total")
    except Exception as e:  # noqa: BLE001
        fallas.append(f"no se pudieron comprobar los movimientos: {e}")

    # 4 · Ninguna cifra en soles puede ser negativa donde no tiene sentido.
    try:
        for nombre, v in filas.todo().items():
            neg = [f for f in v["filas"] if f["monto"] < 0]
            if neg and nombre not in ("Gasto",):
                fallas.append(
                    f"cifra «{nombre}»: {len(neg)} fila(s) con monto negativo")
    except Exception:  # noqa: BLE001 — ya se reportó arriba
        pass

    return fallas
