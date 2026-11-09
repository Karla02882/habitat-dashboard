"""EL EMBUDO DEL CRM."""
from __future__ import annotations

import re
import unicodedata

import pandas as pd

from . import kommo

JORNADA = (9, 18)


_CACHE: dict = {}


def limpiar_cache() -> None:
    """Suelta la foto. La próxima lectura vuelve a construirla."""
    _CACHE.clear()


def _base(mes: int | None = None, anio: int | None = None) -> pd.DataFrame:
    """Los leads del embudo, recortados al mes de CREACIÓN si se pide."""
    clave = ("_base", mes, anio)
    if clave not in _CACHE:
        df = kommo.leads()
        if "creado" not in df.columns or df.empty:
            _CACHE[clave] = df
        else:
            creado = pd.to_datetime(df["creado"], errors="coerce")
            if anio:
                df = df[creado.dt.year == anio]
                creado = creado[creado.dt.year == anio]
            if mes:
                df = df[creado.dt.month == mes]
            _CACHE[clave] = df
    return _CACHE[clave].copy()


def _atencion(df: pd.DataFrame) -> pd.Series:
    """Horas entre la creación del lead y su primera llamada."""
    if df.empty or "primera_llamada" not in df.columns:
        return pd.Series(dtype=float)
    creado = pd.to_datetime(df["creado"], errors="coerce")
    llamada = pd.to_datetime(df["primera_llamada"], errors="coerce")
    h = (llamada - creado).dt.total_seconds() / 3600.0
    return h.mask((h < 0) & (h > -1 / 60), 0.0)


def por_responsable(mes: int | None = None, anio: int | None = None,
                    df: pd.DataFrame | None = None) -> list[dict]:
    """Leads por asesor, con su tiempo de atención. Lo primero que pidió."""
    df = _base(mes, anio) if df is None else df
    if df.empty:
        return []
    horas = _atencion(df)
    df = df.assign(_h=horas)
    filas = []
    for nombre, g in df.groupby("responsable", dropna=False):
        h = g["_h"].dropna()
        h = h[h >= 0]                      # las negativas se reportan aparte
        fin_de_semana = pd.to_datetime(g["creado"], errors="coerce").dt.dayofweek >= 5
        h_fds = g.loc[fin_de_semana, "_h"].dropna()
        h_hab = g.loc[~fin_de_semana, "_h"].dropna()
        h_fds = h_fds[h_fds >= 0]
        h_hab = h_hab[h_hab >= 0]
        filas.append({
            "responsable": str(nombre),
            "leads": int(len(g)),
            "vendidos": int((g["etapa"] == "VENDIDO").sum()),
            "sin_gestionar": int((g["etapa"] == "ASIGNADO").sum()),
            "con_llamada": int(len(h)),
            "horas_promedio": float(h.mean()) if len(h) else None,
            "horas_mediana": float(h.median()) if len(h) else None,
            "horas_habil": float(h_hab.median()) if len(h_hab) else None,
            "horas_finde": float(h_fds.median()) if len(h_fds) else None,
            "leads_finde": int(fin_de_semana.sum()),
        })
    return sorted(filas, key=lambda x: -x["leads"])


ETIQUETAS_INFORME = ("WSP OFICIAL", "FB MESSENGER")


def atencion_por_etiqueta(mes: int | None = None, anio: int | None = None) -> list[dict]:
    """Tiempo de atención por asesor, SOLO de los leads marcados con alguna."""
    df = _base(mes, anio)
    if df.empty or "etiquetas" not in df.columns:
        return []
    marcados = set(ETIQUETAS_INFORME)
    con_tag = df["etiquetas"].apply(
        lambda ts: bool(marcados & set(ts)) if isinstance(ts, list) else False)
    df = df[con_tag]
    if df.empty:
        return []
    horas = _atencion(df)
    df = df.assign(_h=horas)
    creado = pd.to_datetime(df["creado"], errors="coerce")
    fds = creado.dt.dayofweek >= 5
    en_jornada = creado.dt.hour.between(JORNADA[0], JORNADA[1] - 1)

    def _mediana(sel):
        h = df.loc[sel, "_h"].dropna()
        h = h[h >= 0]
        return {"leads": int(sel.sum()), "mediana_h": float(h.median()) if len(h) else None}

    filas = []
    for nombre, idx in df.groupby("responsable", dropna=False).groups.items():
        sel = df.index.isin(idx)
        s_lab = sel & (~fds) & en_jornada
        s_fuera = sel & (~fds) & (~en_jornada)
        s_fds = sel & fds
        filas.append({
            "responsable": str(nombre),
            "leads": int(sel.sum()),
            "laboral": _mediana(s_lab),
            "fuera_horario": _mediana(s_fuera),
            "fin_de_semana": _mediana(s_fds),
        })
    return sorted(filas, key=lambda x: -x["leads"])


def _conteo(df: pd.DataFrame, col: str) -> list[dict]:
    """Conteo con porcentaje sobre el TOTAL de leads, no sobre los que tienen."""
    if df.empty or col not in df.columns:
        return []
    n = len(df)
    vc = df[col].fillna("(sin dato)").value_counts()
    return [{"valor": str(k), "leads": int(v), "pct": 100.0 * v / n}
            for k, v in vc.items()]


def genero(mes=None, anio=None) -> list[dict]:
    return _conteo(_base(mes, anio), "genero")


def campanas(mes=None, anio=None) -> list[dict]:
    return _conteo(_base(mes, anio), "campana")


def etapas(mes=None, anio=None) -> list[dict]:
    return _conteo(_base(mes, anio), "etapa")


def proyectos(mes=None, anio=None) -> list[dict]:
    return _conteo(_base(mes, anio), "proyecto")


CORTES_EXTRA = [
    ("producto", "Producto buscado"),
    ("uso", "Uso declarado"),
    ("nivel_interes", "Nivel de interés"),
    ("ciudad", "Ciudad donde vive"),
    ("contactabilidad", "Contactabilidad"),
    ("medidas", "Medidas buscadas"),
    ("lugar_trabajo", "Lugar de trabajo"),
    ("rango_edad", "Rango de edad"),
    ("dormitorios", "Dormitorios"),
]


def cortes_extra(mes=None, anio=None) -> list[dict]:
    df = _base(mes, anio)
    return [{"titulo": titulo, "items": _conteo(df, col)}
            for col, titulo in CORTES_EXTRA]


_DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]


def por_dia(mes=None, anio=None) -> list[dict]:
    """Leads por día de la semana en que se CREARON, Lunes a Domingo."""
    df = _base(mes, anio)
    if df.empty:
        return []
    n = len(df)
    dow = pd.to_datetime(df["creado"], errors="coerce").dt.dayofweek
    return [{"valor": _DIAS[d], "leads": int((dow == d).sum()),
             "pct": 100.0 * int((dow == d).sum()) / n} for d in range(7)]


def por_hora(mes=None, anio=None) -> list[dict]:
    """Leads por hora del día en que se CREARON, 00 a 23."""
    df = _base(mes, anio)
    if df.empty:
        return []
    n = len(df)
    h = pd.to_datetime(df["creado"], errors="coerce").dt.hour
    return [{"valor": f"{hh:02d}:00", "leads": int((h == hh).sum()),
             "pct": 100.0 * int((h == hh).sum()) / n} for hh in range(24)]


def atencion_global(mes: int | None = None, anio: int | None = None) -> dict:
    """El tiempo de atención del embudo entero, con sus avisos de calidad."""
    df = _base(mes, anio)
    if df.empty:
        return {"leads": 0}
    h = _atencion(df)
    negativas = int((h < 0).sum())
    validas = h[h >= 0].dropna()
    creado = pd.to_datetime(df["creado"], errors="coerce")
    fds = creado.dt.dayofweek >= 5
    en_jornada = creado.dt.hour.between(JORNADA[0], JORNADA[1] - 1)
    h_hab = h[(~fds) & (h >= 0)].dropna()
    h_fds = h[fds & (h >= 0)].dropna()
    return {
        "leads": int(len(df)),
        "con_llamada": int(len(validas)),
        "sin_llamada": int(len(df) - len(h.dropna())),
        "promedio": float(validas.mean()) if len(validas) else None,
        "mediana": float(validas.median()) if len(validas) else None,
        "habil_mediana": float(h_hab.median()) if len(h_hab) else None,
        "finde_mediana": float(h_fds.median()) if len(h_fds) else None,
        "leads_habil": int((~fds).sum()),
        "leads_finde": int(fds.sum()),
        "con_llamada_habil": int(len(h_hab)),
        "con_llamada_finde": int(len(h_fds)),
        "leads_en_jornada": int(en_jornada.sum()),
        "negativas": negativas,
        "sin_gestionar": int((df["etapa"] == "ASIGNADO").sum()),
        "desestimados_sin_llamada": int(
            ((df["etapa"] == "DESESTIMADO") & h.isna()).sum()),
        "desestimados": int((df["etapa"] == "DESESTIMADO").sum()),
        "jornada": JORNADA,
        "visitaron": (int(df["visita_presencial"].notna().sum())
                      if "visita_presencial" in df.columns else None),
    }


COLUMNAS_FILA = ["id", "etapa", "embudo", "responsable", "campana", "proyecto",
                 "contactabilidad", "nivel_interes", "motivo_perdida", "etiquetas",
                 "genero", "uso",
                 "creado", "primera_llamada", "visita_presencial", "horas_atencion"]

PROHIBIDO = ("nombre", "name", "telefono", "teléfono", "phone", "correo",
             "email", "contacto", "contact", "dni", "documento")


def _txt(v) -> str:
    """Texto limpio. `str(NaN)` da `'nan'` y pandas rellena los faltantes con."""
    if v is None:
        return ""
    s = str(v).strip()
    return "" if s.lower() in ("nan", "none", "nat", "<na>") else s


def _iso(v) -> str:
    """Fecha CON HORA, en el mismo formato que `scripts/exportar_crm_detalle.py`."""
    t = pd.to_datetime(v, errors="coerce")
    return "" if pd.isna(t) else t.strftime("%Y-%m-%d %H:%M")


def filas_leads(mes: int | None = None, anio: int | None = None) -> list[dict]:
    """Una fila por lead del embudo, SIN un solo dato de persona adentro."""
    return _filas_de_df(_base(mes, anio))


def _filas_de_df(df: pd.DataFrame) -> list[dict]:
    """El armado fila-por-fila que usa `filas_leads()`, separado para que."""
    if df.empty:
        return []
    horas = _atencion(df)
    if len(horas) != len(df):
        horas = pd.Series([float("nan")] * len(df), index=df.index)
    df = df.assign(_h=horas)

    filas = []
    for _, r in df.iterrows():
        h = r["_h"]
        filas.append({
            "id": (int(r["id"]) if pd.notna(r.get("id")) else None),
            "etapa": _txt(r.get("etapa")),
            "embudo": _txt(r.get("embudo")),
            "responsable": _txt(r.get("responsable")),
            "campana": _txt(r.get("campana")),
            "proyecto": _txt(r.get("proyecto")),
            "contactabilidad": _txt(r.get("contactabilidad")),
            "nivel_interes": _txt(r.get("nivel_interes")),
            "motivo_perdida": _txt(r.get("motivo_perdida")),
            "etiquetas": sorted(str(t) for t in (r.get("etiquetas") or [])),
            "genero": _txt(r.get("genero")),
            "uso": _txt(r.get("uso")),
            "creado": _iso(r.get("creado")),
            "primera_llamada": _iso(r.get("primera_llamada")),
            "visita_presencial": _iso(r.get("visita_presencial")),
            "horas_atencion": (None if pd.isna(h) else round(float(h), 4)),
        })
    return filas


def filas_leads_control(fs: list[dict]) -> dict:
    """Los conteos de las filas, CALCULADOS SOBRE LAS FILAS y no sobre el."""
    hs = [f["horas_atencion"] for f in fs]
    return {
        "filas": len(fs),
        "con_llamada": sum(1 for h in hs if h is not None and h >= 0),
        "sin_llamada": sum(1 for f in fs if not f["primera_llamada"]),
        "negativas": sum(1 for h in hs if h is not None and h < 0),
        "visitaron": sum(1 for f in fs if f["visita_presencial"]),
        "vendidos": sum(1 for f in fs if f["etapa"] == "VENDIDO"),
        "sin_personas": _sin_personas(fs),
    }


def _sin_personas(fs: list[dict]) -> bool:
    """¿Las filas publicadas traen SOLO las columnas de la lista blanca?."""
    malas = {c for c in COLUMNAS_FILA
             if any(c == p or c.startswith(f"{p}_") or c.endswith(f"_{p}")
                    for p in PROHIBIDO)}
    if malas:
        return False
    esperado = set(COLUMNAS_FILA)
    return all(set(f) == esperado for f in fs)


def embudo_decision(mes: int | None = None, anio: int | None = None,
                    df: pd.DataFrame | None = None, con_citas: bool = True) -> dict:
    """EL EMBUDO QUE PIDIÓ EL JEFE DE VENTAS, con su conversión en cada."""
    df = _base(mes, anio) if df is None else df
    if df.empty:
        return {"hay": False}
    total = len(df)
    etapa = df["etapa"].astype(str)
    AVANZADAS = {"CONTACTADO", "SEGUIMIENTO", "VISITA", "PRE CIERRE", "VENDIDO"}
    en_etapa = int(etapa.isin(AVANZADAS).sum())
    tiene_ll = df["primera_llamada"].notna() \
        if "primera_llamada" in df.columns else pd.Series(False, index=df.index)
    contactados = int(tiene_ll.sum())
    horas = _atencion(df)
    llamada_imposible = int((horas < 0).sum())
    sin_llamada = total - contactados
    vendidos_id = set(df[etapa == "VENDIDO"]["id"])
    vendidos = len(vendidos_id)
    cierre_contactados = len(set(df[tiene_ll & (etapa == "VENDIDO")]["id"]))
    visitas = int(df["visita_presencial"].notna().sum()) \
        if "visita_presencial" in df.columns else 0
    visita_vend = int((df["visita_presencial"].notna() &
                       (etapa == "VENDIDO")).sum()) \
        if "visita_presencial" in df.columns else 0

    citas = {"hay": False}
    try:
        if not con_citas:
            raise ValueError("sin citas")
        t = kommo.tareas()
        ids = set(df["id"])
        tl = t[(t["entidad"] == "leads") & (t["entidad_id"].isin(ids))]
        agend = set(tl["entidad_id"])
        comp = set(tl[tl["completada"]]["entidad_id"])
        ahora = pd.Timestamp.now()
        venc = tl[(~tl["completada"]) & (pd.to_datetime(tl["vence"],
                                                        errors="coerce") < ahora)]
        citas = {
            "hay": True,
            "tareas": int(len(tl)),
            "leads_con_cita": len(agend),
            "leads_con_cita_completada": len(comp),
            "vencidas_sin_completar": int(len(venc)),
            "cerraron_con_cita": len(agend & vendidos_id),
            "cerraron_con_cita_completada": len(comp & vendidos_id),
            "vendidos_sin_cita": len(vendidos_id - agend),
            "por_asesor": sorted([
                {"responsable": str(k),
                 "citas": int(len(g)),
                 "completadas": int(g["completada"].sum()),
                 "pct": round(100 * float(g["completada"].sum()) / len(g), 1)}
                for k, g in tl.groupby("responsable", dropna=False)],
                key=lambda x: -x["citas"]),
        }
    except Exception:  # noqa: BLE001
        citas = {"hay": False}

    def corte(col: str) -> list[dict]:
        if col not in df.columns:
            return []
        filas = []
        for k, g in df.groupby(df[col].fillna("(sin dato)").astype(str)):
            n = len(g)
            v = int((g["etapa"].astype(str) == "VENDIDO").sum())
            filas.append({"clave": str(k), "leads": n, "vendidos": v,
                          "pct": round(100 * v / n, 2) if n else 0.0})
        return sorted(filas, key=lambda x: (-x["pct"], -x["leads"]))

    return {
        "hay": True,
        "leads": total,
        "contactados": contactados,
        "pct_contactados": round(100 * contactados / total, 1) if total else 0,
        # Lo que la definición nueva deja de mostrar, publicado al lado.
        "en_etapa_avanzada": en_etapa,
        "pct_en_etapa": round(100 * en_etapa / total, 1) if total else 0,
        "llamada_imposible": llamada_imposible,
        "sin_llamada": sin_llamada,
        "leads_por_venta": round(total / vendidos, 1) if vendidos else None,
        "visitas": visitas,
        "pct_visitas": round(100 * visitas / total, 1) if total else 0,
        "vendidos": vendidos,
        "pct_cierre_leads": round(100 * vendidos / total, 2) if total else 0,
        "pct_cierre_contactados": round(100 * cierre_contactados / contactados, 2)
            if contactados else 0,
        "pct_cierre_visitas": round(100 * visita_vend / visitas, 2)
            if visitas else 0,
        "vendidos_sin_visita": vendidos - visita_vend,
        "citas": citas,
        "por_asesor": corte("responsable"),
        "por_campana": corte("campana"),
        "por_proyecto": corte("proyecto"),
        "por_mes": _serie_mensual(df, etapa),
    }


def _serie_mensual(df: pd.DataFrame, etapa: pd.Series) -> list[dict]:
    """Leads, contactados y cierres por mes de creación."""
    if df.empty or "creado" not in df.columns:
        return []
    creado = pd.to_datetime(df["creado"], errors="coerce")
    tiene_ll = df["primera_llamada"].notna() \
        if "primera_llamada" in df.columns else pd.Series(False, index=df.index)
    vend = etapa == "VENDIDO"
    filas = []
    for mes in sorted({int(m) for m in creado.dt.month.dropna().unique()}):
        sel = creado.dt.month == mes
        n = int(sel.sum())
        c = int((sel & tiene_ll).sum())
        v = int((sel & vend).sum())
        filas.append({"mes": mes, "leads": n, "contactados": c, "vendidos": v,
                      "pct": round(100 * v / n, 2) if n else 0.0})
    return filas


def kpis_asesor(mes: int | None = None, anio: int | None = None) -> dict:
    """LA EVALUACIÓN POR ASESOR."""
    df = _base(mes, anio)
    if df.empty:
        return {"hay": False}
    etapa = df["etapa"].astype(str)
    horas = _atencion(df)
    creado = pd.to_datetime(df["creado"], errors="coerce")
    fds = creado.dt.dayofweek >= 5
    en_jornada = creado.dt.hour.between(JORNADA[0], JORNADA[1] - 1)
    _dfh = df.assign(_h=horas)

    citas_ag: dict[str, int] = {}
    citas_ok: dict[str, int] = {}
    citas_tot: dict[str, int] = {}
    try:
        t = kommo.tareas()
        dueno = dict(zip(df["id"], df["responsable"].astype(str)))
        tl = t[(t["entidad"] == "leads") & (t["entidad_id"].isin(dueno))]
        vistos_ag: dict[str, set] = {}
        vistos_ok: dict[str, set] = {}
        for _, fila in tl.iterrows():
            k = dueno.get(fila["entidad_id"])
            if k is None:
                continue
            citas_tot[k] = citas_tot.get(k, 0) + 1
            vistos_ag.setdefault(k, set()).add(fila["entidad_id"])
            if bool(fila["completada"]):
                vistos_ok.setdefault(k, set()).add(fila["entidad_id"])
        citas_ag = {k: len(v) for k, v in vistos_ag.items()}
        citas_ok = {k: len(v) for k, v in vistos_ok.items()}
    except Exception:  # noqa: BLE001
        citas_ag, citas_ok, citas_tot = {}, {}, {}

    filas = []
    for k, idx in df.groupby("responsable", dropna=False).groups.items():
        sel = df.index.isin(idx)
        nom = str(k)
        n = int(sel.sum())
        h = horas[sel & (horas >= 0)].dropna()
        h_lab = horas[sel & (~fds) & en_jornada & (horas >= 0)].dropna()
        vend = int((sel & (etapa == "VENDIDO")).sum())
        cont = int((sel & df["primera_llamada"].notna()).sum())
        seg = int((sel & df["seguimiento_1"].notna()).sum())             if "seguimiento_1" in df.columns else 0
        vis = int((sel & df["visita_presencial"].notna()).sum()) \
            if "visita_presencial" in df.columns else 0
        seg_cols = [c for c in ("seguimiento_1", "seguimiento_2", "seguimiento_3")
                    if c in df.columns]
        vivo = sel & (etapa != "DESESTIMADO")
        nseg = (df[seg_cols].notna().sum(axis=1) if seg_cols
                else pd.Series(0, index=df.index))
        seg_dist = [int((vivo & (nseg == i)).sum()) for i in range(4)]
        seg_clientes = int(vivo.sum())
        ag = citas_ag.get(nom, 0)
        ok = citas_ok.get(nom, 0)
        tot_citas = citas_tot.get(nom, 0)
        def _corte(mascara):
            hh = _dfh.loc[sel & mascara, "_h"].dropna()
            hh = hh[hh >= 0]
            return {"leads": int((sel & mascara).sum()),
                    "con_llamada": int(len(hh)),
                    "antes": int((sel & mascara & (horas < 0)).sum()),
                    "min": round(float(hh.median()) * 60, 1) if len(hh) else None,
                    "prom_min": round(float(hh.mean()) * 60, 1) if len(hh) else None}

        filas.append({
            "responsable": nom,
            "leads": n,
            "momento": {
                "laboral": _corte((~fds) & en_jornada),
                "fuera": _corte((~fds) & (~en_jornada)),
                "finde": _corte(fds),
            },
            # minutos, no horas: la meta que trae la tabla está en minutos
            "respuesta_min": round(float(h.median()) * 60, 1) if len(h) else None,
            "respuesta_prom_min": round(float(h.mean()) * 60, 1) if len(h) else None,
            "con_llamada": int(len(h)),
            "llamada_antes": int((sel & (horas < 0)).sum()),
            "respuesta_laboral_min": round(float(h_lab.median()) * 60, 1)
                if len(h_lab) else None,
            "citas_agendadas": ag,
            "citas_totales": tot_citas,
            "citas_realizadas": ok,
            "pct_citas_realizadas": round(100 * ok / ag, 1) if ag else None,
            "pct_agendadas_sobre_leads": round(100 * ag / n, 1) if n else None,
            "visitas": vis,
            "contactados": cont,
            "seguimientos": seg,
            "seg_dist": seg_dist,
            "seg_clientes": seg_clientes,
            "pct_seguimiento": round(100 * seg / cont, 1) if cont else None,
            "ventas": vend,
            "pct_lead_venta": round(100 * vend / n, 2) if n else 0.0,
        })
    filas.sort(key=lambda x: (-x["ventas"], -x["leads"]))
    return {
        "hay": True,
        "asesores": filas,
    }


def _palabras_nombre(x) -> list:
    """El nombre en mayúsculas, sin tildes y partido en palabras."""
    import unicodedata as _ud
    y = _ud.normalize("NFD", str(x or "")).encode("ascii", "ignore").decode().upper()
    return re.sub(r"[^A-Z ]", " ", y).split()


def _misma_persona(a, b) -> bool:
    """Si un vendedor de AXION y un usuario de Kommo son la misma persona."""
    wa, wb = _palabras_nombre(a), _palabras_nombre(b)
    if not wa or not wb:
        return False
    ta = {w for w in wa if len(w) >= 4}
    tb = {w for w in wb if len(w) >= 4}
    return len(ta & tb) >= 2 and (wa[0] in wb or wb[0] in wa)


ETAPAS_CALIFICADO = ("SEGUIMIENTO", "VISITA", "PRE CIERRE", "VENDIDO")


def kpis_ventas(mes: int | None = None, anio: int | None = None,
                asesor: str | None = None) -> dict:
    df = _base(mes, anio)
    if df.empty:
        return {"hay": False}

    if asesor:
        df = df[df["responsable"].astype(str).str.upper()
                == str(asesor).upper()]
        if df.empty:
            return {"hay": True, "kpis": [], "leads": 0, "asesor": asesor,
                    "vacio": f"{asesor} no tiene leads en este período"}

    n = len(df)
    etapa = df["etapa"].astype(str)
    horas = _atencion(df)
    h_ok = horas[horas >= 0].dropna()

    contactados = int(df["primera_llamada"].notna().sum())
    visitas = int(df["visita_presencial"].notna().sum()) \
        if "visita_presencial" in df.columns else 0

    agendadas = realizadas = 0
    ag_por: dict[str, set] = {}
    ok_por: dict[str, set] = {}
    try:
        t = kommo.tareas()
        ids = set(df["id"])
        tl = t[(t["entidad"] == "leads") & (t["entidad_id"].isin(ids))]
        agendadas = int(tl["entidad_id"].nunique())
        realizadas = int(tl[tl["completada"].astype(bool)]["entidad_id"].nunique())
        # el mismo conteo, repartido por asesor, para el desglose del clic
        dueno = dict(zip(df["id"], df["responsable"].astype(str)))
        for _, fi in tl.iterrows():
            k_ = dueno.get(fi["entidad_id"])
            if k_ is None:
                continue
            ag_por.setdefault(k_, set()).add(fi["entidad_id"])
            if bool(fi["completada"]):
                ok_por.setdefault(k_, set()).add(fi["entidad_id"])
    except Exception:  # noqa: BLE001 — sin tareas el KPI se declara, no rompe
        agendadas = realizadas = 0

    ventas_ax = None
    propios = None
    propios_de = 0
    ax_agendas = ax_visitas = None
    ax_con = 0
    ax_ag_por: dict[str, int] = {}
    ax_vis_por: dict[str, int] = {}
    ax_fuera = [0, 0]
    try:
        from . import ingest
        s = ingest.fetch_axion_entity("Sale", None, 5000)
        s = s[s["status"] == "Vendido"]
        if asesor:
            s = s[s["advisor"].map(lambda x: _misma_persona(x, asesor))]
        f = s["date"].astype(str)
        cr = pd.to_datetime(df["creado"], errors="coerce").dropna()
        a = anio if anio else (int(cr.dt.year.max()) if len(cr) else None)
        if anio is None and mes is None:
            ventas_ax = int(len(s))          # histórico contra histórico
            pref = None
        else:
            pref = f"{a}-{mes:02d}" if mes else str(a)
            ventas_ax = int((f.str.startswith(pref)).sum())

        adv = ingest.fetch_axion_entity("Advisor", None, 500)
        MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio",
                 "julio", "agosto", "septiembre", "octubre", "noviembre",
                 "diciembre"]
        sel = [MESES[mes - 1]] if mes else MESES
        tot = 0
        for _, r in adv.iterrows():
            o = r.get("own_leads_monthly")
            if not isinstance(o, dict):
                continue
            if asesor and not _misma_persona(r.get("name"), asesor):
                continue
            # en el histórico se suman todos los años que el asesor tenga
            anios = [str(a)] if a else list(o.keys())
            d = {}
            for y in anios:
                for k, vv in (o.get(y) or {}).items():
                    d[k] = d.get(k, 0) + int(vv or 0)
            v = sum(int(d.get(k) or 0) for k in sel)
            if v:
                propios_de += 1
            tot += v
        propios = tot

        nombres_k = df["responsable"].astype(str).value_counts().to_dict()
        ax_agendas = ax_visitas = 0
        for _, r in adv.iterrows():
            md = r.get("monthly_data")
            if not isinstance(md, dict):
                continue
            nom_ax = r.get("name")
            if asesor and not _misma_persona(nom_ax, asesor):
                continue
            anios_m = [str(a)] if a else list(md.keys())
            ag = vi = 0
            hay = False
            for y in anios_m:
                for mk, mv in (md.get(y) or {}).items():
                    en_sel = mk in sel or (mk == "setiembre" and "septiembre" in sel)
                    if en_sel and isinstance(mv, dict):
                        hay = True
                        ag += int(mv.get("agendas") or 0)
                        vi += int(mv.get("visitas") or 0)
            if not hay:
                continue
            ax_con += 1
            ax_agendas += ag
            ax_visitas += vi
            cands = [k for k in nombres_k if _misma_persona(nom_ax, k)]
            if cands:
                dest = max(cands, key=lambda k: nombres_k[k])
                ax_ag_por[dest] = ax_ag_por.get(dest, 0) + ag
                ax_vis_por[dest] = ax_vis_por.get(dest, 0) + vi
            else:
                ax_fuera[0] += ag
                ax_fuera[1] += vi
    except Exception:  # noqa: BLE001
        pass

    por_ase: dict[str, dict] = {}
    for k_, idx in df.groupby("responsable", dropna=False).groups.items():
        sel_ = df.index.isin(idx)
        h_ = horas[sel_ & (horas >= 0)].dropna()
        por_ase[str(k_)] = {
            "leads": int(sel_.sum()),
            "contactados": int((sel_ & df["primera_llamada"].notna()).sum()),
            "visitas": ax_vis_por.get(str(k_), 0),
            "resp_min": (round(float(h_.median()) * 60, 1) if len(h_) else None),
            "agendadas": ax_ag_por.get(str(k_), 0),
            "realizadas": ax_vis_por.get(str(k_), 0),
            "calificados": int((sel_ & etapa.isin(ETAPAS_CALIFICADO)).sum()),
        }

    def desg(titulo, cols, clave):
        """Una tabla por asesor: rótulo, y las columnas que el KPI usa."""
        filas = []
        for nom in sorted(por_ase, key=lambda x: -por_ase[x]["leads"]):
            fila = clave(nom, por_ase[nom])
            if fila is not None:
                filas.append(fila)
        return {"titulo": titulo, "columnas": cols, "filas": filas}

    def pct(num, den):
        return round(100.0 * num / den, 1) if den else None

    F = []

    def kpi(nombre, formula, valor, unidad, detalle, falta=None, alcance=None,
            desglose=None):
        F.append({"kpi": nombre, "formula": formula, "valor": valor,
                  "unidad": unidad, "detalle": detalle,
                  "falta": falta, "alcance": alcance, "desglose": desglose})

    kpi("Ventas cerradas", "N° de operaciones", ventas_ax, "n",
        "contratos firmados en AXION",
        alcance="AXION, no el VENDIDO del CRM: son poblaciones distintas")
    kpi("Leads generados (propios)", "N° de consultas", propios, "n",
        f"cargados por {propios_de} asesores en AXION",
        alcance="solo los asesores que llenan «leads propios» en AXION")
    kpi("Leads generados (marketing)", "N° de consultas",
        (n - propios) if propios is not None else None, "n",
        "total menos los propios",
        alcance="por diferencia: queda inflado con los propios sin cargar")
    kpi("Total leads", "Total N° de consultas", n, "n",
        "creados en el período · Kommo",
        desglose=desg("Leads por asesor", ["Asesor", "Leads"],
                      lambda nom, d: [nom, d["leads"]]))
    calif = int(etapa.isin(ETAPAS_CALIFICADO).sum())
    kpi("Leads calificados",
        "Leads en Seguimiento, Visita, Pre cierre o Vendido ÷ Leads × 100",
        pct(calif, n), "%",
        f"{calif} de {n} leads en Seguimiento, Visita, Pre cierre o Vendido",
        alcance="la etapa es donde está el lead HOY: el que llegó a Visita y "
                "después pasó a Desestimado ya no cuenta",
        desglose=desg("Calificados por asesor",
                      ["Asesor", "Leads", "Calificados", "%"],
                      lambda nom, d: [nom, d["leads"], d["calificados"],
                                      pct(d["calificados"], d["leads"])]))
    kpi("% Contactabilidad", "Contactados ÷ Leads × 100",
        pct(contactados, n), "%", f"{contactados} de {n} con primera llamada",
        desglose=desg("Contactados por asesor",
                      ["Asesor", "Leads", "Contactados", "%"],
                      lambda nom, d: [nom, d["leads"], d["contactados"],
                                      pct(d["contactados"], d["leads"])]))
    kpi("Tiempo de primera respuesta", "Minutos desde lead hasta contacto",
        (round(float(h_ok.median()) * 60, 1) if len(h_ok) else None), "min",
        "mediana, no promedio",
        alcance="un lead atendido meses después mueve el promedio de todo "
                "el equipo; la mediana no",
        desglose=desg("Mediana por asesor", ["Asesor", "Leads", "Minutos"],
                      lambda nom, d: ([nom, d["leads"], d["resp_min"]]
                                      if d["resp_min"] is not None else None)))
    d_vis = desg("Visitas concretadas por asesor · AXION",
                 ["Asesor", "Leads", "Visitas", "%"],
                 lambda nom, d: [nom, d["leads"], d["visitas"],
                                 pct(d["visitas"], d["leads"])])
    d_cit = desg("Visitas por asesor · AXION",
                 ["Asesor", "Agendadas", "Concretadas", "%"],
                 lambda nom, d: ([nom, d["agendadas"], d["realizadas"],
                                  pct(d["realizadas"], d["agendadas"])]
                                 if d["agendadas"] else None))
    if ax_fuera[0] or ax_fuera[1]:
        sin_u = "(vendedores de AXION sin usuario en Kommo)"
        d_vis["filas"].append([sin_u, None, ax_fuera[1], None])
        d_cit["filas"].append([sin_u, ax_fuera[0], ax_fuera[1],
                               pct(ax_fuera[1], ax_fuera[0])])
    if ax_visitas is None:
        falta_ax = "no se pudo leer el módulo Asesores de AXION"
    elif ax_con == 0:
        falta_ax = ("ningún asesor cargó visitas en AXION para este período · "
                    "Comercial, módulo Asesores")
    else:
        falta_ax = None
    kpi("% Lead → Visita", "Visitas ÷ Leads × 100",
        None if falta_ax else pct(ax_visitas, n), "%",
        None if falta_ax else
        f"{ax_visitas} visitas concretadas en AXION sobre {n} leads de Kommo",
        falta=falta_ax,
        alcance=f"visitas del módulo Asesores de AXION, cargadas por {ax_con} asesores",
        desglose=None if falta_ax else d_vis)
    kpi("% Visitas realizadas", "Visitas concretadas ÷ visitas agendadas",
        None if falta_ax else pct(ax_visitas, ax_agendas), "%",
        None if falta_ax else f"{ax_visitas} de {ax_agendas} visitas agendadas · AXION",
        falta=falta_ax,
        alcance=f"módulo Asesores de AXION, cargado por {ax_con} asesores",
        desglose=None if falta_ax else d_cit)
    kpi("% Lead → Venta", "Ventas ÷ Leads × 100",
        pct(ventas_ax, n) if ventas_ax is not None else None, "%",
        (f"{ventas_ax} contratos de AXION sobre {n} leads del CRM"
         if ventas_ax is not None else None),
        alcance="numerador de AXION, denominador de Kommo")

    ventas_por: dict[str, int] = {}
    propios_por: dict[str, int] = {}
    try:
        from . import ingest as _ing

        nombres = list(por_ase)

        def _dueno(nombre_ax):
            cand = [nom for nom in nombres if _misma_persona(nombre_ax, nom)]
            if not cand:
                return None
            wa = {w for w in _palabras_nombre(nombre_ax) if len(w) >= 4}
            return max(cand, key=lambda nom: (
                por_ase[nom]["leads"],
                len(wa & {w for w in _palabras_nombre(nom) if len(w) >= 4})))

        s2 = _ing.fetch_axion_entity("Sale", None, 5000)
        s2 = s2[s2["status"] == "Vendido"]
        f2 = s2["date"].astype(str)
        if not (anio is None and mes is None):
            aa = anio if anio else int(pd.to_datetime(
                df["creado"], errors="coerce").dropna().dt.year.max())
            s2 = s2[f2.str.startswith(f"{aa}-{mes:02d}" if mes else str(aa))]
        for _, rr in s2.iterrows():
            nom = _dueno(rr.get("advisor"))
            if nom is not None:
                ventas_por[nom] = ventas_por.get(nom, 0) + 1
        adv2 = _ing.fetch_axion_entity("Advisor", None, 500)
        MES2 = ["enero", "febrero", "marzo", "abril", "mayo", "junio",
                "julio", "agosto", "septiembre", "octubre", "noviembre",
                "diciembre"]
        sel2 = [MES2[mes - 1]] if mes else MES2
        for _, rr in adv2.iterrows():
            o = rr.get("own_leads_monthly")
            if not isinstance(o, dict):
                continue
            dest = _dueno(rr.get("name"))
            if dest is None:
                continue
            acum = 0
            for y, dd in o.items():
                if anio and y != str(anio):
                    continue
                acum += sum(int((dd or {}).get(k) or 0) for k in sel2)
            if acum:
                propios_por[dest] = propios_por.get(dest, 0) + acum
    except Exception:  # noqa: BLE001
        pass

    piezas = []
    for nom, d in sorted(por_ase.items(), key=lambda x: -x[1]["leads"]):
        piezas.append({
            "asesor": nom, "leads": d["leads"],
            "contactados": d["contactados"], "visitas": d["visitas"],
            "resp_min": d["resp_min"], "agendadas": d["agendadas"],
            "realizadas": d["realizadas"],
            "calificados": d.get("calificados", 0),
            "ventas": ventas_por.get(nom, 0),
            "propios": propios_por.get(nom, 0),
        })

    fuera = {
        "ventas": (ventas_ax or 0) - sum(x["ventas"] for x in piezas),
        "propios": (propios or 0) - sum(x["propios"] for x in piezas),
    }
    return {"hay": True, "kpis": F, "leads": n, "por_asesor": piezas,
            "fuera_del_crm": fuera}


def hoja(mes: int | None = None, anio: int | None = None) -> dict:
    """Todo lo de la hoja, en una sola lectura del CRM (la caché la comparte)."""
    clave = ("hoja", mes, anio)
    if clave in _CACHE:
        return _CACHE[clave]
    try:
        kommo.leads()
    except Exception as e:  # noqa: BLE001
        return {"disponible": False, "mes": mes, "anio": anio,
                "error": f"{type(e).__name__}: {str(e)[:70]}"}
    _CACHE[clave] = _armar_hoja(mes, anio)
    return _CACHE[clave]


def _armar_hoja(mes: int | None, anio: int | None) -> dict:
    return {
        "disponible": True,
        "mes": mes,
        "anio": anio,
        "atencion": atencion_global(mes, anio),
        "responsables": por_responsable(mes, anio),
        "genero": genero(mes, anio),
        "campanas": campanas(mes, anio),
        "etapas": etapas(mes, anio),
        "proyectos": proyectos(mes, anio),
        "extras": cortes_extra(mes, anio),
        "cuando": {"dias": por_dia(mes, anio), "horas": por_hora(mes, anio)},
        "atencion_etiquetas": atencion_por_etiqueta(mes, anio),
        "embudo": embudo_decision(mes, anio),
        # LOS DOCE KPI DE VENTAS del cuadro del jefe de comercial.
        "kpis_ventas": kpis_ventas(mes, anio),
        "kpis_asesor": kpis_asesor(mes, anio),
    }


def filas_leads_concept() -> list[dict]:
    """Una fila por lead del embudo CONCEPT, mismas columnas y misma regla de."""
    try:
        df = kommo.leads(kommo.EMBUDO_CONCEPT)
    except kommo.KommoNoResponde:
        return []
    return _filas_de_df(df)


def hoja_concept() -> dict:
    try:
        df = kommo.leads(kommo.EMBUDO_CONCEPT)
    except kommo.KommoNoResponde:
        return {"disponible": False}
    if df.empty:
        return {"disponible": False}

    f = pd.to_datetime(df["creado"], errors="coerce").dropna()
    meses = f.dt.to_period("M").value_counts().sort_index()

    horas = _atencion(df)
    negativos = int((horas < 0).sum())
    horas = horas[horas >= 0]

    return {
        "disponible": True,
        "total": int(len(df)),
        "etapas": _conteo(df, "etapa"),
        "responsables": _conteo(df, "responsable"),
        "campanas": _conteo(df, "campana"),
        "proyectos": _conteo(df, "proyecto"),
        "meses": [{"k": str(k), "n": int(v)} for k, v in meses.items()],
        "desde": f.min().strftime("%Y-%m-%d") if len(f) else None,
        "hasta": f.max().strftime("%Y-%m-%d") if len(f) else None,
        "atencion": {
            "con_llamada": int(horas.notna().sum()),
            "promedio_h": (float(horas.mean())
                           if horas.notna().any() else None),
            "mediana_h": (float(horas.median())
                          if horas.notna().any() else None),
            "llamada_antes_de_crear": negativos,
        },
        "filas": filas_leads_concept(),
    }
