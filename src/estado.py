"""HOJA 1 · ESTADO."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime  # noqa: F401 — lo usan las fechas de la data

from . import reloj
from pathlib import Path

import pandas as pd

from . import administracion as adm
from . import contasis, ingest, kommo
from . import lectura_excel as lx

RAIZ = Path(__file__).resolve().parent.parent
HUELLA = RAIZ / "data" / "estado_fuentes.json"
ACTA = RAIZ / "data" / "acta_verificacion.json"


@dataclass
class Fuente:
    nombre: str
    conectada: bool
    fecha: str                      # cuándo se leyó
    periodo: str                    # hasta cuándo llegan sus números
    detalle: list[str] = field(default_factory=list)
    faltantes: list[str] = field(default_factory=list)
    aviso: str = ""                 # desconexión declarada


def _huella_leer() -> dict:
    if HUELLA.exists():
        try:
            return json.loads(HUELLA.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def _huella_escribir(clave: str, datos: dict) -> None:
    h = _huella_leer()
    h[clave] = {**datos, "leido": reloj.sello()}
    HUELLA.parent.mkdir(parents=True, exist_ok=True)
    HUELLA.write_text(json.dumps(h, indent=1, ensure_ascii=False), encoding="utf-8")


def fuente_axion() -> Fuente:
    """AXION en vivo. Si no responde, la última lectura buena con su fecha."""
    OPCIONALES = {"KPI", "Lead", "Advisor", "Moroso", "Property", "Ingreso"}
    conteos, error, caidas = {}, None, []
    for ent in ingest.AXION_ENTITIES:
        try:
            if ent in OPCIONALES:
                conteos[ent] = len(ingest.fetch_axion_opcional(ent, []))
            else:
                conteos[ent] = len(ingest.fetch_axion_entity(ent, None, 5000))
        except Exception as e:  # noqa: BLE001
            error = f"{type(e).__name__}: {str(e)[:70]}"
            break
    caidas = [f"{k}: {v}" for k, v in ingest.DEGRADADAS.items()]

    if error:
        prev = _huella_leer().get("AXION")
        if not prev:
            return Fuente("AXION · API", False, "—", "—",
                          aviso=f"la API no responde ({error}) y no hay "
                                f"ninguna lectura anterior guardada")
        f = Fuente("AXION · API", False, prev["leido"], prev.get("periodo", "—"),
                   detalle=[f"{k}: {v} filas"
                            for k, v in sorted(prev.get("conteos", {}).items())],
                   aviso=f"DESCONECTADA ({error}). Lo que se muestra es la "
                         f"última lectura buena, del {prev['leido']}. "
                         f"No es la situación de hoy.")
        return f

    sale = ingest.fetch_axion_entity("Sale", None, 5000)
    fechas = pd.to_datetime(sale["date"], errors="coerce").dropna()
    periodo = (f"ventas de {fechas.min():%Y-%m-%d} a {fechas.max():%Y-%m-%d}"
               if len(fechas) else "sin fechas")
    _huella_escribir("AXION", {"conteos": conteos, "periodo": periodo})

    f = Fuente("AXION · API", True, reloj.sello(),
               periodo,
               detalle=[f"{k}: {v} filas" for k, v in sorted(conteos.items()) if v])
    if caidas:
        f.aviso = ("TABLAS QUE NO RESPONDIERON HOY, servidas desde la última "
                   "lectura buena: " + " · ".join(caidas) +
                   ". El resto del tablero es de hoy. Habitat está editando "
                   "AXION: una tabla renombrada o borrada se ve así.")

    from . import movimientos as _mv
    _gt = _mv.gasto_total(None)
    if _gt.get("hay") and _gt["monto"] and _gt["pct_atribuido"] < 99:
        f.faltantes.append(
            f"COSTOS POR OBRA: de S/ {_gt['monto']:,.2f} en "
            f"{_gt['filas']:,} movimientos de gasto, solo el "
            f"{_gt['pct_atribuido']:.1f}% dice de qué obra es. El resto no "
            f"lleva proyecto cargado, y sin eso no hay margen ni reducción de "
            f"costos por obra (2 indicadores del scorecard).")
    if conteos.get("Lead", 0) == 0:
        vac = int(sale["marketing_source"].map(lambda x: not str(x).strip()).sum())
        f.faltantes.append(
            f"ORIGEN COMERCIAL: la tabla de leads está en cero y el ORIGEN de "
            f"la venta —el campo «Fuente» de la ficha en AXION— viene vacío en "
            f"{vac} de {len(sale)} ventas. Sin eso no hay costo de captación "
            f"ni conversión (Marketing).")
    from . import areas  # tardío: areas importa estado en el sentido inverso
    vacias = [n for n in ("OrdenCompra", "Proveedor", "Material", "Inventory")
              if not len(areas._log(n))]
    if vacias:
        f.faltantes.append(
            "LOGÍSTICA: de las cuatro tablas del módulo de compras, "
            + " y ".join(vacias) + (" sigue vacía" if len(vacias) == 1
                                    else " siguen vacías") +
            ". Sin conteo físico cargado no hay exactitud de inventario.")
    f.faltantes.append(
        "OBRA: el avance sale del cuaderno de obras, hoy no conectado.")
    return f


def _contasis_mensual() -> dict:
    p = RAIZ / "config" / "contasis_mensual.json"
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except json.JSONDecodeError:
        return {}


def fuente_contasis() -> Fuente:
    men = _contasis_mensual()
    emp = men.get("empresas") or {}
    cierres = sorted({m for e in emp.values() for m in e.get("cierres", [])})
    cajas = sorted({m for e in emp.values() for m in e.get("caja", [])})
    inv = contasis.inventario()
    if inv.empty and not emp:
        return Fuente("CONTASIS · Excel del contador", False, "—", "—",
                      aviso="no hay archivos en data/raw_exports/")
    periodos = sorted({p for p in inv["periodo"].dropna()
                       if "JUNIO" in str(p).upper() or "Junio" in str(p)}) if not inv.empty else []
    empresas = sorted({e for e in inv["empresa"].dropna()}) if not inv.empty else []
    archivos = list((lx.CRUDOS / "contasis").rglob("*.xls*"))
    archivos += list((lx.CRUDOS / "contasis_empresas").rglob("*.xls*"))
    mtime = max((f.stat().st_mtime for f in archivos), default=0)
    fecha = reloj.de_marca(mtime).strftime(reloj.FORMATO) if mtime else "—"
    if men.get("generado") and (fecha == "—" or men["generado"] > fecha):
        fecha = men["generado"]
    if cierres or cajas:
        periodos = [" · ".join(
            ([f"cierre mensual hasta {cierres[-1]}"] if cierres else [])
            + ([f"libro caja hasta {cajas[-1]}"] if cajas else []))]
    detalle = []
    if emp:
        con = [e.get("nombre", r) for r, e in emp.items() if e.get("caja") or e.get("cierres")]
        detalle.append(f"{len(con)} empresas con Excel mensual: " + " · ".join(con))
    if not inv.empty:
        detalle += [f"{len(inv)} hojas en {len(archivos)} archivos",
                    f"{len(empresas)} empresas: " + " · ".join(e[:28] for e in empresas)]
    return Fuente(
        "CONTASIS · Excel del contador", True, fecha,
        " · ".join(periodos) if periodos else "sin corte declarado",
        detalle=detalle,
        faltantes=[
            "El cierre de cada mes llega el 15 del mes siguiente: se deja en "
            "data/raw_exports/contasis_mensual/AAAA-MM/ y se corre "
            "scripts/importar_contasis.py.",
            "Alimenta solo la hoja ContaSis de Finanzas; ninguna otra hoja "
            "suma sus cifras con las de AXION.",
        ])


def fuente_administracion() -> Fuente:
    inv = adm.inventario()
    if inv.empty:
        return Fuente("ADMINISTRACIÓN · Excel mensual", False, "—", "—",
                      aviso="no hay archivos en data/raw_exports/gastos_manuales/")
    mov = adm.movimientos()
    det = mov[mov["_clase"] == "detalle"] if not mov.empty else mov
    fechas = []
    for c in det.columns:
        if not c.startswith("_") and "FECHA" in lx.normalizar(c):
            fechas.append(pd.to_datetime(det[c], errors="coerce"))
    todas = pd.concat(fechas).dropna() if fechas else pd.Series(dtype="datetime64[ns]")
    buenas = todas[(todas >= "1900-01-01") & (todas <= "2100-12-31")]
    negocio = buenas[(buenas >= "2020-01-01") & (buenas <= "2028-12-31")]
    lejanas = sorted(buenas[(buenas < "2020-01-01") | (buenas > "2028-12-31")])
    archivos = list((lx.CRUDOS / "gastos_manuales").glob("*.xls*"))
    mtime = max((f.stat().st_mtime for f in archivos), default=0)
    f = Fuente(
        "ADMINISTRACIÓN · Excel mensual", True,
        reloj.de_marca(mtime).strftime(reloj.FORMATO) if mtime else "—",
        (f"movimientos de {negocio.min():%Y-%m-%d} a {negocio.max():%Y-%m-%d}"
         if len(negocio) else "sin fechas legibles"),
        detalle=[f"{len(inv)} hojas en {len(archivos)} archivos",
                 f"{len(det):,} filas de detalle"])
    malas = len(todas) - len(buenas)
    if malas:
        f.faltantes.append(
            f"{malas} fecha(s) imposibles (años tipeados mal, p. ej. 0206). "
            f"Se muestran, no se corrigen.")
    if lejanas:
        f.faltantes.append(
            f"{len(lejanas)} fecha(s) fuera del rango del negocio, la más "
            f"lejana {lejanas[-1]:%Y-%m-%d}. No entran en el período "
            f"declarado arriba, pero sus movimientos siguen contados.")
    f.faltantes.append(
        "AXION va a reemplazar estos Excels. El contador NO: sigue emitiendo "
        "su estado de resultados.")
    return f


def sello_controles() -> dict:
    """El acta de `scripts/verificar.py`. Vive en Estado, no en el header."""
    if not ACTA.exists():
        return {"hay": False,
                "texto": "todavía no se corrió scripts/verificar.py"}
    try:
        a = json.loads(ACTA.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"hay": False, "texto": "el acta no se puede leer"}
    return {"hay": True, "acta": a}


def fuente_kommo() -> Fuente:
    """KOMMO en vivo."""
    try:
        r = kommo.resumen()
    except Exception as e:  # noqa: BLE001
        prev = _huella_leer().get("KOMMO")
        if not prev:
            return Fuente("KOMMO · CRM (API)", False, "—", "—",
                          aviso=f"el CRM no responde ({type(e).__name__}: "
                                f"{str(e)[:60]}) y no hay ninguna lectura "
                                f"anterior guardada")
        return Fuente(
            "KOMMO · CRM (API)", False, prev["leido"], prev.get("periodo", "—"),
            detalle=[f"{k}: {v} leads"
                     for k, v in (prev.get("por_embudo") or {}).items()],
            aviso=f"DESCONECTADA ({type(e).__name__}: {str(e)[:90]}). Lo que "
                  f"se muestra es la última lectura buena, del {prev['leido']}. "
                  f"No es la situación de hoy.")

    _huella_escribir("KOMMO", {"por_embudo": r["por_embudo"],
                               "periodo": r["periodo"],
                               "leidos": r["leidos"]})
    fuera = {k: v for k, v in r["por_embudo"].items()
             if k != "Ventas - Habitat Inmobiliaria"}
    f = Fuente(
        "KOMMO · CRM (API)", True, reloj.sello(),
        r["periodo"],
        detalle=[f"{r['leidos']:,} leads leídos · embudo «Ventas - Habitat "
                 f"Inmobiliaria»",
                 f"la cuenta tiene {r['total_cuenta']:,} leads en 4 embudos"])
    if fuera:
        f.faltantes.append(
            "FUERA DE ALCANCE por decisión de Habitat (03-ago-2026): "
            + " · ".join(f"{k} ({v:,} leads)" for k, v in fuera.items())
            + ". Los proyectos de Concept no existen como obra en AXION: es "
              "otro negocio, y mezclarlo inflaría el embudo.")
    f.faltantes.append(
        "RASTREO DE ANUNCIOS: los 9 campos automáticos (utm_source, gclid, "
        "fbclid, ttad_name…) están vacíos en los 7,799 leads. La campaña la "
        "escribe el asesor a mano: sirve para agrupar, no para costo por "
        "anuncio.")
    f.faltantes.append(
        "PLATA: Kommo no la tiene. `price` está en cero en el 99.6% de los "
        "leads, así que NO entra en Rentabilidad ni en el margen — solo en "
        "Marketing y Comercial.")
    return f


def cambios_en_axion() -> list[dict]:
    """Qué tocó Habitat en AXION desde la última vez que miramos."""
    try:
        from . import cambios_axion
        return cambios_axion.revisar()
    except Exception:  # noqa: BLE001 — el vigilante nunca tumba la hoja
        return []


def hoja_estado() -> list[Fuente]:
    return [fuente_axion(), fuente_kommo(), fuente_contasis(),
            fuente_administracion()]
