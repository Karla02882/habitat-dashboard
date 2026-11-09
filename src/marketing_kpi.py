"""MARKETING · las dos fuentes de sus indicadores, en un solo módulo."""
from __future__ import annotations

import pathlib

import pandas as pd

from . import ingest, periodo


CARPETA = pathlib.Path(__file__).resolve().parent.parent / "data" / "raw_exports" / "marketing"

_MES = ["", "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
        "agosto", "setiembre", "octubre", "noviembre", "diciembre"]

_CACHE: dict[str, object] = {}


def archivo() -> pathlib.Path | None:
    """El libro MÁS RECIENTE de la carpeta, no uno con nombre fijo."""
    if not CARPETA.exists():
        return None
    libros = [p for p in CARPETA.glob("*.xls*") if not p.name.startswith("~$")]
    if not libros:
        return None
    return max(libros, key=lambda p: p.stat().st_mtime)


def _bloques(hoja: pd.DataFrame) -> list[dict]:
    """Las series de una ficha, leídas de su encabezado real."""
    fila_enc = None
    for i in range(min(len(hoja), 20)):
        vals = [str(v).strip().lower() for v in hoja.iloc[i] if pd.notna(v)]
        if "fecha" in vals:
            fila_enc = i
            break
    if fila_enc is None:
        return []

    enc = hoja.iloc[fila_enc]
    cols_fecha = [j for j in range(hoja.shape[1])
                  if str(enc.iloc[j]).strip().lower() == "fecha"]
    out = []
    for k, cf in enumerate(cols_fecha):
        hasta = cols_fecha[k + 1] if k + 1 < len(cols_fecha) else hoja.shape[1]
        fechas = {}
        for i in range(fila_enc + 1, len(hoja)):
            v = hoja.iat[i, cf]
            if hasattr(v, "year") and hasattr(v, "month"):
                fechas[i] = (int(v.year), int(v.month))
        if not fechas:
            continue
        anios = {a for a, _ in fechas.values()}
        anio = max(anios)
        for j in range(cf + 1, hasta):
            rot = str(enc.iloc[j]).strip() if pd.notna(enc.iloc[j]) else ""
            if not rot or rot.lower() == "nan":
                continue
            meses = {}
            for i, (a, m) in fechas.items():
                if a != anio:
                    continue
                x = pd.to_numeric(hoja.iat[i, j], errors="coerce")
                if pd.notna(x):
                    meses[m] = float(x)
            meses = _sin_cola_de_ceros(meses, anio)
            if meses:
                out.append({"rotulo": rot, "anio": anio,
                            "n": len(meses), "meses": meses})
    return out


def _sin_cola_de_ceros(meses: dict[int, float], anio: int) -> dict[int, float]:
    """Los ceros del final del año en curso NO son dato: son la planilla."""
    if anio != periodo.ANIO or not meses:
        return meses
    ks = sorted(meses)
    if all(meses[k] == 0 for k in ks):
        return meses
    corte = len(ks)
    while corte > 0 and meses[ks[corte - 1]] == 0:
        corte -= 1
    return {k: meses[k] for k in ks[:corte]}


def _campo(hoja: pd.DataFrame, etiqueta: str) -> str:
    """El valor escrito a la derecha de una etiqueta de la ficha. Devuelve."""
    for i in range(min(len(hoja), 15)):
        for j in range(hoja.shape[1]):
            v = hoja.iat[i, j]
            if pd.notna(v) and str(v).strip().lower().startswith(etiqueta.lower()):
                for j2 in range(j + 1, hoja.shape[1]):
                    v2 = hoja.iat[i, j2]
                    if pd.notna(v2) and str(v2).strip():
                        return str(v2).strip()
    return ""


def fichas() -> list[dict]:
    """Las fichas del libro de Marketing, una por hoja `KPI_xx`."""
    if "fichas" in _CACHE:
        return list(_CACHE["fichas"])          # type: ignore[arg-type]
    ruta = archivo()
    if ruta is None:
        _CACHE["fichas"] = []
        return []
    try:
        xl = pd.ExcelFile(ruta)
    except Exception:  # noqa: BLE001
        _CACHE["fichas"] = []
        return []
    out = []
    for h in xl.sheet_names:
        if not h.upper().startswith("KPI_"):
            continue
        try:
            d = pd.read_excel(ruta, sheet_name=h, header=None)
        except Exception:  # noqa: BLE001
            continue
        series = _bloques(d)
        nombre = ""
        for i in range(min(len(d), 6)):
            for v in d.iloc[i]:
                if pd.notna(v) and len(str(v).strip()) > 6 \
                        and "ficha de indicador" not in str(v).lower():
                    nombre = str(v).strip()
                    break
            if nombre:
                break
        out.append({
            "hoja": h,
            "nombre": nombre or h,
            "formula": _campo(d, "Fórmula"),
            "fuente": _campo(d, "Fuente"),
            "unidad": _campo(d, "Unidad"),
            "archivo": ruta.name,
            "series": series,
        })
    _CACHE["fichas"] = out
    return list(out)


def corte() -> dict:
    """Hasta qué mes llega el libro, y qué fichas se salen de ese corte."""
    fs = fichas()
    if not fs:
        return {"hay": False}
    ruta = archivo()
    hoy = pd.Timestamp.today()
    anio = periodo.ANIO

    ultimos, sin_anio = {}, []
    for f in fs:
        ms = [m for s in f["series"] if s["anio"] == anio
              for m in s["meses"]]
        if ms:
            ultimos[f["hoja"]] = max(ms)
        else:
            sin_anio.append(f["hoja"])
    if not ultimos:
        return {"hay": False}
    frec: dict[int, int] = {}
    for m in ultimos.values():
        frec[m] = frec.get(m, 0) + 1
    tope = max(frec.values())
    hasta = min(m for m, c in frec.items() if c == tope)

    return {
        "hay": True,
        "archivo": ruta.name if ruta else "—",
        "subido": (pd.Timestamp(ruta.stat().st_mtime, unit="s")
                   .strftime("%d-%b-%Y") if ruta else "—"),
        "indicadores": len(fs),
        "anio": anio,
        "mes": hoy.month if hoy.year == anio else 12,
        "hasta": _MES[hasta],
        "hasta_n": hasta,
        "adelantadas": [h for h, m in ultimos.items() if m > hasta],
        "atrasadas": [h for h, m in ultimos.items() if m < hasta],
        "sin_anio": sin_anio,
    }


def contraste_leads() -> dict:
    """Los leads del Excel contra los del CRM, año por año."""
    fs = {f["hoja"]: f for f in fichas()}
    f1 = fs.get("KPI_01")
    if not f1:
        return {"hay": False}
    excel = {}
    for s in f1["series"]:
        if "lead" in s["rotulo"].lower():
            excel[s["anio"]] = int(round(sum(s["meses"].values())))
    if not excel:
        return {"hay": False}
    crm = {}
    try:
        from . import kommo
        L = kommo.leads()
        f = pd.to_datetime(L["creado"], errors="coerce")
        for a in excel:
            crm[a] = int(f.dt.year.eq(a).sum())
    except Exception:  # noqa: BLE001
        crm = {}
    return {"hay": True, "excel": excel, "crm": crm}


_INDICADORES = {
    "I1":  {"agrega": "suma",   "unidad": "S/.", "persp": "Finanzas",
            "objetivo": "Cuánto ingresó por las ventas que Marketing originó"},
    "I2":  {"agrega": "media",  "unidad": "S/.", "persp": "Clientes",
            "objetivo": "Cuánto cuesta conseguir un interesado"},
    "I3":  {"agrega": "suma",   "unidad": "N°",  "persp": "Clientes",
            "objetivo": "Cuántas campañas se lanzaron"},
    "I4":  {"agrega": "suma",   "unidad": "S/.", "persp": "Clientes",
            "objetivo": "Cuánto se invirtió en publicidad"},
    "I6":  {"agrega": "suma",   "unidad": "N°",  "persp": "Clientes",
            "objetivo": "A cuánta gente llegaron las publicaciones"},
    "I7":  {"agrega": "ultimo", "unidad": "N°",  "persp": "Clientes",
            "objetivo": "Cuánta audiencia propia tiene la marca"},
    "I8":  {"agrega": "suma",   "unidad": "N°",  "persp": "Clientes",
            "objetivo": "Cuánto se publicó en Facebook"},
    "I9":  {"agrega": "suma",   "unidad": "N°",  "persp": "Clientes",
            "objetivo": "Cuánto se publicó en Instagram"},
    "I10": {"agrega": "suma",   "unidad": "N°",  "persp": "Clientes",
            "objetivo": "Cuánto se publicó en TikTok"},
}


def crudo() -> pd.DataFrame:
    """Las filas de `MarketingKPI` tal como llegan. Caché por corrida."""
    if "axion" in _CACHE:
        return _CACHE["axion"].copy()          # type: ignore[union-attr]
    try:
        df = ingest._fetch_base44_entity(
            "AXION_API_BASE_URL", "AXION_API_KEY", "MarketingKPI",
            ["MarketingKPI"], limit=5000)
    except Exception as e:  # noqa: BLE001
        ingest.DEGRADADAS["MarketingKPI"] = (
            f"{type(e).__name__}: la tabla de indicadores de marketing no "
            f"responde")
        df = pd.DataFrame()
    if not df.empty:
        if "is_sample" in df.columns:
            df = df[~df["is_sample"].fillna(False).astype(bool)]
        for c in ("value", "meta", "year", "month"):
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce")
        df = df[df["year"].eq(periodo.ANIO)]
    _CACHE["axion"] = df
    return df.copy()


def _nombre(df: pd.DataFrame, codigo: str) -> str:
    """El rótulo que escribió Habitat, no uno inventado acá."""
    g = df[df["kpi_code"] == codigo]
    n = str(g["kpi_name"].iloc[0]).strip() if len(g) else codigo
    return n or codigo


def _meta(g: pd.DataFrame) -> float | None:
    """La meta, y CERO NO ES UNA META ACÁ."""
    m = pd.to_numeric(g["meta"], errors="coerce").dropna()
    m = m[m > 0]
    return float(m.iloc[0]) if len(m) else None


def _desglose(g: pd.DataFrame) -> list[dict]:
    """El desglose del período —plataforma, formato o tipo de inversión."""
    acc: dict[str, dict] = {}
    for b in g["breakdown"]:
        for e in (b or []) if isinstance(b, list) else []:
            k = str(e.get("dimension") or "").strip()
            if not k:
                continue
            v = pd.to_numeric(e.get("value"), errors="coerce")
            d = acc.setdefault(k, {"dimension": k, "valor": 0.0,
                                   "tipo": str(e.get("dimension_type") or "")})
            d["valor"] += 0.0 if pd.isna(v) else float(v)
    return sorted(acc.values(), key=lambda x: -x["valor"])


def _desglose_ultimo(g: pd.DataFrame) -> list[dict]:
    """El desglose del ÚLTIMO mes con dato. Para los stocks."""
    if not len(g):
        return []
    ult = g.sort_values("month").iloc[-1]
    out = []
    for e in (ult["breakdown"] or []) if isinstance(ult["breakdown"], list) else []:
        v = pd.to_numeric(e.get("value"), errors="coerce")
        out.append({"dimension": str(e.get("dimension") or "").strip(),
                    "valor": 0.0 if pd.isna(v) else float(v),
                    "tipo": str(e.get("dimension_type") or "")})
    return sorted(out, key=lambda x: -x["valor"])


def indicadores(mes: int | None = None) -> list[dict]:
    """Los nueve de AXION, con su cifra del período, su meta y su desglose."""
    df = crudo()
    if df.empty:
        return []
    try:
        _pa, m = periodo.partes(mes)
        if _pa != periodo.ANIO:
            m = None
    except (TypeError, ValueError):
        m = None

    out = []
    for cod, cfg in _INDICADORES.items():
        todos = df[df["kpi_code"] == cod].sort_values("month")
        if not len(todos):
            continue
        g = todos[todos["month"].eq(m)] if m else todos
        vals = pd.to_numeric(g["value"], errors="coerce").dropna()
        if not len(vals):
            valor = None
        elif cfg["agrega"] == "suma":
            valor = float(vals.sum())
        elif cfg["agrega"] == "media":
            valor = float(vals.mean())
        else:
            valor = float(g.sort_values("month")["value"].iloc[-1])

        meses = {int(r.month): float(r.value) for _, r in todos.iterrows()
                 if pd.notna(r.month) and pd.notna(r.value)}
        out.append({
            "codigo": cod,
            "indicador": _nombre(df, cod),
            "objetivo": cfg["objetivo"],
            "unidad": cfg["unidad"],
            "perspectiva": cfg["persp"],
            "agrega": cfg["agrega"],
            "valor": valor,
            "meta": _meta(todos),
            "meses": meses,
            "n_meses": len(vals),
            "desglose": (_desglose_ultimo(g) if cfg["agrega"] == "ultimo"
                         else _desglose(g)),
        })
    return out


def cobertura() -> dict:
    """Hasta dónde llega la carga en AXION. Lo usa el Alcance de cada."""
    df = crudo()
    if df.empty:
        return {"hay": False, "meses": [], "hasta": None, "filas": 0}
    ms = sorted({int(x) for x in df["month"].dropna()})
    completos = [x for x in ms
                 if df[df["month"].eq(x)]["kpi_code"].nunique() >= len(_INDICADORES)]
    return {"hay": True, "meses": ms, "completos": completos,
            "hasta": max(completos) if completos else None,
            "parciales": [x for x in ms if x not in completos],
            "filas": int(len(df)),
            "indicadores": int(df["kpi_code"].nunique())}


def avisos() -> list[dict]:
    """Lo que la data de Habitat NO cierra. Se detecta y se reporta; no se."""
    df = crudo()
    if df.empty:
        return []
    out = []

    g7 = df[df["kpi_code"] == "I7"].sort_values("month")
    if len(g7) >= 2:
        v = pd.to_numeric(g7["value"], errors="coerce")
        salto = v.diff().max()
        i = int(v.diff().idxmax()) if pd.notna(salto) else None
        mes_salto = int(g7.loc[i, "month"]) if i is not None else None
        prev = (float(v.loc[:i].iloc[-2])
                if i is not None and len(v.loc[:i]) > 1 else None)
        if pd.notna(salto) and prev:
            out.append({
                "area": "Marketing",
                "titulo": "«Nuevos Seguidores» guarda el total de seguidores, "
                          "no los que se ganaron",
                "detalle":
                    f"En {_MES[mes_salto]} la cifra pasa de {prev:,.0f} a "
                    f"{prev + salto:,.0f}: un salto de {salto:,.0f} en un mes. "
                    f"No son seguidores ganados — es TikTok apareciendo por "
                    f"primera vez con su base entera. La ficha del Excel dice "
                    f"«Nuevos Seguidores = Total de Seguidores Actuales − …», "
                    f"y en la hoja KPI_07 la columna de al lado trae la resta "
                    f"real: 134, 88, 41, 42, 57 y 30 por mes. En 2025 esa "
                    f"misma hoja sí cargaba los nuevos (76, 94, 62, 66, 71, "
                    f"53). Entre un año y otro cambió qué se anota en la "
                    f"columna. El tablero muestra lo cargado y no lo "
                    f"reinterpreta: decidir cuál de las dos definiciones vale "
                    f"es de Marketing.",
                "grave": True})

    g4 = df[df["kpi_code"] == "I4"]
    m4 = _meta(g4)
    if m4:
        v4 = pd.to_numeric(g4["value"], errors="coerce").dropna()
        out.append({
            "area": "Marketing",
            "titulo": "La meta de inversión publicitaria es mensual, no anual",
            "detalle":
                f"AXION guarda S/ {m4:,.2f} como meta en cada uno de los "
                f"{len(v4)} meses cargados. Comparar el acumulado del año "
                f"(S/ {float(v4.sum()):,.2f}) contra S/ {m4:,.2f} diría que se "
                f"pasó {float(v4.sum()) / m4:.1f} veces, y no es cierto: "
                f"{int((v4 > m4).sum())} de los {len(v4)} meses la superaron. "
                f"El tablero compara mes contra mes y en el acumulado no "
                f"muestra meta.",
            "grave": False})

    # 3 · `meta_type` se contradice entre meses del mismo indicador.
    mezcla = []
    for cod, g in df.groupby("kpi_code"):
        tipos = sorted({str(x).strip() for x in g["meta_type"].dropna()
                        if str(x).strip()})
        if len(tipos) > 1:
            mezcla.append((cod, _nombre(df, cod), tipos))
    if mezcla:
        det = " · ".join(f"{n} ({'/'.join(t)})" for _, n, t in mezcla[:4])
        out.append({
            "area": "Marketing",
            "titulo": f"{len(mezcla)} indicadores cambian de criterio entre un "
                      f"mes y otro",
            "detalle":
                f"El campo que dice si conviene subir o bajar (`meta_type`) "
                f"viene distinto en meses del MISMO indicador: {det}. Mientras "
                f"se contradiga, el tablero muestra la distancia a la meta "
                f"pero no dice si cumple: con la mitad de los meses diciendo "
                f"«mayor es mejor» y la otra mitad «sin meta», cualquier "
                f"semáforo sería una moneda al aire.",
            "grave": False})

    # 4 · El Excel y AXION no dicen lo mismo en todos los meses.
    dif = diferencias_con_excel()
    if dif.get("hay") and dif["difieren"]:
        det = " · ".join(
            f"{d['indicador']} en {_MES[d['mes']]}: el Excel dice "
            f"{d['excel']:,.2f} y AXION {d['axion']:,.2f}"
            for d in dif["filas"][:4])
        out.append({
            "area": "Marketing",
            "titulo": f"El Excel y AXION difieren en {dif['difieren']} de "
                      f"{dif['comparados']} pares (indicador, mes)",
            "detalle":
                f"{det}. Los dos los carga Marketing, así que uno de los dos "
                f"quedó viejo. El tablero no elige: la hoja Marketing muestra "
                f"el Excel y el Scorecard muestra AXION, cada uno diciendo de "
                f"dónde sale. Cuál manda lo decide Marketing.",
            "grave": False})

    return out


def diferencias_con_excel() -> dict:
    """Dónde NO coinciden las dos cargas de Marketing."""
    fs = {f["hoja"]: f for f in fichas()}
    df = crudo()
    if df.empty or not fs:
        return {"hay": False}
    QUE = {
        "I1":  ("KPI_01", ["ingreso hbr"]),
        "I2":  ("KPI_02", ["costo de lead"]),
        "I3":  ("KPI_03", ["campañas"]),
        "I4":  ("KPI_04", ["total"]),
        "I6":  ("KPI_06", ["facebook", "instagram", "tik tok"]),
        "I7":  ("KPI_07", ["facebook", "instagram", "tik tok"]),
        "I8":  ("KPI_08", ["post", "videos", "reel"]),
        "I9":  ("KPI_09", ["post", "videos", "reel"]),
        "I10": ("KPI_10", ["valores"]),
    }
    filas, comparados = [], 0
    for cod, (hoja, claves) in QUE.items():
        f = fs.get(hoja)
        g = df[df["kpi_code"] == cod]
        if not f or not len(g):
            continue
        # las series del año en curso cuyo rótulo empieza por una de las claves
        ser = [s for s in f["series"] if s["anio"] == periodo.ANIO
               and any(s["rotulo"].strip().lower().startswith(k)
                       for k in claves)]
        if not ser:
            continue
        exc: dict[int, float] = {}
        for s in ser:
            for m, v in s["meses"].items():
                exc[m] = exc.get(m, 0.0) + v
        for _, r in g.iterrows():
            m = int(r["month"])
            if m not in exc:
                continue
            comparados += 1
            a = float(r["value"])
            if abs(exc[m] - a) >= 0.02:
                filas.append({"codigo": cod, "indicador": _nombre(df, cod),
                              "mes": m, "excel": exc[m], "axion": a,
                              "dif": a - exc[m]})
    return {"hay": True, "comparados": comparados, "difieren": len(filas),
            "filas": sorted(filas, key=lambda x: -abs(x["dif"]))}


def contra_axion() -> dict:
    df = crudo()
    g = df[df["kpi_code"] == "I1"] if not df.empty else df
    if df.empty or not len(g):
        return {"hay": False}
    sale = ingest.fetch_axion_entity("Sale", None, 5000)
    v = sale[sale["status"] == "Vendido"].copy()
    f = pd.to_datetime(v["date"], errors="coerce")
    v = v[f.dt.year.eq(periodo.ANIO)]
    fm = pd.to_datetime(v["date"], errors="coerce").dt.month
    precio = pd.to_numeric(v["sale_price"], errors="coerce").fillna(0)

    filas, difieren = [], 0
    for _, r in g.sort_values("month").iterrows():
        m = int(r["month"])
        sel = fm.eq(m)
        base = float(precio[sel].sum())
        km = float(r["value"])
        d = km - base
        if abs(d) >= 0.01:
            difieren += 1
        filas.append({"mes": m, "nombre": _MES[m], "marketing": km,
                      "axion": base, "ventas": int(sel.sum()), "dif": d})
    return {"hay": True, "filas": filas, "difieren": difieren,
            "meses": len(filas)}
