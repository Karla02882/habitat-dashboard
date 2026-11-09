"""EL ARCHIVO DE DATOS DE LAS CUENTAS DE VENTAS."""
from __future__ import annotations

# Lo que el motor y las seis hojas leen del primer nivel, tal cual.
CLAVES = ("generado", "publicado", "nombres_mes", "fuentes", "obras_filtro",
          "razones_filtro", "tipos_filtro", "empresa_de_obra", "tipo_de_obra",
          "asesores_filtro", "avance", "ventas_contadora", "metas_gerencia",
          "metas_asesor", "metas_ventas", "crm_concept", "asesores_activos",
          "stock", "actividades_marketing")
# Lo que las hojas leen de `meses[P]` (los indicadores van aparte, filtrados).
CLAVES_MES = ("estructura", "crm", "asesores_axion", "crm_filas", "crm_filas_control")
# Las dos categorías del libro que Marketing lista con su concepto.
CATEGORIAS_MARKETING = ("Marketing", "Publicidad")


def _solo_marketing(lista) -> list:
    return [i for i in (lista or []) if i.get("area") == "Marketing"]


def armar(d: dict) -> dict:
    """El contenido de `ventas_datos.json` a partir del payload grande `d`."""
    v = {k: d[k] for k in CLAVES if k in d}

    v["meses"] = {}
    for p, m in (d.get("meses") or {}).items():
        x = {k: m[k] for k in CLAVES_MES if k in m}
        if "indicadores" in m:
            x["indicadores"] = _solo_marketing(m["indicadores"])
        v["meses"][p] = x
    v["meses"] = v["meses"] or {"None": {}}

    v["indicadores"] = _solo_marketing(d.get("indicadores"))
    v["series"] = {k: s for k, s in (d.get("series") or {}).items() if k == "Leads captados"}
    v["areas"] = {"Marketing": (d.get("areas") or {}).get("Marketing")}

    af = d.get("areas_filas") or {}
    v["areas_filas"] = {
        "Cobranza": [b for b in (af.get("Cobranza") or []) if b.get("nombre") == "Vencido"],
        "Comercial": [b for b in (af.get("Comercial") or [])
                      if b.get("nombre") == "Origen declarado de la venta"],
    }

    fl = d.get("flujo") or {}
    v["flujo"] = {"hay": bool(fl.get("hay")), "anio": fl.get("anio"),
                  "meses": [{k: m.get(k) for k in ("mes", "etiqueta", "pasado", "en_curso")}
                            for m in (fl.get("meses") or [])]}
    v["vencimientos"] = {"composicion": (d.get("vencimientos") or {}).get("composicion")}

    lf = ((d.get("libro") or {}).get("filas")) or {}
    cats = lf.get("cat") or []
    lob, lcu = lf.get("obra") or [], lf.get("cuenta") or []
    nob, ncu, mob, mcu = [], [], {}, {}

    def reindexar(lista, nuevo, mapa, i):
        if i is None:
            return None
        if i not in mapa:
            mapa[i] = len(nuevo)
            nuevo.append(lista[i] if 0 <= i < len(lista) else "")
        return mapa[i]

    filas = []
    for r in (lf.get("f") or []):
        if len(r) < 8 or r[7] != "gasto":
            continue
        cat = cats[r[2]] if r[2] is not None and 0 <= r[2] < len(cats) else ""
        if cat in CATEGORIAS_MARKETING:
            filas.append([r[0], r[1], r[2], r[3], r[4],
                          reindexar(lob, nob, mob, r[5]), reindexar(lcu, ncu, mcu, r[6]), r[7]])
        else:
            filas.append([r[0], r[1], r[2], "", r[4], None, None, r[7]])
    v["libro"] = {"filas": {"mov": lf.get("mov"), "cat": lf.get("cat"),
                            "obra": nob, "cuenta": ncu, "f": filas,
                            "total": len(filas), "recortado": 0}}
    return v
