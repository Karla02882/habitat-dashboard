"""INGESTA · lo FIRMADO según la contadora."""
from __future__ import annotations

import json
import pathlib

RAIZ = pathlib.Path(__file__).resolve().parent.parent
EXCEL = RAIZ / "data" / "raw_exports" / "REPORTE DE VENTAS 2025.xlsx"
TOTALES = RAIZ / "data" / "ventas_contadora" / "2025.json"

MESES = ["ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO", "JULIO",
         "AGOSTO", "SEPTIEMBRE", "OCTUBRE", "NOVIEMBRE", "DICIEMBRE"]


def _del_excel() -> dict:
    """Los doce totales, leídos del Excel de la contadora. Sin openpyxl o sin."""
    try:
        import openpyxl
    except ImportError:
        return {}
    if not EXCEL.exists():
        return {}
    w = openpyxl.load_workbook(EXCEL, data_only=True)
    hojas = {n.strip().upper(): n for n in w.sheetnames}
    out = {}
    for i, nombre in enumerate(MESES, start=1):
        real = hojas.get(nombre)
        if real is None:
            continue
        s = w[real]
        monto, celda, roto = None, "", False
        for r in range(1, min(s.max_row, 80) + 1):
            fila = [s.cell(row=r, column=c).value for c in range(1, 16)]
            if not any(isinstance(x, str) and "total ventas" in x.lower()
                       for x in fila):
                continue
            for c, y in enumerate(fila, start=1):
                if isinstance(y, str) and "#REF" in y:
                    roto = True
                if isinstance(y, (int, float)) and y > 1000:
                    monto = float(y)
                    celda = f"{chr(64 + c)}{r}"
                    break
            break
        if monto is not None or roto:
            out[i] = {"mes": i, "nombre": nombre.capitalize(),
                      "monto": monto, "celda": celda, "roto": roto}
    return out


def totales(anio: int = 2025) -> dict:
    """Lo firmado por mes según la contadora, para la hoja de Ventas."""
    pub = {}
    if TOTALES.exists():
        try:
            d = json.loads(TOTALES.read_text(encoding="utf-8"))
            pub = {int(k): v for k, v in (d.get("meses") or {}).items()}
        except Exception:  # noqa: BLE001 — un JSON roto no tumba el tablero
            pub = {}
    vivo = _del_excel()
    meses = {**pub, **vivo}
    if not meses:
        return {"hay": False,
                "motivo": "el Excel de ventas de la contadora no está cargado"}
    con = [m for m in meses.values() if m.get("monto")]
    return {
        "hay": True,
        "anio": anio,
        "fuente": "Excel de ventas de la contadora · un total por hoja",
        "de_excel": bool(vivo),
        "meses": [meses[k] for k in sorted(meses)],
        "total": round(sum(m["monto"] for m in con), 2),
        "meses_con_cifra": len(con),
        "rotos": [m["nombre"] for m in meses.values() if m.get("roto")],
    }
