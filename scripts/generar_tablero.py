"""Genera el tablero: un solo archivo HTML con la data adentro."""
from __future__ import annotations

import json
import os
import sys
import time
import warnings
from datetime import datetime
from pathlib import Path

warnings.filterwarnings("ignore")
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import pandas as pd  # noqa: E402

from src import (areas, asesores_axion, auditoria, cierre, cola_registro, crm,  # noqa: E402
                 control_cuentas, entre_cuentas, observaciones, proyeccion,
                 estado, ingest, incidencias, marketing_kpi,
                 drill, estructura_ingreso, filas, filas_area, flujo_caja,
                 libro_gastos,
                 movimientos, periodo, reloj, rentabilidad, vencimientos,
                 resultados, scorecard,
                 validacion)


def _logo() -> str:
    """El logo va embebido en base64: el tablero tiene que seguir siendo."""
    import base64
    f = RAIZ / "assets" / "logo-white.png"
    if not f.exists():
        return ""
    b = base64.b64encode(f.read_bytes()).decode()
    return ('<img class="logo" src="data:image/png;base64,' + b
            + '" alt="Habitat Inmobiliaria">')

SALIDA = RAIZ / "tablero.html"


def _n(v):
    return None if v is None or (isinstance(v, float) and pd.isna(v)) else v


def _publicar(destino, texto: str) -> None:
    """Escribe el archivo COMPLETO o no lo escribe: a un temporal y renombra."""
    destino = Path(destino)
    tmp = destino.with_suffix(destino.suffix + f".tmp{os.getpid()}")
    try:
        tmp.write_text(texto, encoding="utf-8")
        os.replace(tmp, destino)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)


def _sin_nan(o):
    """Cambia NaN e Infinity por None en todo el árbol, antes de serializar."""
    if isinstance(o, dict):
        return {k: _sin_nan(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_sin_nan(v) for v in o]
    if isinstance(o, float) and (o != o or o in (float("inf"), float("-inf"))):
        return None
    return o


MESES = {k: periodo.etiqueta(k)
         for k in ([None] + list(range(1, pd.Timestamp.today().month + 1))
                   + [periodo.HISTORICO])}


def _solo_periodos_del_viejo(items):
    import re as _re
    return [(k, v) for k, v in items
            if not _re.fullmatch(r"\d{4}(-\d{1,2})?", str(k))]


def _cobrado_de_las_ventas(estruct) -> dict:
    """Por obra: cuánto entró DE LAS VENTAS DEL PERÍODO, y sobre cuánto se."""
    out: dict = {}
    for mo in (estruct.get("modalidad") or []):
        for x in (mo.get("detalle") or []):
            o = str(x.get("obra") or "").strip()
            r = out.setdefault(o, {"entro": 0.0, "base": 0.0, "sin_credito": 0})
            r["entro"] += float(x.get("entro") or 0)
            if x.get("sin_credito"):
                r["sin_credito"] += 1
            else:
                r["base"] += float(x.get("precio") or 0)
    return out


def _visitas_axion(anio, mes) -> dict:
    """Las visitas que Comercial lleva en AXION. Si Advisor no responde, la."""
    try:
        return asesores_axion.por_asesor(anio, mes)
    except Exception as e:  # noqa: BLE001
        return {"hay": False,
                "motivo": f"no se pudo leer Advisor: {type(e).__name__}"}


def por_mes(mes) -> dict:
    """Lo que cambia al mover el filtro. Solo las tres hojas que dependen del."""
    sc = scorecard.construir(mes)
    ren = rentabilidad.por_obra(mes)
    es_hist = mes == periodo.HISTORICO
    _crm_anio, _crm_mes = periodo.partes(mes)
    crm_hoja = crm.hoja(_crm_mes, _crm_anio)
    crm_filas = crm.filas_leads(_crm_mes, _crm_anio) if crm_hoja.get(
        "disponible") else []
    try:
        estruct = estructura_ingreso.calcular(mes)
    except Exception:  # noqa: BLE001
        estruct = {"hay": False}
    dr = {}
    for et, fn in drill.DRILLS.items():
        d = fn(mes)
        por = d.get("por")
        dr[et] = {
            "titulo": d["titulo"], "regla": d.get("regla", ""), "total": d["total"],
            "dim": por[0] if por is not None and por[1] is not None else "",
            "grupos": ([[str(i), int(r["size"]), float(r["sum"])]
                        for i, r in por[1].sort_values("sum", ascending=False)
                        .iterrows()]
                       if por is not None and por[1] is not None else []),
            "cols": d["cols"],
            "filas": [[(f"{x:,.2f}" if isinstance(x, float) else str(x))
                       for x in fila] for fila in d["filas"]],
        }

    return {
        "drills": dr,
        "estructura": estruct,
        "crm": crm_hoja,
        "asesores_axion": _visitas_axion(_crm_anio, _crm_mes),
        "crm_filas": crm_filas if es_hist else [],
        "crm_filas_control": (crm.filas_leads_control(crm_filas)
                              if crm_filas else {}),
        "resultados": [
            {"etiqueta": c.etiqueta, "valor": _n(c.valor),
             "formula": c.formula, "origen": c.origen}
            for c in (resultados.cifras() if mes is None
                      else resultados.cifras_del_mes(mes))],
        "indicadores": [{
            "perspectiva": i.perspectiva, "objetivo": i.objetivo,
            "indicador": i.indicador, "meta": _n(i.meta), "unidad": i.unidad,
            "unidad_valor": i.unidad_valor,
            "valor": _n(i.valor), "alcance": i.alcance, "motivo": i.motivo,
            "area": i.area, "area_bsc": i.area_bsc, "necesita": i.necesita,
            "estado": i.estado,
            "ojo": " · ".join(x for x in ([i.unidad_no_cuadra]
                                          + i.avisos) if x),
            "no_cuadra": bool(i.unidad_no_cuadra),
            "propio": i.propio,
            "calculo": i.formula,
            "tipeado": sum(i.tipeado.values()) if i.tipeado else None,
            "desglose": i.desglose,
        } for i in sc],
        "obras": [{
            "obra": r["obra"], "empresa": r["razon_social"],
            "etapa": r["etapa"], "ventas": int(r["ventas"]),
            "contratado": _n(r["contratado"]), "cobrado": _n(r["cobrado"]),
            "cobrado_ventas": _cobrado_de_las_ventas(estruct).get(
                str(r["obra"]).strip(), {}).get("entro"),
            "sin_credito_obra": _cobrado_de_las_ventas(estruct).get(
                str(r["obra"]).strip(), {}).get("sin_credito", 0),
            "base_obra": _cobrado_de_las_ventas(estruct).get(
                str(r["obra"]).strip(), {}).get("base"),
            "costo": _n(r["costo"]), "motivo_costo": r["motivo_costo"],
            "costo_nota": r["costo_nota"],
            "motivo": r["motivo_ingreso"],
        } for _, r in ren.iterrows()],
        "razones": [{
            "empresa": r["razon_social"], "obras": int(r["obras"]),
            "contratado": _n(r["contratado"]), "cobrado": _n(r["cobrado"]),
            "costo": _n(r["costo"])}
            for _, r in rentabilidad.por_razon_social(mes).iterrows()],
        "drills": dr,
    }


def _cobros_en_cero() -> list[dict]:
    """Cobros registrados dentro del crédito SIN MONTO. Se detecta y se."""
    import pandas as _pd
    out = []
    try:
        cr = ingest.fetch_axion_entity("Credit", None, 5000)
    except Exception:  # noqa: BLE001
        return out
    for _, c in cr.iterrows():
        xs = c.get("iniciales")
        for x in (xs or []) if isinstance(xs, list) else []:
            f = str(x.get("fecha") or "")
            if f[:4] != str(periodo.ANIO):
                continue
            m = _pd.to_numeric(x.get("monto"), errors="coerce")
            if not (_pd.isna(m) or float(m) <= 0):
                continue
            out.append({"cliente": str(c.get("client_name") or "—"),
                        "obra": str(c.get("project") or "—"),
                        "fecha": f[:10],
                        "tipo": str(x.get("tipo") or "sin tipo"),
                        "vacio": bool(_pd.isna(m)),
                        "serie": str(x.get("serie") or ""),
                        "empresa": str(x.get("empresa") or "")})
    return out


def _leer_en_paralelo() -> None:
    """LAS LECTURAS AL MISMO TIEMPO, NO EN FILA."""
    from concurrent.futures import ThreadPoolExecutor
    from src import kommo as _k

    def _callar(fn, *args):
        try:
            fn(*args)
        except Exception:  # noqa: BLE001 — la lectura de verdad reintenta después
            pass

    def _kommo():
        for fn in (_k.embudos, _k._etapas, _k.usuarios, _k.motivos_perdida,
                   _k._leads_crudos, _k.tareas):
            _callar(fn)

    trabajos = [(_kommo,), (movimientos.crudo,)]
    trabajos += [(areas._log, e) for e in ("OrdenCompra", "Proveedor", "Material")]
    trabajos += [(ingest.fetch_axion_entity, e, None, 5000) for e in ingest.AXION_ENTITIES]
    trabajos += [(ingest.fetch_axion_entity, e, None, n) for e, n in
                 (("Advisor", 500), ("KPI", 200), ("Project", 500),
                  ("Contrato", 2000), ("Cotizacion", 2000))]
    with ThreadPoolExecutor(max_workers=8) as ex:
        for f in [ex.submit(_callar, *t) for t in trabajos]:
            f.result()


def payload() -> dict:
    leido = reloj.ahora()
    _paso("AXION y Kommo al mismo tiempo…")
    _leer_en_paralelo()
    _paso("leyendo AXION…")
    fuentes = [{
        "nombre": f.nombre, "conectada": f.conectada, "fecha": f.fecha,
        "periodo": f.periodo, "detalle": f.detalle, "faltantes": f.faltantes,
        "aviso": f.aviso,
    } for f in estado.hoja_estado()]
    _cab_dir = RAIZ / "data" / "raw_exports" / "cabidas"
    _cab_xl = sorted(_cab_dir.glob("*.xlsx")) if _cab_dir.exists() else []
    if _cab_xl:
        _mtime = max(p.stat().st_mtime for p in _cab_xl)
        fuentes.append({
            "nombre": "CABIDAS · Excel de factibilidad",
            "conectada": True,
            "fecha": datetime.fromtimestamp(_mtime).strftime("%Y-%m-%d %H:%M"),
            "periodo": f"{len(_cab_xl)} estudios",
            "detalle": ["terrenos que todavía no se compran",
                        "no se suman a ninguna obra de AXION"],
            "faltantes": [], "aviso": "",
        })

    _vc_json = RAIZ / "data" / "ventas_contadora" / "2025.json"
    _vc_xl = RAIZ / "data" / "raw_exports" / "REPORTE DE VENTAS 2025.xlsx"
    if _vc_json.exists() or _vc_xl.exists():
        _vm = (_vc_xl if _vc_xl.exists() else _vc_json).stat().st_mtime
        fuentes.append({
            "nombre": "CONTADORA · Excel de ventas firmadas 2025",
            "conectada": True,
            "fecha": datetime.fromtimestamp(_vm).strftime("%Y-%m-%d %H:%M"),
            "periodo": "2025",
            "detalle": ["un total por hoja, el que escribe la contadora"],
            "faltantes": [
                "Julio no tiene cifra: su celda de total dice #REF!, una "
                "formula rota en el Excel. Se muestra vacio en vez de "
                "inventarlo.",
                "El Excel con los nombres y DNI de los clientes NO sube a la "
                "nube: viaja solo el total de cada mes.",
            ],
            "aviso": "",
        })

    _ce_json = RAIZ / "data" / "caja_encadenada" / "2026.json"
    _ce_xl = RAIZ / "data" / "raw_exports" / "CONTROL DE GASTOS - LISBETH 2026.xlsx"
    if _ce_json.exists() or _ce_xl.exists():
        _cm = (_ce_xl if _ce_xl.exists() else _ce_json).stat().st_mtime
        fuentes.append({
            "nombre": "ADMINISTRACIÓN · Excel de control de gastos 2025-2026 + Libro Mayor CMAC",
            "conectada": True,
            "fecha": datetime.fromtimestamp(_cm).strftime("%Y-%m-%d %H:%M"),
            "periodo": "cierre 2025 · enero a agosto 2026",
            "detalle": ["la celda «QUEDA EN CAJA» de cada cuadro, un total por mes",
                        "las 4 CMAC del Libro Mayor de Caja Huancayo, cierre por mes",
                        "agosto: el cierre al 31-ago que pasó Administración el 01-set"],
            "faltantes": [
                "Los Excels con el detalle fila por fila NO suben a la nube: "
                "viaja solo el total de cada mes.",
            ],
            "aviso": "",
        })

    try:
        from src import valorizacion as _val
        _valoriz = _val.calcular()
    except Exception as e:  # noqa: BLE001 — el Drive caído no tumba el tablero
        print(f"  valorizaciones no se pudieron leer: {type(e).__name__}: {str(e)[:70]}")
        _valoriz = {"hay": False, "motivo": f"{type(e).__name__} al leer el Drive"}

    def _drive_faltantes(val) -> list:
        """Lo que hay que decir del Drive, en lineas de datos."""
        out = ["Se lee con una cuenta de servicio y alcance de SOLO LECTURA: "
               "el cockpit no puede modificar ni borrar nada del Drive."]
        v = val or {}
        for par in (v.get("repetidos") or []):
            out.append(f"Mismo archivo subido con dos nombres: {' y '.join(par)}"
                       f" — uno de los dos esta mal. Obra.")
        for o in (v.get("obras") or []):
            if o.get("cuadra") is False:
                out.append(
                    f"{o['obra']}: la suma de sus partidas "
                    f"({o['presupuesto']:,.2f}) no coincide con el COSTO DIRECTO "
                    f"que declara el archivo ({(o.get('costo_directo') or 0):,.2f}). Obra.")
        for f in (v.get("fallidos") or []):
            out.append(f"No se pudo leer {f.get('archivo', '?')}: "
                       f"{f.get('motivo', '?')}. Obra.")
        return out

    try:
        from src import drive as _drv
        _cen = _drv.censo()
        if _cen.get("hay"):
            fuentes.append({
                "nombre": "DRIVE DE OBRA · EJECUCION DE PROYECTOS",
                "conectada": True,
                "fecha": max((c["ultima"] for c in _cen["carpetas"]), default=""),
                "periodo": "lo que Obra tenga subido",
                "detalle": [f"{c['nombre']}: {c['archivos']} archivo(s)"
                            + (f", {c['carpetas']} carpeta(s)" if c["carpetas"] else "")
                            for c in _cen["carpetas"]],
                "faltantes": _drive_faltantes(_valoriz),
                "aviso": "",
            })
        else:
            fuentes.append({
                "nombre": "DRIVE DE OBRA · EJECUCION DE PROYECTOS",
                "conectada": False,
                "fecha": "", "periodo": "",
                "detalle": [_cen.get("motivo", "")],
                "faltantes": [], "aviso": _cen.get("motivo", ""),
            })
    except Exception as e:  # noqa: BLE001
        print(f"  censo del Drive no se pudo leer: {type(e).__name__}")

    _cro_dir = RAIZ / "data" / "raw_exports" / "cronogramas"
    _cro_xl = ([p for p in sorted(_cro_dir.glob("*.xlsx"))
                if not p.name.startswith("~$")] if _cro_dir.exists() else [])
    if _cro_xl:
        _cm = max(p.stat().st_mtime for p in _cro_xl)
        fuentes.append({
            "nombre": "CRONOGRAMAS · Excel del cronograma de obra",
            "conectada": True,
            "fecha": datetime.fromtimestamp(_cm).strftime("%Y-%m-%d %H:%M"),
            "periodo": f"{len(_cro_xl)} obra(s)",
            "detalle": [p.stem for p in _cro_xl],
            "faltantes": [
                "El archivo original es un .mpp del programa de cronogramas; "
                "se convierte a Excel antes de leerlo, porque abrirlo directo "
                "necesita Java y el servidor del cockpit es solo Python.",
                "El % de avance viene en CERO en todas las partidas: nadie lo "
                "carga en el archivo original. Por eso «Vencida» dice que su fin ya "
                "pasó, "
                "nunca que esté atrasada.",
                "Tampoco hay línea base, fechas reales, responsables ni costos.",
            ],
            "aviso": "",
        })

    _paso("cambios en AXION…")
    cambios = estado.cambios_en_axion()
    for c in cambios:
        print(f"   {'!!' if c['grave'] else '·'} {c['titulo']}")

    _paso("scorecard…")
    sc = scorecard.construir()
    indicadores = [{
        "perspectiva": i.perspectiva, "objetivo": i.objetivo,
        "indicador": i.indicador, "meta": _n(i.meta), "unidad": i.unidad,
            "unidad_valor": i.unidad_valor,
        "valor": _n(i.valor), "alcance": i.alcance, "motivo": i.motivo,
        "area": i.area, "area_bsc": i.area_bsc, "necesita": i.necesita,
            "estado": i.estado,
        "ojo": " · ".join(x for x in ([i.unidad_no_cuadra]
                                          + i.avisos) if x),
        "no_cuadra": bool(i.unidad_no_cuadra),
        "propio": i.propio, "calculo": i.formula,
        "tipeado": sum(i.tipeado.values()) if i.tipeado else None,
        "desglose": i.desglose,
    } for i in sc]

    _paso("rentabilidad…")
    ren = rentabilidad.por_obra()
    obras = [{
        "obra": r["obra"], "empresa": r["razon_social"], "etapa": r["etapa"],
        "ventas": int(r["ventas"]), "contratado": _n(r["contratado"]),
        "cobrado": _n(r["cobrado"]), "motivo": r["motivo_ingreso"],
    } for _, r in ren.iterrows()]
    rs = [{"empresa": r["razon_social"], "obras": int(r["obras"]),
           "contratado": _n(r["contratado"]), "cobrado": _n(r["cobrado"])}
          for _, r in rentabilidad.por_razon_social().iterrows()]

    _paso("áreas…")
    hojas_area = {}
    for nombre, fn in areas.HOJAS.items():
        hojas_area[nombre] = [{
            "etiqueta": c.etiqueta, "valor": _n(c.valor), "formula": c.formula,
            "origen": c.origen, "motivo": c.motivo, "area": c.area,
        } for c in fn()]

    _paso("el control de ingresos y gastos (espejo del Excel de la administradora)…")
    try:
        libro = {"control": libro_gastos.control(None),
                 "control_hist": libro_gastos.control(periodo.HISTORICO),
                 "filas": libro_gastos.filas(periodo.HISTORICO)}
    except Exception as e:  # noqa: BLE001 — sin AXION la hoja lo declara
        libro = {"error": f"{type(e).__name__}: {e}"}

    _paso("movimientos de caja (MovimientoGasto)…")
    try:
        mv_res = movimientos.resumen()
        mov = {"hay": mv_res.get("hay", False), "resumen": mv_res,
               "por_obra": movimientos.gasto_por_obra().to_dict("records"),
               "por_obra_anio": movimientos.gasto_por_obra(None).to_dict("records"),
               "anio": movimientos.gasto_total(None),
               "sin_atribuir": movimientos.sin_atribuir().to_dict("records"),
               "desglose": movimientos.desglose(),
               "desglose_anio": movimientos.desglose(None),
               "avisos": movimientos.avisos()}
    except Exception as e:  # noqa: BLE001 — fuente nueva: que no tumbe el tablero
        print(f"   no se pudo leer: {type(e).__name__}: {str(e)[:80]}")
        mov = {"hay": False}

    _paso("flujo de caja…")
    try:
        flujo = {**flujo_caja.por_mes(),
                 "alertas": flujo_caja.alertas_presupuesto(),
                 "diagnostico_presupuesto": flujo_caja.diagnostico_presupuesto()}
    except Exception as e:  # noqa: BLE001
        print(f"   no se pudo: {type(e).__name__}: {str(e)[:70]}")
        flujo = {"hay": False}

    _paso("la caja encadenada…")
    try:
        from src import caja_encadenada as _ce
        cadena = _ce.armar(flujo)
        if cadena.get("hay"):
            _u = cadena.get("cierre") or {}
            print(f"  caja encadenada · arranque {cadena['arranque']['total']:,.2f} · "
                  f"{len(cadena['meses'])} meses · al cierre de "
                  f"{_u.get('nombre', '?')}: calculado {_u.get('calculado') or 0:,.2f} · "
                  f"en cuentas {_u.get('real') or 0:,.2f} · dif {_u.get('dif') or 0:+,.2f}"
                  + (" · de los Excels" if cadena.get("de_excel") else " · del JSON publicado")
                  + (f" · Excel no leído: {cadena['error_excel']}" if cadena.get("error_excel") else ""))
        else:
            print(f"  caja encadenada: {cadena.get('motivo')}")
    except Exception as e:  # noqa: BLE001 — sin los archivos, la hoja lo declara
        print(f"   caja encadenada no se pudo armar: {type(e).__name__}: {str(e)[:90]}")
        cadena = {"hay": False, "motivo": f"{type(e).__name__}: {e}"}

    _paso("vencimientos mes a mes…")
    try:
        venc = {"meses": vencimientos.por_mes(),
                "fuera": vencimientos.fuera_de_la_vista(),
                "composicion": vencimientos.composicion(),
                "cartera": vencimientos.cartera()}
    except Exception as e:  # noqa: BLE001
        print(f"   no se pudo: {type(e).__name__}: {str(e)[:70]}")
        venc = {"meses": [], "fuera": {}, "cartera": {}}

    _paso("validación…")
    val = validacion.hoja()
    bloques = [{"fuente": b.fuente, "pregunta": b.pregunta,
                "cifra": _n(b.cifra), "detalle": b.detalle,
                "ventana": b.ventana, "resaltante": b.resaltante,
                "cols": b.cols, "filas": b.filas, "de_donde": b.de_donde}
               for b in val["bloques"]]

    _paso("resultados…")
    res = [{"etiqueta": c.etiqueta, "valor": _n(c.valor), "formula": c.formula,
            "origen": c.origen} for c in resultados.cifras()]
    res_no = [{"etiqueta": c.etiqueta, "motivo": c.motivo, "area": c.area}
              for c in resultados.lo_que_axion_no_contesta()]

    _paso("cierre…")
    sin_excels: list[str] = []

    def _sin_caerse(nombre, fn, vacio):
        """Corre `fn`; si los Excels no estan, devuelve `vacio` y lo anota."""
        try:
            return fn()
        except Exception as e:  # noqa: BLE001 — cualquier falla de esa fuente
            sin_excels.append(f"{nombre}: {type(e).__name__} {e}")
            print(f"   !! {nombre} no se pudo armar ({type(e).__name__}: {e}) "
                  f"— el tablero sigue sin esa pieza y la hoja Estado lo dice")
            return vacio

    cont = _sin_caerse("gasto contable por obra (ContaSis)",
                       cierre.gasto_contable_por_obra, pd.DataFrame())
    admo = _sin_caerse("gasto de la administradora por obra",
                       cierre.gasto_administradora_por_obra, pd.DataFrame())

    _paso("serie mensual de los indicadores…")
    _hoy = pd.Timestamp.today()
    _HASTA = _hoy.month if _hoy.year == periodo.ANIO else 12
    _serie = {}
    _desg = {}
    for _m in range(1, _HASTA + 1):
        for i in scorecard.construir(_m):
            if i.valor is not None:
                _serie.setdefault(i.indicador, {})[_m] = float(i.valor)
            if i.desglose:
                _desg.setdefault(i.indicador, {})[_m] = i.desglose
    series = {}
    for nom, s in _serie.items():
        vals = list(s.values())
        series[nom] = {"puntos": s, "plana": len(set(vals)) <= 1,
                       # El mes en curso: va incompleto y hay que decirlo.
                       "en_curso": _HASTA if _hoy.year == periodo.ANIO else None,
                       "dia": int(_hoy.day),
                       "dias_mes": int(_hoy.days_in_month),
                       "desglose": _desg.get(nom, {})}

    _paso("avance por obra…")
    _u = ingest.fetch_axion_entity("Unit", None, 5000)
    _pr_ = pd.to_numeric(_u["real_price"], errors="coerce").fillna(0)
    _pc_ = pd.to_numeric(_u.get("catalog_price", pd.Series(0.0, index=_u.index)),
                         errors="coerce").fillna(0)
    _u = _u.assign(_precio=_pr_.where(_pr_ > 0, _pc_))
    _sale_ = ingest.fetch_axion_entity("Sale", None, 5000)
    _vend_ = _sale_[_sale_["status"] == "Vendido"]
    _con_venta_ = {(str(r["project"]).strip(), str(r["unit"]).strip())
                   for _, r in _vend_.iterrows()}
    avance = {}
    for o, g in _u.groupby("project"):
        obra = str(o).strip()
        con = g[g["_precio"] > 0]
        sin = g[g["_precio"] == 0]
        sin_pero_vendidas = sum(
            1 for _, r in sin.iterrows()
            if (obra, str(r["name"]).strip()) in _con_venta_)
        tot = float(con["_precio"].sum())
        vend = float(con[con["status"] == "VENDIDO"]["_precio"].sum())
        avance[obra] = {
            "vendido": vend, "total": tot,
            "pct": (100 * vend / tot) if tot else 0.0,
            # unidades: TODAS, tengan precio o no
            "u_vend": int((g["status"] == "VENDIDO").sum()),
            "u_tot": int(len(g)),
            "u_libre": int((g["status"] == "LIBRE").sum()),
            "u_bloq": int((g["status"] == "BLOQUEADO").sum()),
            "u_sep": int((g["status"] == "SEPARADO").sum()),
            "libre_precio": float(con[con["status"] == "LIBRE"]["_precio"].sum()),
            # y aparte, sobre cuántas se pudo medir la plata
            "u_vend_precio": int((con["status"] == "VENDIDO").sum()),
            "u_tot_precio": int(len(con)),
            "sin_precio": int(len(sin)),
            "sin_precio_con_venta": int(sin_pero_vendidas),
        }

    _paso("avance físico de obra…")
    _pr0 = ingest.fetch_axion_entity("Project", None, 5000)
    avance_fisico = [{"obra": str(r["name"]).strip(),
                      "etapa": str(r["project_stage"]).strip() or "—",
                      "pct": float(pd.to_numeric(
                          pd.Series([r["construction_progress"]]),
                          errors="coerce").fillna(0).iloc[0])}
                     for _, r in _pr0.sort_values(
                         "construction_progress", ascending=False).iterrows()]

    _paso("razones sociales…")
    _pr = ingest.fetch_axion_entity("Project", None, 5000)
    empresa_de_obra = {str(r["name"]).strip():
                       (str(r["company_name"]).strip() or rentabilidad.SIN_RAZON)
                       for _, r in _pr.iterrows()}
    razones = sorted(set(empresa_de_obra.values()))
    SIN_TIPO = "— sin tipo declarado en AXION —"
    tipo_de_obra = {}
    for _, r in _pr.iterrows():
        t = str(r.get("project_type") or "").strip()
        tipo_de_obra[str(r["name"]).strip()] = t if t and t.lower() != "nan" else SIN_TIPO
    tipos = sorted(set(tipo_de_obra.values()))
    asesores = sorted({filas.asesor(r["advisor"]) for _, r in _sale_.iterrows()}
                      | {filas.asesor(r["advisor"]) for _, r in _u.iterrows()})
    def _activos():
        adv = ingest.fetch_axion_entity("Advisor", None, 500)
        return sorted({filas.asesor(r["name"]) for _, r in adv.iterrows()
                       if str(r.get("active")).strip().lower() == "true"})
    asesores_activos = _sin_caerse("asesores activos (AXION · Advisor.active)",
                                   _activos, [])
    if asesores_activos:
        asesores = asesores_activos + ([filas.SIN_ASESOR]
                                       if filas.SIN_ASESOR in asesores else [])

    _paso("filas de las hojas de área…")
    areas_filas = filas_area.todo()

    _paso("órdenes de compra…")
    oc_df = ingest.fetch_axion_opcional("OrdenCompra", [
        "oc_number", "date", "proveedor", "proyecto_destino", "tipo",
        "flujo_estado", "terminos_pago", "imponible", "impuesto", "total",
        "solicitado_por", "comentarios", "items"])
    ordenes = []
    for _, r in oc_df.iterrows():
        prov = r.get("proveedor") if isinstance(r.get("proveedor"), dict) else {}
        items = [{
            "producto": str(x.get("producto") or ""),
            "codigo": str(x.get("codigo") or ""),
            "unidad": str(x.get("unidad") or ""),
            "cantidad": float(x.get("cantidad") or 0),
            "precio_unit": float(x.get("precio_unit") or 0),
            "total": float(x.get("total") or 0),
        } for x in (r.get("items") if isinstance(r.get("items"), list) else [])]
        ordenes.append({
            "oc": str(r.get("oc_number") or ""),
            "fecha": str(r.get("date") or "")[:10],
            "proveedor": str(prov.get("empresa") or "(sin proveedor)"),
            "ruc": str(prov.get("ruc") or ""),
            "obra": str(r.get("proyecto_destino") or ""),
            "tipo": str(r.get("tipo") or ""),
            "estado": str(r.get("flujo_estado") or ""),
            "terminos": str(r.get("terminos_pago") or ""),
            "imponible": float(r.get("imponible") or 0),
            "impuesto": float(r.get("impuesto") or 0),
            "total": float(r.get("total") or 0),
            "solicito": str(r.get("solicitado_por") or ""),
            "comentarios": str(r.get("comentarios") or ""),
            "items": items,
        })

    _paso("atención al cliente…")
    incidentes = _sin_caerse("incidencias (Atención al Cliente)", incidencias.filas, [])

    _paso("filas para el filtro…")
    crudas = filas.todo()
    obras_filtro = filas.obras_disponibles()

    _paso("períodos…")
    extras: dict = {}
    try:
        _fmov = movimientos.crudo()["fecha_n"]
        for a in sorted({int(x) for x in _fmov.dt.year.dropna().unique()
                         if int(x) != periodo.ANIO}, reverse=True):
            extras[str(a)] = periodo.etiqueta(str(a))
            for mnum in sorted({int(x) for x in
                                _fmov[_fmov.dt.year.eq(a)].dt.month
                                .dropna().unique()}):
                extras[f"{a}-{mnum}"] = periodo.etiqueta(f"{a}-{mnum}")
    except Exception as e:  # noqa: BLE001 — sin años extra, el filtro de siempre
        print(f"   (sin años anteriores: {type(e).__name__}: {e})")

    claves = ([k for k in MESES if k != periodo.HISTORICO]
              + list(extras) + [periodo.HISTORICO])
    nombres = {str(k): (extras[k] if k in extras else MESES[k])
               for k in claves}
    meses = {}
    for m in claves:
        _t_mes = time.time()
        meses[str(m)] = por_mes(m)
        print(f"   {nombres[str(m)]}   ({time.time() - _t_mes:.0f} s)")

    _cc_pub = _sin_caerse(
        "control mes a mes por cuenta (src/control_cuentas.py)",
        lambda: control_cuentas.control(movimientos.crudo()), {})
    _hasta_axion = _sin_caerse(
        "fecha de la última fila de AXION",
        lambda: str(movimientos.crudo()["fecha_n"].max())[:10], "")

    return {
        "series": series, "avance": avance, "avance_fisico": avance_fisico,
        "empresa_de_obra": empresa_de_obra,
        "razones_filtro": razones, "asesores_filtro": asesores,
        "asesores_activos": asesores_activos,
        "tipo_de_obra": tipo_de_obra, "tipos_filtro": tipos,
        "areas_filas": areas_filas,
        "crudas": crudas, "obras_filtro": obras_filtro,
        "ordenes_compra": ordenes,
        "incidentes": incidentes,
        "meses": meses, "nombres_mes": nombres,
        "resultados": res, "resultados_no": res_no,
        "metas": _sin_caerse("metas", lambda: cierre.metas().to_dict("records"), []),
        "por_crear": _sin_caerse("lo que falta crear en AXION", cierre.por_crear, []),
        "ingresos": _sin_caerse("ingresos reconocidos (ContaSis)", cierre.ingresos, []),
        "utilidad": _sin_caerse("utilidad declarada", cierre.utilidad_declarada, None),
        "gasto_contable": cont.to_dict("records") if len(cont) else [],
        "gasto_contable_total": cont.attrs.get("total_6x", 0),
        "gasto_contable_atribuido": cont.attrs.get("atribuido", 0),
        "gasto_admin": admo.to_dict("records") if len(admo) else [],
        "incongruencias": _sin_caerse("incongruencias entre fuentes",
                                      cierre.incongruencias, []),
        "sin_excels": sin_excels,
        "generado": leido.strftime(reloj.FORMATO),
        "publicado": reloj.sello(),
        "tardo_min": round((reloj.ahora() - leido).total_seconds() / 60),
        "cobrado_cero": _cobros_en_cero(),
        "gasto_fuera": movimientos.gasto_fuera_de_alcance(None),
        "gasto_fuera_hist": movimientos.gasto_fuera_de_alcance(periodo.HISTORICO),
        "cola": cola_registro.calcular(None),
        "proyeccion": proyeccion.calcular(None),
        "entre_cuentas": entre_cuentas.calcular(None),
        "crm_concept": crm.hoja_concept(),
        "fuentes": fuentes, "indicadores": indicadores,
        "cambios_axion": cambios,
        "flujo": flujo,
        "vencimientos": venc,
        "movimientos": mov,
        "libro": libro,
        "valorizaciones": _valoriz,
        "caja_encadenada": cadena,
        "saldos_externos": _sin_caerse(
            "saldos externos CMAC (config/saldos_externos.json)",
            lambda: json.loads((RAIZ / "config" / "saldos_externos.json")
                               .read_text(encoding="utf-8")), {}),
        "saldos_iniciales": _sin_caerse(
            "saldos iniciales de AXION (tabla SaldoInicial)",
            lambda: movimientos.aperturas(), {}),
        "control_cuentas": _cc_pub,
        "observaciones": _sin_caerse(
            "observaciones abiertas de caja (src/observaciones.py)",
            lambda: observaciones.caja(_cc_pub, cadena, _hasta_axion), []),
        "contasis_mensual": _sin_caerse(
            "cierres de ContaSis (config/contasis_mensual.json)",
            lambda: json.loads((RAIZ / "config" / "contasis_mensual.json")
                               .read_text(encoding="utf-8")), {}),
        "operacion": _sin_caerse(
            "indicadores de operación de AXION",
            lambda: __import__("src.indicadores_operacion",
                               fromlist=["calcular"]).calcular(), {"hay": False}),
        "metas_gerencia": _sin_caerse(
            "metas de gerencia (config/metas.json)",
            lambda: json.loads((RAIZ / "config" / "metas.json")
                               .read_text(encoding="utf-8")), {}),
        "metas_asesor": _sin_caerse(
            "metas por asesor (config/metas_asesor.json)",
            lambda: json.loads((RAIZ / "config" / "metas_asesor.json")
                               .read_text(encoding="utf-8")), {}),
        "marketing_extra": _sin_caerse(
            "fuente y dias del lead a la venta (areas.marketing_extra)",
            lambda: areas.marketing_extra(periodo.ANIO), {}),
        "metas_ventas": _sin_caerse(
            "metas de ventas (config/metas_ventas.json)",
            lambda: json.loads((RAIZ / "config" / "metas_ventas.json")
                               .read_text(encoding="utf-8")), {}),
        "cabidas": _sin_caerse(
            "cabidas y factibilidad (config/cabidas.json)",
            lambda: json.loads((RAIZ / "config" / "cabidas.json")
                               .read_text(encoding="utf-8")), {}),
        "obras": obras, "razones": rs, "areas": hojas_area,
        "validacion": {"mes": val["mes"], "bloques": bloques,
                       "porque": val["por_que_una_sola_fuente"]},
        "avisos_rentabilidad": [
            {"etiqueta": c.etiqueta, "valor": _n(c.valor),
             "motivo": c.motivo, "area": c.area}
            for c in rentabilidad.avisos()],
        "avisos_marketing": _sin_caerse(
            "avisos de marketing_kpi", marketing_kpi.avisos, []),
    }


def _fmt(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—"
    if isinstance(v, (int, float)):
        return f"{v:,.2f}" if isinstance(v, float) else f"{v:,}"
    return str(v)


def _abrev(v, moneda: bool = False) -> str:
    """La cifra grande, abreviada, con el exacto pegado debajo."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—"
    try:
        n = float(v)
    except (TypeError, ValueError):
        return _esc(v)
    a = abs(n)
    if a >= 1_000_000:
        return f"{n/1_000_000:,.2f}<i>M</i>"
    if a >= 10_000:
        return f"{n/1_000:,.1f}<i>K</i>"
    return (f"S/ {n:,.2f}" if moneda else _fmt(v))


def _se_abrevia(v) -> bool:
    """¿La cifra se mostró acortada? Solo entonces hace falta el exacto."""
    try:
        return abs(float(v)) >= 10_000
    except (TypeError, ValueError):
        return False


def _esc(s) -> str:
    return (str(s or "").replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;"))


def _soles(v) -> str:
    """Plata, siempre con el símbolo adelante."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—"
    return f"S/ {float(v):,.2f}"


def _con_unidad(v, unidad: str) -> str:
    """La cifra con la unidad que declara AXION, pero legible."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—"
    u = str(unidad or "").strip()
    if u in ("S/.", "S/", "soles", "PEN"):
        return _soles(v)
    if u == "%":
        return f"{_fmt(v)}%"
    if u in ("", "N°", "Nº", "N"):
        return _fmt(v)
    return f"{_fmt(v)} {u}"


def _alerta_html(a: str) -> str:
    """Una alerta, plegable, con las tres cosas que hacen falta para cerrarla."""
    partes = str(a).split("∷")
    if len(partes) < 4:
        return f'<div class="ojo">{_esc(a)}</div>'
    titulo, que_paso, como, area = partes[0], partes[1], partes[2], partes[3]
    return (
        '<details class="ojo alerta"><summary><b>⚠ '
        f'{_esc(titulo)}</b>  <span class="f">— ver qué pasó y cómo se '
        'cierra</span></summary>'
        f'<div class="cuerpo"><p><b>Qué pasó.</b> {_esc(que_paso)}</p>'
        f'<p><b>Cómo se cierra.</b> {_esc(como)}</p>'
        f'<div class="quien">lo resuelve: {_esc(area)}</div>'
        '<div class="f">Esto no se corrige desde el tablero a propósito: se '
        'arregla en AXION, que es donde vive el dato. Al corregirlo, la '
        'alerta desaparece sola en la siguiente actualización — así se sabe '
        'que quedó resuelto de verdad.</div></div></details>')


def _detalle_modalidad(m: dict) -> str:
    """Las ventas de UNA modalidad, una por una, con lo contratado y lo que."""
    filas = m.get("detalle") or []
    if not filas:
        return ('<div class="vacio">No hay ventas que mostrar en esta '
                'modalidad para el período elegido.</div>')
    con_banco = any(f.get("banco") for f in filas)
    cab = ('<tr><th>Cliente</th><th>Obra · unidad</th><th>Firmada</th>'
           + ('<th>Banco</th>' if con_banco else '')
           + '<th class="num">Contratado</th><th class="num">Ya entró</th>'
             '<th class="num">Falta</th></tr>')
    cuerpo = ""
    for f in filas:
        # Marca la venta que no tiene NADA cobrado: es la que hay que mirar.
        alerta = ' class="cero"' if f["entro"] <= 0 else ""
        nota = ""
        if f.get("sin_credito"):
            nota = ('<div class="f">sin crédito registrado en AXION — su '
                    'cobro no se puede seguir</div>')
        cuerpo += (
            f'<tr{alerta}><td>{_esc(f["cliente"])}{nota}</td>'
            f'<td>{_esc(f["obra"])} · {_esc(f["unidad"])}</td>'
            f'<td>{_esc(f["fecha"])}</td>'
            + (f'<td>{_esc(f["banco"] or "—")}</td>' if con_banco else '')
            + f'<td class="num">{_soles(f["precio"])}</td>'
              f'<td class="num">{_soles(f["entro"])}</td>'
              f'<td class="num">{_soles(f["falta"])}</td></tr>')
    n_col = 4 if con_banco else 3
    cuerpo += (
        f'<tr class="tot"><td colspan="{n_col}"><b>Total {_esc(m["modalidad"])}'
        f'</b></td>'
        f'<td class="num"><b>{_soles(m["monto"])}</b></td>'
        f'<td class="num"><b>{_soles(m.get("entro"))}</b></td>'
        f'<td class="num"><b>{_soles(m["monto"] - (m.get("entro") or 0))}'
        f'</b></td></tr>')
    sin_nada = sum(1 for f in filas if f["entro"] <= 0)
    pie = ""
    if sin_nada:
        pie = (f'<div class="f">{sin_nada} de {len(filas)} ventas no tienen '
               f'ni un sol cobrado (van marcadas). En hipoteca es normal '
               f'mientras el banco no desembolse; en contado no lo es.</div>')
    return (f'<div class="subdet"><table class="fina">{cab}{cuerpo}</table>'
            f'{pie}<div class="f">«Ya entró» = iniciales cobradas + cuotas '
            f'pagadas de esa venta. «Falta» = contratado − ya entró. Se cruza '
            f'por DNI y cada crédito se cuenta una sola vez.</div></div>')


_RELOJ: list = [None, None]


def _paso(nombre: str) -> None:
    """Anuncia la fase que empieza y dice cuánto tardó la anterior."""
    ahora = time.time()
    if _RELOJ[0] is not None:
        print(f"   ({time.time() - _RELOJ[0]:.0f} s)")
    else:
        _RELOJ[1] = ahora
    _RELOJ[0] = ahora
    print(nombre, end="", flush=True)


def _paso_fin() -> None:
    """Cierra la última fase e informa el total."""
    if _RELOJ[0] is not None:
        print(f"   ({time.time() - _RELOJ[0]:.0f} s)")
    if _RELOJ[1] is not None:
        print(f"\nla corrida entera tardó {(time.time() - _RELOJ[1]) / 60:.1f} min")


def _resumen_lecturas() -> None:
    """Cuánto de la corrida fue ESPERAR a las APIs, tabla por tabla y ruta por."""
    ax = list(ingest.MEDICION)
    if ax:
        print(f"\nlecturas de AXION · {len(ax)} lecturas · "
              f"{sum(x['segundos'] for x in ax):.0f} s sumando cada una")
        por_tabla: dict = {}
        for x in ax:
            t = por_tabla.setdefault(x["tabla"], [0, 0.0, 0])
            t[0] += 1
            t[1] += x["segundos"]
            t[2] = max(t[2], x["filas"])
        for tabla, t in sorted(por_tabla.items(), key=lambda kv: -kv[1][1]):
            print(f"   {tabla:<16} {t[0]:>3} veces · {t[1]:>6.1f} s · {t[2]:,} filas")
    from src import kommo as _k
    pr = _k.MEDICION.get("por_ruta") or {}
    if pr:
        print(f"lecturas de Kommo · {sum(v[0] for v in pr.values())} pedidos · "
              f"{sum(v[1] for v in pr.values()):.0f} s, más "
              f"{_k.MEDICION.get('pausas', 0):.0f} s de pausas entre páginas")
        for ruta, v in sorted(pr.items(), key=lambda kv: -kv[1][1]):
            print(f"   {ruta:<30} {v[0]:>4} pedidos · {v[1]:>6.1f} s")


def _tardanza(d: dict) -> str:
    try:
        m = int(d.get("tardo_min") or 0)
    except (TypeError, ValueError):
        return ""
    if m <= 20:
        return ""
    pub = str(d.get("publicado") or d.get("generado") or "")[11:16]
    return (f' · <b>la lectura tardó {m} min</b> y se publicó {pub}: '
            f'la máquina estuvo suspendida o la API respondió lenta')


def _bloque_estructura(v: dict) -> str:
    """La estructura del ingreso, pegada al Vendido."""
    e = v.get("estructura") or {}
    if not e.get("hay") or not e.get("contratado"):
        if e.get("periodo"):
            return ('<div class="graf"><h4>Cómo entra ese dinero · lo firmado '
                    'no es lo cobrado</h4><div class="vacio">Sin ventas '
                    f'registradas en {_esc(e["periodo"].lower())}: no hay '
                    'estructura de ingreso que mostrar. Si el mes ya empezó y '
                    'esto sigue en cero, la pregunta es para Comercial.</div>'
                    '</div>')
        return ""
    pct = e["pct_entro"]
    _p = "no se puede medir" if pct is None else f"{pct:.1f}%"
    _pf = "—" if pct is None else f"{100 - pct:.1f}%"
    barra = ("" if pct is None else
             f'<div class="cartbar">'
             f'<i class="ok" style="width:{min(pct,100):.1f}%"></i>'
             f'<i class="parc" style="width:{max(0, 100-pct):.1f}%"></i></div>')
    mods = "".join(
        f'<tr class="mrow" onclick="toggleFila(this)">'
        f'<td><b>{_esc(m["modalidad"])}</b> <span class="verdet">ver las '
        f'{m["ventas"]} ventas</span>'
        f'<div class="f">{_esc(m["ritmo"])}</div></td>'
        f'<td class="num">{m["ventas"]}</td>'
        f'<td class="num">{_soles(m["monto"])}</td>'
        f'<td class="num">{_soles(m.get("entro"))}</td></tr>'
        f'<tr class="mdet" hidden><td colspan="4">'
        f'{_detalle_modalidad(m)}</td></tr>'
        for m in e["modalidad"])
    mods += (f'<tr class="tot"><td><b>Total</b></td>'
             f'<td class="num">{e["ventas"]}</td>'
             f'<td class="num">{_soles(e["contratado"])}</td>'
             f'<td class="num"><b>{_soles(e["entro"])}</b></td></tr>')
    avisos = ""
    _n = e.get("sin_credito") or 0
    if _n:
        avisos += (f'<div class="ojo">{_n} de {e["ventas"]} '
                   f'{"venta no tiene" if _n == 1 else "ventas no tienen"} crédito '
                   f'registrado en AXION ({_soles(e["monto_sin_credito"])}): su cobro '
                   f'no se puede leer, porque lo cobrado vive dentro del crédito. '
                   f'No dice que no hayan pagado, dice que no hay dónde mirarlo — '
                   f'es carga pendiente de Comercial.</div>')
    _c = e.get("credito_compartido") or 0
    if _c:
        avisos += (f'<div class="ojo">{_c} '
                   f'{"venta comparte" if _c == 1 else "ventas comparten"} su crédito '
                   f'con otra venta del mismo cliente '
                   f'({_soles(e.get("monto_credito_compartido") or 0)}) — pasa cuando un '
                   f'crédito cubre dos unidades, como «COCHERA 6 + DPTO 1003». Su cobro '
                   f'SÍ está contado, del lado de la venta hermana: acá no falta nada.</div>')
    if abs(e.get("descuadre") or 0) > 1:
        avisos += (
            f'<div class="ojo"><b>AXION dice que falta cobrar '
            f'{_soles(e["saldo"])}, y la resta da {_soles(e["falta"])}: '
            f'{_soles(abs(e["descuadre"]))} de diferencia.</b> Acá se publica '
            f'la resta, que es la que cuadra con lo firmado. La diferencia son '
            f'los créditos duplicados y las iniciales mal tipeadas que ya '
            f'están señalados en Cobranza — es un hallazgo sobre la carga, no '
            f'un ajuste nuestro.'
            f'<div class="quien">responde: Cobranzas</div></div>')
    flojas = e.get("contado_incompleto") or []
    if flojas:
        falta_tot = sum(f["falta"] for f in flojas)
        detalle = " · ".join(
            f'{_esc(f["cliente"])} (faltan {_soles(f["falta"])}'
            + (', sin crédito registrado' if f["sin_credito"] else '')
            + ')' for f in flojas[:5])
        avisos += (
            f'<div class="ojo"><b>{len(flojas)} ventas figuran «al contado» '
            f'pero no están pagadas completas — faltan {_soles(falta_tot)}.'
            f'</b> Al contado se paga todo al firmar, así que o esas ventas no '
            f'son al contado, o falta registrar sus pagos. Los mayores: '
            f'{detalle}.'
            f'<div class="quien">responde: Cobranzas</div></div>')
    frescas = e.get("contado_recien_firmado") or []
    if frescas:
        tot_f = sum(f["falta"] for f in frescas)
        obras = sorted({f["obra"] for f in frescas})
        avisos += (
            f'<div class="f"><b>{len(frescas)} ventas al contado se firmaron '
            f'en los últimos {e.get("dias_gracia", 7)} días</b> '
            f'({_esc(", ".join(obras))}) y todavía no tienen pago registrado '
            f'— {_soles(tot_f)}. No entran en el aviso de arriba: recién '
            f'cargadas, el cobro puede estar hecho y sin registrar. Si en unos '
            f'días siguen así, pasan solas a la lista de Cobranzas.</div>')
    # El total es exacto; el reparto por modalidad puede correrse. Se dice.
    if e.get("clientes_con_varias_ventas"):
        avisos += (
            f'<div class="f">Nota de método: <b>el total es exacto</b>, pero '
            f'el reparto por modalidad es aproximado. '
            f'{e["clientes_con_varias_ventas"]} clientes tienen más de una '
            f'venta en el período, y su pago se asigna a la primera que '
            f'coincide por unidad; si ninguna coincide, a la primera de la '
            f'lista. Eso puede correr unos soles entre modalidades, nunca del '
            f'total.</div>')
    return (
        '<div class="graf"><h4>Cómo entra ese dinero · lo firmado no es lo '
        'cobrado</h4>'
        f'<div class="nota">De los <b>{_soles(e["contratado"])}</b> firmados '
        f'en {_esc(e["periodo"].lower())}, <b>ya entraron '
        f'{_soles(e["entro"])}</b> — el <b>{_p}</b>. El resto está en '
        f'cuotas por vencer, hipotecas sin desembolsar y saldos. La meta '
        f'comercial se mide sobre lo firmado; la caja, sobre lo que entró. '
        f'Cada crédito se cuenta una sola vez, cruzado por DNI.'
        f'</div>{barra}'
        f'<div class="leyenda"><span><i class="ok"></i> Ya entró '
        f'<b>{_soles(e["entro"])}</b> ({_p})</span>'
        f'<span><i class="parc"></i> Falta que entre '
        f'<b>{_soles(e["falta"])}</b> ({_pf})</span></div>'
        f'<div class="f">{_soles(e["contratado"])} firmados − '
        f'{_soles(e["entro"])} cobrados = {_soles(e["falta"])} por cobrar.'
        f'</div>'
        f'<table><tr><th>Modalidad de pago</th><th class="num">Ventas</th>'
        f'<th class="num">Contratado</th><th class="num">Ya entró</th></tr>'
        f'{mods}</table>'
        f'<div class="f">Clic en cualquier modalidad para ver las ventas que '
        f'la componen, una por una.</div>'
        + avisos + '</div>')


def _bloque_flujo(d: dict) -> str:
    """El flujo de caja mes a mes. Lo pidieron Administración y Gerencia el."""
    f = d.get("flujo") or {}
    if not f.get("hay"):
        return ""
    a = f["acumulado"]
    filas_ = ""
    for m in f["meses"]:
        neto = m["neto"]
        tono = "ok" if neto >= 0 else "no"
        ejec = ""
        if m["ejecucion"] is not None:
            t = ("no" if m["ejecucion"] > 100 else
                 "ok" if m["ejecucion"] >= 60 else "parc")
            ejec = (f'<div class="mini"><i class="{t}" style="width:'
                    f'{min(m["ejecucion"], 100):.0f}%"></i></div>'
                    f'<span class="mpct">{m["ejecucion"]:.0f}%</span>')
        elif not m.get("mide_presupuesto"):
            ejec = ('<span class="f">no se mide · lo cargado no es un plan '
                    '(ver nota)</span>')
        marca = ' style="font-weight:600"' if m["en_curso"] else ""
        filas_ += (
            f'<tr{marca}><td><b>{_esc(m["etiqueta"])}</b>'
            + ('<div class="f">mes en curso</div>' if m["en_curso"] else "")
            + f'</td>'
            f'<td class="num">{_soles(m["entro"]) if m["entro"] else "—"}</td>'
            f'<td class="num">{_soles(m["salio"]) if m["salio"] else "—"}</td>'
            f'<td class="num"><span class="pill {tono}">{_soles(neto)}</span></td>'
            f'<td class="num">{_soles(m["por_entrar"]) if m["por_entrar"] else "—"}</td>'
            f'<td class="num">{_soles(m["presupuesto"]) if m["presupuesto"] else "—"}</td>'
            f'<td>{ejec}</td></tr>')

    al = ""
    for x in (f.get("alertas") or []):
        al += (f'<div class="ojo"><b>{_esc(x["mes"])}: el gasto superó al '
               f'presupuesto en {_soles(x["exceso"])}</b> — se presupuestó '
               f'{_soles(x["presupuesto"])} y se gastó {_soles(x["gasto"])} '
               f'({x["pct"]:.0f}%).</div>')

    obs = ('<div class="ojo"><b>Sobre la columna Presupuesto — se mide desde '
           'agosto 2026.</b> Lo cargado antes son movimientos entre cuentas '
           'del grupo («BCP Corporación Habitat», «Retiro de Escalar y '
           'Habitat»), no un plan de gastos: por eso coincide con el gasto '
           'real al céntimo —en marzo difieren S/ 9 sobre S/ 648,000— y '
           'compararlos no mediría gestión. Para comparar planeado contra '
           'real hace falta que Obra informe ANTES cuánto va a gastar en '
           'personal, activos, tercerizaciones y materiales.'
           '<div class="quien">responde: Obra · y Administración lo carga'
           '</div></div>')

    fu = f.get("futuros") or {}
    if fu.get("n"):
        quienes = " · ".join(
            f'{_esc(x["quien"])} ({_esc(x["unidad"])}, {_esc(x["fecha"])}, '
            f'{_soles(x["monto"])})' for x in fu["detalle"][:4])
        al = (f'<div class="ojo"><b>{_soles(fu["monto"])} figuran como '
              f'cobrados con fecha que todavía no llega</b> — '
              f'{fu["n"]} registro(s): {quienes}. Están dentro de «entró en el '
              f'año», así que esa cifra trae plata que aún no entró. O es un '
              f'pago pactado a futuro cargado como si ya se hubiera cobrado, o '
              f'la fecha está mal escrita.'
              f'<div class="quien">responde: Cobranzas</div></div>') + al

    hip = f.get("hipotecas") or {}
    hueco = ""
    if hip.get("ventas"):
        hueco = (f'<div class="ojo"><b>La proyección de entradas es un PISO, '
                 f'no el total.</b> Hay {hip["ventas"]} ventas por hipoteca '
                 f'({_soles(hip["monto"])}) esperando que el banco desembolse, '
                 f'y AXION no registra en qué fecha llega esa plata. Solo se '
                 f'proyectan las cuotas con cronograma. Falta una casilla de '
                 f'«fecha estimada de desembolso» en la ficha de venta.'
                 f'<div class="quien">responde: Administración · y la '
                 f'desarrolladora de AXION</div></div>')

    return (
        '<div class="graf"><h4>Flujo de caja · lo que entró, lo que salió y '
        'lo que viene</h4>'
        f'<div class="nota">Las cuatro columnas <b>no se suman entre sí</b>. '
        f'«Entró» y «Salió» son historia: plata que se movió. «Por entrar» es '
        f'proyección —cuotas que vencen ese mes si el cliente paga en fecha—. '
        f'«Presupuesto» es un plan, y va al lado del gasto para compararlos, '
        f'nunca sumado a la caja.</div>'
        f'<div class="tarjetas">'
        + _tarjeta("Entró en el año", a["entro"],
                   "iniciales cobradas más cuotas pagadas, por su fecha de cobro")
        + _tarjeta("Salió en el año", a["salio"],
                   "movimientos de gasto. NO incluye el presupuesto")
        + _tarjeta("Caja neta del año", a["neto"],
                   f"lo que entró menos lo que salió. <b>Los dos lados no "
                   f"cubren lo mismo</b>: «Entró» sale del circuito comercial "
                   f"(créditos y cuotas) y «Salió» del libro de caja. Ese "
                   f"mismo libro registra S/ {f.get('cobros_del_libro', 0):,.2f} "
                   f"de cobros en el año — más que el lado que se resta. "
                   f"<b>No es una pérdida</b>, y tampoco es la utilidad: esa "
                   f"la calcula el contador")
        + _tarjeta("Por entrar (cuotas)", a["por_entrar"],
                   "cuotas pendientes por su mes de vencimiento. Es un piso: "
                   "las hipotecas sin fecha de desembolso no están acá")
        + '</div>'
        '<table><tr><th>Mes</th><th class="num">Entró</th>'
        '<th class="num">Salió</th><th class="num">Neto</th>'
        '<th class="num">Por entrar</th><th class="num">Presupuesto</th>'
        '<th>Ejecución</th></tr>' + filas_ + '</table>'
        + al + obs + hueco + '</div>')


def _bloque_vencimientos(d: dict) -> str:
    """El reparto del saldo + los vencimientos mes a mes, en la hoja donde."""
    v = d.get("vencimientos") or {}
    meses = v.get("meses") or []
    fuera = v.get("fuera") or {}
    reparto = ('<div class="graf"><h4>El saldo por cobrar, repartido</h4>'
               '<div id="grCartera"></div></div>')
    if not meses:
        return reparto

    filas_ = ""
    for m in meses:
        pend = m["falta"]
        tono = ("no" if (m["pasado"] and pend > 1) else
                "ok" if pend <= 1 else "parc")
        etiqueta = ("vencido y sin cobrar" if (m["pasado"] and pend > 1)
                    else "cobrado" if pend <= 1 else "por vencer")
        filas_ += (
            f'<tr><td><b>{_esc(m["etiqueta"])}</b>'
            f'<div class="f">{m["cuotas"]} cuota'
            f'{"s" if m["cuotas"] != 1 else ""}</div></td>'
            f'<td class="num">{_soles(m["vencia"])}</td>'
            f'<td class="num">{_soles(m["cobrado"])}</td>'
            f'<td class="num">{_soles(pend) if abs(pend) > 0.01 else "—"}</td>'
            f'<td><div class="bar"><i class="{tono}" '
            f'style="width:{min(max(m["pct"], 0), 100):.1f}%"></i></div>'
            f'<div class="f">{m["pct"]:.0f}% · {etiqueta}</div></td></tr>')

    nota_fuera = ""
    if fuera.get("creditos"):
        nota_fuera = (
            f'<div class="ojo">Esta tabla NO muestra toda la cartera: '
            f'{fuera["creditos"]} de {fuera["total_creditos"]} créditos no '
            f'tienen cronograma cargado, así que sus '
            f'{_soles(fuera["saldo"])} no vencen en ningún mes y no pueden '
            f'aparecer acá. Es lo mismo que señala la alerta de Cobranza.</div>')

    return (reparto
            + '<div class="graf"><h4>Vencimientos mes a mes · de lo que '
              'vencía, cuánto entró</h4>'
              '<div class="nota">Se agrupa por la fecha en que la cuota '
              '<b>vencía</b>, no por la fecha en que se cobró. Es la pregunta '
              'que el filtro de período no puede contestar: «por cobrar» es un '
              'saldo a hoy, no algo que pertenezca a un mes.</div>'
              '<table><tr><th>Mes de vencimiento</th>'
              '<th class="num">Vencía</th><th class="num">Cobrado</th>'
              '<th class="num">Falta</th><th>Avance</th></tr>'
            + filas_ + '</table>' + nota_fuera + '</div>')


def _es_kommo(c) -> bool:
    return str(c.get("origen", "")).upper().startswith("KOMMO")


SIN_FILTRO = {
    "Comercial": ["Asesores con venta cerrada", "Mejor asesor",
                  "Visitas hechas"],
    "Ventas": ["Vendido del inventario (%)"],
}


def _bloque_sin_filtro(hoja: str, d: dict) -> str:
    """Las cifras de AXION que no siguen el filtro, en su propio bloque."""
    quiero = SIN_FILTRO.get(hoja) or []
    cifras = [c for c in d["areas"].get(hoja, [])
              if c["etiqueta"] in quiero and not _es_kommo(c)]
    if not cifras:
        return ""
    return ('<div class="graf"><h4>De AXION · acumulado de todos los años</h4>'
            '<div class="nota">Estas cifras <b>no siguen el filtro de '
            'período</b>: son el acumulado histórico. Las de arriba sí lo '
            'siguen. Van aparte para que no se lean como si midieran la misma '
            'ventana de tiempo.</div><div class="tarjetas">'
            + "".join(_tarjeta(
                c["etiqueta"], c["valor"],
                c["formula"] if c["valor"] is not None else c["motivo"],
                c["area"], c["motivo"] if c["valor"] is not None else "")
                for c in cifras)
            + "</div></div>")


def _kommo_del_periodo(hoja: str, v: dict) -> str:
    """Las cifras del CRM de UN período, para Comercial y Marketing."""
    crm_ = (v or {}).get("crm") or {}
    if not crm_.get("disponible"):
        return ""
    at = crm_.get("atencion") or {}
    n = int(at.get("leads") or 0)
    if not n:
        return ""
    etapas = {e["valor"]: e for e in (crm_.get("etapas") or [])}
    camp = crm_.get("campanas") or []
    pct = lambda x: f"{100 * x / n:.2f}%" if n else "—"          # noqa: E731

    fichas = []
    if hoja == "Comercial":
        vend = int((etapas.get("VENDIDO") or {}).get("leads") or 0)
        des = int((etapas.get("DESESTIMADO") or {}).get("leads") or 0)
        vis = at.get("visitaron")
        fichas = [
            ("Leads del embudo", n,
             f"leads creados en el período, en el embudo «Ventas - Habitat "
             f"Inmobiliaria» — el único dentro del alcance"),
            ("Leads que visitaron", vis,
             f"leads con fecha de visita presencial cargada, de {n:,} "
             f"({pct(vis or 0)}). Se usa la FECHA y no la etapa: el que "
             f"visitó y compró ya salió de «VISITA» y no se contaría"),
            ("Leads marcados VENDIDO", vend,
             f"leads en etapa VENDIDO, de {n:,} ({pct(vend)}). **No se compara "
             f"con las ventas de AXION**: son dos sistemas con definiciones "
             f"distintas y restarlos inventaría una brecha"),
            ("Conversión del embudo (%)", (100 * vend / n) if n else None,
             f"los {vend} leads en VENDIDO sobre los {n:,} del embudo. "
             f"Numerador y denominador salen de la misma población y del "
             f"mismo período"),
            ("Leads desestimados", des,
             f"leads en etapa DESESTIMADO, de {n:,} ({pct(des)})"),
        ]
    elif hoja == "Marketing":
        sin = next((c["leads"] for c in camp
                    if "sin dato" in str(c["valor"]).lower()), 0)
        con = n - int(sin)
        reales = [c for c in camp if "sin dato" not in str(c["valor"]).lower()]
        top = reales[0] if reales else None
        fichas = [
            ("Leads captados", n,
             "leads creados en el período, en el embudo de Habitat "
             "Inmobiliaria"),
            ("Leads con campaña declarada", con,
             f"leads con campaña cargada, de {n:,} ({pct(con)}). Es el dato "
             f"que AXION no tiene: acá el origen está casi siempre"),
            ("Campaña con más leads", (top or {}).get("leads"),
             (f"«{top['valor']}» — conteo de LEADS, no de ventas ni de soles, "
              f"sobre los {con:,} con campaña. Hay {len(reales)} campañas "
              f"distintas en uso. Ojo: el campo mezcla obras, formatos de "
              f"anuncio y canales, así que el primero y el segundo no siempre "
              f"son la misma clase de cosa" if top else "sin campañas en el "
              "período")),
        ]

    if not fichas:
        return ""
    tarjetas = "".join(_tarjeta(et, val, det, "", "")
                       for et, val, det in fichas if val is not None)
    return ('<div class="graf"><h4>Del CRM (Kommo) · el embudo previo a la '
            'venta</h4><div class="nota">Estas cifras <b>no salen de AXION</b> '
            'y <b>sí siguen el filtro de período</b>: son los leads creados en '
            'la ventana elegida. Kommo no registra montos, así que no entra en '
            'rentabilidad ni en el margen.</div><div class="tarjetas">'
            + tarjetas + "</div></div>")


# Las hojas cuyo bloque del CRM se dibuja una vez por período.
CRM_POR_PERIODO = {"Comercial", "Marketing"}

CUBIERTAS = {"Leads en el embudo", "Leads del embudo", "Leads que visitaron",
             "Leads marcados VENDIDO", "Conversión del embudo (%)",
             "Leads desestimados", "Leads captados",
             "Leads con campaña declarada", "Campaña con más leads"}


def _kommo_por_periodo(hoja: str, d: dict) -> str:
    """Una copia del bloque del CRM por cada período, para que el filtro lo."""
    partes = []
    for k, v in _solo_periodos_del_viejo(d["meses"].items()):
        cuerpo = _kommo_del_periodo(hoja, v)
        if not cuerpo:
            cuerpo = ('<div class="graf"><h4>Del CRM (Kommo)</h4>'
                      '<div class="vacio">Sin leads creados en este período. '
                      'El embudo existe: elegí otro período para verlo.</div>'
                      '</div>')
        partes.append(f'<div class="mes" data-mes="{k}"'
                      f'{"" if k == "None" else " hidden"}>{cuerpo}</div>')
    return "".join(partes)


def _bloque_kommo(cifras) -> str:
    """Las cifras del CRM, SIEMPRE en su propio bloque y rotuladas."""
    if not cifras:
        return ""
    return ('<div class="graf"><h4>Del CRM (Kommo) · el embudo previo a la '
            'venta</h4><div class="nota">Estas cifras <b>no salen de AXION</b> '
            'y <b>no responden a los filtros de arriba</b>: son el acumulado '
            'del embudo «Ventas - Habitat Inmobiliaria», el único dentro del '
            'alcance. Kommo no registra montos, así que no entra en '
            'rentabilidad ni en el margen.</div><div class="tarjetas">'
            + "".join(_tarjeta(
                c["etiqueta"], c["valor"],
                c["formula"] if c["valor"] is not None else c["motivo"],
                c["area"], c["motivo"] if c["valor"] is not None else "")
                for c in cifras)
            + "</div></div>")


def _horas(x) -> str:
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return "—"
    if x < 1:
        return f"{x * 60:.0f} min"
    if x < 48:
        return f"{x:.1f} h"
    return f"{x / 24:.1f} d"


def _tabla(cabeceras: list[str], filas: list[list[str]], clase="") -> str:
    th = "".join(f"<th>{_esc(c)}</th>" for c in cabeceras)
    tr = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in f) + "</tr>"
                 for f in filas)
    return f'<table class="{clase}"><tr>{th}</tr>{tr}</table>'


def _barras(items: list[dict], etiqueta="valor", n=15) -> str:
    """Un conteo con su barra. Se dibuja sobre el MÁXIMO de la lista, no sobre."""
    if not items:
        return ""
    tope = max(i["leads"] for i in items) or 1
    g = ""
    for i in items[:n]:
        g += (f'<div class="gb"><div>{_esc(i[etiqueta])}</div>'
              f'<div class="bar"><i class="ok" '
              f'style="width:{100 * i["leads"] / tope:.1f}%"></i></div>'
              f'<div class="val">{i["leads"]:,} · {i["pct"]:.1f}%</div></div>')
    if len(items) > n:
        g += (f'<div class="f">y {len(items) - n} más, con '
              f'{sum(i["leads"] for i in items[n:]):,} leads entre todas</div>')
    return g


def _bloque_crm(d, v) -> str:
    c = v.get("crm") or {}
    if not c.get("disponible"):
        return ('<div class="nota"><b>El CRM no respondió en esta lectura.</b> '
                f'{_esc(c.get("error", ""))}<br>Las cifras existen: son los '
                'leads del embudo «Ventas - Habitat Inmobiliaria» en Kommo. '
                'No se muestra un cero porque un cero se leería como «no hubo '
                'leads».</div>')
    a = c["atencion"]
    if not a.get("leads"):
        return ('<div class="nota">No hay leads creados en este período. '
                'El CRM tiene data desde julio de 2025.</div>')

    n = a["leads"]
    j0, j1 = a["jornada"]
    tarjetas = "".join([
        _tarjeta("Leads del período", n,
                 "leads CREADOS en la ventana elegida, embudo «Ventas - "
                 "Habitat Inmobiliaria». Se filtra por creación: son los que "
                 "ENTRARON, no los que se cerraron"),
        _tarjeta("Con atención medible", a["con_llamada"],
                 f'leads con primera llamada POSTERIOR a su creación, de '
                 f'{n:,} ({100 * a["con_llamada"] / n:.1f}%) — son los únicos '
                 f'que entran en los promedios de abajo. Los otros '
                 f'{n - a["con_llamada"]:,} se reparten en '
                 f'{a["sin_llamada"]:,} sin llamada cargada y '
                 f'{a.get("negativas", 0):,} con la llamada fechada antes de '
                 f'que el lead existiera'),
        _tarjeta("Atención · mediana (horas)", None if a["mediana"] is None else
                 round(a["mediana"], 1),
                 f'MEDIANA de horas entre la creación del lead y su primera '
                 f'llamada = {_horas(a["mediana"])}. El promedio es '
                 f'{_horas(a["promedio"])}: la diferencia la hacen unos pocos '
                 f'leads atendidos muy tarde, y por eso manda la mediana'),
        _tarjeta("Sin gestionar", a["sin_gestionar"],
                 "leads en etapa «ASIGNADO»: entregados a un asesor y todavía "
                 "sin mover"),
    ])

    fds = ('<div class="graf"><h4>Tiempo de atención · día hábil contra fin de '
           'semana</h4>'
           + _tabla(["Cuándo entró el lead", "Leads", "Mediana de atención"], [
               ["Lunes a viernes", f'{a["leads_habil"]:,}',
                _horas(a["habil_mediana"])],
               ["Sábado y domingo", f'{a["leads_finde"]:,}',
                _horas(a["finde_mediana"])],
           ])
           + f'<div class="f">Fin de semana se decide con la <b>hora de '
             f'Huancayo</b> (UTC−5), no con la hora del servidor: sin '
             f'convertir, un lead del viernes 20:00 se contaría como sábado. '
             f'De los {n:,} leads, {a["leads_en_jornada"]:,} entraron entre '
             f'las {j0}:00 y las {j1}:00 — ese rango es un supuesto nuestro, '
             f'corríjanlo si su jornada es otra.</div></div>')

    filas = []
    for r in c["responsables"]:
        filas.append([
            _esc(r["responsable"]), f'{r["leads"]:,}',
            f'{100 * r["leads"] / n:.1f}%', f'{r["vendidos"]:,}',
            f'{r["con_llamada"]:,}', _horas(r["horas_mediana"]),
            _horas(r["horas_habil"]), _horas(r["horas_finde"]),
            f'{r["leads_finde"]:,}',
        ])
    tabla_resp = (
        '<div class="graf"><h4>Leads por responsable</h4>'
        + _tabla(["Asesor", "Leads", "% del total", "Vendidos",
                  "Con llamada", "Atención (mediana)", "Hábil", "Fin de semana",
                  "Leads de fin de semana"], filas)
        + '<div class="f">«Atención» es la mediana de horas entre la creación '
          'del lead y su primera llamada. Se publica la mediana y no el '
          'promedio porque un solo lead atendido meses después mueve el '
          'promedio de un asesor entero: donde las dos difieren mucho, la que '
          'miente es el promedio.</div></div>')

    aviso = ""
    if a["negativas"]:
        aviso = ('<div class="nota"><b>Dato para Comercial: '
                 f'{a["negativas"]:,} leads tienen su primera llamada '
                 f'ANTERIOR a la creación del lead.</b> No es un tiempo '
                 'negativo, es un registro mal cargado —o la llamada se agendó '
                 'antes de crear la ficha—. Quedan fuera de todos los '
                 'promedios de esta hoja, y se muestran acá en vez de '
                 'corregirse: la decisión es de Habitat.</div>')

    gen = ('<div class="graf"><h4>Género</h4>' + _barras(c["genero"])
           + '<div class="f">Porcentaje sobre el total de leads del período, '
             'no sobre los que tienen el campo lleno. Por eso «(sin dato)» '
             'aparece como fila: esconderlo haría que los porcentajes sumen '
             '100% sobre una base distinta a la del rótulo.</div></div>')
    camp = ('<div class="graf"><h4>Leads por campaña</h4>'
            + _barras(c["campanas"])
            + '<div class="f">La campaña la escribe el asesor a mano: los 9 '
              'campos de rastreo automático (utm_source, gclid, fbclid, '
              'ttad_name…) están vacíos. Sirve para agrupar, no para calcular '
              'costo por anuncio.</div></div>')
    et = ('<div class="graf"><h4>Etapa del lead</h4>' + _barras(c["etapas"])
          + '<div class="f">Es la etapa donde está el lead <b>hoy</b>, no por '
            'la que pasó. Los «VENDIDO» de acá <b>no son</b> las ventas de '
            'AXION: dos sistemas, dos definiciones, dos ventanas — restarlos '
            'inventaría una brecha.</div></div>')
    proy = ('<div class="graf"><h4>Proyecto de interés</h4>'
            + _barras(c["proyectos"]) + '</div>')

    extras = "".join(
        f'<div class="graf"><h4>{_esc(e["titulo"])}</h4>'
        + _barras(e["items"]) + '</div>'
        for e in c.get("extras", []) if e["items"])

    return ('<div class="nota"><b>Todo de KOMMO en vivo.</b> Embudo «Ventas - '
            'Habitat Inmobiliaria», el único dentro del alcance: los otros '
            'tres de la cuenta —Concept y Atención al cliente— quedan fuera '
            'por decisión de Habitat. <b>Kommo no registra montos</b>, así que '
            'nada de esta hoja entra en rentabilidad ni en el margen.</div>'
            + f'<div class="tarjetas">{tarjetas}</div>' + aviso + tabla_resp
            + fds + gen + camp + et + proy + extras)


def _tarjeta(et, val, pie, area="", ojo="") -> str:
    hay = val is not None and not (isinstance(val, float) and pd.isna(val))
    v = _abrev(val) if hay else "SIN DATO"
    exacto = (f'<div class="exacto">{_fmt(val)}</div>'
              if hay and _se_abrevia(val) else "")
    return (f'<div class="c"><div class="et">{_esc(et)}</div>'
            f'<div class="v {"" if hay else "sin"}">{v}</div>'
            + exacto
            + f'<div class="f">{_esc(pie)}</div>'
            + (f'<div class="ojo">{_esc(ojo)}</div>' if ojo else "")
            + (f'<div class="quien">responde: {_esc(area)}</div>' if area else "")
            + "</div>")


def _auditar(clave: str) -> str:
    """Un desplegable con las filas que producen la cifra."""
    fn = auditoria.DETALLES.get(clave)
    if fn is None:
        return ""
    titulo, cols, filas = fn()
    if not filas:
        return ""
    th = "".join(f"<th>{_esc(c)}</th>" for c in cols)
    tr = "".join("<tr>" + "".join(f"<td>{_esc(v)}</td>" for v in f) + "</tr>"
                 for f in filas)
    return (f'<details class="aud"><summary>{_esc(titulo)}</summary>'
            f'<div class="cuerpo"><table><tr>{th}</tr>{tr}</table></div>'
            f'</details>')


def _evolucion(d: dict, i: dict) -> str:
    """La evolución mes a mes del indicador, o por qué no la tiene."""
    if i["valor"] is None:
        return ('<div class="evo vacia"><b>Sin evolución.</b> Este indicador '
                'no tiene fuente en AXION, así que no hay serie que mostrar. '
                'El motivo y el área que puede destrabarlo están abajo.</div>')
    s = d.get("series", {}).get(i["indicador"])
    if not s or not s["puntos"]:
        return ('<div class="evo vacia"><b>Sin evolución mensual.</b> La cifra '
                'existe pero no se puede cortar por mes.</div>')
    if s["plana"]:
        return ('<div class="evo vacia"><b>Sin evolución mensual.</b> Este '
                'indicador mide sobre toda la población a la vez, así que da '
                'lo mismo en cada mes. Dibujar una línea plana sugeriría un '
                'movimiento que no existe.</div>')
    pts = s["puntos"]
    mx = max(pts.values()) or 1
    curso = s.get("en_curso")
    barras = "".join(
        f'<div class="ev{" curso" if m == curso else ""}"><b>{pts[m]:,.0f}</b>'
        f'<i style="height:{max(3, 100 * pts[m] / mx):.0f}%" '
        f'title="{MES_CORTO[m]}: {pts[m]:,.2f}"></i>'
        f'<span>{MES_CORTO[m]}{" · en curso" if m == curso else ""}</span></div>'
        for m in sorted(pts))
    ult, prev = pts[max(pts)], pts.get(max(pts) - 1)
    if curso is not None and max(pts) == curso:
        delta = (f' · <span class="f">agosto va {s["dia"]} de '
                 f'{s["dias_mes"]} días: no se compara contra el mes completo'
                 f'</span>') if curso == 8 else (
                 f' · <span class="f">mes en curso, {s["dia"]} de '
                 f'{s["dias_mes"]} días: no se compara contra el mes anterior'
                 f'</span>')
    elif prev:
        dif = 100 * (ult - prev) / prev
        flecha = "▲" if dif > 0 else "▼" if dif < 0 else "="
        color = "ok" if dif > 0 else "no" if dif < 0 else ""
        delta = (f' · <span class="{color}">{flecha} {abs(dif):.0f}% '
                 f'vs el mes anterior</span>')
    else:
        delta = ""
    rotulo = ("Último mes con dato" if max(pts) != curso
              else f"{MES_CORTO[curso]} al día de hoy")
    return (f'<div class="evo"><div class="et">Evolución 2026</div>'
            f'<div class="evb">{barras}</div>'
            f'<div class="evd">{rotulo}: {_fmt(ult)}{delta}</div>'
            f'</div>')


MES_CORTO = {1: "Ene", 2: "Feb", 3: "Mar", 4: "Abr", 5: "May", 6: "Jun",
             7: "Jul", 8: "Ago", 9: "Set", 10: "Oct", 11: "Nov", 12: "Dic"}


RETIRADOS_DE_LA_VISTA = {
    "Tasa de visibilidad de marca":
        "no tiene definición medible: «visibilidad» no tiene fórmula "
        "declarada en ningún lado, la meta dice «100%» sin decir de qué, "
        "marketing_source llega vacío en la mitad de las ventas y Lead está "
        "en cero",
    "Tasa de innovación en proyectos":
        "no hay definición de qué cuenta como «innovación» ni registro que "
        "la mida; con meta «100%» y sin fórmula posible no es un indicador "
        "todavía, es una intención",
}


def _spark(d: dict, i: dict) -> str:
    """La columna de evolución: la misma serie que el detalle grande, en."""
    s = d.get("series", {}).get(i["indicador"])
    if not s or not s["puntos"] or s["plana"]:
        return '<span class="sinserie">—</span>'
    pts = s["puntos"]
    mx = max(pts.values()) or 1
    MES = MES_CORTO
    return ('<div class="spark">' + "".join(
        f'<i style="height:{max(8, 100 * pts[m] / mx):.0f}%" '
        f'title="{MES[m]}: {pts[m]:,.2f}"></i>' for m in sorted(pts))
        + "</div>")


def _fila_matriz(d: dict, i: dict) -> str:
    """Un indicador = una fila de la matriz + su fila de detalle escondida."""
    cls = {"calculado": "ok", "parcial": "parc"}.get(i["estado"], "no")
    real = (_fmt(i["valor"]) if i["no_cuadra"]
            else _con_unidad(i["valor"], i["unidad"]))
    meta = ("la define Habitat" if i["propio"]
            else _con_unidad(i["meta"], i["unidad"]))
    avance = '<span class="sinserie">—</span>'
    if i["valor"] is not None and i["meta"] and not i["no_cuadra"]:
        pct = 100 * float(i["valor"]) / float(i["meta"])
        tono = "ok" if pct >= 100 else "parc" if pct >= 60 else "no"
        avance = (f'<div class="mini"><i class="{tono}" '
                  f'style="width:{max(2, min(pct, 100)):.0f}%"></i></div>'
                  f'<span class="mpct">{pct:,.0f}%</span>')
    elif i["no_cuadra"]:
        avance = (f'<span class="nocomp" title="{_esc(i["ojo"])}">'
                  f'no comparable ⚠</span>')
    pills = f'<span class="pill {cls}">{i["estado"]}</span>'
    if i["propio"]:
        pills += '<span class="pill prop">propuesto</span>'
    det = (_evolucion(d, i)
           + (f'<div><b>Para qué sirve:</b> {_esc(i["objetivo"])}</div>'
              if i.get("objetivo") else "")
           + (f'<div><b>Qué se necesita para generarlo:</b> '
              f'{_esc(i["necesita"])}</div>' if i.get("necesita") else "")
           + (f'<div><b>Cómo se calcula:</b> {_esc(i["calculo"])}</div>'
              if i.get("calculo") else "")
           + f'<div><b>Alcance:</b> <span class="pill {cls}">{i["estado"]}'
           f'</span> {_esc(i["alcance"] or i["motivo"])}</div>'
           + (f'<div class="ojo">{_esc(i["ojo"])}</div>' if i["ojo"] else "")
           + (f'<div class="quien">responde: {_esc(i["area"])}</div>'
              if i["area"] else "")
           + (f'<div><b>Ellos tipearon:</b> {_fmt(i["tipeado"])} — el '
              f'tablero calcula en vivo, no copia ese número</div>'
              if i["tipeado"] else "")
           + ('<div class="ini"><button class="irdet" '
              'onclick="event.stopPropagation();irA(\'Rentabilidad\',\'\')">'
              'ver la hoja Rentabilidad</button> la mitad de ingresos ya '
              'está ahí, en vivo</div>' if i["propio"] else
              '<div class="ini">Iniciativa: <i>la carga Habitat</i></div>'))
    return (f'<tr class="mrow {cls}" onclick="toggleFila(this)">'
            f'<td><b>{_esc(i["indicador"])}</b>'
            f'<div class="mobj">{_esc(i["objetivo"])}</div></td>'
            f'<td class="num">{meta}</td>'
            f'<td class="num"><b>{real}</b></td>'
            f'<td class="av">{avance}</td>'
            f'<td>{_spark(d, i)}</td>'
            f'<td class="est">{pills}</td></tr>'
            f'<tr class="mdet" hidden><td colspan="6">{det}</td></tr>')


def _bloque_scorecard(d, v) -> str:
    """El scorecard como matriz gerencial: una fila por indicador con."""
    PERS = ("Finanzas", "Clientes", "Procesos Internos",
            "Aprendizaje y Crecimiento")
    activos = [i for i in v["indicadores"]
               if i["indicador"] not in RETIRADOS_DE_LA_VISTA]
    n_hab = sum(1 for i in activos if not i["propio"])
    n_pro = sum(1 for i in activos if i["propio"])
    n_ok = sum(1 for i in activos if i["estado"] == "calculado")
    n_pa = sum(1 for i in activos if i["estado"] == "parcial")
    n_no = sum(1 for i in activos if i["estado"] == "sin fuente")
    h = (f'<div class="nota"><b>Los indicadores y sus metas los definió '
         f'Habitat; lo que aporta este tablero es medirlos en vivo.</b><br>'
         f'<b>La ventana del Scorecard es 2026</b> — la misma de las metas. '
         f'Lo registrado de años anteriores no entra acá: queda en '
         f'Resultados, que es el corte histórico.<br>'
         f'En vista: <b>{n_hab} de Habitat</b> más <b>{n_pro} propuestos por '
         f'nosotros</b> (rentabilidad por obra y por razón social, marcados). '
         f'{len(RETIRADOS_DE_LA_VISTA)} se retiraron de la vista por no tener '
         f'definición medible: siguen al pie, con su motivo. '
         f'Clic en cualquier fila para abrir su detalle.</div>'
         f'<div class="leyenda">'
         f'<span><i class="p ok"></i> <b>{n_ok} con cifra completa</b> — la '
         f'data cubre todo lo que el indicador mide</span>'
         f'<span><i class="p parc"></i> <b>{n_pa} parcial</b> — se calcula, '
         f'pero sobre data incompleta</span>'
         f'<span><i class="p no"></i> <b>{n_no} sin fuente</b> — AXION no '
         f'tiene con qué calcularlo</span></div>')
    AREAS_SC = []
    for i in activos:
        a = i.get("area_bsc") or "Otros"
        if a not in AREAS_SC:
            AREAS_SC.append(a)
    h += ('<div class="chips"><button class="chip on" data-p="">Todas las '
          'áreas</button>')
    for a_ in AREAS_SC:
        h += f'<button class="chip" data-p="{_esc(a_)}">{_esc(a_)}</button>'
    h += "</div>"
    h += ('<div class="chips"><span class="f" style="align-self:center;'
          'margin-right:6px">o por perspectiva del BSC:</span>')
    for p_ in PERS:
        h += (f'<button class="chip" data-pp="{_esc(p_)}">Perspectiva · '
              f'{_esc(p_)}</button>')
    h += "</div>"

    h += ('<table class="matriz"><thead><tr>'
          '<th>Indicador · objetivo</th><th class="num">Meta</th>'
          '<th class="num">Real</th><th>% de la meta</th>'
          '<th>Evolución 2026</th><th>Estado</th></tr></thead>')
    for p_ in AREAS_SC:
        g = [i for i in activos if (i.get("area_bsc") or "Otros") == p_]
        if not g:
            continue
        n = {e: sum(1 for i in g if i["estado"] == e)
             for e in ("calculado", "parcial", "sin fuente")}
        persp_del_grupo = "|".join(sorted({i["perspectiva"] for i in g}))
        h += (f'<tbody class="cuad" data-p="{_esc(p_)}" '
              f'data-pp="{_esc(persp_del_grupo)}">'
              f'<tr class="mp"><td colspan="6"><h3>{_esc(p_)}</h3>'
              f'<span class="pill ok">{n["calculado"]} completo</span>'
              f'<span class="pill parc">{n["parcial"]} parcial</span>'
              f'<span class="pill no">{n["sin fuente"]} sin fuente</span>'
              f'</td></tr>')
        for i in g:
            h += _fila_matriz(d, i)
        h += "</tbody>"
    return h + "</table>"


def _bloque_rentabilidad(d, v) -> str:
    rango = ""
    try:
        _m = movimientos.crudo()
        _g = _m[_m["clase"] == "gasto"] if not _m.empty else _m
        _f = pd.to_datetime(_g["fecha"], errors="coerce").dropna()
        if len(_f):
            rango = (f" <b>El costo existe desde {_f.min():%b-%Y} "
                     f"({_f.min():%d-%m-%Y} en adelante)</b>: en los períodos "
                     f"que abarcan años anteriores, la columna Contratado cubre "
                     f"más tiempo que la de Costo, así que las dos NO se "
                     f"restan.")
    except Exception:  # noqa: BLE001
        pass
    h = ('<div class="nota"><b>Todo en esta hoja sale de AXION</b> —Sale, '
         'Credit, CxCPayment, Project y, desde el 04-ago, MovimientoGasto '
         'para el costo—. Ni una cifra viene de ContaSis ni de los Excels de '
         'la administradora: eso vive en Validación y en Junio. <b>El costo '
         'respeta el mismo período que el resto de la fila</b> y cubre solo lo '
         'emparejado a obra: lo que falta está declarado al pie, con su monto.'
         + rango + '</div>'
         '<div class="notaObraRent" hidden><div class="nota">Hay una obra '
         'elegida en el filtro: la tabla por empresa se oculta porque sus '
         'totales incluyen TODAS las obras de cada empresa, no solo la '
         'elegida. Elegí «Todas las obras» para verla.</div></div>'
         '<div class="soloEmpresas">'
         '<div class="persp">Por razón social</div><table><tr>'
         '<th>Empresa</th><th class="num">Obras</th>'
         '<th class="num">Contratado S/</th><th class="num">Cobrado S/</th>'
         '<th class="num">Costo S/</th></tr>')
    for x in v["razones"]:
        costo_rs = (f'<td class="num">{_soles(x["costo"])}</td>'
                    if x.get("costo") is not None else
                    '<td class="vacio">sin gasto atribuido</td>')
        h += (f'<tr data-emp="{_esc(x["empresa"])}">'
              f'<td>{_esc(x["empresa"])}</td>'
              f'<td class="num">{x["obras"]}</td>'
              f'<td class="num">{_soles(x["contratado"])}</td>'
              f'<td class="num">{_soles(x["cobrado"])}</td>'
              + costo_rs + '</tr>')
    h += ('</table></div>'
          '<div class="persp">Por obra · <span class="contObras">'
          f'las {len(v["obras"])}, ninguna omitida</span></div>'
          '<table><tr><th>Obra</th><th>Etapa</th><th class="num">Ventas</th>'
          '<th class="num">Contratado S/</th><th class="num">Cobrado S/</th>'
          '<th class="num">Costo S/</th></tr>')
    for o in v["obras"]:
        if o.get("costo") is not None:
            celda = (f'<td class="num">{_soles(o["costo"])}'
                     f'<div class="f">{_esc(o.get("costo_nota", ""))}</div>'
                     f'</td>')
        else:
            celda = (f'<td class="vacio">'
                     f'{_esc(o.get("motivo_costo") or o["motivo"] or "esperando carga de costos")}'
                     f'</td>')
        sin_ingreso = (not o["ventas"]) and not (o["contratado"] or o["cobrado"])
        nota_obra = (f'<div class="f">{_esc(o["motivo"])}</div>'
                     if sin_ingreso and o.get("motivo") else "")
        h += (f'<tr data-emp="{_esc(o["empresa"])}" data-obra="{_esc(o["obra"])}">'
              f'<td><b>{_esc(o["obra"])}</b>'
              f'<div class="f">{_esc(o["empresa"])}</div>{nota_obra}</td>'
              f'<td>{_esc(o["etapa"])}</td>'
              f'<td class="num">{o["ventas"]}</td>'
              f'<td class="num">{_soles(o["contratado"])}</td>'
              f'<td class="num">{_soles(o["cobrado"])}</td>'
              + celda + '</tr>')
    return h + "</table>"


def _hoja_validacion(d: dict) -> str:
    """Las tres fuentes del mismo mes, cada una con su detalle abrible."""
    v = d["validacion"]
    h = (f'<div class="nota"><b>Para qué sirve esta hoja.</b> Los mismos '
         f'S/ de un mes se ven distintos según a quién le preguntes, y '
         f'<b>las tres respuestas son correctas</b>: firmar un contrato, '
         f'reconocer el ingreso ante SUNAT y cobrar la plata pasan en '
         f'momentos distintos. Acá están las tres, una al lado de la otra, '
         f'con lo que cada una mide y qué ventana cubre de verdad.<br>'
         f'<b>No se restan entre sí</b> —esa resta daría una brecha '
         f'inventada— y por eso esta hoja NO es un comparativo: es el '
         f'argumento de por qué hace falta una sola fuente.<br>'
         f'<b>Mes validado: {_esc(v["mes"])} 2026.</b> Esta hoja no sigue el '
         f'selector de arriba: ContaSis y los Excels de la administradora '
         f'cierran por mes y el último cerrado es ese. Julio se lee igual '
         f'cuando cierre, sin rehacer nada.</div>'
         f'<div class="tarjetas">')
    for k, b in enumerate(v["bloques"]):
        hay = b["filas"]
        idb = f"val{k}"
        h += (f'<div class="c fuente{" clic" if hay else ""}"'
              + (f' onclick="abrir(\'{idb}\')"' if hay else "")
              + f'><div class="et">{_esc(b["fuente"])}</div>'
              f'<div class="v">{_abrev(b["cifra"], moneda=True)}</div>'
              + (f'<div class="exacto">{_soles(b["cifra"])}</div>'
                 if _se_abrevia(b["cifra"]) else "")
              + f'<div class="f">{_esc(b["pregunta"])}<br>'
              f'<b>{_esc(b["detalle"])}</b><br>'
              f'ventana: {_esc(b["ventana"])}</div>'
              + (f'<div class="ojo">{_esc(b["resaltante"])}</div>'
                 if b["resaltante"] else "")
              + f'<div class="quien">sale de: {_esc(b["de_donde"])}</div>'
              + ('<div class="verdet">ver las filas que la suman</div>'
                 if hay else
                 '<div class="quien">sin filas para mostrar</div>')
              + '</div>')
    h += "</div>"
    for k, b in enumerate(v["bloques"]):
        if not b["filas"]:
            continue
        idb = f"val{k}"
        th = "".join(f'<th>{_esc(c)}</th>' for c in b["cols"])
        tr = "".join("<tr>" + "".join(f'<td>{_esc(c)}</td>' for c in f)
                     + "</tr>" for f in b["filas"])
        h += (f'<div class="panel" id="{idb}" hidden>'
              f'<div class="ph"><b>{_esc(b["fuente"])} · '
              f'{_esc(b["pregunta"])}</b>'
              f'<button onclick="cerrar(\'{idb}\')">cerrar</button></div>'
              f'<div class="regla">{_esc(b["de_donde"])} · ventana: '
              f'{_esc(b["ventana"])}</div>'
              f'<div class="persp tot">{len(b["filas"])} filas · '
              f'suman {_soles(b["cifra"])}</div>'
              f'<div class="cuerpo"><table><tr>{th}</tr>{tr}</table></div>'
              f'</div>')
    return (h + '<div class="nota"><b>Por qué hace falta una sola fuente</b>'
            '<br>' + "<br>".join(_esc(x) for x in v["porque"]) + "</div>")


def _referencias(claves: list[str]) -> str:
    """Las listas de referencia del pie de cada hoja, con un encabezado que."""
    cuerpo = "".join(_auditar(k) for k in claves)
    if not cuerpo:
        return ""
    return ('<div class="persp">Listas de referencia · no cambian con el '
            'período</div>' + cuerpo)


def _bloque_movimientos(d: dict) -> str:
    """El costo real por obra, de `MovimientoGasto`."""
    m = d.get("movimientos") or {}
    if not m.get("hay"):
        return ""
    r = m["resumen"]
    emp_de_obra = d.get("empresa_de_obra") or {}
    filas = "".join(
        f'<tr data-obra-mov="{_esc(o["obra"])}" '
        f'data-emp-mov="{_esc(emp_de_obra.get(o["obra"], ""))}">'
        f'<td>{_esc(o["obra"])}</td>'
        f'<td class="num">{o["movimientos"]:,}</td>'
        f'<td class="num">{_soles(o["gasto"])}</td></tr>'
        for o in m["por_obra"])

    des = m.get("desglose") or {}

    def _detalle(clave: str, titulo: str, cab: str) -> str:
        """Lo que compone una tarjeta, abrible. Agrupado, no las 4,000 filas."""
        items = des.get(clave) or []
        if not items:
            return ""
        cuerpo = "".join(
            f'<tr><td>{_esc(i["clave"])}</td>'
            f'<td class="num">{i["filas"]:,}</td>'
            f'<td class="num">{_soles(i["monto"])}</td></tr>' for i in items)
        return (f'<details class="aud"><summary>{_esc(titulo)}</summary>'
                f'<div class="cuerpo"><table><tr><th>{_esc(cab)}</th>'
                f'<th class="num">Movimientos</th><th class="num">Monto</th>'
                f'</tr>{cuerpo}</table>'
                f'<div class="f">Los 30 mayores. Agrupado, no fila por fila: '
                f'el detalle completo vive en AXION.</div>'
                f'</div></details>')
    avisos = "".join(
        f'<div class="nota"><b>{_esc(a["etiqueta"])}</b>'
        + (f' — {_soles(a["cifra"])}' if a.get("cifra") else "")
        + f'<br>{_esc(a["texto"])}'
        f'<div class="quien">responde: {_esc(a["area"])}</div></div>'
        for a in m["avisos"])
    sin = "".join(
        f'<tr><td>{_esc(s["proyecto"])}</td>'
        f'<td class="num">{s["filas"]:,}</td>'
        f'<td class="num">{_soles(s["monto"])}</td></tr>'
        for s in m["sin_atribuir"][:20])
    return (
        '<div class="graf"><h4>Costo real por obra · tabla '
        '<code>MovimientoGasto</code> de AXION</h4>'
        f'<div class="nota"><b>Esto es nuevo.</b> AXION estrenó el módulo de '
        f'movimientos y por fin trae el campo <b>proyecto</b>, que es lo que '
        f'faltaba para calcular margen por obra. {r["filas"]:,} movimientos, '
        f'período {_esc(r["periodo"])}. <b>No responde al filtro de mes</b>: '
        f'es el acumulado.</div>'
        f'<div class="tarjetas">'
        + _tarjeta("Gasto real registrado", r["gasto"]["monto"],
                   f'{r["gasto"]["filas"]:,} movimientos de gasto. NO incluye '
                   f'el presupuesto: ese va aparte porque no es plata que salió')
        + _tarjeta("De eso, atribuido a obra", r["gasto_atribuido"],
                   f'{r["pct_atribuido"]:.1f}% del gasto, repartido en '
                   f'{r["obras_con_gasto"]} de las 18 obras. El resto no se '
                   f'reparte: se lista abajo con su monto')
        + _tarjeta("Venta registrada en caja", r["venta"]["monto"],
                   f'{r["venta"]["filas"]:,} movimientos «Venta al detalle» y '
                   f'«Venta Mayoreo». NO se compara con el Vendido de Sale: '
                   f'son dos definiciones distintas')
        + _tarjeta("Presupuesto (NO es caja)", r["presupuesto"]["monto"],
                   f'{r["presupuesto"]["filas"]:,} movimientos de presupuesto. '
                   f'AXION los marca como «Ingreso», junto a las ventas. Acá '
                   f'van separados y nunca se suman con la caja')
        + '</div>'
        + _detalle("gasto", "▸ Qué compone el gasto real · por proyecto tal "
                            "como lo escribió AXION", "Valor de «proyecto»")
        + _detalle("atribuido", "▸ Qué compone lo atribuido a obra",
                   "Obra de AXION")
        + _detalle("venta", "▸ Qué compone la venta en caja", "Tipo")
        + _detalle("presupuesto", "▸ Qué compone el presupuesto", "Tipo")
        + f'<table><tr><th>Obra</th><th class="num">Movimientos</th>'
        f'<th class="num">Gasto real</th></tr>{filas}</table>'
        '<div class="vacioMov" hidden><div class="vacio">Con este filtro no '
        'hay gasto atribuido en MovimientoGasto: puede estar cargado bajo un '
        'rótulo que todavía no empareja con la obra. Los rótulos sin emparejar '
        'están listados más abajo con su monto.</div></div>'
        '<div class="f">Emparejado por PALABRAS COMPLETAS contra las 18 obras '
        'de <code>Project</code>, nunca por prefijo. Lo que no empareja no se '
        'reparte entre las demás.</div>'
        + avisos
        + '<details class="aud"><summary>Los valores de «proyecto» que NO son '
        f'una obra de AXION ({len(m["sin_atribuir"])}) — con su plata'
        '</summary><div class="cuerpo"><table><tr><th>Valor del campo</th>'
        '<th class="num">Filas</th><th class="num">Monto</th></tr>'
        + sin + '</table></div></details></div>')


def _extras_hoja(hoja: str, d: dict) -> str:
    """Lo que NO cambia con el período y va al pie de esas hojas."""
    if hoja == "Rentabilidad":
        return (_bloque_movimientos(d)
                + '<div class="persp">Lo que falta para cerrar la '
                  'rentabilidad</div><div class="tarjetas">'
                + "".join(_tarjeta(a["etiqueta"], a["valor"], a["motivo"],
                                   a["area"])
                          for a in d["avisos_rentabilidad"])
                + "</div>" + _referencias(["obras", "duplicados"]))
    if hoja == "Scorecard":
        ret = [i for i in d["indicadores"]
               if i["indicador"] in RETIRADOS_DE_LA_VISTA]
        x = (f'<details class="aud"><summary>Indicadores retirados de la '
             f'vista gerencial ({len(ret)}) — el dato no se borra'
             f'</summary><div class="cuerpo"><table><tr><th>Indicador</th>'
             f'<th>Perspectiva</th><th class="num">Meta</th>'
             f'<th>Por qué se retiró</th></tr>')
        for i in ret:
            x += (f'<tr><td><b>{_esc(i["indicador"])}</b></td>'
                  f'<td>{_esc(i["perspectiva"])}</td>'
                  f'<td class="num">{_con_unidad(i["meta"], i["unidad"])}</td>'
                  f'<td>{_esc(RETIRADOS_DE_LA_VISTA[i["indicador"]])}</td>'
                  f'</tr>')
        x += ('</table></div></details>')
        return x
    return ""


def _hoja_area_filtrable(hoja: str, cifras: list, extra: str = "") -> str:
    """Igual que Resultados: las cifras se dibujan con el acumulado y el JS."""
    h = ('<div class="volver"><button class="irhoja" '
         'onclick="volverAResultados()">volver a Resultados</button>'
         '<span>Los filtros de arriba —período, obra, razón social y asesor— '
         'siguen puestos: esta hoja muestra el mismo recorte que traías.'
         '</span></div>'
         '<div class="nota">Las cifras de esta sección salen de AXION por API '
         'y responden a los filtros de arriba: se suman las filas que ves al '
         'abrir cada una. <b>El período por defecto es el año 2026</b>; lo '
         'registrado en años anteriores se ve eligiendo «Todos los años». '
         'Si al final de la hoja hay un bloque del CRM, ese va aparte y lo '
         'dice: no sale de AXION ni sigue estos filtros.</div>'
         '<div class="destacados">')
    for k, c in enumerate(cifras):
        fs, _fuera = _del_anio(c)
        s = sum(f["monto"] for f in fs)
        val = (s if c["modo"] == "suma" else
               len(fs) if c["modo"] == "cuenta" else
               (s / len(fs) if fs else 0))
        h += (f'<div class="dest clic" onclick="verArea(\'{hoja}\',{k})">'
              f'<div class="et">{_esc(c["nombre"])}</div>'
              f'<div class="vg" id="a{hoja}{k}">'
              + (f'{val:,.0f}' if c["modo"] == "cuenta"
                 else _abrev(val, moneda=c.get("unidad") != "%")) + '</div>'
              + ('' if c["modo"] == "cuenta" else
                 f'<div class="exacto" id="x{hoja}{k}">'
                 + (f'S/ {val:,.2f}' if _se_abrevia(val) else '') + '</div>')
              + f'<div class="cant" id="c{hoja}{k}">{len(fs)} '
              f'{_esc(c["unidad"])}</div>'
              f'<div class="f">{_esc(c["calculo"])}</div>'
              + ("" if c["mensual"] else
                 '<div class="src">saldo a hoy · el período no lo cambia</div>')
              + '<div class="acciones"><span class="verdet">'
              'ver qué la compone</span></div></div>')
    h += "</div>"
    GRAF = {"Ventas": ("Vendido por obra", "Vendido"),
            "Cobranza": ("Saldo por cobrar, por obra", "Por cobrar"),
            "Comercial": ("Vendido por asesor", "Vendido por asesor")}
    if hoja in GRAF:
        titulo, cifra_ = GRAF[hoja]
        h += (f'<div class="graf"><h4>{_esc(titulo)}</h4>'
              f'<div id="gr{hoja}"></div>'
              f'<div class="f">Sale de las mismas filas que suman la tarjeta '
              f'«{_esc(cifra_)}», y respeta los filtros de arriba.</div></div>')
    if hoja == "Cobranza":
        h += ('<div class="dosgraf">'
              '<div class="graf"><h4>Morosidad por antigüedad</h4>'
              '<div id="grMora"></div>'
              '<div class="f">Los días se cuentan desde '
              '<code>Installment.fecha_vencimiento</code> hasta hoy. Una '
              'cuota de 15 días y otra de dos años no se cobran igual, aunque '
              'las dos digan «vencida».</div></div>'
              '<div class="graf"><h4>Cronograma · próximos 12 meses</h4>'
              '<div id="grCrono"></div>'
              '<div class="f">Las cuotas pendientes que todavía no vencen, '
              'por mes de vencimiento. Es lo que entra si todos pagan en '
              'fecha, no una proyección nuestra.</div></div></div>')
    if hoja == "Comercial":
        h += ('<div class="dosgraf">'
              '<div class="graf"><h4>Ticket promedio por asesor</h4>'
              '<div id="grTicket"></div>'
              '<div class="f">Lo vendido por el asesor dividido entre sus '
              'ventas cerradas. Vender más veces y vender más plata no son '
              'lo mismo: este gráfico separa las dos cosas.</div></div>'
              '<div class="graf"><h4>Separaciones por asesor</h4>'
              '<div id="grSep"></div>'
              '<div class="f">Status «Separación» de <code>Sale</code>. No se '
              'suman con las cerradas: todavía no son venta.</div></div>'
              '</div>')
    if hoja == "Ventas":
        h += ('<div class="graf"><h4>Avance de venta por obra</h4>'
              '<div id="avObras"></div>'
              '<div class="f">Vendido sobre el valor total de la obra, con la '
              'misma columna de precio de <code>Unit</code> arriba y abajo. '
              'Las unidades sin precio cargado quedan fuera de la suma.</div>'
              '</div>')
        h += ('<div class="dosgraf">'
              '<div class="graf"><h4>Por modalidad de venta</h4>'
              '<div id="grModalidad"></div>'
              '<div class="f">Sale de <code>Sale.modality</code>.</div></div>'
              '<div class="graf"><h4>Por asesor</h4>'
              '<div id="grAsesor"></div>'
              '<div class="f">Sale de <code>Sale.advisor</code>.</div></div>'
              '</div>'
              '<div class="graf"><h4>Vendido por mes · 2026</h4>'
              '<div id="grMes"></div>'
              '<div class="f">Agrupado por el mes de <code>Sale.date</code>. '
              'Ignora el filtro de mes de arriba, para poder ver la curva '
              'entera.</div></div>')
    h += (f'<div class="panel" id="pan{hoja}" hidden>'
          f'<div class="ph"><b id="tit{hoja}">Detalle</b>'
          f'<button onclick="cerrarArea(\'{hoja}\')">cerrar</button></div>'
          f'<div class="regla" id="reg{hoja}"></div>'
          f'<div id="por{hoja}"></div>'
          f'<div class="persp tot" id="cnt{hoja}"></div>'
          f'<div class="cuerpo"><table id="tab{hoja}"></table></div></div>')
    return h + extra


BLOQUES_RESULTADOS = (
    ("Ventas", "Ventas",
     "lo que se cerró, lo que está apalabrado y lo que queda en stock",
     ("Vendido", "Separaciones", "Devoluciones", "Falta vender")),
    ("Cobranza", "Cobranza",
     "la plata: lo que entró, lo que falta que entre y lo que se atrasó",
     ("Cobrado", "Por cobrar", "Vencido", "Por vencer")),
    ("Gastos", "",
     "lo que sale. AXION no asocia el gasto a una obra, así que todavía no "
     "hay hoja de área que lo reciba: el detalle se abre acá mismo",
     ("Gasto",)),
)

DESTINO = {
    "Vendido": ("Ventas", "Vendido"),
    "Separaciones": ("Ventas", "Separaciones"),
    "Devoluciones": ("Ventas", "Devoluciones"),
    "Falta vender": ("Ventas", "Falta vender"),
    "Cobrado": ("Cobranza", "Cobrado"),
    "Por cobrar": ("Cobranza", "Por cobrar"),
    "Vencido": ("Cobranza", "Vencido"),
    "Por vencer": ("Cobranza", "Por vencer"),
}


def _del_anio(c: dict) -> tuple[list, list]:
    """Las filas que se dibujan ANTES de que corra el JS: las del AÑO, que es."""
    fs = c["filas"]
    if not c["mensual"]:
        return fs, []
    return ([f for f in fs if f["fecha"][:4] == str(periodo.ANIO)],
            [f for f in fs if not f["fecha"]])


def _pie_sin_fecha(k: str, fuera: list) -> str:
    return (f'<div class="comparativo" id="cp{k}"></div>'
            f'<div class="sinfecha" id="sf{k}">'
            + (f'<b>{len(fuera)}</b> sin fecha cargada '
               f'(S/ {sum(f["monto"] for f in fuera):,.2f}) quedan fuera: no '
               f'están en ningún año' if fuera else "")
            + '</div>')


def _tarjeta_resultado(nombre: str, c: dict, k: int, btn: str = "") -> str:
    """UNA tarjeta de Resultados. Una sola función para los dos recorridos."""
    dentro, fuera = _del_anio(c)
    total = sum(f["monto"] for f in dentro)
    avisos = c.get("avisos", [])
    pliegue = ""
    if avisos:
        lista = "".join(_alerta_html(a) for a in avisos)
        pliegue = (f'<button class="chav" onclick="event.stopPropagation();'
                   f'toggleAvisos(this)">⚠ {len(avisos)} '
                   f'aviso{"s" if len(avisos) > 1 else ""} de data</button>'
                   f'<div class="avlist" hidden '
                   f'onclick="event.stopPropagation()">{lista}</div>')
    return (f'<div class="dest clic" onclick="verDet(\'{k}\')">'
            f'<div class="et">{_esc(nombre)}</div>'
            f'<div class="vg" id="vg{k}">{_abrev(total, moneda=True)}</div>'
            f'<div class="exacto" id="ex{k}">'
            + (f'S/ {total:,.2f}' if _se_abrevia(total) else '') + '</div>'
            f'<div class="cant" id="cn{k}">{len(dentro)} '
            f'{_esc(c["unidad"])}</div>'
            + _pie_sin_fecha(k, fuera)
            + f'<div class="f">{_esc(c["corta"])}</div>'
            + ("" if c["mensual"] else
               '<div class="src">saldo a hoy · el período no lo cambia</div>')
            + pliegue
            + f'<div class="acciones"><span class="verdet">'
            f'ver acá qué la compone</span>{btn}</div></div>')


def _hero_modalidades(e: dict) -> str:
    """El hueco de la derecha del hero, lleno con algo que hace falta ahí."""
    mods = [m for m in (e.get("modalidad") or []) if float(m.get("monto") or 0)]
    if not mods:
        return ""
    mods.sort(key=lambda m: -float(m["monto"]))
    filas = ""
    for m in mods[:4]:
        monto = float(m["monto"])
        entro = float(m.get("entro") or 0)
        p = 100.0 * entro / monto if monto else 0.0
        filas += (
            f'<div class="hmod" title="{_esc(m["modalidad"])}: '
            f'S/ {monto:,.2f} contratado · S/ {entro:,.2f} ya entró">'
            f'<div class="hmn">{_esc(m["modalidad"])}'
            f'<b>{p:.0f}%</b></div>'
            f'<div class="hmb"><i style="width:{min(p,100):.1f}%"></i></div>'
            f'<div class="hmp">{int(m.get("ventas") or 0)} ventas · '
            f'{_abrev(monto, moneda=True)}</div></div>')
    return (f'<div class="hmods"><div class="hmt">Por modalidad de pago</div>'
            f'{filas}</div>')


def _hero(d: dict) -> str:
    """La franja de portada: la cifra madre del año con su avance de caja."""
    e = ((d.get("meses") or {}).get("None") or {}).get("estructura") or {}
    if not e.get("contratado"):
        return ""
    contratado = float(e["contratado"])
    entro = float(e.get("entro") or 0)
    # el del año: si el acumulado no tiene base comparable, no hay cifra
    pct = e.get("pct_entro")
    pct = 0.0 if pct is None else float(pct)
    ventas = int(e.get("ventas") or 0)
    de_cada_100 = 100.0 * entro / contratado if contratado else 0.0
    falta = contratado - entro
    return (
        '<div class="hero"><div class="hero-in"><div>'
        '<div class="hrule"></div>'
        f'<h3 class="hfrase">De cada S/ 100 firmados, entraron '
        f'S/ {de_cada_100:,.2f}</h3>'
        f'<div class="hlee">Firmar no es cobrar. Esta pantalla mide la '
        f'distancia entre las dos cosas, y hoy esa distancia es de '
        f'S/ {_abrev(falta, moneda=True)} en {ventas} ventas.</div></div>'
        '<div class="hcifra"><div class="et">Cobrado del contratado</div>'
        f'<div class="n"><b>{pct:.1f}%</b>'
        f'<span>S/ {entro:,.2f}<br>de S/ {contratado:,.2f}</span></div>'
        '</div></div>'
        f'<div class="hsplit"><div class="a" style="width:{min(pct,100):.2f}%">'
        f'<b>S/ {_abrev(entro, moneda=True)}</b></div>'
        f'<div class="b"><b>S/ {_abrev(falta, moneda=True)} pendientes de '
        f'cobro</b></div></div>'
        + _hero_tres(e)
        + '</div>')


def _hero_tres(e: dict) -> str:
    """La fila de tres métricas del hero, sobre línea."""
    contratado = float(e.get("contratado") or 0)
    falta = contratado - float(e.get("entro") or 0)
    pct_falta = 100.0 * falta / contratado if contratado else 0.0
    sin_cred = int(e.get("sin_credito") or 0)
    return (
        '<div class="htres">'
        f'<div><div class="et">Contratado en el año</div>'
        f'<div class="v">S/ {contratado:,.2f}</div>'
        f'<div class="n">{int(e.get("ventas") or 0)} ventas con estado '
        f'«Vendido» en AXION</div></div>'
        f'<div><div class="et">Falta cobrar</div>'
        f'<div class="v">S/ {falta:,.2f}</div>'
        f'<div class="n">{pct_falta:.1f}% del contratado · incluye cuotas '
        f'que todavía no vencen</div></div>'
        f'<div><div class="et">Ventas sin crédito propio</div>'
        f'<div class="v{"" if sin_cred else " sin"}">'
        f'{sin_cred if sin_cred else "&mdash;"}</div>'
        f'<div class="n">no tienen crédito cargado para su unidad: figuran '
        f'con S/ 0.00 entrado y se declaran</div></div>'
        '</div>')


def _fuentes_bar(d: dict) -> str:
    """La franja de fuentes con sus puntos de color, arriba de todo."""
    fs = d.get("fuentes") or []
    if not fs:
        return ""
    trozos, faltan = "", 0
    for f in fs:
        cl = "" if f.get("conectada") else " no"
        fecha = str(f.get("fecha") or "").strip() or "sin fecha"
        trozos += (f'<div class="f{cl}"><i></i><b>{_esc(f["nombre"])}</b> '
                   f'{_esc(fecha)}</div>')
        faltan += len(f.get("faltantes") or [])
    aviso = (f'<div class="aviso">{faltan} huecos declarados</div>'
             if faltan else "")
    return (f'<div class="fuentesbar"><div class="et">Fuentes</div>'
            f'{trozos}{aviso}</div>')


def _hoja_resultados(d: dict) -> str:
    """Las cifras se dibujan con el acumulado del AÑO y el JS las recalcula al."""
    orden = list(d["crudas"].keys())
    disponibles = {h: {c["nombre"] for c in cs}
                   for h, cs in d["areas_filas"].items()}
    h = _hero(d)
    h += ('<div class="nota"><b>Todo sale de AXION en vivo · período por '
          'defecto: año 2026</b> («Todos los años» muestra el histórico) · '
          'los saldos son a hoy · todos los montos en soles (S/). La cifra y '
          'su detalle son las mismas filas.</div>')
    puestas = set()
    for titulo, hoja_destino, bajada, nombres in BLOQUES_RESULTADOS:
        presentes = [n for n in nombres if n in d["crudas"]]
        if not presentes:
            continue
        ir = ""
        if hoja_destino:
            ir = (f'<button class="irhoja" onclick="irA(\'{hoja_destino}\','
                  f'\'\')">abrir la hoja de {_esc(hoja_destino)}</button>')
        h += (f'<div class="bloqueres"><div class="brh">'
              f'<div><b>{_esc(titulo)}</b> <span>{_esc(bajada)}</span></div>'
              f'{ir}</div><div class="destacados">')
        for nombre in presentes:
            puestas.add(nombre)
            c = d["crudas"][nombre]
            k = orden.index(nombre)
            dest = DESTINO.get(nombre)
            btn = ""
            if dest and dest[1] in disponibles.get(dest[0], set()):
                btn = (f'<button class="irdet" onclick="event.stopPropagation();'
                       f'irA(\'{dest[0]}\',\'{_esc(dest[1])}\')">'
                       f'ir al detalle en {_esc(dest[0])}</button>')
            elif dest:
                print(f"   ⚠ «{nombre}» apunta a {dest[0]}/{dest[1]} y esa "
                      f"cifra no existe: la tarjeta va sin botón")
            h += _tarjeta_resultado(nombre, c, k, btn)
        h += "</div>"
        if titulo == "Ventas":
            h += "".join(
                f'<div class="mes" data-mes="{k}"'
                f'{"" if k == "None" else " hidden"}>'
                + _bloque_estructura(v_) + '</div>'
                for k, v_ in _solo_periodos_del_viejo(d["meses"].items()))
        if titulo == "Cobranza":
            h += _bloque_flujo(d)
            h += ('<div class="nota">Del saldo por cobrar hay una parte que '
                  '<b>no tiene vencimiento asignado</b>: no aparece en ninguna '
                  'cuota con fecha, así que no se sabe cuándo entra. El '
                  'reparto completo y los vencimientos mes a mes están en la '
                  'hoja de Cobranza.</div>')
        h += "</div>"
    sueltas = [n for n in orden if n not in puestas]
    if sueltas:
        h += ('<div class="bloqueres"><div class="brh"><div><b>Otras</b> '
              '<span>cifras que todavía no están asignadas a un área</span>'
              '</div></div><div class="destacados">')
        for nombre in sueltas:
            h += _tarjeta_resultado(nombre, d["crudas"][nombre],
                                    orden.index(nombre))
        h += "</div></div>"
    h += ('<div class="panel" id="detalle" hidden>'
          '<div class="ph"><b id="detTit">Detalle</b>'
          '<button onclick="cerrarDet()">cerrar</button></div>'
          '<div class="dettabs chips" id="detTabs"></div>'
          '<div id="detAvance"></div>'
          '<div class="regla" id="detRegla"></div>'
          '<div id="detAvisos"></div>'
          '<div id="detPor"></div>'
          '<div class="persp tot" id="detCuenta"></div>'
          '<div class="cuerpo"><table id="detTabla"></table></div></div>')
    x = ('<div class="persp">Lo que AXION todavía no contesta</div>'
         '<div class="tarjetas">')
    for r in d["resultados_no"]:
        x += (f'<div class="c"><div class="et">{_esc(r["etiqueta"])}</div>'
              f'<div class="v sin">SIN DATO</div>'
              f'<div class="f">{_esc(r["motivo"])}</div>'
              f'<div class="quien">responde: {_esc(r["area"])}</div></div>')
    return h + x + "</div>"


def render(d: dict) -> str:
    H = {}

    H["Resultados"] = ""

    est = ""
    for f in d["fuentes"]:
        falt = ("".join(f'<li>{_esc(x)}</li>' for x in f["faltantes"]))
        est += (f'<div class="c fuente"><div class="et">{_esc(f["nombre"])}</div>'
                f'<div class="v texto {"" if f["conectada"] else "sin"}">'
                f'{"CONECTADA" if f["conectada"] else "NO CONECTADA"}</div>'
                f'<div class="f">leído {_esc(f["fecha"])}<br>{_esc(f["periodo"])}</div>'
                + (f'<div class="ojo">{_esc(f["aviso"])}</div>' if f["aviso"] else "")
                + (f'<div class="falta"><b>Falta cargar</b><ul>{falt}</ul></div>'
                   if falt else "") + "</div>")
    H["Estado"] = f'<div class="tarjetas">{est}</div>'

    cam = d.get("cambios_axion") or []
    if cam:
        graves = [c for c in cam if c["grave"]]
        tarj = "".join(
            f'<div class="c"><div class="et">'
            f'{"⚠ " if c["grave"] else ""}{_esc(c["titulo"])}</div>'
            f'<div class="f">{_esc(c["texto"])}</div></div>' for c in cam)
        H["Estado"] = (
            '<div class="nota"><b>Qué cambió en AXION desde la última '
            'lectura.</b> Habitat está construyendo su sistema mientras el '
            'tablero lee de él. Acá aparece solo, cada vez, lo que agregaron, '
            'quitaron o movió mucho de tamaño — para que nadie se entere '
            'porque una pantalla se rompió.'
            + (f' <b>Hay {len(graves)} que conviene consultar hoy.</b>'
               if graves else ' Nada urgente esta vez.')
            + '</div>'
            f'<div class="tarjetas">{tarj}</div>'
            '<div class="persp">Las fuentes y su fecha</div>' + H["Estado"]) 

    H["Scorecard"] = ""
    H["Rentabilidad"] = ""

    FILTRABLES = {"Ventas", "Cobranza", "Comercial"}
    for nombre, cifras in d["areas_filas"].items():
        extra = _referencias({"Cobranza": ["duplicados"]}.get(nombre, []))
        H[nombre] = _hoja_area_filtrable(nombre, cifras, extra)
        H[nombre] += _bloque_sin_filtro(nombre, d)
        H[nombre] += _kommo_por_periodo(nombre, d)
        if nombre == "Cobranza":
            H[nombre] += _bloque_vencimientos(d)

    EXTRA = {"Obra": ["obras"]}
    for nombre, cifras in d["areas"].items():
        if nombre in FILTRABLES:
            continue
        H[nombre] = '<div class="tarjetas">' + "".join(
            _tarjeta(c["etiqueta"], c["valor"],
                     c["formula"] if c["valor"] is not None else c["motivo"],
                     c["area"],
                     c["motivo"] if c["valor"] is not None else "")
            for c in cifras if not _es_kommo(c)) + "</div>"
        if nombre in CRM_POR_PERIODO:
            H[nombre] += _kommo_por_periodo(nombre, d)
            H[nombre] += _bloque_kommo(
                [c for c in cifras
                 if _es_kommo(c) and c["etiqueta"] not in CUBIERTAS])
        else:
            H[nombre] += _bloque_kommo([c for c in cifras if _es_kommo(c)])
        if nombre == "Obra":
            g = ""
            for a in d["avance_fisico"]:
                tono = ("ok" if a["pct"] >= 80 else
                        "parc" if a["pct"] >= 40 else "no")
                g += (f'<div class="gb"><div>{_esc(a["obra"])}'
                      f'<div class="f">{_esc(a["etapa"])}</div></div>'
                      f'<div class="bar"><i class="{tono}" '
                      f'style="width:{min(a["pct"], 100):.1f}%"></i></div>'
                      f'<div class="val">{a["pct"]:.0f}%</div></div>')
            H[nombre] += ('<div class="graf"><h4>Avance de construcción por '
                          'obra</h4>' + g +
                          '<div class="f">Tal cual lo declara Habitat en '
                          '<code>Project.construction_progress</code>: el '
                          'tablero lo muestra, no lo mide. Su contraste '
                          'natural —el cuaderno de obra— no está conectado.'
                          '</div></div>')
        H[nombre] += _referencias(EXTRA.get(nombre, []))

    H["CRM"] = ""

    H["Validación"] = _hoja_validacion(d)

    met = ('<div class="nota"><b>Esta hoja sigue la estructura de una matriz '
           'BSC: Objetivo → Iniciativa → Indicador → Meta vs Real → Plan de '
           'acción.</b><br>Las tres columnas del medio ya las resuelve el '
           'tablero desde AXION. Las dos de los extremos —la <b>iniciativa</b> '
           'y el <b>plan de acción</b> con responsable y fechas— son decisiones '
           'de gestión: las carga Habitat, no se inventan.</div>'
           '<table><tr><th>Perspectiva</th><th>Objetivo</th>'
           '<th>Iniciativa estratégica</th><th>Indicador</th>'
           '<th class="num">Meta</th><th class="num">Real</th>'
           '<th>Responsable</th><th>Plazo</th></tr>')
    real = {i["indicador"]: i for i in d["indicadores"]}
    for m in d["metas"]:
        r = real.get(m["indicador"], {})
        v = ('<span class="nodato">sin fuente</span>' if r.get("valor") is None
             else (_fmt(r["valor"]) if r.get("no_cuadra")
                   else _con_unidad(r["valor"], m["unidad"])))
        met += (f'<tr><td>{_esc(m["perspectiva"])}</td>'
                f'<td>{_esc(m["objetivo"])}</td>'
                f'<td class="vacio">la carga Habitat</td>'
                f'<td><b>{_esc(m["indicador"])}</b></td>'
                f'<td class="num">{_con_unidad(m["meta"], m["unidad"])}</td>'
                f'<td class="num">{v}</td>'
                f'<td class="vacio">—</td><td class="vacio">—</td></tr>')
    met += '</table>'

    _om = cierre.origen_metas()
    if _om["en_axion"]:
        _de_donde = ('<b>Las metas de arriba salen del campo '
                     '<code>target</code> de la tabla KPI de AXION</b>, tal '
                     'cual: el tablero no las inventa ni las edita. Hoy hay '
                     '<b>una sola forma de cambiarlas y es dentro de '
                     'AXION</b>; al regenerar, la nueva meta aparece acá '
                     'sola.<br>')
    else:
        _de_donde = (
            f'<b>La tabla KPI ya no existe en AXION.</b> Se le pidió a la API '
            f'y contesta «no encontrada», así que estas {_om["filas"]} filas '
            f'salen del <b>catálogo propio del proyecto</b>, guardado en disco '
            f'el 06-ago-2026 — no de AXION en vivo.<br>'
            f'De las {_om["filas"]}, <b>{_om["con_meta"]} traen una meta '
            f'numérica que escribimos nosotros</b> y que Habitat todavía no '
            f'confirmó: van así, a la vista, porque una meta propuesta que se '
            f'oculta se termina leyendo como una meta acordada. Las otras '
            f'{_om["filas"] - _om["con_meta"]} van en blanco a propósito.<br>'
            f'<b>Mientras la tabla no vuelva, cambiar una meta acá no es '
            f'posible desde AXION.</b> Hay que decidir dónde viven — es la '
            f'misma decisión de abajo.<br>')
    met += ('<div class="persp">Cómo se cargan y se cambian las metas</div>'
            '<div class="nota">' + _de_donde +
            'Este archivo es un HTML: <b>lo que se escriba encima no se '
            'guarda en ningún lado</b>, así que una meta editable en pantalla '
            'sería una meta que se pierde al cerrar. Por eso no la hay.<br>'
            '<b>Lo que falta decidir</b> —y es de Habitat, no nuestro— es '
            'dónde viven las tres columnas que AXION no tiene: '
            '<b>iniciativa estratégica, responsable y plazo</b>. Dos caminos: '
            'crear esos campos en la tabla KPI de AXION (queda todo en un '
            'sistema), o un Excel con una fila por indicador que el tablero '
            'lea igual que lee los demás. Cualquiera de los dos funciona; lo '
            'que no funciona es tipearlas en una reunión y que vivan en un '
            'PowerPoint.</div>')
    met += ('<div class="persp">Plan de acción — lo que Habitat carga acá</div>'
            '<div class="nota">Columnas de la matriz: <b>Nro · Iniciativa · '
            'Acción · Fecha de inicio · Fecha de término · Responsable · '
            'Evidencia de cierre · Conformidad del líder · Estado</b>. '
            'Hoy está vacío porque ninguna de esas columnas existe en AXION: '
            'son decisiones y compromisos, no datos del sistema. Cuando '
            'Habitat las cargue, cada iniciativa queda ligada a su indicador y '
            'el avance se mide contra el mismo número que ya calcula el '
            'tablero.</div>')

    met += ('<div class="persp">Lo que falta crear en AXION</div>'
            '<table><tr><th>Qué</th><th>En qué consiste</th>'
            '<th>Qué desbloquea</th></tr>')
    for nom, que, porque in d["por_crear"]:
        met += (f'<tr><td><b>{_esc(nom)}</b></td><td>{_esc(que)}</td>'
                f'<td>{_esc(porque)}</td></tr>')
    H["Metas"] = met + "</table>"

    j = ('<div class="nota"><b>Es una muestra de lo que el tablero mostrará '
         'cuando la data esté completa, no el indicador vivo.</b> Período '
         'ene–jun 2026. El margen contable NO se compara contra las ventas de '
         'AXION: cubren ventanas distintas y la resta daría una brecha '
         'inventada.</div>')
    j += ('<div class="persp">1 · Ingresos</div><table><tr><th>Fuente</th>'
          '<th class="num">Monto S/</th><th>Detalle</th></tr>')
    for x in d["ingresos"]:
        j += (f'<tr><td>{_esc(x["fuente"])}</td>'
              f'<td class="num">{_soles(x["monto"])}</td>'
              f'<td>{_esc(x["detalle"])}</td></tr>')
    j += "</table>"
    if d["utilidad"]:
        j += ('<div class="persp">Utilidad según libros</div><table><tr>'
              '<th>Empresa</th><th class="num">Utilidad S/</th>'
              '<th>Período</th></tr>')
        for x in d["utilidad"]:
            j += (f'<tr><td>{_esc(x["empresa"])}</td>'
                  f'<td class="num">{_soles(x["monto"])}</td>'
                  f'<td>{_esc(x["periodo"])}</td></tr>')
        j += "</table>"
    tot = d["gasto_contable_total"]
    atr = d["gasto_contable_atribuido"]
    pct = f"{100 * atr / tot:.1f}%" if tot else "—"
    j += (f'<div class="persp">2 · Contable · gasto por obra</div>'
          f'<div class="nota">Gasto 6x total S/ {tot:,.2f} · atribuido a una '
          f'obra S/ {atr:,.2f} ({pct}). El resto está en cuentas sin nombre '
          f'de obra.</div><table><tr><th>Obra</th>'
          f'<th class="num">Gasto S/</th></tr>')
    for x in d["gasto_contable"]:
        v = (_soles(x["gasto"]) if x["gasto"]
             else '<span class="vacio">sin gasto identificable</span>')
        j += f'<tr><td>{_esc(x["obra"])}</td><td class="num">{v}</td></tr>'
    j += ('</table><div class="persp">3 · Administradora · gasto por obra</div>'
          '<table><tr><th>Obra</th><th class="num">Monto S/</th>'
          '<th>Hoja</th></tr>')
    for x in d["gasto_admin"]:
        v = (_soles(x["monto"]) if x["monto"] is not None
             else '<span class="vacio">sin hoja propia</span>')
        j += (f'<tr><td>{_esc(x["obra"])}</td><td class="num">{v}</td>'
              f'<td>{_esc(x["hoja"])} {_esc(x["nota"])}</td></tr>')
    j += '</table><div class="persp">Las 5 incongruencias más resaltantes</div>'
    for x in d["incongruencias"]:
        j += (f'<div class="ind parc"><div class="obj">Incongruencia {x["n"]}</div>'
              f'<div class="nom">{_esc(x["titulo"])}</div>'
              f'<div class="cifras"><div><span class="lab">Cifra</span>'
              f'<b>{_esc(x["cifra"])}</b></div></div>'
              f'<div class="alc">{_esc(x["detalle"])}</div></div>')
    H["Junio"] = j

    H["Resultados"] = _hoja_resultados(d)

    for hoja, fn in (("Scorecard", _bloque_scorecard),
                     ("Rentabilidad", _bloque_rentabilidad),
                     ("CRM", _bloque_crm)):
        H[hoja] = "".join(
            f'<div class="mes" data-mes="{k}"'
            f'{"" if k == "None" else " hidden"}>{fn(d, v)}</div>'
            for k, v in _solo_periodos_del_viejo(d["meses"].items())) + _extras_hoja(hoja, d)

    nav = "".join(
        f'<button data-hoja="s{k}"{" class=on" if k == 0 else ""}>'
        f'{_esc(n)}</button>'
        for k, n in enumerate(H))
    secs = "".join(
        f'<section id="s{k}"{" class=on" if k == 0 else ""}>'
        f'<h2>{_esc(n)}</h2>{c}</section>'
        for k, (n, c) in enumerate(H.items()))
    return nav, secs

def _css() -> str:
    """La capa visual, leída de `assets/tablero.css`."""
    ruta = RAIZ / "assets" / "tablero.css"
    base = CSS_RESPALDO
    if ruta.exists():
        try:
            base = ruta.read_text(encoding="utf-8")
        except OSError:
            pass
    extra = RAIZ / "assets" / "tablero-motor.css"
    if extra.exists():
        try:
            base += ("\n/* ── assets/tablero-motor.css · reglas que el motor "
                     "agregó mientras diseño trabaja ── */\n"
                     + extra.read_text(encoding="utf-8"))
        except OSError:
            pass
    return base


CSS_RESPALDO = """
.comparativo{font-size:11.5px;color:#5a6b8c;margin-top:6px;line-height:1.5}
.comp{padding:6px 8px;background:#f3f6fb;border-radius:6px}
.comp.alerta{background:#fff4e5;color:#8a5a00;border-left:3px solid #f0a020}
.pordia{display:flex;align-items:flex-end;gap:2px;height:26px;margin-top:6px}
.pordia i{flex:1;min-width:2px;background:#163180;opacity:.45;border-radius:1px}
.pordia i:hover{opacity:1}
@import url("https://fonts.googleapis.com/css2?family=Poppins:wght@500;600;700&family=Manrope:wght@400;500;600;700&display=swap");
*{box-sizing:border-box;margin:0;padding:0}
[hidden]{display:none!important}
:root{
  --navy-50:#eef1fb; --navy-100:#dde3f5; --navy-200:#b9c5e9;
  --navy-300:#8b9edb; --navy-400:#5570c2; --navy-500:#2e4ca6;
  --navy-600:#1f3a8f; --navy-700:#163180; --navy-800:#122763;
  --navy-900:#0d1b45; --navy-950:#081029;
  --yellow-300:#fee98a; --yellow-400:#fde04e; --yellow-500:#fcd925;
  --yellow-600:#eac40a;
  --neutral-50:#f6f7fb; --neutral-100:#edeff5; --neutral-200:#dfe3ec;
  --neutral-300:#c6cdda; --neutral-400:#99a2b7; --neutral-500:#6b7488;
  --neutral-600:#4a5266; --neutral-700:#333a4a; --neutral-800:#1f2433;
  --navy:var(--navy-700); --amarillo:var(--yellow-500);
  --papel:var(--neutral-50); --carta:#fff; --linea:var(--neutral-200);
  --texto:var(--neutral-700); --fuerte:var(--navy-900);
  --gris:var(--neutral-500);
  --verde:#0f8a5f; --verde-bg:#e5f6ef; --rojo:#c62a22; --rojo-bg:#fcebea;
  --ambar:#f5a623; --ambar-bg:#fdf0d9;
  --sombra:0 1px 2px rgba(13,27,69,.04),0 8px 24px -16px rgba(13,27,69,.28);
  --sombra-alta:0 30px 80px -44px rgba(13,27,69,.6);
  --ls-caps:.18em;
}
body{background:var(--papel);color:var(--texto);
  font-family:Manrope,"Segoe UI",system-ui,sans-serif;font-size:14px;line-height:1.55;
  -webkit-font-smoothing:antialiased}
h1,h2,h3,.nom,.v{font-family:Poppins,Manrope,sans-serif}
header{background:var(--navy-900);color:#fff;padding:16px 30px;
  display:grid;grid-template-columns:auto 1fr auto;align-items:center;
  gap:26px;border-bottom:3px solid var(--amarillo)}
@media (max-width:1180px){
  header{grid-template-columns:1fr;gap:12px}
  header .sello{text-align:left}
  .filtro{justify-content:flex-start}
}
.marca{display:flex;align-items:center;gap:16px}
.logo{height:40px;width:auto;display:block}
header h1{font-size:16px;letter-spacing:.04em;font-weight:600;line-height:1.3}
.baja{font-size:12px;opacity:.8;margin-top:2px}
header .sello{font-size:11.5px;text-align:right;opacity:.9;line-height:1.7}
.vivo{display:inline-block;background:var(--amarillo);color:var(--navy-900);
  padding:2px 9px;border-radius:3px;font-size:10.5px;font-weight:700;
  letter-spacing:.1em;margin-right:9px}
nav{background:var(--carta);border-bottom:1px solid var(--linea);
  padding:0 30px;display:flex;flex-wrap:wrap;gap:2px;
  box-shadow:0 1px 3px rgba(13,27,69,.04)}
nav button{background:none;border:none;border-bottom:3px solid transparent;
  padding:14px 15px;cursor:pointer;font-size:11px;color:var(--neutral-500);
  font-family:inherit;font-weight:700;letter-spacing:.11em;
  text-transform:uppercase;transition:color 160ms}
nav button:hover{color:var(--navy)}
nav button.on{color:var(--navy);border-bottom-color:var(--amarillo)}
main{padding:30px 30px 80px;max-width:1560px;margin:0 auto}
section{display:none} section.on{display:block}
h2{font-size:23px;margin-bottom:20px;color:var(--fuerte);font-weight:800;
  letter-spacing:-.02em;padding-left:14px;position:relative;line-height:1.25}
h2::before{content:"";position:absolute;left:0;top:.18em;bottom:.18em;
  width:4px;background:var(--amarillo);border-radius:2px}
.tarjetas{display:grid;grid-template-columns:repeat(auto-fill,minmax(288px,1fr));gap:16px}
.c{background:var(--carta);border:1px solid var(--linea);border-radius:10px;
  padding:20px 22px;box-shadow:var(--sombra);
  transition:box-shadow 180ms,transform 180ms}
.c:hover{box-shadow:0 2px 4px rgba(13,27,69,.05),0 18px 40px -24px rgba(13,27,69,.4)}
.c .et{font-size:10px;color:var(--neutral-400);letter-spacing:var(--ls-caps);
  text-transform:uppercase;font-weight:700;font-family:Manrope,sans-serif}
.c .v{font-size:32px;font-weight:800;margin:10px 0 4px;color:var(--fuerte);
  font-variant-numeric:tabular-nums;letter-spacing:-.025em;line-height:1.05}
.c .v.sin{font-size:14px;color:var(--rojo);font-weight:700;letter-spacing:0}
.c .f{font-size:11.5px;color:var(--gris);border-top:1px solid var(--linea);
  padding-top:11px;margin-top:12px;line-height:1.6;
  font-variant-numeric:tabular-nums}
.c .ojo{font-size:12px;color:var(--rojo);margin-top:9px;line-height:1.55}
.c .quien{font-size:10px;color:var(--navy);margin-top:8px;font-weight:700;
  letter-spacing:.1em;text-transform:uppercase}
table{width:100%;border-collapse:collapse;background:var(--carta);
  border:1px solid var(--linea);border-radius:10px;font-size:13px;
  box-shadow:var(--sombra)}
th:first-child{border-top-left-radius:7px}
th:last-child{border-top-right-radius:7px}
th{background:var(--navy-50);text-align:left;padding:11px 13px;font-size:9.5px;
  letter-spacing:var(--ls-caps);text-transform:uppercase;color:var(--navy-600);
  font-weight:700;border-bottom:1px solid var(--linea)}
td{padding:10px 13px;border-bottom:1px solid var(--neutral-100);vertical-align:top}
tbody tr:hover td,table tr:hover td{background:var(--neutral-50)}
tr:last-child td{border-bottom:none}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.pill{display:inline-block;padding:2px 8px;border-radius:11px;font-size:10.5px;font-weight:700}
.ok{background:var(--verde-bg);color:var(--verde)}
.parc{background:var(--ambar-bg);color:#8a6d1f}
.no{background:var(--rojo-bg);color:var(--rojo)}
.persp{margin:24px 0 10px;font-size:12px;letter-spacing:.08em;
  text-transform:uppercase;color:var(--gris);font-weight:700}
.nota{background:#fffbea;border-left:4px solid var(--amarillo);padding:12px 15px;
  font-size:13px;margin:16px 0;border-radius:0 6px 6px 0}
.vacio{color:var(--gris);font-style:italic}
.leyenda{display:flex;gap:20px;flex-wrap:wrap;font-size:12px;
  color:var(--gris);margin:12px 0 4px;padding:10px 14px;
  background:var(--carta);border:1px solid var(--linea);border-radius:8px}
.leyenda i.p{display:inline-block;width:10px;height:10px;border-radius:3px;
  vertical-align:-1px;margin-right:5px}
.leyenda i.p.ok{background:var(--verde)}
.leyenda i.p.parc{background:var(--ambar)}
.leyenda i.p.no{background:var(--rojo)}
.evo{background:var(--carta);border:1px solid var(--linea);border-radius:7px;
  padding:11px 13px;margin-bottom:9px}
.evo .et{font-size:10px;letter-spacing:.07em;text-transform:uppercase;
  color:var(--gris);font-weight:700;margin-bottom:7px}
.evo.vacia{background:#fffbea;border-color:var(--amarillo);font-size:12px;
  color:var(--texto);line-height:1.5}
.evb{display:flex;align-items:flex-end;gap:5px;height:74px}
.ev{flex:1;display:flex;flex-direction:column;align-items:center;height:100%}
.ev b{margin-top:auto;font-size:9.5px;color:var(--fuerte);
  font-variant-numeric:tabular-nums;white-space:nowrap;margin-bottom:2px}
.ev i{display:block;width:100%;background:var(--navy);border-radius:3px 3px 0 0;
  min-height:3px}
.ev span{font-size:9.5px;color:var(--gris);margin-top:3px}
.evd{font-size:11.5px;color:var(--gris);margin-top:7px;font-weight:600}
.evd .ok{color:var(--verde)} .evd .no{color:var(--rojo)}
.chips{display:flex;gap:7px;flex-wrap:wrap;margin:16px 0 14px}
.chip{background:var(--carta);border:1px solid var(--linea);border-radius:16px;
  padding:6px 14px;font-family:inherit;font-size:12px;font-weight:600;
  color:var(--gris);cursor:pointer}
.chip.on{background:var(--navy);color:#fff;border-color:var(--navy)}
.matriz{margin-top:8px}
.matriz th{white-space:nowrap}
.mp td{background:var(--navy)!important;color:#fff;padding:9px 14px}
.mp h3{display:inline;font-size:12px;letter-spacing:.09em;
  text-transform:uppercase;margin-right:12px}
.mp .pill{margin-right:5px}
.mrow{cursor:pointer}
.mrow:hover td{background:var(--navy-50)}
.mrow td:first-child{border-left:4px solid var(--gris)}
.mrow.ok td:first-child{border-left-color:var(--verde)}
.mrow.parc td:first-child{border-left-color:var(--ambar)}
.mrow.no td:first-child{border-left-color:var(--rojo)}
.mobj{font-size:11px;color:var(--gris);font-weight:400;margin-top:3px;
  line-height:1.45;max-width:420px}
.mini{display:inline-block;width:110px;height:6px;background:var(--linea);
  border-radius:3px;overflow:hidden;vertical-align:middle}
.mini i{display:block;height:100%}
.mini i.ok{background:var(--verde)} .mini i.parc{background:var(--ambar)}
.mini i.no{background:var(--rojo)}
.mpct{font-size:11.5px;font-weight:700;color:var(--fuerte);margin-left:7px;
  font-variant-numeric:tabular-nums}
.av,.est{white-space:nowrap}
.est .pill{margin-right:4px}
.nocomp{font-size:11px;color:var(--ambar);font-weight:700;cursor:help}
.sinserie{color:var(--gris)}
.spark{display:flex;align-items:flex-end;gap:2px;height:26px;width:104px}
.spark i{flex:1;background:var(--navy);border-radius:1px 1px 0 0;min-height:2px}
.pill.prop{background:var(--amarillo);color:var(--navy-900)}
.mdet td{background:var(--navy-50)!important;font-size:12px;line-height:1.6;
  padding:12px 16px;border-left:4px solid var(--navy)}
.mdet td>div{margin-bottom:4px}
.graf{background:var(--carta);border:1px solid var(--linea);border-radius:9px;
  padding:16px 18px;margin:16px 0}
.dosgraf{display:grid;grid-template-columns:repeat(auto-fit,minmax(360px,1fr));gap:14px}
.subv{font-size:11px;color:var(--gris);margin:-2px 0 9px 0;padding-left:2px}
.graf h4{font-size:12px;letter-spacing:.07em;text-transform:uppercase;
  color:var(--navy);margin-bottom:12px}
.gb{display:grid;grid-template-columns:170px 1fr 110px;gap:9px;
  align-items:center;margin-bottom:6px;font-size:12px}
.gb .bar{height:17px;background:var(--linea);border-radius:3px;overflow:hidden}
.gb .bar i{display:block;height:100%;background:var(--navy);border-radius:3px}
.gb .bar i.ok{background:var(--verde)} .gb .bar i.parc{background:var(--ambar)}
.gb .bar i.no{background:var(--rojo)}
.gb .val{text-align:right;font-variant-numeric:tabular-nums;font-weight:600}
.bloque{margin:20px 0 28px}
.bh{display:flex;justify-content:space-between;align-items:center;
  border-bottom:3px solid var(--navy);padding-bottom:8px;margin-bottom:13px;
  flex-wrap:wrap;gap:8px}
.bh h3{font-size:13px;letter-spacing:.1em;text-transform:uppercase;color:var(--navy)}
.cuenta{display:flex;gap:6px}
.ind{background:var(--carta);border:1px solid var(--linea);
  border-left:5px solid var(--gris);border-radius:8px;padding:14px 18px;margin-bottom:10px}
.ind.ok{border-left-color:var(--verde)} .ind.parc{border-left-color:var(--ambar)}
.ind.no{border-left-color:var(--rojo)}
.obj{font-size:10.5px;letter-spacing:.07em;text-transform:uppercase;
  color:var(--gris);font-weight:700}
.nom{font-size:16px;font-weight:600;margin:3px 0 10px;color:var(--fuerte)}
.cifras{display:flex;gap:32px;flex-wrap:wrap;margin-bottom:9px}
.cifras .lab{display:block;font-size:10px;letter-spacing:.07em;
  text-transform:uppercase;color:var(--gris);margin-bottom:2px;font-weight:700}
.cifras b{font-size:18px;font-variant-numeric:tabular-nums;color:var(--fuerte)}
.cifras b.tip{color:var(--gris);font-weight:500}
.nodato{color:var(--rojo);font-size:13px;font-weight:700}
.barra{height:7px;background:var(--linea);border-radius:4px;overflow:hidden;
  margin:4px 0 3px;max-width:420px}
.barra i{display:block;height:100%;border-radius:4px}
.barra i.ok{background:var(--verde)} .barra i.parc{background:var(--ambar)}
.barra i.no{background:var(--rojo)}
.pct{font-size:11px;color:var(--gris);margin-bottom:8px;font-weight:600}
.calc{font-size:12px;color:var(--navy);background:var(--navy-50);
  padding:8px 11px;border-radius:6px;margin:8px 0}
.calc b{font-weight:700}
.alc{font-size:12px;color:var(--gris);border-top:1px solid #eef0f5;padding-top:9px}
.ini{font-size:11px;color:var(--gris);margin-top:6px}
.falta{margin-top:10px;font-size:12px;color:var(--rojo)}
.falta ul{margin:5px 0 0 16px} .falta li{margin-bottom:4px}
.fuente{display:flex;flex-direction:column}
.c.clic{cursor:pointer;transition:box-shadow .12s,transform .12s}
.c.clic:hover{box-shadow:0 4px 16px rgba(22,49,128,.14);transform:translateY(-1px)}
.c .verdet{margin-top:9px}
.destacados{display:grid;grid-template-columns:repeat(auto-fill,minmax(302px,1fr));gap:16px}
.dest{background:var(--carta);border:1px solid var(--linea);border-radius:10px;
  padding:22px 24px;border-top:3px solid var(--navy);box-shadow:var(--sombra);
  transition:box-shadow 180ms}
.dest:hover{box-shadow:0 2px 4px rgba(13,27,69,.05),0 18px 40px -24px rgba(13,27,69,.4)}
.dest .et{font-size:10px;color:var(--neutral-400);letter-spacing:var(--ls-caps);
  text-transform:uppercase;font-weight:700}
.dest .vg{font-family:Poppins,sans-serif;font-size:40px;font-weight:800;
  color:var(--navy-900);margin:12px 0 10px;font-variant-numeric:tabular-nums;
  line-height:1;letter-spacing:-.035em}
.dest .cant{font-size:10.5px;color:var(--navy);font-weight:700;
  margin:-4px 0 10px;letter-spacing:.1em;text-transform:uppercase}
.dest .f{font-size:11.5px;color:var(--gris);border-top:1px solid var(--linea);
  padding-top:11px;line-height:1.6;font-variant-numeric:tabular-nums}
.filtro{display:flex;align-items:center;gap:8px;color:#fff;flex-wrap:wrap;
  justify-content:center}
.filtro .par{display:flex;align-items:center;gap:7px}
.filtro label{font-size:10.5px;letter-spacing:.09em;text-transform:uppercase;
  opacity:.85;font-weight:700}
.filtro select{font-family:inherit;font-size:13px;font-weight:600;padding:6px 10px;
  border-radius:5px;border:1px solid rgba(255,255,255,.35);background:#fff;
  color:var(--navy);cursor:pointer}
.solo-axion{font-size:10px;letter-spacing:.08em;text-transform:uppercase;
  background:rgba(255,255,255,.15);padding:3px 8px;border-radius:3px;font-weight:700}
.dest.clic{cursor:pointer;transition:box-shadow .12s,transform .12s;
  display:flex;flex-direction:column}
.dest.clic:hover{box-shadow:0 4px 16px rgba(22,49,128,.14);transform:translateY(-1px)}
.verdet{font-size:10.5px;color:var(--navy);font-weight:700;
  letter-spacing:.04em;text-transform:uppercase}
.verdet::after{content:" >"}
.acciones{margin-top:auto;padding-top:11px;display:flex;align-items:center;
  justify-content:space-between;gap:10px;flex-wrap:wrap}
.irdet{background:var(--navy);color:#fff;border:none;font-family:inherit;
  font-size:10.5px;font-weight:700;letter-spacing:.04em;padding:6px 11px;
  border-radius:4px;cursor:pointer;text-transform:uppercase}
.irdet:hover{background:var(--navy-900)}
.irdet::after{content:" →"}
.bloqueres{margin-bottom:26px}
.brh{display:flex;justify-content:space-between;align-items:center;gap:16px;
  flex-wrap:wrap;padding:0 2px 10px;margin-bottom:2px;
  border-bottom:2px solid var(--navy)}
.brh b{font-family:Poppins,sans-serif;font-size:15px;color:var(--navy);
  letter-spacing:.02em}
.brh span{font-size:12px;color:var(--gris)}
.irhoja{background:var(--amarillo);color:var(--navy-900);border:none;
  font-family:inherit;font-size:11px;font-weight:700;letter-spacing:.05em;
  padding:7px 14px;border-radius:5px;cursor:pointer;text-transform:uppercase;
  white-space:nowrap}
.irhoja::after{content:" →"}
.irhoja:hover{filter:brightness(.94)}
.volver{display:flex;align-items:center;gap:14px;flex-wrap:wrap;
  margin-bottom:14px}
.volver .irhoja{background:var(--navy);color:#fff}
.volver .irhoja::after{content:""}
.volver .irhoja::before{content:"← "}
.volver span{font-size:12px;color:var(--gris)}
.panel{border:2px solid var(--navy);border-radius:10px;background:var(--carta);
  margin:16px 0 22px}
.panel .ph{border-radius:8px 8px 0 0}
.panel .ph{background:var(--navy);color:#fff;padding:11px 16px;display:flex;
  justify-content:space-between;align-items:center;font-size:14px}
.panel .ph button{background:var(--amarillo);border:none;color:var(--navy);
  font-family:inherit;font-weight:700;font-size:11px;padding:4px 12px;
  border-radius:4px;cursor:pointer}
th.ord{cursor:pointer;user-select:none}
th.ord:hover{background:var(--navy-100)}
th.ord::after{content:" ⇅";opacity:.45;font-size:10px}
tr.clicf{cursor:pointer}
tr.clicf:hover{background:var(--navy-50)}
.avance{padding:13px 16px;background:#fffbea;border-bottom:1px solid var(--linea)}
.avance .al{font-size:11px;letter-spacing:.06em;text-transform:uppercase;
  color:var(--gris);font-weight:700;margin-bottom:6px}
.avance .barra{max-width:100%;height:12px}
.avance .ad{font-size:13px;margin-top:6px}
.avance .an{font-size:11.5px;color:var(--gris);margin-top:5px}
.dettabs{padding:11px 16px 4px;margin:0;background:var(--carta);
  border-bottom:1px solid var(--linea)}
.panel .regla{padding:11px 16px;font-size:12.5px;color:var(--gris);
  background:var(--navy-50);border-bottom:1px solid var(--linea)}
.panel .persp{margin:14px 16px 8px}
.panel table{margin:0 16px 14px;width:calc(100% - 32px)}
.panel .cuerpo{overflow:visible}
.panel table td, .panel table th{word-break:break-word;overflow-wrap:anywhere}
.panel table td.num, .panel table th.num{word-break:normal;
  overflow-wrap:normal}
.panel .f, .panel .nota, .panel .vacio{padding:0 16px 12px;font-size:12px;
  color:var(--gris)}
.panel .persp{display:flex;justify-content:space-between;align-items:baseline;
  gap:14px;flex-wrap:wrap}
.panel .persp .pista{font-size:11px;letter-spacing:0;text-transform:none;
  font-weight:600;color:var(--gris)}
.dest .src{font-size:10.5px;color:var(--navy);font-weight:700;margin-top:7px;
  letter-spacing:.03em}
.sinfecha:not(:empty){font-size:11px;color:var(--ambar);font-weight:600;
  background:var(--ambar-bg);border-radius:4px;padding:5px 8px;margin:0 0 8px}
.chav{background:var(--ambar-bg);color:#8a6100;border:1px solid var(--ambar);
  font-family:inherit;font-size:10.5px;font-weight:700;padding:4px 10px;
  border-radius:12px;cursor:pointer;margin-top:9px;align-self:flex-start}
.chav:hover{filter:brightness(.96)}
.avlist{margin-top:7px}
.avlist .ojo{font-size:11.5px;color:var(--texto);background:var(--ambar-bg);
  border-left:3px solid var(--ambar);border-radius:4px;padding:7px 9px;
  margin-bottom:5px;line-height:1.5}
#detAvisos .ojo{font-size:12px;color:var(--texto);background:var(--ambar-bg);
  border-left:3px solid var(--ambar);border-radius:4px;padding:8px 12px;
  margin:10px 16px 0;line-height:1.55}
.cartbar{display:flex;height:24px;border-radius:6px;overflow:hidden;
  background:var(--linea)}
.cartbar i{display:block;height:100%}
.cartbar i.no{background:var(--rojo)} .cartbar i.ok{background:var(--verde)}
.cartbar i.parc{background:var(--ambar)}
.cartleg{display:flex;gap:18px;flex-wrap:wrap;margin-top:10px;font-size:12.5px;
  color:var(--texto)}
.cartleg i.p{width:10px;height:10px;border-radius:3px;display:inline-block;
  margin-right:5px;vertical-align:-1px}
.cartleg i.p.no{background:var(--rojo)} .cartleg i.p.ok{background:var(--verde)}
.cartleg i.p.parc{background:var(--ambar)}
#grCartera .ojo{font-size:12px;color:var(--rojo);margin-top:8px}
#grCartera .f{margin-top:8px}
details.aud{margin:14px 0;border:1px solid var(--linea);border-radius:8px;
  background:var(--carta);overflow:hidden}
details.aud summary{cursor:pointer;padding:11px 16px;font-size:13px;
  font-weight:700;color:var(--navy);background:var(--navy-50);list-style:none;
  display:flex;justify-content:space-between;align-items:center;gap:12px}
details.aud summary::-webkit-details-marker{display:none}
details.aud summary::after{content:"ver las filas";font-size:11px;
  font-weight:600;color:var(--gris);white-space:nowrap}
details.aud[open] summary::after{content:"ocultar"}
details.aud .cuerpo{max-height:430px;overflow:auto}
.cuerpo table th{position:sticky;top:0;z-index:3;
  box-shadow:0 1px 0 var(--linea)}
.panel .ph{position:sticky;top:0;z-index:5;min-height:46px}
.panel .cuerpo table th{top:46px}
tr.clicf.sel td{background:var(--navy-100);font-weight:700}
details.aud table{border:none;border-radius:0}
"""

JS = """
function abrir(id){
  document.querySelectorAll('.panel').forEach(function(p){p.hidden = true;});
  var p = document.getElementById(id);
  if(p){ p.hidden = false; p.scrollIntoView({behavior:'smooth', block:'nearest'}); }
}
function cerrar(id){ var p=document.getElementById(id); if(p) p.hidden = true; }
function enPeriodo(fecha, p){
  if (p === 'hist') return true;
  if (!fecha) return false;
  if (fecha.slice(0,4) !== ANIO) return false;
  if (p === 'None') return true;
  return fecha.slice(5,7) === ('0'+p).slice(-2);
}
function periodoActual(){ return document.getElementById('selmes').value; }
function irA(hoja, cifra){
  var b = null;
  document.querySelectorAll('nav button').forEach(function(x){
    if (x.textContent.trim() === hoja) b = x; });
  if (!b) return;
  cerrarDet();
  b.click();
  var cs = AREAS[hoja] || [], k = -1;
  for (var j = 0; j < cs.length; j++) if (cs[j].nombre === cifra) k = j;
  if (k >= 0) verArea(hoja, k);
  else window.scrollTo({top:0, behavior:'smooth'});
}
function volverAResultados(){
  var b = document.querySelectorAll('nav button')[0];
  if (b) b.click();
  window.scrollTo({top:0, behavior:'smooth'});
}
var NOMS = Object.keys(CRUDAS);
function filtrarArea(c){
  var mes = periodoActual(),
      obra = document.getElementById('selobra').value;
  var rs = document.getElementById('selrs').value;
  var asr = document.getElementById('selasesor').value;
  return c.filas.filter(function(f){
    if (obra && f.obra !== obra) return false;
    if (rs && EMPRESA[f.obra] !== rs) return false;
    if (asr && (f.asesor || '') !== asr) return false;
    if (c.mensual && !enPeriodo(f.fecha, mes)) return false;
    return true;
  });
}
function valorArea(c, fs){
  var s = 0; fs.forEach(function(f){ s += f.monto; });
  if (c.modo === 'cuenta') return fs.length;
  if (c.modo === 'promedio') return fs.length ? s/fs.length : 0;
  return s;
}
function pintarAreas(){
  Object.keys(AREAS).forEach(function(hoja){
    AREAS[hoja].forEach(function(c,k){
      var fs = filtrarArea(c);
      var e = document.getElementById('a'+hoja+k);
      if (!e) return;
      var _v = valorArea(c, fs);
      e.innerHTML = c.modo==='cuenta'
        ? _v.toLocaleString('es-PE') : abrev(_v);
      pintaExacto(document.getElementById('x'+hoja+k), _v);
      document.getElementById('c'+hoja+k).textContent = fs.length+' '+c.unidad;
    });
    var p = document.getElementById('pan'+hoja);
    if (p && !p.hidden && p.dataset.k !== undefined) verArea(hoja, +p.dataset.k);
    if (hoja === 'Ventas'){
      var cv = AREAS['Ventas'][0], fv = filtrarArea(cv);
      var av = document.getElementById('avObras');
      if (av){
        var sel = document.getElementById('selobra').value;
        var lista = Object.keys(AVANCE).filter(function(o){
          return (!sel || o === sel) && AVANCE[o].total > 0; })
          .sort(function(a,b){ return AVANCE[b].pct - AVANCE[a].pct; });
        av.innerHTML = lista.map(function(o){
          var a = AVANCE[o], tono = a.pct>=80?'ok':a.pct>=40?'parc':'no';
          return '<div class="gb"><div>'+esc(o)+'</div>'
            + '<div class="bar"><i class="'+tono+'" style="width:'
            + Math.min(a.pct,100).toFixed(1)+'%"></i></div>'
            + '<div class="val">'+a.pct.toFixed(1)+'%</div></div>'
            + '<div class="subv">S/ '+fmt(a.vendido)+' de S/ '+fmt(a.total)
            + ' · '+a.u_vend+' de '+a.u_tot+' unidades'
            + (a.sin_precio ? ' · '+a.sin_precio+' sin precio, fuera de la suma' : '')
            + '</div>'; }).join('') || '<div class="vacio">sin datos</div>';
      }
      [['grModalidad','modalidad'],['grAsesor','asesor']].forEach(function(par){
        var e = document.getElementById(par[0]); if (!e) return;
        var por = {};
        fv.forEach(function(f){ var kk = f[par[1]] || '(sin declarar)';
          por[kk] = (por[kk]||0) + f.monto; });
        grafico(e, Object.keys(por).map(function(o){ return [o, por[o]]; })
          .sort(function(a,b){ return b[1]-a[1]; }));
      });
      var em = document.getElementById('grMes');
      if (em){
        var obra = document.getElementById('selobra').value,
            rs = document.getElementById('selrs').value, pm = {};
        cv.filas.forEach(function(f){
          if (obra && f.obra !== obra) return;
          if (rs && EMPRESA[f.obra] !== rs) return;
          if (!f.fecha || f.fecha.slice(0,4) !== ANIO) return;
          var k2 = f.fecha.slice(0,7); pm[k2] = (pm[k2]||0) + f.monto; });
        grafico(em, Object.keys(pm).sort().map(function(o){ return [o, pm[o]]; }));
      }
    }
    if (hoja === 'Cobranza'){
      pintarGraf('grMora', 'Cobranza', 'Vencido', 'antig', 'suma', TRAMOS);
      var ec = document.getElementById('grCrono'), cp = cifra('Cobranza','Por vencer');
      if (ec && cp){
        var pm = {};
        filtrarArea(cp).forEach(function(f){
          if (!f.fecha) return;
          var k2 = f.fecha.slice(0,7); pm[k2] = (pm[k2]||0) + f.monto; });
        grafico(ec, Object.keys(pm).sort().slice(0,12)
          .map(function(o){ return [o, pm[o]]; }), 12);
      }
    }
    if (hoja === 'Comercial'){
      pintarGraf('grTicket', 'Comercial', 'Ticket promedio por venta',
                 'asesor', 'promedio');
      pintarGraf('grSep', 'Comercial', 'Separaciones por asesor',
                 'asesor', 'suma');
    }
    var G = {Ventas:['Vendido','obra'], Cobranza:['Por cobrar','obra'],
             Comercial:['Vendido por asesor','asesor']};
    if (G[hoja]) pintarGraf('gr'+hoja, hoja, G[hoja][0], G[hoja][1], 'suma');
  });
}
var TRAMOS = ['1 a 30 días','31 a 60 días','61 a 90 días','más de 90 días'];
function cifra(hoja, nombre){
  var cs = AREAS[hoja] || [];
  for (var j = 0; j < cs.length; j++) if (cs[j].nombre === nombre) return cs[j];
  return null;
}
function pintarGraf(id, hoja, nombre, campo, modo, orden){
  var e = document.getElementById(id);
  if (!e) return;
  var c = cifra(hoja, nombre);
  if (!c){ e.innerHTML = '<div class="vacio">la cifra «'+esc(nombre)
    + '» ya no está en esta hoja</div>'; return; }
  var por = {};
  filtrarArea(c).forEach(function(f){
    var k = f[campo] || '(sin dato)';
    por[k] = (por[k] || {n:0, m:0}); por[k].n++; por[k].m += f.monto; });
  var claves = orden ? orden.filter(function(k){ return por[k]; })
                     : Object.keys(por);
  var datos = claves.map(function(o){
    return [o, modo === 'cuenta' ? por[o].n
             : modo === 'promedio' ? por[o].m / por[o].n : por[o].m]; });
  if (!orden) datos.sort(function(a,b){ return b[1] - a[1]; });
  grafico(e, datos);
}
function verArea(hoja, k){
  var c = AREAS[hoja][k], fs = filtrarArea(c), s = 0, por = {};
  var dim = c.agrupa ? 'grupo' : 'obra';
  fs.forEach(function(f){ s += f.monto;
    var g = f[dim] || f.obra;
    por[g] = (por[g]||{n:0,m:0}); por[g].n++; por[g].m += f.monto; });
  document.getElementById('tit'+hoja).textContent = 'Qué incluye «'+c.nombre+'»';
  document.getElementById('reg'+hoja).textContent = c.calculo;
  var g = Object.keys(por).sort(function(a,b){return por[b].m-por[a].m;});
  var col = c.agrupa ? c.cols.indexOf('Asesor') : 1;
  if (col < 0) col = 1;
  document.getElementById('por'+hoja).innerHTML = g.length<2 ? '' :
    '<div class="persp"><span>Por '+esc(c.agrupa||'obra')+'</span>'
    + '<span class="pista">clic en una fila para dejar abajo solo la suya</span>'
    + '</div><table><tr><th>'
    + esc(c.agrupa ? 'Asesor' : 'Obra') + '</th><th class="num">'+esc(c.unidad)
    + '</th><th class="num">Monto</th></tr>'
    + g.map(function(o){ return '<tr class="clicf" data-col="'+col+'" '
      + 'onclick="filaGrupo(this)"><td>'+esc(o)+'</td><td class="num">'
      + por[o].n+'</td><td class="num">S/ '+fmt(por[o].m)+'</td></tr>'; }).join('')
    + '</table>';
  document.getElementById('cnt'+hoja).textContent =
    fs.length+' '+c.unidad+' · '+(c.modo==='cuenta' ? 'se cuentan' :
      c.modo==='promedio' ? 'promedio S/ '+fmt(valorArea(c,fs)) : 'suman S/ '+fmt(s));
  document.getElementById('tab'+hoja).innerHTML =
    '<tr>'+c.cols.map(function(x,ci){
        var num = ci === c.cols.length-1;
        return '<th class="ord'+(num?' num':'')+'" onclick="ordenar(this)">'
          +esc(x)+'</th>'; }).join('')+'</tr>'
    + fs.map(function(f){
        return '<tr><td>'+esc(f.fecha||'—')+'</td><td>'+esc(f.obra)+'</td>'
          + f.d.map(function(x){return '<td>'+esc(x)+'</td>';}).join('')
          + '<td class="num">S/ '+fmt(f.monto)+'</td></tr>'; }).join('');
  var p = document.getElementById('pan'+hoja);
  p.dataset.k = k; p.dataset.hoja = hoja; p.hidden = false;
  fondo(p.parentElement.id, 'none');
  window.scrollTo({top:0, behavior:'smooth'});
}
function filtrarRent(){
  var rs = document.getElementById('selrs').value;
  var obra = document.getElementById('selobra').value;
  document.querySelectorAll('#s3 tr[data-obra]').forEach(function(tr){
    tr.hidden = !!((obra && tr.dataset.obra !== obra) ||
                   (rs && tr.dataset.emp !== rs));
  });
  document.querySelectorAll('#s3 .soloEmpresas').forEach(function(el){
    el.hidden = !!obra;
  });
  document.querySelectorAll('#s3 .notaObraRent').forEach(function(el){
    el.hidden = !obra;
  });
  document.querySelectorAll('#s3 .soloEmpresas tr[data-emp]').forEach(function(tr){
    tr.hidden = !!(rs && tr.dataset.emp !== rs);
  });
  var visiblesMov = 0;
  document.querySelectorAll('#s3 tr[data-obra-mov]').forEach(function(tr){
    tr.hidden = !!((obra && tr.dataset.obraMov !== obra) ||
                   (rs && tr.dataset.empMov !== rs));
    if (!tr.hidden) visiblesMov++;
  });
  document.querySelectorAll('#s3 .vacioMov').forEach(function(el){
    el.hidden = !((obra || rs) && visiblesMov === 0);
  });
  document.querySelectorAll('#s3 .contObras').forEach(function(el){
    var n = 0, tot = 0;
    var cont = el.closest('.mes') || document;
    cont.querySelectorAll('tr[data-obra]').forEach(function(tr){
      tot++; if (!tr.hidden) n++;
    });
    el.textContent = (n === tot)
      ? 'las ' + tot + ', ninguna omitida'
      : n + ' de ' + tot + ' obras · filtro aplicado';
  });
}
function pintarEdad(){
  var el = document.getElementById('edad');
  if(!el || typeof GENERADO === 'undefined') return;
  var g = new Date(GENERADO.replace(' ', 'T'));
  if (isNaN(g)) return;
  var min = Math.round((Date.now() - g) / 60000);
  var hoy = new Date();
  var otroDia = g.toDateString() !== hoy.toDateString();
  var txt, cls;
  if (otroDia){
    txt = ' · ⚠ ES DE OTRO DÍA — usá «Actualizar ahora»'; cls = 'viejo';
  } else if (min >= 90){
    txt = ' · hace ' + Math.floor(min/60) + ' h ' + (min%60) + ' min'; cls = 'viejo';
  } else if (min >= 45){
    txt = ' · hace ' + min + ' min'; cls = 'tibio';
  } else {
    txt = (min <= 1) ? ' · recién' : ' · hace ' + min + ' min'; cls = '';
  }
  el.textContent = txt;
  el.className = cls;
}
pintarEdad();
setInterval(pintarEdad, 60000);
function toggleAvisos(btn){
  var d = btn.nextElementSibling;
  if (d) d.hidden = !d.hidden;
}
function pintarCartera(){
  var e = document.getElementById('grCartera');
  if (!e) return;
  function suma(nom){ var s=0; filtrar(nom).forEach(function(f){s+=f.monto;}); return s; }
  var pc = suma('Por cobrar'), ve = suma('Vencido'), pv = suma('Por vencer');
  if (pc <= 0){ e.innerHTML = '<div class="vacio">sin saldo por cobrar con este filtro</div>'; return; }
  var resto = pc - ve - pv;
  var seg = [['Vencido', ve, 'no'], ['Por vencer', pv, 'ok']];
  if (resto > 1) seg.push(['Sin vencimiento asignado', resto, 'parc']);
  var html = '<div class="cartbar">' + seg.map(function(s){
    return '<i class="'+s[2]+'" style="width:'+(100*s[1]/pc).toFixed(2)
      + '%" title="'+esc(s[0])+': S/ '+fmt(s[1])+'"></i>'; }).join('') + '</div>';
  html += '<div class="cartleg">'
    + '<span>Por cobrar <b>S/ '+fmt(pc)+'</b> =</span>'
    + seg.map(function(s){ return '<span><i class="p '+s[2]+'"></i>'
      + esc(s[0])+' <b>S/ '+fmt(s[1])+'</b></span>'; }).join('') + '</div>';
  if (resto < -1) html += '<div class="ojo">las cuotas pendientes superan el '
    + 'saldo de los créditos en S/ '+fmt(-resto)+' con este filtro — data de '
    + 'Habitat, se reporta</div>';
  html += '<div class="f">«Sin vencimiento asignado» es el saldo que no '
    + 'aparece en ninguna cuota con fecha. Viene sobre todo de créditos a los '
    + 'que nadie les cargó el cronograma, pero NO es exactamente eso: algunos '
    + 'créditos tienen cargado más en cuotas que su propio saldo y compensan '
    + 'la resta. Mismas filas que las tarjetas de arriba.</div>';
  e.innerHTML = html;
}
function toggleFila(tr){
  var d = tr.nextElementSibling;
  if (d && d.classList.contains('mdet')) d.hidden = !d.hidden;
}
document.addEventListener('click', function(ev){
  var b = ev.target.closest('.chip');
  if (!b) return;
  var esArea = b.dataset.p !== undefined, esPersp = b.dataset.pp !== undefined;
  if (!esArea && !esPersp) return;
  var p = esArea ? b.dataset.p : b.dataset.pp;
  document.querySelectorAll('.chip[data-p],.chip[data-pp]').forEach(function(x){
    x.className = 'chip' + (x === b || (!p && x.dataset.p === '') ? ' on' : '');
  });
  document.querySelectorAll('.cuad').forEach(function(c){
    if (!p) { c.hidden = false; return; }
    if (esArea){
      c.hidden = (c.dataset.p !== p);
    } else {
      c.hidden = (('|' + (c.dataset.pp || '') + '|').indexOf('|' + p + '|') === -1);
    }
  });
});
function grafico(cont, datos, cuantas){
  if (!cont) return;
  var max = 0; datos.forEach(function(d){ if (d[1] > max) max = d[1]; });
  cont.innerHTML = datos.slice(0, cuantas || 10).map(function(d){
    return '<div class="gb"><div>'+esc(d[0])+'</div><div class="bar"><i style="width:'
      + (max ? (100*d[1]/max).toFixed(1) : 0) + '%"></i></div>'
      + '<div class="val">'+fmt(d[1])+'</div></div>'; }).join('')
    || '<div class="vacio">sin datos con este filtro</div>';
}
function cerrarArea(hoja){
  var p = document.getElementById('pan'+hoja);
  p.hidden = true;
  fondo(p.parentElement.id, '');
  pintarAreas();
}
function fmt(n){ return n.toLocaleString('es-PE',{minimumFractionDigits:2,maximumFractionDigits:2}); }
function abrev(n){
  var a = Math.abs(n);
  if (a >= 1e6) return (n/1e6).toLocaleString('es-PE',{minimumFractionDigits:2,maximumFractionDigits:2}) + '<i>M</i>';
  if (a >= 1e4) return (n/1e3).toLocaleString('es-PE',{minimumFractionDigits:1,maximumFractionDigits:1}) + '<i>K</i>';
  return 'S/ ' + fmt(n);
}
function pintaExacto(el, n){
  if (!el) return;
  el.textContent = Math.abs(n) >= 1e4 ? 'S/ ' + fmt(n) : '';
}
function esc(s){ return String(s==null?'':s).replace(/[&<>]/g,function(c){
  return {'&':'&amp;','<':'&lt;','>':'&gt;'}[c]; }); }
function filtrar(nom){
  var c = CRUDAS[nom], mes = periodoActual(),
      obra = document.getElementById('selobra').value,
      rs = document.getElementById('selrs').value;
  return c.filas.filter(function(f){
    if (obra && f.obra !== obra) return false;
    if (rs && EMPRESA[f.obra] !== rs) return false;
    if (c.mensual && !enPeriodo(f.fecha, mes)) return false;
    return true;
  });
}
function sinFechaFuera(nom){
  var c = CRUDAS[nom];
  if (!c.mensual || periodoActual() === 'hist') return null;
  var obra = document.getElementById('selobra').value,
      rs = document.getElementById('selrs').value, n = 0, s = 0;
  c.filas.forEach(function(f){
    if (f.fecha) return;
    if (obra && f.obra !== obra) return;
    if (rs && EMPRESA[f.obra] !== rs) return;
    n++; s += f.monto;
  });
  return n ? {n: n, monto: s} : null;
}
function comparativo(nom, mes){
  if (!mes || mes === 'hist' || !CRUDAS[nom] || !CRUDAS[nom].mensual) return '';
  var m = parseInt(mes, 10);
  if (m <= 1) return '';
  var hoy = new Date(), corte = 31;
  if (String(hoy.getFullYear()) === ANIO && (hoy.getMonth() + 1) === m) corte = hoy.getDate();
  var obra = document.getElementById('selobra').value;
  var act = 0, ant = 0, nAct = 0, nAnt = 0, porDia = {};
  (CRUDAS[nom].filas || []).forEach(function(f){
    if (!f.fecha || (obra && f.obra !== obra)) return;
    var p = f.fecha.split('-');
    if (p[0] !== ANIO) return;   // ANIO es texto ('2026'), no número
    var mm = parseInt(p[1], 10), dd = parseInt(p[2], 10);
    if (mm === m){ act += f.monto; nAct++; porDia[dd] = (porDia[dd]||0) + f.monto; }
    else if (mm === m - 1 && dd <= corte){ ant += f.monto; nAnt++; }
  });
  var nomMes = (NOMBRES_MES[String(m)]||'').replace(/^\d+ · /, '');
  var nomAnt = (NOMBRES_MES[String(m-1)]||'').replace(/^\d+ · /, '');
  var txt;
  if (ant <= 0 && act <= 0) return '';
  if (ant <= 0) txt = 'en ' + nomAnt + ' a esta altura tampoco había nada';
  else {
    var pct = Math.round(100 * act / ant);
    txt = 'vas <b>' + pct + '%</b> de lo que iba ' + nomAnt + ' al día ' + corte
        + ' (S/ ' + fmt(ant) + ' · ' + nAnt + ')';
    if (act === 0) txt = '<b>nada registrado en ' + nomMes + '</b>, y ' + nomAnt
        + ' al día ' + corte + ' iba S/ ' + fmt(ant) + ' en ' + nAnt + ' operaciones';
  }
  var dias = Object.keys(porDia).map(Number).sort(function(a,b){return a-b;});
  var barras = '';
  if (dias.length){
    var tope = Math.max.apply(null, dias.map(function(d){ return porDia[d]; }));
    barras = '<div class="pordia">' + dias.map(function(d){
      return '<i style="height:' + Math.max(3, 100*porDia[d]/tope).toFixed(0)
        + '%" title="' + d + ' de ' + nomMes + ': S/ ' + fmt(porDia[d]) + '"></i>';
    }).join('') + '</div>';
  }
  return '<div class="comp' + (act === 0 && ant > 0 ? ' alerta' : '') + '">'
    + txt + barras + '</div>';
}
function pintar(){
  var mesSel = document.getElementById('selmes') ? document.getElementById('selmes').value : '';
  NOMS.forEach(function(nom,k){
    var fs = filtrar(nom), s = 0;
    fs.forEach(function(f){ s += f.monto; });
    document.getElementById('vg'+k).innerHTML = abrev(s);
    pintaExacto(document.getElementById('ex'+k), s);
    document.getElementById('cn'+k).textContent = fs.length+' '+CRUDAS[nom].unidad;
    var cp = document.getElementById('cp'+k);
    if (cp) cp.innerHTML = comparativo(nom, mesSel);
    var sf = document.getElementById('sf'+k), fuera = sinFechaFuera(nom);
    if (sf) sf.innerHTML = fuera
      ? '<b>' + fuera.n + '</b> sin fecha cargada (S/ ' + fmt(fuera.monto)
        + ') quedan fuera: no están en ningún año'
      : '';
  });
  var d = document.getElementById('detalle');
  if (d && !d.hidden && d.dataset.k !== undefined) verDet(d.dataset.k);
  pintarCartera();
  pintarAreas();
}
function barraAvance(obra){
  var e = document.getElementById('detAvance');
  if (!e) return;
  var a = obra ? AVANCE[obra] : null;
  if (!a){ e.innerHTML = ''; return; }
  var tono = a.pct >= 80 ? 'ok' : a.pct >= 40 ? 'parc' : 'no';
  e.innerHTML = '<div class="avance"><div class="al">Avance de venta de '
    + esc(obra) + '</div>'
    + '<div class="barra"><i class="' + tono + '" style="width:'
    + Math.min(a.pct,100).toFixed(1) + '%"></i></div>'
    + '<div class="ad"><b>' + a.pct.toFixed(1) + '%</b> · vendido S/ '
    + fmt(a.vendido) + ' de S/ ' + fmt(a.total) + ' · ' + a.u_vend + ' de '
    + a.u_tot + ' unidades</div>'
    + '<div class="an">El valor total es la SUMA de las unidades de la obra: '
    + 'AXION no trae un campo «valor del proyecto». Las dos cifras salen de la '
    + 'misma columna de precio de Unit, no de Sale, porque esas dos bases de '
    + 'precio discrepan entre sí.'
    + (a.sin_precio ? ' <b>' + a.sin_precio + ' unidad(es) sin precio cargado '
       + 'quedan FUERA de la suma</b> —no se cuentan como cero— así que el '
       + 'total real es mayor.'
       + (a.sin_precio_con_venta ? ' De ellas, ' + a.sin_precio_con_venta
          + ' sí tienen venta registrada en Sale: el precio existe, falta en '
          + 'la ficha de la unidad.' : '') : '') + '</div></div>';
}
function ordenar(th){
  var tb = th.closest('table');
  var col = Array.prototype.indexOf.call(th.parentElement.children, th);
  var num = th.classList.contains('num');
  var fs = Array.from(tb.querySelectorAll('tr')).slice(1);
  var asc = tb.dataset.ord === col+'-desc';
  fs.sort(function(a,b){
    var x = a.children[col].textContent.trim(), y = b.children[col].textContent.trim();
    if (x === '—') return 1; if (y === '—') return -1;
    if (num){ x = parseFloat(x.replace(/[^0-9.-]/g,''))||0;
              y = parseFloat(y.replace(/[^0-9.-]/g,''))||0; }
    return (x < y ? -1 : x > y ? 1 : 0) * (asc ? 1 : -1);
  });
  tb.dataset.ord = col + (asc ? '-asc' : '-desc');
  fs.forEach(function(f){ tb.appendChild(f); });
}
function verDet(k){
  var nom = NOMS[k], c = CRUDAS[nom], fs = filtrar(nom), s = 0, por = {};
  fs.forEach(function(f){ s += f.monto;
    por[f.obra] = (por[f.obra]||{n:0,m:0}); por[f.obra].n++; por[f.obra].m += f.monto; });
  document.getElementById('detTit').textContent = 'Qué incluye «'+nom+'»';
  document.getElementById('detTabs').innerHTML = NOMS.map(function(n,j){
    return '<button class="chip'+(j==k?' on':'')+'" onclick="verDet('+j+')">'
      + esc(n)+'</button>'; }).join('');
  document.getElementById('detRegla').textContent = c.regla;
  document.getElementById('detAvisos').innerHTML = (c.avisos || [])
    .map(function(a){
      var p = String(a).split('∷');
      if (p.length < 4) return '<div class="ojo">'+esc(a)+'</div>';
      return '<div class="ojo alerta"><b>⚠ '+esc(p[0])+'</b>'
        + '<p><b>Qué pasó.</b> '+esc(p[1])+'</p>'
        + '<p><b>Cómo se cierra.</b> '+esc(p[2])+'</p>'
        + '<div class="quien">lo resuelve: '+esc(p[3])+'</div>'
        + '<div class="f">Se arregla en AXION, no acá. Al corregirlo, esta '
        + 'alerta desaparece sola en la siguiente actualización.</div></div>';
    }).join('');
  var g = Object.keys(por).sort(function(a,b){return por[b].m-por[a].m;});
  document.getElementById('detPor').innerHTML = g.length<2 ? '' :
    '<div class="persp"><span>Por obra</span>'
    + '<span class="pista">clic en una obra para dejar abajo solo sus filas</span>'
    + '</div><table><tr><th>Obra</th><th class="num">'
    + esc(c.unidad) + '</th><th class="num">Monto</th></tr>'
    + g.map(function(o){ return '<tr class="clicf" data-col="1" '
      + 'onclick="filaGrupo(this)">'
      + '<td>'+esc(o)+'</td><td class="num">'
      + por[o].n + '</td><td class="num">S/ ' + fmt(por[o].m) + '</td></tr>'; }).join('')
    + '</table>';
  document.getElementById('detCuenta').textContent =
    fs.length+' '+c.unidad+' · suman S/ '+fmt(s);
  var sinFecha = fs.filter(function(f){ return !f.fecha; }).length;
  document.getElementById('detTabla').innerHTML =
    '<tr>' + c.cols.map(function(x,ci){
        var num = ci === c.cols.length-1;
        return '<th class="ord'+(num?' num':'')+'" onclick="ordenar(this)">'
          +esc(x)+'</th>'; }).join('') + '</tr>'
    + fs.map(function(f){
        return '<tr><td>'+esc(f.fecha||'—')+'</td><td>'+esc(f.obra)+'</td>'
          + f.d.map(function(x){return '<td>'+esc(x)+'</td>';}).join('')
          + '<td class="num">S/ '+fmt(f.monto)+'</td></tr>'; }).join('');
  if (sinFecha) document.getElementById('detCuenta').textContent +=
    ' · ' + sinFecha + ' sin fecha cargada';
  barraAvance(document.getElementById('selobra').value);
  var d = document.getElementById('detalle');
  d.dataset.k = k; d.hidden = false;
  fondo('s0', 'none');
  window.scrollTo({top:0, behavior:'smooth'});
}
function fondo(sec, display){
  var s = document.getElementById(sec);
  if (!s) return;
  Array.prototype.forEach.call(s.children, function(x){
    if (x.classList.contains('panel') || x.tagName === 'H2') return;
    if (x.classList.contains('volver')) return;
    x.style.display = display;
  });
}
function filaGrupo(tr){
  var pan = tr.closest('.panel');
  var tb = pan.querySelector('.cuerpo table');
  var cnt = pan.querySelector('.tot');
  var col = +tr.dataset.col, val = tr.children[0].textContent.trim();
  var ya = tr.classList.contains('sel');
  tr.closest('table').querySelectorAll('tr.clicf')
    .forEach(function(x){ x.classList.remove('sel'); });
  if (ya){
    if (pan.dataset.hoja) verArea(pan.dataset.hoja, +pan.dataset.k);
    else if (pan.dataset.k !== undefined) verDet(+pan.dataset.k);
    return;
  }
  tr.classList.add('sel');
  var n = 0, s = 0;
  Array.prototype.slice.call(tb.querySelectorAll('tr'), 1).forEach(function(r){
    var vis = r.children[col] && r.children[col].textContent.trim() === val;
    r.hidden = !vis;
    if (vis){ n++;
      s += parseFloat(r.children[r.children.length-1].textContent
            .replace(/[^0-9.-]/g,'')) || 0; }
  });
  var c = pan.dataset.hoja ? AREAS[pan.dataset.hoja][+pan.dataset.k] : null;
  var modo = c ? c.modo : 'suma';
  cnt.textContent = n + ' filas de ' + val + ' · '
    + (modo === 'cuenta' ? 'se cuentan'
       : modo === 'promedio' ? 'promedio S/ ' + fmt(n ? s/n : 0)
       : 'suman S/ ' + fmt(s))
    + ' · clic de nuevo para ver todas';
}
function cerrarDet(){
  document.getElementById('detalle').hidden = true;
  fondo('s0', '');
}
var selo = document.getElementById('selobra');
if (selo) selo.onchange = function(){ pintar(); filtrarRent(); };
var selr = document.getElementById('selrs');
if (selr) selr.onchange = function(){ pintar(); filtrarRent(); };
var sela = document.getElementById('selasesor');
if (sela) sela.onchange = pintar;
pintarCartera();
pintarAreas();
var sel = document.getElementById('selmes');
if (sel) sel.onchange = function(){
  document.querySelectorAll('.mes').forEach(function(m){
    m.hidden = (m.dataset.mes !== sel.value);
  });
  pintar();
};
document.querySelectorAll('nav button').forEach(function(b){
  b.onclick = function(){
    document.querySelectorAll('nav button').forEach(function(x){x.className='';});
    document.querySelectorAll('section').forEach(function(x){x.className='';});
    b.className = 'on';
    document.getElementById(b.dataset.hoja).className = 'on';
    var hoja = b.textContent.trim();
    var CON_RS = ['Rentabilidad','Ventas','Cobranza','Comercial'];
    var CON_ASESOR = ['Ventas','Comercial'];
    var verRs = CON_RS.indexOf(hoja) >= 0, verAs = CON_ASESOR.indexOf(hoja) >= 0;
    document.getElementById('parrs').hidden = !verRs;
    document.getElementById('parasesor').hidden = !verAs;
    var toco = false;
    if (!verRs && document.getElementById('selrs').value){
      document.getElementById('selrs').value = ''; toco = true;
    }
    if (!verAs && document.getElementById('selasesor').value){
      document.getElementById('selasesor').value = ''; toco = true;
    }
    if (toco) pintar();
    if (hoja === 'Rentabilidad') filtrarRent();
    try { history.replaceState(null, '', '#' + encodeURIComponent(hoja)); }
    catch(e){}
  };
});
(function(){
  var h = decodeURIComponent((location.hash || '').replace('#','')).trim();
  if (!h) return;
  var b = [...document.querySelectorAll('nav button')]
    .find(function(x){ return x.textContent.trim().toLowerCase() === h.toLowerCase(); });
  if (b) b.click();
})();
"""


def main() -> int:
    d = payload()
    _paso("tablero.html…")
    nav, secs = render(d)
    opciones = "".join(f'<option value="{k}">{_esc(v)}</option>'
                       for k, v in _solo_periodos_del_viejo(d["nombres_mes"].items()))
    opciones_rs = ('<option value="">Todas las empresas</option>'
                   + "".join(f'<option value="{_esc(r)}">{_esc(r[:34])}</option>'
                             for r in d["razones_filtro"]))
    opciones_obra = ('<option value="">Todas las obras</option>'
                     + "".join(f'<option value="{_esc(o)}">{_esc(o)}</option>'
                               for o in d["obras_filtro"]))
    opciones_asesor = ('<option value="">Todos los asesores</option>'
                       + "".join(f'<option value="{_esc(a)}">{_esc(a[:30])}'
                                 f'</option>' for a in d["asesores_filtro"]))
    html = f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Habitat · Cockpit de Rentabilidad</title><style>{_css()}</style></head><body>
<header>
  <div class="marca">{_logo()}
    <div><h1>HABITAT CONTROL</h1>
      <div class="baja">Control de gestión y rentabilidad · Corte {d['generado'][:10]}</div></div></div>
  <div class="filtro">
    <div class="par"><label>Período</label>
      <select id="selmes">{opciones}</select></div>
    <div class="par" id="parobra"><label>Obra</label>
      <select id="selobra">{opciones_obra}</select></div>
    <div class="par" id="parrs" hidden><label>Razón social</label>
      <select id="selrs">{opciones_rs}</select></div>
    <div class="par" id="parasesor" hidden><label>Asesor</label>
      <select id="selasesor">{opciones_asesor}</select></div>
  </div>
  <div class="sello"><span class="vivo">EN VIVO</span>
    Datos de AXION {d['generado']}<span id="edad"></span>
    <button id="btnactualizar">Actualizar ahora</button><br>
    <span class="f">Cada cifra indica su origen y abre sus filas{_tardanza(d)}</span></div>
</header>
<nav>{nav}</nav><main>{secs}</main>
<script>const AVANCE={json.dumps(d['avance'], ensure_ascii=False)};const EMPRESA={json.dumps(d['empresa_de_obra'], ensure_ascii=False)};const AREAS={json.dumps(d['areas_filas'], ensure_ascii=False)};const CRUDAS={json.dumps(d['crudas'], ensure_ascii=False)};const NOMBRES_MES={json.dumps(d['nombres_mes'], ensure_ascii=False)};const ANIO={json.dumps(str(periodo.ANIO))};const GENERADO={json.dumps(d['generado'])};{JS}</script>
<script>(function(){{let visto=null;let cada=120000;let timer=null;
try{{const prev=sessionStorage.getItem('marcaprevia');
if(sessionStorage.getItem('actualizando')){{sessionStorage.removeItem('actualizando');sessionStorage.removeItem('marcaprevia');
const cambio=(prev===null)||(prev!==GENERADO);
const b=document.createElement('div');
b.textContent=cambio?('Actualizado · los datos ahora son de '+GENERADO)
                    :('Sin cambios · los datos siguen siendo de '+GENERADO+' — la lectura no trajo nada nuevo');
b.style.cssText='position:relative;z-index:5;background:'+(cambio?'#0a7d3f':'#8a6d00')+';color:#fff;padding:9px 14px;text-align:center;font-weight:600;font-size:13px';
document.body.insertBefore(b,document.body.firstChild);setTimeout(()=>b.remove(),10000);}}}}catch(e){{}}
function avisarNuevo(){{if(document.getElementById('av-nuevo'))return;
const d=document.createElement('div');d.id='av-nuevo';
d.style.cssText='position:fixed;right:24px;bottom:24px;z-index:60;display:flex;gap:12px;align-items:center;background:#0d1b45;color:#fff;padding:12px 16px;border-radius:12px;box-shadow:0 6px 24px rgba(8,16,41,.28);font-size:13px;max-width:min(92vw,520px)';
d.innerHTML='<span style="color:#b9c5e9">Hay una lectura mas nueva del motor.</span>'
+'<button id="av-si" style="font:inherit;font-weight:600;cursor:pointer;padding:5px 12px;border:0;border-radius:6px;background:#fcd925;color:#0d1b45">Cargarla</button>'
+'<button id="av-no" style="font:inherit;font-weight:600;cursor:pointer;padding:5px 12px;border-radius:6px;background:transparent;color:#b9c5e9;border:1px solid #163180">Ahora no</button>';
document.body.appendChild(d);
document.getElementById('av-si').onclick=function(){{location.reload();}};
document.getElementById('av-no').onclick=function(){{d.remove();}};}}
async function ver(){{try{{const r=await fetch('tablero_datos.json',{{method:'HEAD',cache:'no-store'}});if(!r.ok)return;const m=r.headers.get('last-modified');if(visto&&m&&m!==visto){{avisarNuevo();return;}}if(m)visto=m;}}catch(e){{}}}}function arrancar(ms){{if(timer)clearInterval(timer);cada=ms;timer=setInterval(ver,cada);}}arrancar(120000);ver();
const btn=document.getElementById('btnactualizar');
if(btn){{btn.addEventListener('click',async()=>{{
  btn.disabled=true;btn.textContent='Preguntando al servidor…';
  let base=null;
  try{{const e0=await(await fetch('estado',{{cache:'no-store'}})).json();base=e0.publicado;}}catch(e){{}}
  let r;
  try{{r=await fetch('actualizar',{{method:'POST'}});if(!r.ok)throw new Error(r.status);}}
  catch(e){{btn.textContent='No se pudo · el servidor no respondió';btn.disabled=false;return;}}
  let ya=false;
  try{{ya=/en marcha/.test((await r.json()).estado||'');}}catch(e){{}}
  sessionStorage.setItem('actualizando','1');
  sessionStorage.setItem('marcaprevia',GENERADO);
  arrancar(10000);
  const vigilar=setInterval(async()=>{{
    let s;
    try{{s=await(await fetch('estado',{{cache:'no-store'}})).json();}}catch(e){{return;}}
    if(s.corriendo){{
      const m=s.va_min||0;
      btn.textContent=(ya?'Ya se estaba actualizando sola · va ':'Actualizando… va ')
        +(m<1?'menos de 1 min':m+' min')+' · se recarga al terminar';
      if(m>=25) btn.textContent+=' — está tardando más de lo normal';
      return;
    }}
    clearInterval(vigilar);
    if(base && s.publicado && s.publicado!==base){{ location.reload(); return; }}
    sessionStorage.removeItem('actualizando');sessionStorage.removeItem('marcaprevia');
    btn.textContent='Terminó sin publicar nada · revisá data\\\\cockpit.log';
    btn.disabled=false;
  }},10000);
}});}}}})();</script></body></html>"""
    _publicar(SALIDA, html)
    _carpeta = (os.getenv("TABLERO_DATOS_DIR") or "").strip()
    _destino = (Path(_carpeta) if _carpeta
                else Path("/var/data") if (os.getenv("RENDER") and Path("/var/data").is_dir())
                else RAIZ)
    _paso("bitácora, ventas de la contadora, cronogramas y stock…")
    print()
    try:
        from src import bitacora as _bit
        d["bitacora"] = _bit.calcular()
        _b = d["bitacora"]
        if _b.get("hay"):
            _t = _b["totales"]
            print(f"  bitacora · {_t['partes']} partes en {_t['proyectos']} obras · "
                  f"{_t['desde']} a {_t['hasta']} · {_t['contratos']} contratos · "
                  f"{_t['cotizaciones']} cotizaciones")
    except Exception as e:  # noqa: BLE001
        print(f"  bitacora no se pudo calcular: {type(e).__name__}: {e}")
        d["bitacora"] = {"hay": False, "motivo": "la bitácora no se pudo calcular"}
    try:
        from src import actividades_marketing as _am
        d["actividades_marketing"] = _am.calcular()
        _a = d["actividades_marketing"]
        if _a.get("hay"):
            print(f"  actividades de marketing · {_a['total']} de {len(_a['resp'])} personas · "
                  f"{_a['desde']} a {_a['hasta']}")
    except Exception as e:  # noqa: BLE001
        print(f"  actividades de marketing no se pudieron calcular: {type(e).__name__}: {e}")
        d["actividades_marketing"] = {"hay": False, "motivo": "las actividades no se pudieron calcular"}
    try:
        from src import informe_quincenal as _iq
        d["informe_quincenal"] = _iq.calcular()
        _q = d["informe_quincenal"]
        if _q.get("hay"):
            print(f"  informe mensual · {len(_q['meses_inf'])} meses · "
                  f"ventas {len(_q.get('ventas') or {})} · marketing {len(_q.get('marketing') or {})}"
                  + (f" · ERROR ventas: {_q['ventas_error']}" if _q.get('ventas_error') else "")
                  + (f" · ERROR marketing: {_q['marketing_error']}" if _q.get('marketing_error') else ""))
    except Exception as e:  # noqa: BLE001
        print(f"  informe mensual no se pudo calcular: {type(e).__name__}: {e}")
        d["informe_quincenal"] = {"hay": False, "motivo": "el informe mensual no se pudo calcular"}
    try:
        from src import bitacora as _bit
        d["pagos_personal"] = _bit.pagos_personal()
        _pp = d["pagos_personal"]
        if _pp.get("hay"):
            _t = _pp["totales"]
            print(f"  pagos a personal · {_t['partidas']} partidas en {_t['proyectos']} "
                  f"proyectos · total {_t['total']:,.2f} · pagado {_t['pagado']:,.2f} · "
                  f"saldo {_t['saldo']:,.2f} · {_t['con_obs']} con observación")
    except Exception as e:  # noqa: BLE001
        print(f"  pagos a personal no se pudo calcular: {type(e).__name__}: {e}")
        d["pagos_personal"] = {"hay": False, "motivo": "Pagos a Personal no se pudo calcular"}

    try:
        from src import ventas_contadora as _vco
        d["ventas_contadora"] = _vco.totales()
        _v = d["ventas_contadora"]
        if _v.get("hay"):
            print(f"  ventas contadora · {_v['meses_con_cifra']} meses con "
                  f"cifra · {_v['total']:,.2f}"
                  + (f" · rotos: {', '.join(_v['rotos'])}" if _v.get("rotos") else ""))
        else:
            print(f"  ventas contadora: {_v.get('motivo')}")
    except Exception as e:  # noqa: BLE001
        print(f"  ventas contadora no se pudo leer: {type(e).__name__}: {e}")
        d["ventas_contadora"] = {"hay": False,
                                 "motivo": "no se pudo leer el Excel de ventas"}

    _v2 = d.get("valorizaciones") or {"hay": False}
    if _v2.get("hay"):
        print(f"  valorizaciones · {len(_v2['obras'])} obra(s) · "
              + " · ".join(f"{o['obra'][:22]} {o['n']}p "
                           f"{(o['avance_pct'] or 0) * 100:.1f}%"
                           for o in _v2["obras"]))
        _nocuadra = [o["obra"] for o in _v2["obras"] if not o.get("cuadra")]
        if _nocuadra:
            print(f"    OJO: no cuadran con su COSTO DIRECTO: {_nocuadra}")
        if _v2.get("repetidos"):
            print(f"    archivos repetidos: {_v2['repetidos']}")
    else:
        print(f"  valorizaciones: {_v2.get('motivo')}")

    try:
        from src import cronograma as _cro
        d["cronogramas"] = _cro.calcular()
        _c = d["cronogramas"]
        if _c.get("hay"):
            print(f"  cronogramas · {len(_c['obras'])} obra(s) · "
                  f"{sum(o['n'] for o in _c['obras'])} partidas")
        else:
            print(f"  cronogramas: {_c.get('motivo')}")
    except Exception as e:  # noqa: BLE001
        print(f"  cronogramas no se pudo calcular: {type(e).__name__}: {e}")
        d["cronogramas"] = {"hay": False, "motivo": "el cronograma no se pudo leer"}

    try:
        from src import stock as _stock
        _st = _stock.calcular()
        _fallas = _stock.sin_datos_de_personas(_st) if _st.get("hay") else []
        if _fallas:
            print("  stock NO publicado: " + " · ".join(_fallas))
            _st = {"hay": False, "motivo": "el control de datos de personas falló"}
        d["stock"] = _st
    except Exception as e:  # noqa: BLE001
        print(f"  stock no se pudo calcular: {type(e).__name__}: {e}")
        _st = {"hay": False, "motivo": "el stock no se pudo calcular"}
        d["stock"] = _st

    _paso("escribir tablero_datos.json…")
    _publicar(_destino / "tablero_datos.json",
              json.dumps(_sin_nan(d), ensure_ascii=False, indent=1,
                         allow_nan=False))

    try:
        _sobre = {
            "generado": d.get("generado"),
            "publicado": d.get("publicado"),
            "nombres_mes": d.get("nombres_mes") or {},
            "meses": {"None": {}},
            "obras_filtro": [],
            "razones_filtro": [],
            "tipos_filtro": [],
            "asesores_filtro": [],
            "stock": _st,
        }
        _publicar(_destino / "stock_datos.json",
                  json.dumps(_sin_nan(_sobre), ensure_ascii=False, indent=1,
                             allow_nan=False))
        if _st.get("hay"):
            _t = _st["totales"]
            print(f"  stock_datos.json · {_t['proyectos']} proyectos · "
                  f"{_t['libres']} libres de {_t['unidades']} unidades")
    except Exception as e:  # noqa: BLE001
        print(f"  stock del externo no se pudo generar: {type(e).__name__}: {e}")

    try:
        _FIN = ("generado", "publicado", "nombres_mes", "fuentes", "obras_filtro",
                "razones_filtro", "tipos_filtro", "empresa_de_obra", "tipo_de_obra",
                "flujo", "libro", "ordenes_compra", "proyeccion", "control_cuentas",
                "saldos_externos", "saldos_iniciales", "contasis_mensual",
                "caja_encadenada", "operacion")
        _fin = {k: d[k] for k in _FIN if k in d}
        _fin["meses"] = {k: {} for k in (d.get("meses") or {})} or {"None": {}}
        _fin["asesores_filtro"] = []
        _pv = [g for g in ((d.get("areas_filas") or {}).get("Cobranza") or [])
               if g.get("nombre") == "Por vencer"]
        _fin["areas_filas"] = {"Cobranza": [{
            "nombre": "Por vencer",
            "filas": [{"fecha": r.get("fecha"), "obra": r.get("obra"),
                       "monto": r.get("monto"), "fuera": r.get("fuera"),
                       "d": (r.get("d") or [])[:1]}
                      for r in (_pv[0].get("filas") or [])],
        }]} if _pv else {}
        _publicar(_destino / "finanzas_datos.json",
                  json.dumps(_sin_nan(_fin), ensure_ascii=False, indent=1,
                             allow_nan=False))
        print(f"  finanzas_datos.json · {len(_fin)} claves · "
              f"{len(_fin['areas_filas'].get('Cobranza', [{}])[0].get('filas', [])) if _fin['areas_filas'] else 0} "
              f"cuotas por vencer")
    except Exception as e:  # noqa: BLE001
        print(f"  el archivo de Finanzas no se pudo generar: {type(e).__name__}: {e}")

    try:
        _OBR = ("generado", "publicado", "nombres_mes", "fuentes", "obras_filtro",
                "razones_filtro", "tipos_filtro", "empresa_de_obra", "tipo_de_obra",
                "avance", "avance_fisico", "cabidas", "incidentes", "bitacora",
                "pagos_personal", "cronogramas", "valorizaciones")
        _ob = {k: d[k] for k in _OBR if k in d}
        _ob["meses"] = {k: {} for k in (d.get("meses") or {})} or {"None": {}}
        _ob["asesores_filtro"] = []
        _fl = d.get("flujo") or {}
        _ob["flujo"] = {"hay": bool(_fl.get("hay")), "anio": _fl.get("anio"),
                        "meses": [{k: m.get(k) for k in ("mes", "etiqueta", "pasado", "en_curso")}
                                  for m in (_fl.get("meses") or [])]}
        _lf = ((d.get("libro") or {}).get("filas")) or {}
        _gastos = [r for r in (_lf.get("f") or []) if len(r) > 7 and r[7] == "gasto"]
        _ob["libro"] = {"filas": {**{k: v for k, v in _lf.items() if k not in ("f", "total", "recortado")},
                                  "f": _gastos, "total": len(_gastos), "recortado": 0}}
        _publicar(_destino / "obras_datos.json",
                  json.dumps(_sin_nan(_ob), ensure_ascii=False, indent=1,
                             allow_nan=False))
        print(f"  obras_datos.json · {len(_ob)} claves · {len(_gastos)} gastos del libro")
    except Exception as e:  # noqa: BLE001
        print(f"  el archivo de Obras no se pudo generar: {type(e).__name__}: {e}")

    try:
        from src import datos_ventas as _dv
        _ve = _dv.armar(d)
        _publicar(_destino / "ventas_datos.json",
                  json.dumps(_sin_nan(_ve), ensure_ascii=False, indent=1,
                             allow_nan=False))
        print(f"  ventas_datos.json · {len(_ve)} claves · "
              f"{len(_ve['libro']['filas']['f'])} gastos del libro")
    except Exception as e:  # noqa: BLE001
        print(f"  el archivo de Ventas no se pudo generar: {type(e).__name__}: {e}")
    print(f"\n{SALIDA.name} · {len(html) // 1024} KB · "
          f"{html.count('<section')} hojas")

    _paso_fin()
    _resumen_lecturas()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
