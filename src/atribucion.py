"""PASO 3 · ATRIBUCIÓN POR OBRA."""
from __future__ import annotations

import re

import pandas as pd

from . import administracion as adm
from . import contasis, ingest
from . import lectura_excel as lx

ARCHIVO_OBRAS_ADM = "GASTOS POR PROYECTOS"

HOJAS_NO_OBRA = {"SERVICIOS", "PAGO ADMIN", "ADM", "COMERCIAL",
                 "PROYECTOS ANTIGUOA"}


def _tokens(s: str) -> list[str]:
    """Palabras completas, sin tildes y en mayúsculas. Se parte por cualquier."""
    return [t for t in re.split(r"[^A-Z0-9Ñ]+", lx.normalizar(s)) if t]


def obras_axion() -> pd.DataFrame:
    """La lista maestra: las obras que AXION declara en `Project`."""
    pr = ingest.fetch_axion_entity("Project", None, 5000)
    maestra = sorted({str(x).strip() for x in pr["name"].dropna()})
    usadas: dict[str, set[str]] = {}
    for ent in ("Sale", "Unit", "Credit", "Property", "Moroso"):
        try:
            df = ingest.fetch_axion_entity(ent, None, 5000)
        except Exception:  # noqa: BLE001
            continue
        if "project" not in df.columns:
            continue
        for v in df["project"].dropna():
            usadas.setdefault(lx.normalizar(v), set()).add(ent)
    filas = []
    for nombre in maestra:
        filas.append({"obra": nombre,
                      "en_tablas": ", ".join(sorted(usadas.get(lx.normalizar(nombre), []))) or "—",
                      "declarada_en_Project": True})
    # Nombres que aparecen en las tablas y NO están declarados en Project.
    for clave, ents in sorted(usadas.items()):
        if clave not in {lx.normalizar(m) for m in maestra}:
            filas.append({"obra": clave, "en_tablas": ", ".join(sorted(ents)),
                          "declarada_en_Project": False})
    return pd.DataFrame(filas)


def etiquetas_contasis() -> pd.DataFrame:
    """Cómo escribe el contador cada obra: el sufijo del nombre de la cuenta."""
    may = contasis.tablas("LIBRO MAYOR")
    if may.empty:
        return pd.DataFrame()
    det = may[may["_clase"] == "detalle"]
    col_desc = next((c for c in det.columns if lx.normalizar(c) == "DESCRIPCION"), None)
    if col_desc is None:
        return pd.DataFrame()
    montos = pd.Series(0.0, index=det.index)
    for c in det.columns:
        if lx.normalizar(c) in ("DEBE", "DEBITO"):
            montos = montos.add(pd.to_numeric(det[c], errors="coerce").fillna(0),
                                fill_value=0)
    desc = det[col_desc].astype(str).str.strip()
    con = desc.str.contains(" - |-", regex=True)
    suf = desc[con].str.rsplit(" - ", n=1).str[-1].str.strip()
    tabla = pd.DataFrame({"etiqueta": suf, "monto": montos[con],
                          "empresa": det.loc[con, "_empresa"]})
    return (tabla.groupby("etiqueta")
            .agg(movimientos=("monto", "size"), monto_debe=("monto", "sum"),
                 empresas=("empresa", lambda s: s.nunique()))
            .reset_index().sort_values("monto_debe", ascending=False))


def etiquetas_administracion() -> pd.DataFrame:
    """Cómo nombra la administradora cada obra: una hoja por obra."""
    filas = []
    for h in adm.hojas():
        if ARCHIVO_OBRAS_ADM not in h.archivo.upper() or h.forma != "tabla":
            continue
        det = h.datos[h.datos["_clase"] == "detalle"] if "_clase" in h.datos else h.datos
        col = next((c for c in det.columns
                    if lx.normalizar(c).startswith("MONTO")), None)
        monto = (round(float(pd.to_numeric(det[col], errors="coerce").fillna(0).sum()), 2)
                 if col else None)
        filas.append({"etiqueta": h.hoja.strip(), "movimientos": len(det),
                      "monto": monto, "columna_monto": col or "NO ENCONTRADA",
                      "es_obra": h.hoja.strip().upper() not in HOJAS_NO_OBRA})
    if not filas:
        return pd.DataFrame(columns=["etiqueta", "movimientos", "monto",
                                     "columna_monto", "es_obra"])
    return pd.DataFrame(filas).sort_values(
        "monto", ascending=False, na_position="last")


def obras_en_hoja_ancha() -> list[str]:
    """La hoja `PROYECTOS ANTIGUOA` no tiene una obra: tiene ocho, puestas."""
    for h in adm.hojas():
        if "PROYECTOS ANTIGUOA" not in h.hoja.upper() or not h.fila_encabezado:
            continue
        arriba = h.fila_encabezado - 2          # fila_encabezado es 1-based
        if arriba < 0 or arriba >= len(h.crudo):
            return []
        return [lx.texto(v) for v in h.crudo.iloc[arriba] if lx.texto(v)]
    return []


def _emparejar(etiqueta: str, obras: list[str]) -> tuple[str, str]:
    """Devuelve (obra, cómo). Palabras completas o nada."""
    net, tok = lx.normalizar(etiqueta), set(_tokens(etiqueta))
    exactas = [o for o in obras if lx.normalizar(o) == net]
    if len(exactas) == 1:
        return exactas[0], "exacta"
    if len(exactas) > 1:
        return " · ".join(exactas), "AMBIGUA"
    candidatas = []
    for o in obras:
        to = _tokens(o)
        if not any(len(t) >= 4 for t in to):
            continue
        if set(to) <= tok:
            candidatas.append(o)
    if len(candidatas) == 1:
        return candidatas[0], "contenida"
    if len(candidatas) > 1:
        return " · ".join(sorted(candidatas)), "AMBIGUA"
    return "—", "—"


def equivalencias() -> pd.DataFrame:
    """La tabla para aprobar: cada etiqueta de cada fuente con la obra de AXION."""
    obras = [o for o in obras_axion()
             .query("declarada_en_Project")["obra"].tolist()]
    filas = []
    for _, r in etiquetas_contasis().iterrows():
        obra, como = _emparejar(r["etiqueta"], obras)
        filas.append({"fuente": "ContaSis", "etiqueta": r["etiqueta"],
                      "obra_axion": obra, "como": como,
                      "movimientos": int(r["movimientos"]),
                      "monto": round(float(r["monto_debe"]), 2)})
    for _, r in etiquetas_administracion().iterrows():
        obra, como = _emparejar(r["etiqueta"], obras)
        if not r["es_obra"]:
            obra, como = "—", "hoja de área, no de obra"
        filas.append({"fuente": "Administración", "etiqueta": r["etiqueta"],
                      "obra_axion": obra, "como": como,
                      "movimientos": int(r["movimientos"]),
                      "monto": None if pd.isna(r["monto"]) else float(r["monto"]),
                      "nota": "" if r["columna_monto"] != "NO ENCONTRADA"
                              else "sin columna MONTO: el importe está en otra columna"})
    for etiqueta in obras_en_hoja_ancha():
        obra, como = _emparejar(etiqueta, obras)
        filas.append({"fuente": "Administración · hoja PROYECTOS ANTIGUOA",
                      "etiqueta": etiqueta, "obra_axion": obra, "como": como,
                      "movimientos": None, "monto": None,
                      "nota": "obra puesta como encabezado de columna"})
    COLS = ["fuente", "etiqueta", "obra_axion", "como", "movimientos",
            "monto", "nota"]
    if not filas:
        return pd.DataFrame(columns=COLS)
    df = pd.DataFrame(filas)
    return df.assign(nota=df.get("nota", pd.Series("", index=df.index)).fillna(""))


def menciones_sin_declarar(obra: str) -> dict:
    """Cuánto movimiento MENCIONA a esta obra, sin atribuirle nada."""
    palabras = [t for t in _tokens(obra) if len(t) >= 5]
    if not palabras:
        return {"obra": obra, "patron": None, "movimientos": 0,
                "monto": 0.0, "hojas": []}
    # Variante de singular/plural: HUERTAS también encuentra HUERTA.
    alternativas = {p for p in palabras} | {p[:-1] for p in palabras if p.endswith("S")}
    patron = "|".join(sorted(alternativas, key=len, reverse=True))

    mov = adm.movimientos()
    if mov.empty:
        return {"obra": obra, "patron": patron, "movimientos": 0,
                "monto": 0.0, "hojas": []}
    cols = [c for c in mov.columns if not c.startswith("_")]
    tx = mov[cols].astype(str)
    marca = tx.apply(lambda s: s.str.contains(patron, case=False, na=False,
                                              regex=True)).any(axis=1)
    filas = mov[marca & (mov["_clase"] == "detalle")]

    rotuladas = [c for c in cols
                 if lx.normalizar(c).startswith(("MONTO", "MATERIALES",
                                                 "IMPORTE"))]
    monto = sum(float(pd.to_numeric(filas[c], errors="coerce").fillna(0).sum())
                for c in rotuladas)
    sin_rotulo = [c for c in cols if c.startswith("col")
                  and pd.to_numeric(filas[c], errors="coerce").notna().any()]
    filas_sin_rotulo = int(
        filas[sin_rotulo].apply(pd.to_numeric, errors="coerce").notna().any(axis=1).sum()
    ) if sin_rotulo else 0
    return {"obra": obra, "patron": patron, "movimientos": len(filas),
            "monto_rotulado": round(monto, 2),
            "filas_con_importe_sin_rotular": filas_sin_rotulo,
            "hojas": sorted(filas["_hoja"].astype(str).str.strip().unique())}


def sin_correspondencia_declarada() -> pd.DataFrame:
    """Las obras sin equivalencia, con lo que hay sin atribuir detrás de cada."""
    filas = [menciones_sin_declarar(o) for o in obras_sin_etiqueta()]
    df = pd.DataFrame(filas)
    if df.empty:
        return df
    def _leyenda(r) -> str:
        if not r["movimientos"]:
            return "sin correspondencia declarada · sin movimiento encontrado"
        base = (f"sin correspondencia declarada · {r['movimientos']} "
                f"movimientos la mencionan · S/ {r['monto_rotulado']:,.2f} "
                f"sin atribuir")
        if r["filas_con_importe_sin_rotular"]:
            base += (f" · de esas mismas filas, "
                     f"{r['filas_con_importe_sin_rotular']} traen además "
                     f"importe en columnas que la hoja no rotula, así que el "
                     f"total sin atribuir es MAYOR que esta cifra")
        return base

    df["leyenda"] = df.apply(_leyenda, axis=1)
    return df.sort_values("monto_rotulado", ascending=False)


def obras_sin_etiqueta(eq: pd.DataFrame | None = None) -> list[str]:
    """Obras de AXION a las que ninguna fuente externa le puso nombre. No es un."""
    eq = equivalencias() if eq is None else eq
    con = set(eq.loc[eq["como"].isin(["exacta", "contenida"]), "obra_axion"])
    return [o for o in obras_axion().query("declarada_en_Project")["obra"]
            if o not in con]
