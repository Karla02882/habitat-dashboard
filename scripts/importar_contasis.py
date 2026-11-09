"""EXTRACTOR · Cierres mensuales de ContaSis → config/contasis_mensual.json."""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from datetime import datetime
from pathlib import Path

import openpyxl

RAIZ = Path(__file__).resolve().parents[1]
CRUDOS = RAIZ / "data" / "raw_exports"
# El orden es la prioridad ante dos archivos del mismo cierre: gana el último.
CARPETAS = [CRUDOS / "contasis_mensual"]
SALIDA = RAIZ / "config" / "contasis_mensual.json"

# Las cuatro empresas del grupo, por RUC — los mismos de `src/contasis.py`.
EMPRESAS = {
    "20605163557": "Habitat Bienes Raíces",
    "20607720224": "Corporación Habitat",
    "20608888188": "Constructora Velasco León",
    "20611216565": "Escalar y Habitat",
}
MESES = {"ENERO": 1, "FEBRERO": 2, "MARZO": 3, "ABRIL": 4, "MAYO": 5,
         "JUNIO": 6, "JULIO": 7, "AGOSTO": 8, "SETIEMBRE": 9,
         "SEPTIEMBRE": 9, "OCTUBRE": 10, "NOVIEMBRE": 11, "DICIEMBRE": 12}


def norm(s) -> str:
    """Mayúsculas, sin tildes y con un solo espacio: los rótulos de ContaSis."""
    t = unicodedata.normalize("NFD", str(s or "")).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", t).strip().upper()


def limpio(s) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()


def num(v):
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).replace(",", ""))
    except ValueError:
        return None


def leer(f: Path) -> list:
    ws = openpyxl.load_workbook(f, data_only=True, read_only=True).worksheets[0]
    return [list(r) for r in ws.iter_rows(values_only=True)]


def textos(filas, desde, hasta) -> list[str]:
    out = []
    for r in filas[desde:hasta]:
        out += [limpio(c) for c in r if c not in (None, "")]
    return out


def membrete(filas) -> dict:
    """Empresa, RUC, título, período y fecha de generación del archivo."""
    arriba = textos(filas, 0, 8)
    ruc = next((re.sub(r"\D", "", t) for t in arriba if "R.U.C" in t.upper()), "")
    titulo = ""
    for i in (5, 4, 6):
        if i < len(filas):
            t = next((limpio(c) for c in filas[i] if c not in (None, "")), "")
            if t and not t.upper().startswith("PERIODO"):
                titulo = t
                break
    periodo_txt = next((t for t in arriba if t.upper().startswith("PERIODO")), "")
    fecha_txt = next((t for t in arriba if norm(t).startswith("AL ")
                      and re.search(r"\d{4}", t)), "")
    gen = None
    for r in filas[-6:]:
        for c in r:
            m = re.search(r"el (\d{2})/(\d{2})/(\d{4})", str(c or ""))
            if m:
                gen = datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    return {"ruc": ruc, "titulo": titulo, "periodo_txt": periodo_txt,
            "fecha_txt": fecha_txt, "generado": gen}


def tipo_de(titulo: str) -> str | None:
    t = norm(titulo)
    if "SITUACION FINANCIERA" in t:
        return "esf"
    if t.startswith("ESTADO DE RESULTADOS"):
        return "er"
    if "BALANCE COMPROBACION" in t:
        return "balance"
    if "LIBRO CAJA ANALITICO" in t:
        return "caja_analitico"
    if "LIBRO CAJA GENERAL" in t:
        return "caja_general"
    if t.startswith("REGISTRO DE VENTAS"):
        return "ventas"
    if t.startswith("REGISTRO DE COMPRAS"):
        return "compras"
    return None


def tipo_por_columnas(filas) -> str | None:
    cab = [norm(c) for c in filas[7]] if len(filas) > 7 else []
    if not any(c.startswith("F.EMIS") for c in cab):
        return None
    if "INAFECTO" in cab or "EXONERADO" in cab:
        return "ventas"
    if "NO GRAVADO" in cab:
        return "compras"
    return None


def mes_de(texto: str) -> int | None:
    t = norm(texto)
    for nombre, n in MESES.items():
        if re.search(rf"\b{nombre}\b", t):
            return n
    return None


def periodo_de(m: dict) -> tuple[int, int] | None:
    """(año, mes) del cierre que el archivo dice cubrir."""
    for txt in (m["fecha_txt"], m["periodo_txt"]):
        mes = mes_de(txt)
        anio = re.search(r"(\d{4})", txt or "")
        if mes and anio:
            return int(anio.group(1)), mes
    mes = mes_de(m["titulo"])
    if mes and m["generado"]:
        g = m["generado"]
        # Un cierre de diciembre generado en enero es del año anterior.
        return (g.year - 1 if mes > g.month else g.year), mes
    return None


def clave(anio: int, mes: int) -> str:
    return f"{anio:04d}-{mes:02d}"


def _fin(fila) -> bool:
    return any("GENERADO AUTOMATICAMENTE" in norm(c) for c in fila if c)


def estado_dos_columnas(filas) -> tuple[list, list]:
    """ESF y ER: rótulo en B y cifra en C a la izquierda; rótulo en E y cifra."""
    izq, der = [], []
    for r in filas[9:]:
        if _fin(r):
            break
        r = r + [None] * (6 - len(r))
        if r[1] not in (None, ""):
            izq.append([limpio(r[1]), num(r[2])])
        if r[4] not in (None, ""):
            der.append([limpio(r[4]), num(r[5])])
    return izq, der


def buscar(lineas: list, *rotulos) -> float | None:
    """La cifra del primer rótulo que empiece como alguno de los pedidos."""
    for rot in rotulos:
        for k, v in lineas:
            if norm(k).startswith(norm(rot)):
                return v
    return None


PCGE = {
    "10": "EFECTIVO Y EQUIVALENTES DE EFECTIVO", "11": "INVERSIONES FINANCIERAS",
    "12": "CUENTAS POR COBRAR COMERCIALES - TERCEROS",
    "13": "CUENTAS POR COBRAR COMERCIALES - RELACIONADAS",
    "14": "CUENTAS POR COBRAR AL PERSONAL, ACCIONISTAS Y DIRECTORES",
    "16": "CUENTAS POR COBRAR DIVERSAS - TERCEROS",
    "17": "CUENTAS POR COBRAR DIVERSAS - RELACIONADAS",
    "18": "SERVICIOS Y OTROS CONTRATADOS POR ANTICIPADO", "20": "MERCADERÍAS",
    "21": "PRODUCTOS TERMINADOS", "23": "PRODUCTOS EN PROCESO",
    "25": "MATERIALES AUXILIARES, SUMINISTROS Y REPUESTOS",
    "28": "EXISTENCIAS POR RECIBIR", "31": "INVERSIONES INMOBILIARIAS",
    "33": "INMUEBLES, MAQUINARIA Y EQUIPO",
    "39": "DEPRECIACIÓN, AMORTIZACIÓN Y AGOTAMIENTO ACUMULADOS",
    "40": "TRIBUTOS Y APORTES POR PAGAR", "41": "REMUNERACIONES Y PARTICIPACIONES POR PAGAR",
    "42": "CUENTAS POR PAGAR COMERCIALES - TERCEROS",
    "43": "CUENTAS POR PAGAR COMERCIALES - RELACIONADAS",
    "44": "CUENTAS POR PAGAR A LOS ACCIONISTAS Y DIRECTORES",
    "45": "OBLIGACIONES FINANCIERAS", "46": "CUENTAS POR PAGAR DIVERSAS - TERCEROS",
    "47": "CUENTAS POR PAGAR DIVERSAS - RELACIONADAS", "48": "PROVISIONES",
    "49": "PASIVO DIFERIDO", "50": "CAPITAL", "56": "RESULTADOS NO REALIZADOS",
    "58": "RESERVAS", "59": "RESULTADOS ACUMULADOS", "60": "COMPRAS",
    "61": "VARIACIÓN DE EXISTENCIAS", "62": "GASTOS DE PERSONAL Y DIRECTORES",
    "63": "GASTOS DE SERVICIOS PRESTADOS POR TERCEROS", "64": "GASTOS POR TRIBUTOS",
    "65": "OTROS GASTOS DE GESTIÓN", "66": "PÉRDIDA POR MEDICIÓN DE ACTIVOS",
    "67": "GASTOS FINANCIEROS", "68": "VALUACIÓN Y DETERIORO DE ACTIVOS Y PROVISIONES",
    "69": "COSTO DE VENTAS", "70": "VENTAS", "71": "VARIACIÓN DE LA PRODUCCIÓN ALMACENADA",
    "73": "DESCUENTOS, REBAJAS Y BONIFICACIONES OBTENIDOS", "75": "OTROS INGRESOS DE GESTIÓN",
    "76": "GANANCIA POR MEDICIÓN DE ACTIVOS", "77": "INGRESOS FINANCIEROS",
    "79": "CARGAS IMPUTABLES A CUENTAS DE COSTOS Y GASTOS",
    "90": "COSTOS DE PRODUCCIÓN", "94": "GASTOS ADMINISTRATIVOS",
    "95": "GASTOS DE VENTAS", "97": "GASTOS FINANCIEROS",
}


def balance(filas) -> dict | None:
    """Hoja de trabajo (balance de comprobación a 10 columnas), por cuenta de."""
    cab = [norm(c) for c in filas[7]] if len(filas) > 7 else []
    if "CUENTA" not in cab:
        return None
    ix = {n: i for i, n in enumerate(cab) if n}
    cols = ["DEBITO", "CREDITO", "S.DEUDOR", "S.ACREEDOR", "ACTIVO", "PASIVO",
            "PER. NAT.", "GAN. NAT.", "PER. FUN.", "GAN. FUN."]
    grupos: dict = {}
    totales, resultado, nativo = None, None, True
    for r in filas[8:]:
        if _fin(r):
            break
        r = r + [None] * (len(cab) - len(r))
        cta = re.sub(r"\D", "", limpio(r[ix["CUENTA"]]))
        nom = limpio(r[ix["NOMBRE"]]) if "NOMBRE" in ix else ""
        vals = {c: num(r[ix[c]]) or 0.0 for c in cols if c in ix}
        if cta:
            if len(cta) != 2:
                nativo = False
            k = cta[:2]
            g = grupos.setdefault(k, {"cuenta": k, "nombre": "", "subcuentas": 0,
                                      **{c: 0.0 for c in vals}})
            if len(cta) == 2 and nom:
                g["nombre"] = nom
            g["subcuentas"] += 1
            for c, v in vals.items():
                g[c] += v
        elif norm(nom) == "TOTALES":
            totales = vals
        elif "DEL EJERCICIO" in norm(nom):
            resultado = {"rotulo": nom, **vals}
    if not grupos:
        return None
    cuentas = []
    for k in sorted(grupos):
        g = grupos[k]
        if not g["nombre"]:
            g["nombre"] = PCGE.get(k, f"Cuenta {k}")
        cuentas.append({c: (round(v, 2) if isinstance(v, float) else v)
                        for c, v in g.items()})
    cuadra = None
    if totales:
        cuadra = all(abs(sum(c[col] for c in cuentas) - (totales.get(col) or 0.0)) < 0.05
                     for col in ("DEBITO", "CREDITO"))
    return {"cuentas": cuentas, "totales": totales, "resultado": resultado,
            "nativo": nativo, "cuadra": cuadra}


def es_empresa(documento: str) -> bool:
    return len(documento) == 11 and documento.startswith("20")


DIARIO_COLS = ["fecha", "sd", "asiento", "cuenta", "doc", "empresa", "numero",
               "debe", "haber"]
# Un comprobante de los registros de ventas y compras (ver `registro`).
REGISTRO_COLS = ["fecha", "doc", "numero", "empresa", "base", "igv", "otros",
                 "total"]


def caja(filas, analitico: bool) -> dict:
    """El libro caja por mes: saldo inicial, entradas, salidas, saldo final."""
    cab = [norm(c) for c in filas[7]]
    ix = {n: i for i, n in enumerate(cab) if n}
    inicial = num(filas[8][ix["SALDO"]]) or 0.0
    meses: dict = {}
    ultimo_saldo = None
    for r in filas[8:]:
        if _fin(r):
            break
        r = r + [None] * (len(cab) - len(r))
        mes = limpio(r[ix["MES"]])
        if not re.fullmatch(r"\d{2}", mes):
            continue
        cta = limpio(r[ix["CUENTA"]])
        desc = limpio(r[ix["DESCRIPCION"]])
        d, h = num(r[ix["DEBE"]]) or 0.0, num(r[ix["HABER"]]) or 0.0
        s = num(r[ix["SALDO"]])
        if s is not None:
            ultimo_saldo = s
        m = meses.setdefault(int(mes), {"debe": 0.0, "haber": 0.0, "filas": 0,
                                        "cuentas": {}, "diario": []})
        m["debe"] += d
        m["haber"] += h
        m["filas"] += 1
        c = m["cuentas"].setdefault(cta, {"cuenta": cta, "descripcion": desc,
                                          "debe": 0.0, "haber": 0.0, "filas": 0})
        c["debe"] += d
        c["haber"] += h
        c["filas"] += 1
        if analitico:
            f = r[ix["FECHA"]] if "FECHA" in ix else None
            ruc = re.sub(r"\D", "", limpio(r[ix["R.U.C"]])) if "R.U.C" in ix else ""
            empresa = (limpio(r[ix["RAZON SOCIAL"]]) if es_empresa(ruc)
                       else ("Persona natural" if ruc else ""))
            numero = limpio(r[ix["NUMERO"]]) if es_empresa(ruc) and "NUMERO" in ix else ""
            m["diario"].append([
                f.strftime("%Y-%m-%d") if isinstance(f, datetime) else "",
                limpio(r[ix["S/D"]]) if "S/D" in ix else "",
                limpio(r[ix["ASIENTO"]]) if "ASIENTO" in ix else "",
                cta, limpio(r[ix["D."]]) if "D." in ix else "",
                empresa, numero, round(d, 2), round(h, 2)])
    out, corre = {}, inicial
    for mes in sorted(meses):
        m = meses[mes]
        fin = corre + m["debe"] - m["haber"]
        out[mes] = {
            "inicial": round(corre, 2), "debe": round(m["debe"], 2),
            "haber": round(m["haber"], 2), "final": round(fin, 2),
            "filas": m["filas"], "fuente": "analítico" if analitico else "general",
            "cuentas": sorted(({**c, "debe": round(c["debe"], 2),
                                "haber": round(c["haber"], 2)}
                               for c in m["cuentas"].values()),
                              key=lambda c: c["cuenta"]),
        }
        if analitico:
            out[mes]["diario"] = m["diario"]
        corre = fin
    return {"meses": out,
            "cuadra": ultimo_saldo is None or abs(ultimo_saldo - corre) < 0.05,
            "saldo_ultima_fila": ultimo_saldo}


def registro(filas, es_compras: bool, vistas: set | None = None) -> dict:
    """Totales por mes de emisión. Sin nombres de personas."""
    cab = [limpio(c) for c in filas[7]]
    ixf = next(i for i, c in enumerate(cab) if norm(c).startswith("F.EMIS"))
    ixr = next(i for i, c in enumerate(cab) if norm(c).startswith("R.U.C"))
    ixn = next(i for i, c in enumerate(cab) if norm(c).startswith("RAZON SOCIAL"))
    ixt = next(i for i, c in enumerate(cab) if norm(c) == "TOTAL")
    ixb = [i for i, c in enumerate(cab) if norm(c).startswith("BASE IMP")]
    ixi = [i for i, c in enumerate(cab) if norm(c).startswith("IGV")]
    ixo = [i for i in range(ixn + 1, ixt)
           if cab[i] and i not in ixb and i not in ixi and norm(cab[i]) != "%"]
    ixd = next((i for i, c in enumerate(cab) if norm(c) in ("D.", "D")), None)
    ixnum = next((i for i, c in enumerate(cab)
                  if norm(c).startswith(("NUMERO", "NRO", "N.", "SERIE"))), None)
    meses: dict = {}
    provs: dict = {}
    detalle: list = []
    total_pie = None
    con_otros: set = set()
    sin_desglose_n = 0
    repetidas = 0
    for r in filas[8:]:
        if _fin(r):
            break
        r = r + [None] * (len(cab) - len(r))
        if any(("TOTAL REGISTRO" in norm(c) or "TOTAL GENERAL" in norm(c))
               for c in r if c):
            total_pie = num(r[ixt])
            continue
        f = r[ixf]
        if not isinstance(f, datetime):
            continue
        kmes = clave(f.year, f.month)
        tot = num(r[ixt]) or 0.0
        if vistas is not None:
            k = (f.date().isoformat(),
                 limpio(r[ixd]) if ixd is not None else "",
                 limpio(r[ixnum]) if ixnum is not None else "",
                 re.sub(r"\D", "", str(r[ixr] or "")), round(tot, 2))
            if k in vistas:
                repetidas += 1
                continue
            vistas.add(k)
        m = meses.setdefault(kmes,
                             {"n": 0, "base": 0.0, "igv": 0.0, "otros": 0.0,
                              "sin_desglose": 0.0, "total": 0.0})
        base = sum(num(r[i]) or 0.0 for i in ixb)
        igv = sum(num(r[i]) or 0.0 for i in ixi)
        otros = 0.0
        for i in ixo:
            v = num(r[i]) or 0.0
            if v:
                con_otros.add(cab[i])
            otros += v
        resto = tot - base - igv - otros
        if abs(resto) > 0.005:
            sin_desglose_n += 1
        m["n"] += 1
        m["base"] += base
        m["igv"] += igv
        m["otros"] += otros
        m["sin_desglose"] += resto
        m["total"] += tot
        doc_ruc = re.sub(r"\D", "", str(r[ixr] or ""))
        emp = es_empresa(doc_ruc)
        detalle.append([
            f.date().isoformat(),
            limpio(r[ixd]) if ixd is not None else "",
            limpio(r[ixnum]) if emp and ixnum is not None else "",
            limpio(r[ixn]) if emp else ("Persona natural" if doc_ruc else ""),
            round(base, 2), round(igv, 2), round(otros, 2), round(tot, 2)])
        if es_compras:
            ruc = re.sub(r"\D", "", str(r[ixr] or ""))
            nombre = limpio(r[ixn]) if es_empresa(ruc) else "Personas naturales"
            p = provs.setdefault(nombre, {"proveedor": nombre, "n": 0, "total": 0.0})
            p["n"] += 1
            p["total"] += tot
    for m in meses.values():
        for k in ("base", "igv", "otros", "sin_desglose", "total"):
            m[k] = round(m[k], 2)
    suma = round(sum(m["total"] for m in meses.values()), 2)
    out = {"meses": meses, "total": suma, "total_pie": total_pie,
           "cuadra": total_pie is None or abs(total_pie - suma) < 0.05,
           "otros_cols": [c for c in (cab[i] for i in ixo) if c in con_otros],
           "sin_desglose_n": sin_desglose_n, "repetidas": repetidas,
           "filas": detalle}
    if es_compras:
        out["provs_todos"] = {k: {**v, "total": round(v["total"], 2)}
                              for k, v in provs.items()}
        out["proveedores"] = sorted(({**p, "total": round(p["total"], 2)}
                                     for p in provs.values()),
                                    key=lambda p: -p["total"])[:15]
    return out


def _unir_registros(lista: list, es_compras: bool) -> dict:
    """TODOS los comprobantes de TODOS los archivos, sin contar ninguno dos veces."""
    lista = sorted(lista, key=lambda x: x[0])
    vistas: set = set()
    meses: dict = {}
    fuentes: list = []
    provs: dict = {}
    otros: list = []
    detalle: list = []
    sin_desglose_n = 0
    for per, rel, filas in reversed(lista):
        parte = registro(filas, es_compras, vistas=vistas)
        detalle += parte["filas"]
        fuentes.append({
            "archivo": rel, "periodo": per,
            "meses_que_aporta": sorted(parte["meses"]),
            "filas_que_aporta": sum(m["n"] for m in parte["meses"].values()),
            "filas_repetidas": parte["repetidas"],
            "total_que_aporta": parte["total"],
            "total_pie": (None if parte["total_pie"] is None
                          else round(parte["total_pie"], 2)),
        })
    
        sin_desglose_n += parte["sin_desglose_n"]
        for c in parte["otros_cols"]:
            if c not in otros:
                otros.append(c)
        for k, datos in parte["meses"].items():
            m = meses.setdefault(k, {"n": 0, "base": 0.0, "igv": 0.0,
                                     "otros": 0.0, "sin_desglose": 0.0,
                                     "total": 0.0})
            for campo in ("n", "base", "igv", "otros", "sin_desglose", "total"):
                m[campo] += datos[campo]
        for nom, q in (parte.get("provs_todos") or {}).items():
            nom = limpio(nom)
            t = provs.setdefault(nom, {"proveedor": nom, "n": 0, "total": 0.0})
            t["n"] += q["n"]
            t["total"] += q["total"]
    for m in meses.values():
        for campo in ("base", "igv", "otros", "sin_desglose", "total"):
            m[campo] = round(m[campo], 2)
    suma = round(sum(m["total"] for m in meses.values()), 2)
    usables = [f for f in fuentes if f["filas_que_aporta"]]
    parciales = [f for f in usables if f["filas_repetidas"]]
    pie = (round(sum(f["total_pie"] for f in usables), 2)
           if not parciales and all(f["total_pie"] is not None for f in usables)
           else None)
    out = {"meses": meses, "total": suma, "fuentes": fuentes,
           "otros_cols": otros, "sin_desglose_n": sin_desglose_n,
           "periodo": lista[-1][0], "archivo": lista[-1][1],
           "total_pie": pie,
           "cuadra": (abs(pie - suma) < 0.05 if pie is not None else None),
           "filas_cols": REGISTRO_COLS,
           "filas": sorted(detalle, key=lambda x: (x[0], x[1], x[2]))}
    if es_compras:
        out["proveedores"] = sorted(({**q, "total": round(q["total"], 2)}
                                     for q in provs.values()),
                                    key=lambda q: -q["total"])[:15]
    return out


def ratios(esf: dict, er: dict) -> dict:
    act, pas = esf["activo"], esf["pasivo"]
    nat, fun = er["naturaleza"], er["funcion"]
    ac = buscar(act, "TOTAL ACTIVO CORRIENTE")
    inv = buscar(act, "Inventarios") or 0.0
    pc = buscar(pas, "TOTAL PASIVOS CORRIENTES")
    ta = buscar(act, "T O T A L A C T I V O")
    pat = buscar(pas, "TOTAL PATRIMONIO")
    tp = None
    for k, v in pas:
        if norm(k) == "TOTAL PASIVO":
            tp = v
    nota_tp = None
    if tp is None and ta is not None and pat is not None:
        tp = round(ta - pat, 2)
        nota_tp = "Pasivo total = Total activo − Total patrimonio (la celda del Excel viene vacía)"
    res = buscar(fun, "Ganancia (Pérdida) Neta del Ejercicio")
    if res is None:
        res = buscar(nat, "RESULTADO DEL EJERCICIO")

    def q(a, b, pct=False):
        if a is None or not b:
            return None
        return round((100 if pct else 1) * a / b, 4)

    return {
        "liquidez": {"valor": q(ac, pc), "formula": "Activo corriente ÷ Pasivo corriente",
                     "insumos": {"Activo corriente": ac, "Pasivo corriente": pc}},
        "prueba_acida": {"valor": q(None if ac is None else ac - inv, pc),
                         "formula": "(Activo corriente − Inventarios) ÷ Pasivo corriente",
                         "insumos": {"Activo corriente": ac, "Inventarios": inv,
                                     "Pasivo corriente": pc}},
        "endeudamiento": {"valor": q(tp, pat), "formula": "Pasivo total ÷ Patrimonio",
                          "insumos": {"Pasivo total": tp, "Patrimonio": pat},
                          "nota": nota_tp},
        "roe": {"valor": q(res, pat, True),
                "formula": "Resultado del ejercicio ÷ Patrimonio × 100",
                "insumos": {"Resultado del ejercicio": res, "Patrimonio": pat}},
    }


def tipos(cuentas: list) -> list:
    """El libro caja por cuenta de DOS dígitos del plan contable: suma lo mismo."""
    g: dict = {}
    for c in cuentas:
        k = c["cuenta"][:2]
        x = g.setdefault(k, {"cuenta": k, "nombre": PCGE.get(k, f"Cuenta {k}"),
                             "debe": 0.0, "haber": 0.0, "filas": 0})
        x["debe"] += c["debe"]
        x["haber"] += c["haber"]
        x["filas"] += c["filas"]
    return [{**x, "debe": round(x["debe"], 2), "haber": round(x["haber"], 2)}
            for _, x in sorted(g.items())]


OBRAS_EN_CUENTA = (
    "MANCHEGO LAS MAGNOLIAS", "OFICINAS MANZANOS", "OFICINAS MAZANOS",
    "OFICINA MANZANOS", "AGUIRRE MORALES", "TORRE BLANCA", "LOS JARDINES",
    "LAS MAGNOLIAS", "JOYA VERDE", "SAN ANTONIO", "ULPAYPUQUIO", "LA HUAYCHA",
    "AÑAS UCLO", "MATASUCYA", "HABITAT 2", "MAGNOLIAS", "JARDINES", "MANCHEGO",
    "ALAMEDA", "SICAYA", "PALIAN", "LIMA 2", "ISLAS", "MIAMI",
)
SIN_OBRA = "Sin obra en la cuenta"
ENTRE_CUENTAS = "Entre cuentas propias (caja y bancos)"


def obra_de(cuenta: str, descripcion: str) -> str | None:
    if cuenta[:2] == "10":
        return None
    t = norm(descripcion)
    for o in OBRAS_EN_CUENTA:
        if re.search(rf"(?<![A-Z0-9]){re.escape(norm(o))}(?![A-Z0-9])", t):
            return o
    return None


def por_obra(cuentas: list) -> list:
    g: dict = {}
    for c in cuentas:
        o = obra_de(c["cuenta"], c["descripcion"])
        k = o or (ENTRE_CUENTAS if c["cuenta"][:2] == "10" else SIN_OBRA)
        x = g.setdefault(k, {"obra": k, "debe": 0.0, "haber": 0.0, "filas": 0,
                             "cuentas": 0})
        x["debe"] += c["debe"]
        x["haber"] += c["haber"]
        x["filas"] += c["filas"]
        x["cuentas"] += 1
    fijas = (SIN_OBRA, ENTRE_CUENTAS)
    orden = sorted((x for k, x in g.items() if k not in fijas),
                   key=lambda x: -x["haber"])
    orden += [g[k] for k in fijas if k in g]
    return [{**x, "debe": round(x["debe"], 2), "haber": round(x["haber"], 2)}
            for x in orden]


MINIMO_BASE = 1000.0
GASTOS = ("60", "61", "62", "63", "64", "65", "66", "67", "68")
GRUPO = ("HABITAT", "CORPORACION", "CONSTRUCTORA", "ESCALAR", "VELASCO", "YEAN")


def indicadores_caja(m: dict) -> dict:
    cs = m["cuentas"]
    ent, sal, ini, fin = m["debe"], m["haber"], m["inicial"], m["final"]
    cob = round(sum(c["debe"] for c in cs if c["cuenta"][:2] in ("12", "13")), 2)
    gas = round(sum(c["haber"] for c in cs if c["cuenta"][:2] in GASTOS), 2)
    del_grupo = [c for c in cs if c["cuenta"][:2] in ("16", "17", "46", "47")
                 and any(w in norm(c["descripcion"]) for w in GRUPO) and c["haber"]]
    gru = round(sum(c["haber"] for c in del_grupo), 2)
    obra = round(sum(c["haber"] for c in cs if obra_de(c["cuenta"], c["descripcion"])), 2)

    def q(a, b, pct=True):
        if b is None or abs(b) < MINIMO_BASE:
            return None
        return round((100 if pct else 1) * a / b, 4)

    return {
        "flujo": {"valor": round(ent - sal, 2),
                  "insumos": {"Entradas del mes": ent, "Salidas del mes": sal}},
        "variacion": {"valor": q(fin - ini, ini),
                      "insumos": {"Saldo inicial": ini, "Saldo final": fin}},
        "cobros_salidas": {"valor": q(cob, sal),
                           "insumos": {"Cobros de clientes (cuentas 12 y 13)": cob,
                                       "Salidas del mes": sal}},
        "gastos_cobros": {"valor": q(gas, cob),
                          "insumos": {"Gastos (cuentas 60 a 68)": gas,
                                      "Cobros de clientes (cuentas 12 y 13)": cob}},
        "grupo_salidas": {"valor": q(gru, sal),
                          "insumos": {**{f"{c['cuenta']} · {c['descripcion']}": c["haber"]
                                         for c in del_grupo},
                                      "Enviado a empresas del grupo y al socio": gru,
                                      "Salidas del mes": sal}},
        "meses_caja": {"valor": q(fin, sal, False),
                       "insumos": {"Saldo final": fin, "Salidas del mes": sal}},
        "obra_salidas": {"valor": q(obra, sal),
                         "insumos": {"Salidas cuya cuenta nombra una obra": obra,
                                     "Salidas del mes": sal}},
    }


def _rel(f: Path) -> str:
    return str(f.relative_to(CRUDOS)).replace("\\", "/")


def main() -> int:
    global CRUDOS, CARPETAS, SALIDA
    ap = argparse.ArgumentParser()
    ap.add_argument("--crudos", help="carpeta que hace de data/raw_exports")
    ap.add_argument("--salida", help="JSON a escribir en vez de config/contasis_mensual.json")
    a = ap.parse_args()
    if a.crudos:
        CRUDOS = Path(a.crudos).resolve()
        CARPETAS = [CRUDOS / "contasis_mensual"]
    if a.salida:
        SALIDA = Path(a.salida).resolve()
    archivos, vistos = [], {}
    for carpeta in CARPETAS:
        if not carpeta.exists():
            continue
        for f in sorted(carpeta.rglob("*.xls*")):
            if f.name.startswith("~$"):
                continue
            try:
                filas = leer(f)
            except Exception as e:  # noqa: BLE001
                archivos.append({"archivo": _rel(f), "usado": False,
                                 "motivo": f"no se pudo abrir: {type(e).__name__}"})
                continue
            m = membrete(filas)
            tipo = tipo_de(m["titulo"]) or tipo_por_columnas(filas)
            per = periodo_de(m)
            fila = {"archivo": _rel(f), "titulo": m["titulo"], "ruc": m["ruc"],
                    "tipo": tipo, "periodo": clave(*per) if per else None}
            if m["ruc"] not in EMPRESAS:
                fila.update(usado=False, motivo="RUC fuera de las cuatro empresas")
            elif tipo is None:
                fila.update(usado=False, motivo="tipo de reporte que la hoja no usa")
            elif per is None:
                fila.update(usado=False, motivo="no se pudo leer el período")
            else:
                fila["usado"] = True
                vistos.setdefault((m["ruc"], tipo, fila["periodo"]), []).append((f, filas, m))
            archivos.append(fila)

    empresas = {ruc: {"nombre": nom, "cierres": {}, "caja": {}, "registros": {}}
                for ruc, nom in EMPRESAS.items()}
    no_usados: dict = {}
    pend: dict = {}
    for (ruc, tipo, per), lista in sorted(vistos.items()):
        for x in lista[:-1]:
            no_usados[_rel(x[0])] = "hay otro archivo del mismo cierre que se leyó después"
        f, filas, m = lista[-1]
        rel = _rel(f)
        e = empresas[ruc]
        if tipo in ("esf", "er"):
            izq, der = estado_dos_columnas(filas)
            c = e["cierres"].setdefault(per, {"archivos": {}})
            c["archivos"][tipo] = rel
            if tipo == "esf":
                c["esf"] = {"activo": izq, "pasivo": der, "fecha": m["fecha_txt"]}
            else:
                c["er"] = {"naturaleza": izq, "funcion": der, "fecha": m["fecha_txt"]}
        elif tipo == "balance":
            probados = [(x, balance(x[1])) for x in lista]
            buenos = [p for p in probados if p[1] is not None]
            if not buenos:
                for x, _ in probados:
                    no_usados[_rel(x[0])] = "balance sin cuentas legibles"
                continue
            elegido = next((p for p in buenos if p[1]["nativo"]), buenos[-1])
            for x, _ in probados:
                if x is elegido[0]:
                    no_usados.pop(_rel(x[0]), None)
                else:
                    no_usados[_rel(x[0])] = "la otra hoja de trabajo del mismo cierre"
            rel, b = _rel(elegido[0][0]), elegido[1]
            c = e["cierres"].setdefault(per, {"archivos": {}})
            c["archivos"]["balance"] = rel
            c["balance"] = b
        elif tipo in ("caja_analitico", "caja_general"):
            analitico = tipo == "caja_analitico"
            cj = caja(filas, analitico)
            anio = int(per[:4])
            for mes, datos in cj["meses"].items():
                k = clave(anio, mes)
                previo = e["caja"].get(k)
                if previo and previo["fuente"] == "analítico" and not analitico:
                    continue
                e["caja"][k] = {**datos, "archivo": rel, "cuadra": cj["cuadra"]}
        elif tipo in ("ventas", "compras"):
            pend.setdefault((ruc, tipo), []).append((per, rel, filas))

    for (ruc, tipo), lista in sorted(pend.items()):
        empresas[ruc]["registros"][tipo] = _unir_registros(lista, tipo == "compras")

    for e in empresas.values():
        for c in e["cierres"].values():
            if "esf" in c and "er" in c:
                c["ratios"] = ratios(c["esf"], c["er"])
        ks = sorted(e["caja"])
        for x, y in zip(ks, ks[1:]):
            e["caja"][y]["vs_anterior"] = round(
                e["caja"][y]["inicial"] - e["caja"][x]["final"], 2)
        for k in ks:
            mc = e["caja"][k]
            mc["tipos"] = tipos(mc["cuentas"])
            mc["obras"] = por_obra(mc["cuentas"])
            mc["indicadores"] = indicadores_caja(mc)
    for f in archivos:
        if f["archivo"] in no_usados:
            f.update(usado=False, motivo=no_usados[f["archivo"]])

    salida = {
        "_que_es": ("Cierres mensuales de ContaSis por empresa: libro caja por "
                    "cuenta, su diario sin personas, el resumen por tipo de "
                    "cuenta, la obra que nombra cada cuenta y los indicadores "
                    "de caja; y, cuando llegan, estados, balance de "
                    "comprobación y registros por mes y por comprobante. Sin "
                    "nombres ni documentos de personas."),
        "diario_cols": DIARIO_COLS,
        "minimo_base": MINIMO_BASE,
        "_como_se_actualiza": ("Dejar los Excel del mes en data/raw_exports/"
                               "contasis_mensual/AAAA-MM/ y correr "
                               "scripts/importar_contasis.py"),
        "generado": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "empresas": empresas,
        "archivos": archivos,
    }
    SALIDA.write_text(json.dumps(salida, ensure_ascii=False, indent=1),
                      encoding="utf-8")
    usados = sum(1 for f in archivos if f.get("usado"))
    print(f"escrito {SALIDA} · {len(archivos)} archivos vistos · "
          f"{usados} usados")
    for e in empresas.values():
        regs = {k: v["periodo"] for k, v in e["registros"].items()}
        print(f"  {e['nombre']:<26} cierres {sorted(e['cierres'])} · caja "
              f"{sorted(e['caja'])} · registros {regs}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
