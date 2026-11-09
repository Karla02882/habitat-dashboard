"""INGESTA · EL CONTROL MES A MES, CUENTA POR CUENTA."""
from __future__ import annotations

import datetime as dt
import json
import pathlib

RAIZ = pathlib.Path(__file__).resolve().parent.parent
CRUDOS = RAIZ / "data" / "raw_exports"
EXCEL_2026 = CRUDOS / "CONTROL DE GASTOS - LISBETH 2026.xlsx"
LIBRO_CMAC = CRUDOS / "SALDOS CAJA HUANCAYO.xlsx"
SALDOS_EXTERNOS = RAIZ / "config" / "saldos_externos.json"
CONGELADOS = RAIZ / "config" / "cierres_congelados.json"

ANIO = 2026
MESES = ["ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO", "JULIO",
         "AGOSTO", "SETIEMBRE", "OCTUBRE", "NOVIEMBRE", "DICIEMBRE"]
_ALIAS = {"SEPTIEMBRE": "SETIEMBRE"}
_ROTULOS_COLUMNA = {"FECHA", "MONTO", "CONCEPTO", "DE QUIEN RECIBO",
                    "INGRESO", "EGRESO"}
# El rótulo de cada hoja del Libro Mayor contra el nombre de la cuenta en AXION.
HOJA_CMAC = {
    "ESCALAR": "CMAC HUANCAYO - ESCALAR Y HABITAT GRUPO INMOBILIARIO SAC",
    "HABITAT EIRL": "CMAC HUANCAYO - HABITAT BIENES RAICES EIRL",
    "CORPORACION YEAN": "CMAC HUANCAYO - CORPORACION HABITAT SAC - YEAN",
    "CORPORACION GLORIA": "CMAC HUANCAYO - CORPORACION HABITAT SAC - GLORIA",
}


def _mes_de_hoja(nombre: str) -> int | None:
    n = nombre.replace("LIS", "").strip().upper()
    n = _ALIAS.get(n, n)
    return MESES.index(n) + 1 if n in MESES else None


def _rotulo_cuadro(s, col: int) -> str:
    """El rótulo del cuadro al que pertenece la columna: el texto más cercano."""
    for c in range(col, 0, -1):
        for r in (4, 3, 2, 1):
            v = s.cell(row=r, column=c).value
            if isinstance(v, str) and v.strip():
                x = " ".join(v.split()).upper()
                if x in _ROTULOS_COLUMNA:
                    continue
                return x
    return ""


def _excel_administracion() -> dict:
    try:
        import openpyxl
    except ImportError:
        return {}
    if not EXCEL_2026.exists():
        return {}
    w = openpyxl.load_workbook(EXCEL_2026, data_only=True)
    out: dict[str, dict[int, float]] = {}
    for n in w.sheetnames:
        mes = _mes_de_hoja(n)
        if mes is None:
            continue
        s = w[n]
        for r in range(1, s.max_row + 1):
            for c in range(2, s.max_column + 1):
                v = s.cell(row=r, column=c).value
                if not (isinstance(v, str) and "QUEDA EN CAJA" in v.upper()):
                    continue
                monto = s.cell(row=r, column=c - 1).value
                if not isinstance(monto, (int, float)):
                    continue
                rot = _rotulo_cuadro(s, c)
                cuenta = "EFECTIVO" if ("GASTO MENSUAL" in rot or not rot) else rot
                out.setdefault(cuenta, {})[mes] = round(float(monto), 2)
    return out


def _libro_cmac() -> dict:
    """{cuenta: {mes: cierre}} del Libro Mayor de Caja Huancayo."""
    try:
        import openpyxl
    except ImportError:
        return {}
    if not LIBRO_CMAC.exists():
        return {}
    w = openpyxl.load_workbook(LIBRO_CMAC, data_only=True)
    out: dict[str, dict[int, float]] = {}
    for n in w.sheetnames:
        cuenta = HOJA_CMAC.get(n.strip().upper())
        if not cuenta:
            continue
        s = w[n]
        sa: dict[int, float] = {}
        deb: dict[int, float] = {}
        cred: dict[int, float] = {}
        mes_actual = None
        ultima_fecha = None
        for r in range(1, s.max_row + 1):
            b = s.cell(row=r, column=2).value
            con = str(s.cell(row=r, column=8).value or "").strip().upper()
            rot = str(s.cell(row=r, column=9).value or "").strip().upper()
            f = s.cell(row=r, column=3).value
            if isinstance(f, dt.datetime):
                ultima_fecha = f.date()
            if isinstance(b, str) and b.strip().isdigit():
                mes_actual = int(b.strip())
            if con == "SALDO INICIAL" and mes_actual:
                sa[mes_actual] = float(s.cell(row=r, column=9).value or 0)
            elif rot.startswith("TOTAL MES"):
                nom = rot.replace("TOTAL MES", "").strip(" :").strip()
                nom = _ALIAS.get(nom, nom)
                if nom not in MESES:
                    continue
                m = MESES.index(nom) + 1
                deb[m] = float(s.cell(row=r, column=10).value or 0)
                cred[m] = float(s.cell(row=r, column=11).value or 0)
        tope = ultima_fecha.month if ultima_fecha and ultima_fecha.year == ANIO else 12
        for m in sorted(sa):
            if m in deb and m <= tope:
                out.setdefault(cuenta, {})[m] = round(sa[m] + deb[m] - cred[m], 2)
    return out


def _banco_externo() -> dict:
    """{cuenta: {mes: saldo}} con lo que Administración bajó del banco."""
    if not SALDOS_EXTERNOS.exists():
        return {}
    try:
        d = json.loads(SALDOS_EXTERNOS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    out: dict[str, dict[int, float]] = {}
    for fecha, v in (d.get("aperturas") or {}).items():
        try:
            anio, mes = int(fecha[:4]), int(fecha[5:7])
        except (TypeError, ValueError):
            continue
        cierre_mes = mes - 1 if mes > 1 else 12
        if (anio if mes > 1 else anio - 1) != ANIO:
            continue
        fue = v.get("fuente") or {}
        for cuenta, saldo in (v.get("cuentas") or {}).items():
            if str(fue.get(cuenta, "")).lower() != "banco":
                continue
            out.setdefault(cuenta, {})[cierre_mes] = round(float(saldo), 2)
    return out


def _banco_al_dia() -> dict:
    if not SALDOS_EXTERNOS.exists():
        return {}
    try:
        d = json.loads(SALDOS_EXTERNOS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    hoy = dt.date.today().isoformat()
    fechas = sorted(f for f in (d.get("al_dia") or {}) if f <= hoy)
    if not fechas:
        return {}
    f = fechas[-1]
    v = (d.get("al_dia") or {})[f]
    return {"fecha": f,
            "fuente": v.get("_fuente", ""),
            "faltan": v.get("_faltan", ""),
            "cuentas": {k: round(float(x), 2)
                        for k, x in (v.get("cuentas") or {}).items()},
            "fuente_de": dict(v.get("fuente") or {})}


def _congelados() -> dict:
    """{cuenta: {mes: cierre}} de la foto guardada, o vacío si no hay."""
    if not CONGELADOS.exists():
        return {}
    try:
        d = json.loads(CONGELADOS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    out: dict[str, dict[int, float]] = {}
    for cuenta, meses in (d.get("cierres") or {}).items():
        for m, v in meses.items():
            try:
                out.setdefault(cuenta, {})[int(m)] = round(float(v), 2)
            except (TypeError, ValueError):
                continue
    return out


def control(df) -> dict:
    """El cuadro completo. `df` son los movimientos crudos de AXION."""
    from src import movimientos

    ap = movimientos.aperturas()
    adm = _excel_administracion()
    adm_cmac = _libro_cmac()
    banco = _banco_externo()
    foto = _congelados()
    bhoy = _banco_al_dia()

    d = df.copy()
    d["cu"] = d["cuenta"].fillna("").astype(str).str.strip().replace("", "SIN BANCO")
    con = d["concepto"].fillna("").astype(str).str.strip().str.upper()
    d["es_saldo"] = d["clase"].eq("presupuesto") & con.str.startswith("SALDO")
    d = d[d["fecha_n"].dt.year.eq(ANIO)]

    cuentas = []
    for cu in sorted(set(d["cu"]) | set(ap)):
        meses_ap = ap.get(cu) or {}
        arranque = meses_ap.get(f"{ANIO}-01")
        # Sin fila de enero se toma la más vieja: es el arranque que tenga.
        if arranque is None and meses_ap:
            arranque = meses_ap[min(meses_ap)]
        g = d[d["cu"].eq(cu)]
        saldo = arranque or 0.0
        meses = []
        for m in range(1, 13):
            gm = g[g["fecha_n"].dt.month.eq(m)]
            if gm.empty and m > int(d["fecha_n"].dt.month.max() or 1):
                break
            mov = gm[~gm["es_saldo"]]
            ven = float(mov.loc[mov["clase"].eq("venta"), "monto_n"].sum())
            tra = float(mov.loc[mov["clase"].eq("presupuesto"), "monto_n"].sum())
            ent = ven + tra
            sal = float(mov.loc[mov["clase"].eq("gasto"), "monto_n"].sum())
            saldo = round(saldo + ent - sal, 2)
            dup = float(gm.loc[gm["es_saldo"], "monto_n"].sum())
            fila = {"m": m, "ax": saldo, "e": round(ent, 2), "v": round(ven, 2),
                    "tr": round(tra, 2), "s": round(sal, 2), "n": int(len(mov))}
            if dup:
                fila["dup"] = round(dup, 2)
            ref = (adm_cmac.get(cu) or {}).get(m)
            fuente_ref = "Libro Mayor"
            if ref is None:
                ref = (adm.get(cu) or {}).get(m)
                fuente_ref = "Excel"
            if ref is not None:
                fila["adm"] = ref
                fila["adm_f"] = fuente_ref
            bn = (banco.get(cu) or {}).get(m)
            if bn is not None:
                fila["bco"] = bn
            era = (foto.get(cu) or {}).get(m)
            if era is not None and abs(era - saldo) > 0.01:
                fila["era"] = era
            meses.append(fila)
        if arranque is None and not meses:
            continue
        pz = cu.split(" - ")
        reg = {"cu": cu, "banco": pz[0] or cu,
               "cuenta": " - ".join(pz[1:]) or "—",
               "ap": arranque, "meses": meses}
        if cu in (bhoy.get("cuentas") or {}):
            reg["bhoy"] = bhoy["cuentas"][cu]
            f_b = (bhoy.get("fuente_de") or {}).get(cu)
            if f_b and f_b != "banco":
                reg["bhoy_f"] = f_b
            import pandas as pd
            corte_f = pd.Timestamp(bhoy["fecha"])
            gf = g[(~g["es_saldo"]) & (g["fecha_n"] <= corte_f)]
            ent_f = float(gf.loc[gf["clase"].isin(["venta", "presupuesto"]), "monto_n"].sum())
            sal_f = float(gf.loc[gf["clase"].eq("gasto"), "monto_n"].sum())
            reg["axb"] = round((arranque or 0.0) + ent_f - sal_f, 2)
        cuentas.append(reg)
    cuentas.sort(key=lambda x: -(x["meses"][-1]["ax"] if x["meses"] else 0))
    return {
        "anio": ANIO,
        "cuentas": cuentas,
        "banco_al_dia": bhoy,
        "fuentes": {
            "axion": "tabla SaldoInicial + Registro de Movimientos, sin las filas SALDO",
            "administracion": ("Excel de Administración y Libro Mayor de Caja Huancayo"
                               if (adm or adm_cmac) else "no disponible acá"),
            "banco": "saldos que Administración bajó del banco" if banco else "no disponible acá",
        },
    }
