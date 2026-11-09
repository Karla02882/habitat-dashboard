"""INGESTA · LA CAJA ENCADENADA."""
from __future__ import annotations

import json
import pathlib
import re

RAIZ = pathlib.Path(__file__).resolve().parent.parent
CRUDOS = RAIZ / "data" / "raw_exports"
EXCEL_2026 = CRUDOS / "CONTROL DE GASTOS - LISBETH 2026.xlsx"
EXCEL_2025 = CRUDOS / "CONTROL DE GASTOS - LISBETH 2025.xlsx"
LIBRO_CMAC = CRUDOS / "SALDOS CAJA HUANCAYO.xlsx"
SALDOS_EXTERNOS = RAIZ / "config" / "saldos_externos.json"
# Lo ÚNICO que viaja a git y a Render.
CIERRES = RAIZ / "data" / "caja_encadenada" / "2026.json"

ANIO = 2026
MESES = ["ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO", "JULIO",
         "AGOSTO", "SETIEMBRE", "OCTUBRE", "NOVIEMBRE", "DICIEMBRE"]
NOMBRES = ["", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio",
           "Agosto", "Setiembre", "Octubre", "Noviembre", "Diciembre"]
_ALIAS = {"SEPTIEMBRE": "SETIEMBRE"}
CIERRE_AGOSTO = "2026-09-01"
MES_CIERRE_AGOSTO = 8
_ROTULOS_COLUMNA = {"FECHA", "MONTO", "CONCEPTO", "DE QUIEN RECIBO",
                    "INGRESO", "EGRESO"}


def _mes_de_hoja(nombre: str) -> int | None:
    n = nombre.replace("LIS", "").strip().upper()
    n = _ALIAS.get(n, n)
    return MESES.index(n) + 1 if n in MESES else None


def _es_caja(s, col: int) -> bool:
    """Si el cuadro al que pertenece la columna `col` es la caja en efectivo."""
    for c in range(col, 0, -1):
        for r in (4, 3, 2):
            v = s.cell(row=r, column=c).value
            if isinstance(v, str) and v.strip():
                x = " ".join(v.split()).upper()
                if x in _ROTULOS_COLUMNA:
                    continue
                return "GASTO MENSUAL" in x
    return True


def _queda_en_caja(ruta: pathlib.Path) -> dict[int, dict]:
    try:
        import openpyxl
    except ImportError:
        return {}
    if not ruta.exists():
        return {}
    w = openpyxl.load_workbook(ruta, data_only=True)
    out: dict[int, dict] = {}
    for n in w.sheetnames:
        m = _mes_de_hoja(n)
        if m is None:
            continue
        s = w[n]
        total, efectivo, cuadros = 0.0, 0.0, 0
        for r in range(1, s.max_row + 1):
            for c in range(2, s.max_column + 1):
                v = s.cell(row=r, column=c).value
                if not (isinstance(v, str) and "QUEDA EN CAJA" in v.upper()):
                    continue
                monto = s.cell(row=r, column=c - 1).value
                if not isinstance(monto, (int, float)):
                    continue
                total += float(monto)
                cuadros += 1
                if _es_caja(s, c):
                    efectivo += float(monto)
        if cuadros:
            out[m] = {"total": round(total, 2), "efectivo": round(efectivo, 2),
                      "cuadros": cuadros, "filas": s.max_row}
    return out


def _cmac_libro() -> dict:
    """Las cuentas CMAC del Libro Mayor: apertura del año y cierre de cada."""
    try:
        import openpyxl
    except ImportError:
        return {}
    if not LIBRO_CMAC.exists():
        return {}
    w = openpyxl.load_workbook(LIBRO_CMAC, data_only=True)
    apertura = 0.0
    por_hoja: dict[str, dict[int, float]] = {}
    generado = ""
    for n in w.sheetnames:
        s = w[n]
        sa: dict[int, float] = {}
        deb: dict[int, float] = {}
        cred: dict[int, float] = {}
        mes_actual = None
        for r in range(1, s.max_row + 1):
            b = s.cell(row=r, column=2).value
            con = str(s.cell(row=r, column=8).value or "").strip().upper()
            rot = str(s.cell(row=r, column=9).value or "").strip().upper()
            if isinstance(b, str) and b.strip().isdigit():
                mes_actual = int(b.strip())
            if con == "SALDO INICIAL" and mes_actual:
                sa[mes_actual] = float(s.cell(row=r, column=9).value or 0)
            elif rot.startswith("TOTAL MES"):
                nom = rot.replace("TOTAL MES", "").strip(" :").strip()
                nom = _ALIAS.get(nom, nom)
                if nom == "APERTURA":
                    mes_total = 0
                elif nom in MESES:
                    mes_total = MESES.index(nom) + 1
                else:
                    raise ValueError(f"Libro Mayor · hoja {n}: total de mes "
                                     f"que no se entiende: «{rot}»")
                deb[mes_total] = float(s.cell(row=r, column=10).value or 0)
                cred[mes_total] = float(s.cell(row=r, column=11).value or 0)
            elif isinstance(b, str) and "GENERADO" in b.upper():
                mm = re.search(r"(\d{2})/(\d{2})/(\d{4})", b)
                if mm:
                    generado = f"{mm.group(3)}-{mm.group(2)}-{mm.group(1)}"
        if 1 not in sa:
            raise ValueError(f"Libro Mayor · hoja {n}: sin SALDO INICIAL de enero")
        apertura += sa[1]
        cierres_hoja: dict[int, float] = {}
        for m in sorted(sa):
            if m not in deb:
                continue
            cierre = round(sa[m] + deb[m] - cred[m], 2)
            if (m + 1) in sa and abs(cierre - sa[m + 1]) > 0.005:
                raise ValueError(
                    f"Libro Mayor · hoja {n}: el cierre de {m:02d} "
                    f"({cierre:,.2f}) no es el S.ANTERIOR de {m + 1:02d} "
                    f"({sa[m + 1]:,.2f})")
            if (m + 1) in sa or deb[m] != 0 or cred[m] != 0:
                cierres_hoja[m] = cierre
        por_hoja[n] = cierres_hoja
    comunes = set.intersection(*(set(c) for c in por_hoja.values()))
    cierres: dict[int, float] = {}
    for m in sorted(comunes):
        if m > 1 and (m - 1) not in cierres:
            break
        cierres[m] = round(sum(c[m] for c in por_hoja.values()), 2)
    return {"apertura": round(apertura, 2), "cierres": cierres,
            "hojas": len(w.sheetnames), "generado": generado}


def _cierre_pasado_por_administracion() -> dict:
    if not SALDOS_EXTERNOS.exists():
        return {}
    d = json.loads(SALDOS_EXTERNOS.read_text(encoding="utf-8"))
    ap = (d.get("aperturas") or {}).get(CIERRE_AGOSTO) or {}
    cuentas = ap.get("cuentas") or {}
    if not cuentas:
        return {}
    es_cmac = {k: k.upper().startswith("CMAC") for k in cuentas}
    cmac = sum(v for k, v in cuentas.items() if es_cmac[k])
    otras = sum(v for k, v in cuentas.items() if not es_cmac[k])
    return {"cmac": round(cmac, 2), "otras": round(otras, 2),
            "n_cmac": sum(1 for k in cuentas if es_cmac[k]),
            "n_otras": sum(1 for k in cuentas if not es_cmac[k])}


def _de_excel() -> dict:
    """Los cierres, leídos de los archivos. Vacío si falta alguno."""
    adm26 = _queda_en_caja(EXCEL_2026)
    adm25 = _queda_en_caja(EXCEL_2025)
    libro = _cmac_libro()
    if not adm26 or not adm25 or not libro or 12 not in adm25:
        return {}
    cierres = libro["cierres"]
    arranque = {
        "administracion": adm25[12]["total"],
        "cmac": libro["apertura"],
        "total": round(adm25[12]["total"] + libro["apertura"], 2),
        "cuentas": adm25[12]["cuadros"] + libro["hojas"],
        "fuente": ("cierre de diciembre 2025 · Excel de Administración "
                   f"({adm25[12]['cuadros']} cuadros «QUEDA EN CAJA») + fila "
                   f"«Apertura» de las {libro['hojas']} CMAC en el Libro Mayor"),
    }
    meses: dict[int, dict] = {}
    for m in range(1, 13):
        if m in adm26 and m in cierres:
            meses[m] = {
                "mes": m, "nombre": NOMBRES[m],
                "administracion": adm26[m]["total"],
                "cmac": cierres[m],
                "real": round(adm26[m]["total"] + cierres[m], 2),
                "cuentas": adm26[m]["cuadros"] + libro["hojas"],
                "fuente": (f"Excel de Administración ({adm26[m]['cuadros']} "
                           f"cuadros) + Libro Mayor Caja Huancayo "
                           f"({libro['hojas']} CMAC, cierre de "
                           f"{NOMBRES[m].lower()})"),
            }
    pasado = _cierre_pasado_por_administracion()
    m8 = MES_CIERRE_AGOSTO
    if pasado and m8 in adm26 and m8 not in meses:
        efectivo = adm26[m8]["efectivo"]
        meses[m8] = {
            "mes": m8, "nombre": NOMBRES[m8],
            "administracion": round(pasado["otras"] + efectivo, 2),
            "cmac": pasado["cmac"],
            "real": round(pasado["otras"] + efectivo + pasado["cmac"], 2),
            "cuentas": pasado["n_cmac"] + pasado["n_otras"] + 1,
            "fuente": (f"cierre al 31-ago que pasó Administración el 01-set "
                       f"({pasado['n_cmac']} CMAC del banco + "
                       f"{pasado['n_otras']} BCP/BBVA según AXION) + el "
                       f"efectivo de su Excel al 28-ago"),
        }
    return {
        "anio": ANIO,
        "fuente": ("Excel de Administración 2025 y 2026 (celdas «QUEDA EN "
                   "CAJA») + Libro Mayor Caja Huancayo (4 CMAC) + el cierre "
                   "de agosto pasado el 01-set (config/saldos_externos.json)"),
        "libro_generado": libro.get("generado", ""),
        "arranque": arranque,
        "meses": meses,
    }


def cierres() -> dict:
    """Arranque y saldo en cuentas por mes. Lee el JSON publicado —lo único."""
    pub: dict = {}
    if CIERRES.exists():
        try:
            pub = json.loads(CIERRES.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 — un JSON roto no tumba el tablero
            pub = {}
    error = ""
    try:
        vivo = _de_excel()
    except Exception as e:  # noqa: BLE001 — se declara, no se inventa
        vivo, error = {}, f"{type(e).__name__}: {e}"
    base = vivo or pub
    if not base or not base.get("meses"):
        return {"hay": False, "error_excel": error,
                "motivo": "faltan los Excels de Administración o el Libro Mayor"}
    meses = {int(k): v for k, v in base["meses"].items()}
    return {"hay": True, "anio": base.get("anio", ANIO),
            "fuente": base.get("fuente", ""),
            "libro_generado": base.get("libro_generado", ""),
            "arranque": base["arranque"], "meses": meses,
            "de_excel": bool(vivo), "error_excel": error}


def armar(flujo: dict | None) -> dict:
    """La cadena completa para el payload, mes a mes."""
    c = cierres()
    if not c.get("hay"):
        return c
    fl = flujo or {}
    if int(fl.get("anio") or 0) != int(c["anio"]):
        return {"hay": False,
                "motivo": f"el flujo es de {fl.get('anio')} y los cierres de {c['anio']}"}
    por_mes = {int(m.get("mes")): m for m in (fl.get("meses") or [])}
    filas = []
    acum = float(c["arranque"]["total"])
    ultimo = None
    for m in range(1, 13):
        fm = por_mes.get(m)
        if not fm or not (fm.get("pasado") or fm.get("en_curso")):
            continue
        entro = float(fm.get("cobros_libro") or 0)
        salio = float(fm.get("salio") or 0)
        if entro == 0 and salio == 0:
            continue
        inicial = acum
        acum = round(inicial + entro - salio, 2)
        r = c["meses"].get(m)
        fila = {"mes": m, "nombre": NOMBRES[m], "inicial": round(inicial, 2),
                "entro": round(entro, 2), "salio": round(salio, 2),
                "calculado": acum, "en_curso": bool(fm.get("en_curso")),
                "real": None, "dif": None, "administracion": None,
                "cmac": None, "cuentas": None, "fuente": ""}
        if r:
            fila.update({"real": r["real"], "dif": round(r["real"] - acum, 2),
                         "administracion": r["administracion"], "cmac": r["cmac"],
                         "cuentas": r.get("cuentas"), "fuente": r.get("fuente", "")})
            ultimo = fila
        filas.append(fila)
    return {
        "hay": True, "anio": c["anio"], "arranque": c["arranque"],
        "fuente": c["fuente"], "libro_generado": c.get("libro_generado", ""),
        "de_excel": c.get("de_excel", False), "error_excel": c.get("error_excel", ""),
        "meses": filas,
        "cierre": ({"mes": ultimo["mes"], "nombre": ultimo["nombre"],
                    "calculado": ultimo["calculado"], "real": ultimo["real"],
                    "dif": ultimo["dif"]} if ultimo else None),
    }
