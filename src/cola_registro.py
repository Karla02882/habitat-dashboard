"""LA COLA · lo que ya entró a caja y todavía no está registrado en Cuentas por."""
from __future__ import annotations

import pandas as pd

from . import flujo_caja, movimientos

DIAS = 3


def _n(s) -> pd.Series:
    return pd.to_numeric(s, errors="coerce").fillna(0)


def calcular(anio: int | None = None) -> dict:
    """Las dos listas del cruce, con su detalle fila por fila."""
    hoy = pd.Timestamp.today().normalize()
    anio = anio or hoy.year

    # Lado Cuentas por Cobrar: iniciales de crédito + cuotas, con su fecha.
    ent = flujo_caja._entradas_reales()
    if ent.empty:
        return {"hay": False}
    ent = ent[pd.to_datetime(ent["fecha"]).dt.year.eq(anio)].copy()

    # Lado caja: los ingresos que el libro marca como venta.
    mv = movimientos.crudo()
    if mv.empty:
        return {"hay": False}
    lib = mv[mv["clase"].eq("venta")].copy()
    lib["fecha"] = pd.to_datetime(lib["fecha"], errors="coerce")
    lib = lib[lib["fecha"].dt.year.eq(anio)].copy()
    lib["m"] = _n(lib["monto"])

    usados: set = set()
    casados: list = []
    filas_lib = list(lib[["fecha", "m"]].itertuples(index=True))
    for i, r in ent.iterrows():
        mejor, mejor_d = None, 99
        for x in filas_lib:
            if x.Index in usados or abs(x.m - r["monto"]) > 0.01:
                continue
            d = abs((x.fecha - r["fecha"]).days)
            if d < mejor_d:
                mejor, mejor_d = x, d
        if mejor is not None and mejor_d <= DIAS:
            usados.add(mejor.Index)
            casados.append(i)

    cola = lib[~lib.index.isin(usados)].copy()
    sin_caja = ent.drop(index=casados)

    cola["dias"] = (hoy - cola["fecha"]).dt.days
    cola = cola.sort_values("fecha")

    def _fila_cola(r) -> dict:
        return {
            "fecha": str(r["fecha"].date()),
            "dias": int(r["dias"]),
            "monto": float(r["m"]),
            "concepto": str(r.get("concepto") or "—"),
        }

    def _fila_sin_caja(r) -> dict:
        return {
            "fecha": str(pd.to_datetime(r["fecha"]).date()),
            "monto": float(r["monto"]),
            "tipo": str(r.get("tipo") or "—"),
            "quien": str(r.get("quien") or "—"),
            "unidad": str(r.get("unidad") or "—"),
        }

    tramos = [("hasta 7 días", 0, 7), ("8 a 30 días", 8, 30),
              ("31 a 90 días", 31, 90), ("más de 90 días", 91, 10 ** 6)]
    antiguedad = []
    for rot, a, b in tramos:
        sel = cola[(cola["dias"] >= a) & (cola["dias"] <= b)]
        if len(sel):
            antiguedad.append({"tramo": rot, "filas": int(len(sel)),
                               "monto": float(sel["m"].sum())})

    return {
        "hay": True,
        "anio": anio,
        "dias_tolerancia": DIAS,
        # lo que entró por caja y espera registro en Cuentas por Cobrar
        "cola": {
            "filas": int(len(cola)),
            "monto": float(cola["m"].sum()),
            "mas_viejo": str(cola["fecha"].min().date()) if len(cola) else "",
            "dias_mas_viejo": int(cola["dias"].max()) if len(cola) else 0,
            "antiguedad": antiguedad,
            "detalle": [_fila_cola(r) for _, r in
                        cola.sort_values("m", ascending=False).head(80).iterrows()],
        },
        # registrado en Cuentas por Cobrar sin ingreso que lo respalde
        "sin_caja": {
            "filas": int(len(sin_caja)),
            "monto": float(sin_caja["monto"].sum()),
            "detalle": [_fila_sin_caja(r) for _, r in
                        sin_caja.sort_values("monto", ascending=False).head(40).iterrows()],
        },
        # los que sí casan: el circuito funcionando, para poder decir cuánto es
        "casados": {
            "filas": int(len(casados)),
            "monto": float(ent.loc[casados, "monto"].sum()) if casados else 0.0,
        },
        "total_cxc": float(ent["monto"].sum()),
        "total_libro": float(lib["m"].sum()),
    }
