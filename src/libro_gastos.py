from __future__ import annotations

import pandas as pd

from . import movimientos, periodo

BLOQUES = (
    ("PRESUPUESTOS", "presupuesto",
     ("Presup. Administrativo", "Presup. Operativo", "Presup. Urgencia")),
    ("INGRESOS", "venta",
     ("Venta al detalle", "Venta Mayoreo", "Otros ingresos")),
    ("GASTOS", "gasto",
     ("Gasto Admistrativo", "Gasto Operativo", "Gasto urgencia")),
)

# Los subtipos que AXION no tiene. Se publican en cero, con este motivo.
SIN_EQUIVALENTE = {
    "Presup. Urgencia": "no existe en AXION · su Excel sí la tiene",
    "Gasto urgencia": "no existe en AXION · su Excel sí la tiene",
}

RAZONES = (
    ("VENTAS HBR EIRL", r"HABITAT\s+BIENES\s+RAICES",
     "HABITAT BIENES RAICES EMPRESA INDIVIDUAL DE RESPONSABILIDAD LIMITADA"),
    ("VENTAS COR SAC", r"CORPORACION\s+HABITAT",
     "CORPORACION HABITAT SOCIEDAD ANONIMA CERRADA"),
    ("VENTAS YEAN", r"YEAN", ""),
    ("VENTAS ESCALAR", r"ESCALAR", ""),
    ("CONSTRUCTORA", r"CONSTRUCTORA|VELASCO\s+LEON",
     "CONSTRUCTORA VELASCO LEON SOCIEDAD ANONIMA CERRADA"),
    ("COMI CONCEP", r"CONCEP", ""),
)

_VACIO = ("", "nan", "none", "-")


def _txt(s: pd.Series) -> pd.Series:
    return s.fillna("").astype(str).str.strip()


def _limpio(v) -> str:
    t = str(v or "").strip()
    return "" if t.lower() in _VACIO or t == "—" else t


def _marco(mes=periodo.HISTORICO) -> pd.DataFrame:
    """Los movimientos del período pedido, ya clasificados por `movimientos`."""
    df = movimientos.crudo()
    if df.empty:
        return df
    return periodo.recortar(df, "fecha", mes)


def bloques(mes=periodo.HISTORICO) -> list[dict]:
    """Los tres bloques de arriba de su control, con sus subtipos y su total."""
    df = _marco(mes)
    if df.empty:
        return [{"rotulo": r, "filas": [], "total": 0.0, "n": 0}
                for r, _c, _s in BLOQUES]

    mov = _txt(df["movimiento"])
    monto = pd.to_numeric(df["monto"], errors="coerce").fillna(0)
    out = []
    for rot, clase, subs in BLOQUES:
        filas, tot, nn = [], 0.0, 0
        for s in subs:
            sel = mov.eq(s)
            m = float(monto[sel].sum())
            tot += m
            nn += int(sel.sum())
            filas.append({"rotulo": s, "n": int(sel.sum()), "monto": m,
                          "falta": SIN_EQUIVALENTE.get(s, "")})
        # Las filas SIN rótulo que este bloque se lleva por su tipo.
        huerf = mov.eq("") & df["clase"].eq(clase)
        if int(huerf.sum()):
            m = float(monto[huerf].sum())
            tot += m
            nn += int(huerf.sum())
            filas.append({
                "rotulo": "Sin tipo cargado", "n": int(huerf.sum()), "monto": m,
                "falta": "AXION los dejó sin la columna «Movimiento»: entran acá "
                         "por su tipo de operación —Ingreso o Egreso—, que es lo "
                         "único que traen"})
        out.append({"rotulo": rot, "filas": filas, "total": tot, "n": nn})
    return out


def detalle_ventas(mes=periodo.HISTORICO) -> dict:
    vacio = {"filas": [], "no_dice": {"n": 0, "monto": 0.0},
             "total": 0.0, "n": 0, "leidos": 0, "monto_leido": 0.0}
    df = _marco(mes)
    if df.empty:
        return vacio
    v = df[df["clase"].eq("venta")].copy()
    if v.empty:
        return vacio
    v["_m"] = pd.to_numeric(v["monto"], errors="coerce").fillna(0)
    txt = (_txt(v["concepto"]) + " | " + _txt(v["cuenta"])).str.upper()

    filas, vistos = [], pd.Series(False, index=v.index)
    for rotulo, patron, empresa in RAZONES:
        m = txt.str.contains(patron, regex=True, na=False) & ~vistos
        vistos = vistos | m
        filas.append({"rotulo": rotulo, "n": int(m.sum()),
                      "monto": float(v.loc[m, "_m"].sum()), "empresa": empresa})
    return {
        "filas": filas,
        "no_dice": {"n": int((~vistos).sum()),
                    "monto": float(v.loc[~vistos, "_m"].sum())},
        "total": float(v["_m"].sum()), "n": len(v),
        "leidos": int(vistos.sum()),
        "monto_leido": float(v.loc[vistos, "_m"].sum()),
    }


def cobertura_tipo(mes=periodo.HISTORICO) -> dict:
    """Cuán llena está `categoria`."""
    df = _marco(mes)
    if df.empty:
        return {"llenos": 0, "total": 0, "pct": None, "valores": [],
                "monto_lleno": 0.0, "monto_total": 0.0}
    c = _txt(df["categoria"])
    lleno = ~c.str.lower().isin(("", "nan", "none"))
    vc = c[lleno].value_counts()
    m = pd.to_numeric(df["monto"], errors="coerce").fillna(0)
    return {
        "llenos": int(lleno.sum()), "total": len(df),
        "pct": (100.0 * int(lleno.sum()) / len(df)) if len(df) else None,
        "monto_lleno": float(m[lleno].sum()), "monto_total": float(m.sum()),
        "valores": [{"rotulo": k, "n": int(x)} for k, x in vc.items()],
    }


def filas(mes=periodo.HISTORICO, tope: int = 12000) -> dict:
    """El detalle movimiento por movimiento, con LAS COLUMNAS DE SU EXCEL."""
    df = _marco(mes)
    if df.empty:
        return {"mov": [], "cat": [], "obra": [], "cuenta": [], "f": [],
                "total": 0, "recortado": 0}
    mapa = movimientos.mapa_proyectos().set_index("proyecto")["obra_axion"].to_dict()
    df = df.sort_values("fecha_n", ascending=False, na_position="last")
    total = len(df)
    if tope and total > tope:
        df = df.head(tope)

    dic: dict[str, list] = {"mov": [], "cat": [], "obra": [], "cuenta": []}
    idx: dict[str, dict] = {k: {} for k in dic}

    def _i(campo: str, valor) -> int:
        v = _limpio(valor)
        if v not in idx[campo]:
            idx[campo][v] = len(dic[campo])
            dic[campo].append(v)
        return idx[campo][v]

    out = []
    for _, r in df.iterrows():
        proy = _limpio(r.get("proyecto"))
        obra = mapa.get(proy, "")
        f = r.get("fecha_n")
        out.append([
            "" if pd.isna(f) else f.strftime("%Y-%m-%d"),
            _i("mov", r.get("movimiento")),
            _i("cat", r.get("categoria")),
            _limpio(r.get("concepto"))[:90],
            round(float(r.get("monto_n") or 0), 2),
            _i("obra", obra if obra and obra != "—" else ""),
            _i("cuenta", r.get("cuenta")),
            str(r.get("clase") or ""),
        ])
    return {**dic, "f": out, "total": total, "recortado": max(0, total - len(out))}


def control(mes=periodo.HISTORICO) -> dict:
    """Todo el espejo, de una. Lo que la hoja Gastos consume."""
    b = bloques(mes)
    por = {x["rotulo"]: x for x in b}
    ing = por.get("INGRESOS", {}).get("total", 0.0)
    pre = por.get("PRESUPUESTOS", {}).get("total", 0.0)
    gas = por.get("GASTOS", {}).get("total", 0.0)
    return {
        "bloques": b,
        "grafico": [{"rotulo": "Total Ingresos", "monto": ing},
                    {"rotulo": "Total Presup. Gastos", "monto": pre},
                    {"rotulo": "Total Gastos", "monto": gas}],
        "detalle": detalle_ventas(mes),
        "tipo": cobertura_tipo(mes),
        "saldo": ing - gas,
        "ingreso_presup": pre,
        "gasto_general": gas,
    }
