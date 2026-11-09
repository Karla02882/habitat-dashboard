"""INGESTA · LAS VALORIZACIONES DE OBRA."""
from __future__ import annotations

import hashlib
import pathlib
import tempfile

import pandas as pd

from . import drive

C_ITEM, C_DESC, C_UND, C_METRADO = 0, 1, 2, 3
C_CU, C_COSTO = 4, 5
C_ACUM_METRADO, C_ACUM_MONTO, C_ACUM_PCT = 12, 13, 14
FILA_CUERPO = 14          # la cabecera ocupa 11, 12 y 13

# GRAFICA — las dos tablas, mes a mes
G_FILA_CUERPO = 32
G_PROG = (0, 1, 2, 3, 4)  # mes · parcial S/ · acum S/ · % parcial · % acum
G_EJEC = (6, 7, 8, 9, 10)

CIERRES = ("COSTO DIRECTO", "GASTOS GENERALES", "UTILIDAD", "SUBTOTAL",
           "IGV", "TOTAL")


def _n(v):
    """Un número, o None. Nunca revienta con texto."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if pd.isna(f) else f


def _t(v) -> str:
    s = "" if v is None or (isinstance(v, float) and pd.isna(v)) else str(v).strip()
    return "" if s.lower() in ("nan", "none") else " ".join(s.split())


def _abrir(ruta: pathlib.Path):
    """El ExcelFile, probando los dos motores. .xls viejo y .xlsx nuevo."""
    for motor in ("openpyxl", "xlrd"):
        try:
            return pd.ExcelFile(ruta, engine=motor)
        except Exception:  # noqa: BLE001
            continue
    return None


def _hoja(x, arranca: str):
    """La hoja cuyo nombre empieza así, ignorando espacios y mayúsculas: el."""
    for h in x.sheet_names:
        if h.strip().upper().startswith(arranca.upper()):
            return h
    return None


def _partidas(x) -> dict:
    """Las partidas de VAL 01, con su presupuesto y su avance acumulado."""
    h = _hoja(x, "VAL 01")
    if not h:
        return {"error": "el archivo no trae la hoja VAL 01"}
    df = x.parse(h, header=None)
    if df.shape[1] <= C_ACUM_PCT:
        return {"error": f"VAL 01 trae {df.shape[1]} columnas y se esperaban "
                         f"al menos {C_ACUM_PCT + 1}"}

    caps: list[dict] = []
    actual: dict | None = None
    cierre: dict[str, float] = {}
    for i in range(FILA_CUERPO, df.shape[0]):
        desc = _t(df.iat[i, C_DESC])
        if not desc:
            continue
        crudo_und = df.iat[i, C_UND]
        und = _t(crudo_und) if isinstance(crudo_und, str) else ""
        item = _t(df.iat[i, C_ITEM])
        if not und:
            arr = desc.upper()
            if any(arr.startswith(c) for c in CIERRES):
                v = _n(df.iat[i, C_COSTO])
                if v is not None and arr not in cierre:
                    cierre[arr] = v
                continue
            if item:                       # título de capítulo
                actual = {"item": item, "nombre": desc, "partidas": []}
                caps.append(actual)
            continue
        p = {
            "item": item, "nombre": desc, "und": und,
            "metrado": _n(df.iat[i, C_METRADO]),
            "cu": _n(df.iat[i, C_CU]),
            "costo": _n(df.iat[i, C_COSTO]) or 0.0,
            "avance_monto": _n(df.iat[i, C_ACUM_MONTO]) or 0.0,
            "avance_pct": _n(df.iat[i, C_ACUM_PCT]),
        }
        if actual is None:
            actual = {"item": "", "nombre": "(sin capítulo)", "partidas": []}
            caps.append(actual)
        actual["partidas"].append(p)

    caps = [c for c in caps if c["partidas"]]
    todas = [p for c in caps for p in c["partidas"]]
    if not todas:
        return {"error": "VAL 01 no trae ninguna partida con unidad"}

    for c in caps:
        c["costo"] = round(sum(p["costo"] for p in c["partidas"]), 2)
        c["avance_monto"] = round(sum(p["avance_monto"] for p in c["partidas"]), 2)
        c["avance_pct"] = (c["avance_monto"] / c["costo"]) if c["costo"] else None
        c["n"] = len(c["partidas"])

    presu = round(sum(p["costo"] for p in todas), 2)
    avance = round(sum(p["avance_monto"] for p in todas), 2)
    cd = cierre.get("COSTO DIRECTO")
    dif = None if cd is None else round(presu - cd, 2)
    return {
        "caps": caps, "n": len(todas), "capn": len(caps),
        "presupuesto": presu, "avance_monto": avance,
        "avance_pct": (avance / presu) if presu else None,
        "costo_directo": cd, "dif_costo_directo": dif,
        "cuadra": dif is not None and abs(dif) < 0.05,
    }


def _curva(x) -> dict:
    """La curva S de la hoja GRAFICA: programado y ejecutado, mes a mes."""
    h = _hoja(x, "GRAFICA")
    if not h:
        return {"hay": False, "motivo": "el archivo no trae la hoja GRAFICA"}
    df = x.parse(h, header=None)

    def leer(cols):
        cm, cp, ca, pp, pa = cols
        if df.shape[1] <= pa:
            return []
        out = []
        for i in range(G_FILA_CUERPO, df.shape[0]):
            mes = _t(df.iat[i, cm])
            if not mes:
                continue
            if mes.upper().startswith("TOTAL"):
                break
            out.append({
                "mes": mes,
                "parcial": _n(df.iat[i, cp]),
                "acumulado": _n(df.iat[i, ca]),
                "pct_parcial": _n(df.iat[i, pp]),
                "pct_acumulado": _n(df.iat[i, pa]),
            })
        return out

    prog, ejec = leer(G_PROG), leer(G_EJEC)
    puntos = [e for e in ejec if (e["acumulado"] or 0) > 0]
    return {
        "hay": bool(prog or ejec),
        "programado": prog, "ejecutado": ejec,
        "valorizaciones": len(puntos),
        "ultimo_ejecutado": puntos[-1] if puntos else None,
    }


def _datos(x) -> dict:
    """Presupuesto, plazo y % de avance de la hoja DATOS GN. Sin personas: no."""
    h = _hoja(x, "DATOS GN")
    if not h:
        return {}
    df = x.parse(h, header=None)
    quiero = {"VALOR REFERENCIAL": "referencial", "MONTO CONTRATADO": "contratado",
              "PLAZO DE EJECUCION": "plazo", "PORCENTAJE DE AVANCE": "pct",
              "MODALIDAD": "modalidad"}
    out: dict = {}
    for i in range(df.shape[0]):
        rot = _t(df.iat[i, 1]).upper() if df.shape[1] > 1 else ""
        if not rot:
            continue
        for arranca, clave in quiero.items():
            if rot.startswith(arranca) and clave not in out:
                v = df.iat[i, 2] if df.shape[1] > 2 else None
                out[clave] = _n(v) if clave in ("referencial", "contratado", "pct") else _t(v)
    return out


def _una(archivo: dict, ruta: pathlib.Path) -> dict:
    x = _abrir(ruta)
    if x is None:
        return {"obra": archivo["nombre"], "error": "no se pudo abrir el Excel"}
    try:
        d = _partidas(x)
        if d.get("error"):
            return {"obra": archivo["nombre"], "error": d["error"]}
        return {
            "obra": archivo["nombre"].upper(),
            "archivo": archivo["nombre"],
            "fecha": archivo.get("fecha", ""),
            "huella": hashlib.md5(ruta.read_bytes()).hexdigest()[:12],
            **d,
            "curva": _curva(x),
            "datos": _datos(x),
        }
    finally:
        try:
            x.close()
        except Exception:  # noqa: BLE001
            pass


def calcular() -> dict:
    """Las valorizaciones publicadas en el Drive, una por archivo."""
    if not drive.hay_credencial():
        return {"hay": False, "motivo": "no hay credencial del Drive"}
    try:
        carpeta = drive.subcarpeta("VALORIZACIONES")
    except Exception as e:  # noqa: BLE001
        return {"hay": False, "motivo": f"no se pudo leer el Drive: {type(e).__name__}"}
    if not carpeta:
        return {"hay": False, "motivo": "no existe la carpeta VALORIZACIONES en el Drive"}

    archivos = [a for a in drive.listar(carpeta) if not a["carpeta"]]
    if not archivos:
        return {"hay": False, "motivo": "la carpeta VALORIZACIONES está vacía"}

    obras, fallidos = [], []
    with tempfile.TemporaryDirectory(prefix="val_", ignore_cleanup_errors=True) as tmp:
        for a in archivos:
            ruta = pathlib.Path(tmp) / (f"{a['id']}.xlsx" if a["tipo"] != drive.MIME_SHEETS
                                        else f"{a['id']}.xlsx")
            if a["tipo"] == "application/vnd.ms-excel":
                ruta = ruta.with_suffix(".xls")
            if drive.bajar(a, ruta) is None:
                fallidos.append({"archivo": a["nombre"], "motivo": "no se pudo bajar"})
                continue
            r = _una(a, ruta)
            if r.get("error"):
                fallidos.append({"archivo": a["nombre"], "motivo": r["error"]})
            else:
                obras.append(r)

    porhuella: dict[str, list] = {}
    for o in obras:
        porhuella.setdefault(o["huella"], []).append(o["obra"])
    repetidos = [v for v in porhuella.values() if len(v) > 1]
    for o in obras:
        o["repetido_con"] = [x for x in porhuella[o["huella"]] if x != o["obra"]]

    return {
        "hay": bool(obras),
        "obras": obras,
        "fallidos": fallidos,
        "repetidos": repetidos,
        "fuente": "Drive · VALORIZACIONES (cuenta de servicio, solo lectura)",
        "motivo": "" if obras else "ninguna valorización se pudo leer",
    }
