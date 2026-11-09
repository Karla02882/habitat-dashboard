"""EL CRONOGRAMA DE OBRA."""
from __future__ import annotations

import datetime as dt
import re
import tempfile
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
CARPETA = RAIZ / "data" / "raw_exports" / "cronogramas"

COLUMNAS = ["N°", "WBS", "Nivel", "Tarea", "Tipo", "Inicio", "Fin",
            "Duración (días)", "Restricción", "Fecha restricción"]

ESTADOS = ("En curso", "Vencida", "Por arrancar", "Sin programar")


def _f(v) -> str:
    """Una fecha a dd/mm/aaaa, o cadena vacía."""
    if v is None or pd.isna(v):
        return ""
    try:
        return pd.Timestamp(v).strftime("%d/%m/%Y")
    except Exception:  # noqa: BLE001
        return ""


def _num(v):
    if v is None or pd.isna(v):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _txt(v) -> str:
    s = "" if v is None or pd.isna(v) else str(v).strip()
    return "" if s.lower() in ("nan", "none", "na") else s


COLS_DRIVE = ["ID", "Name", "Duration", "Start", "Finish", "Outline Level"]
_DIAS_EN = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def _fecha_project(v):
    s = _txt(v)
    if not s or s.upper() in ("NA", "N/A"):
        return pd.NaT
    for d in _DIAS_EN:
        if s.startswith(d):
            s = s[len(d):].strip()
            break
    return pd.to_datetime(s, format="%m/%d/%y", errors="coerce")


def _dias_project(v):
    s = _txt(v).lower().replace("days", "").replace("day", "")
    s = s.replace("edays", "").replace("?", "").strip()
    return _num(s)


def _traducir_drive(d: pd.DataFrame) -> pd.DataFrame:
    """Task_Table de Project -> las columnas que espera `_una_obra`."""
    d = d.copy()
    niveles = pd.to_numeric(d["Outline Level"], errors="coerce").fillna(1).astype(int)
    # WBS: se cuenta el hermano dentro de cada nivel, reiniciando al bajar
    contador: dict[int, int] = {}
    wbs: list[str] = []
    for niv in niveles:
        contador[niv] = contador.get(niv, 0) + 1
        for mayor in [k for k in contador if k > niv]:
            contador.pop(mayor)
        wbs.append(".".join(str(contador.get(k, 1)) for k in range(1, niv + 1)))
    sig = list(niveles[1:]) + [0]
    tipo = ["Resumen" if s > n else "Tarea" for n, s in zip(niveles, sig)]
    return pd.DataFrame({
        "N°": d["ID"],
        "WBS": wbs,
        "Nivel": niveles,
        "Tarea": d["Name"].fillna("").astype(str),
        "Tipo": tipo,
        "Inicio": [_fecha_project(v) for v in d["Start"]],
        "Fin": [_fecha_project(v) for v in d["Finish"]],
        "Duración (días)": [_dias_project(v) for v in d["Duration"]],
        "Restricción": "",
        "Fecha restricción": "",
    })


def _leer(ruta: Path):
    """El Excel, con el motor que sirva y la hoja que tenga las tareas."""
    ultimo = None
    for motor in ("openpyxl", "xlrd"):
        try:
            x = pd.ExcelFile(ruta, engine=motor)
        except Exception as e:  # noqa: BLE001
            ultimo = e
            continue
        try:
            hoja = next((h for h in x.sheet_names
                         if h.strip().upper().startswith("TASK")), x.sheet_names[0])
            return x.parse(hoja)
        finally:
            try:
                x.close()
            except Exception:  # noqa: BLE001
                pass
    if ultimo is not None:
        raise ultimo
    return None


def _una_obra(ruta: Path, hoy: pd.Timestamp) -> dict | None:
    """Un Excel → una obra con sus capítulos. None si el archivo no sirve."""
    try:
        d = _leer(ruta)
    except Exception as e:  # noqa: BLE001
        return {"obra": ruta.stem, "error": f"no se pudo abrir: {type(e).__name__}"}
    if d is None:
        return {"obra": ruta.stem, "error": "no se pudo abrir con ningún motor"}

    # LAS DOS FORMAS: el Excel convertido a mano y el export del Drive.
    if all(c in d.columns for c in COLS_DRIVE):
        d = _traducir_drive(d)
    faltan = [c for c in COLUMNAS if c not in d.columns]
    if faltan:
        return {"obra": ruta.stem, "error": "le faltan columnas: " + ", ".join(faltan[:4])}

    d = d.copy()
    d["Inicio"] = pd.to_datetime(d["Inicio"], errors="coerce")
    d["Fin"] = pd.to_datetime(d["Fin"], errors="coerce")
    d["Tarea"] = d["Tarea"].fillna("").astype(str)
    ini_proy = d["Inicio"].min()

    def estado(r) -> str:
        if pd.isna(r["Inicio"]) or pd.isna(r["Fin"]):
            return "Sin programar"
        if r["Inicio"] == ini_proy:
            return "Sin programar"
        if r["Fin"] < hoy:
            return "Vencida"
        if r["Inicio"] <= hoy <= r["Fin"]:
            return "En curso"
        return "Por arrancar"

    def fila(r) -> dict:
        return {
            "wbs": _txt(r["WBS"]),
            "nombre": r["Tarea"].strip(),
            "ini": _f(r["Inicio"]),
            "fin": _f(r["Fin"]),
            "dias": _num(r["Duración (días)"]),
            "estado": estado(r),
            "rest": _txt(r["Restricción"]),
            "restf": _f(r["Fecha restricción"]),
        }

    caps: list[dict] = []
    actual: dict | None = None
    esp = ""
    for _, r in d.iterrows():
        try:
            niv = int(r["Nivel"])
        except (TypeError, ValueError):
            continue
        if niv == 1:
            esp = r["Tarea"].strip()
            continue
        if niv < 1:
            continue
        if niv == 2:
            actual = {"nombre": r["Tarea"].strip() or "(sin nombre)",
                      "esp": esp, "wbs": _txt(r["WBS"]), "partidas": []}
            caps.append(actual)
            if _txt(r["Tipo"]) != "Resumen":
                actual["partidas"].append(fila(r))
                actual = None
        elif actual is not None:
            actual["partidas"].append(fila(r))

    caps = [c for c in caps if c["partidas"]]
    esps = {c.get("esp") for c in caps if c.get("esp")}
    if len(esps) < 2:
        for c in caps:
            c.pop("esp", None)
    for c in caps:
        es = [p["estado"] for p in c["partidas"]]
        c["cuenta"] = {k: es.count(k) for k in ESTADOS}
        con = [p for p in c["partidas"] if p["estado"] != "Sin programar"]
        c["desde"] = min((p["ini"] for p in con), key=_orden) if con else ""
        c["hasta"] = max((p["fin"] for p in con), key=_orden) if con else ""

    partidas = [p for c in caps for p in c["partidas"]]
    if not partidas:
        return {"obra": ruta.stem, "error": "el archivo no trae partidas"}

    fechas = [x for x in d["Inicio"].tolist() + d["Fin"].tolist() if not pd.isna(x)]
    return {
        "obra": ruta.stem.upper(),
        "caps": caps,
        "n": len(partidas),
        "capn": len(caps),
        "tot": {k: sum(1 for p in partidas if p["estado"] == k) for k in ESTADOS},
        "rango": (f"{min(fechas).strftime('%d/%m/%Y')} a {max(fechas).strftime('%d/%m/%Y')}"
                  if fechas else ""),
    }


def _orden(f: str):
    """dd/mm/aaaa se ordena mal como texto; esto lo vuelve comparable."""
    try:
        d, m, a = f.split("/")
        return (a, m, d)
    except Exception:  # noqa: BLE001
        return ("", "", "")


def _del_drive(tmp: Path) -> list[Path]:
    """Baja los cronogramas del Drive a `tmp` y devuelve sus rutas."""
    try:
        from . import drive
    except ImportError:
        return []
    if not drive.hay_credencial():
        return []
    try:
        carpeta = drive.subcarpeta("CRONOGRAMA")
        if not carpeta:
            return []
        archivos = _recorrer(drive, carpeta, [])
    except Exception:  # noqa: BLE001 — el Drive caído no tumba la hoja
        return []
    archivos.sort(key=lambda a: -len(a["ruta"]))
    salida, vistas, pals = [], set(), []
    for a in archivos:
        obra = a["obra"]
        if obra in vistas:
            continue
        mias = _palabras(obra)
        if not a["ruta"] and any(mias and mias <= otras for otras in pals):
            continue
        vistas.add(obra)
        pals.append(mias)
        ext = ".xls" if a["tipo"] == "application/vnd.ms-excel" else ".xlsx"
        destino = tmp / (obra + ext)
        if drive.bajar(a, destino) is not None:
            salida.append(destino)
    return salida


def _recorrer(drive, carpeta: str, ruta: list[str]) -> list[dict]:
    """Los Excel de la carpeta y de todas sus subcarpetas."""
    out = []
    for a in drive.listar(carpeta):
        if a["carpeta"]:
            out += _recorrer(drive, a["id"], ruta + [a["nombre"]])
            continue
        if a["nombre"].lower().endswith(".mpp"):
            continue
        out.append({**a, "ruta": ruta,
                    "obra": _obra_de_ruta(ruta) or _nombre_obra(a["nombre"])})
    return out


def _palabras(nombre: str) -> set:
    """Las palabras que distinguen una obra, sin las que tienen todas."""
    vacias = {"RESIDENCIAL", "PROYECTO", "CASA", "OFICINA", "DE", "DEL", "Y",
              "URBANIZACION", "URBANIZACIÓN", "·", "-"}
    return {x for x in re.split(r"[^A-Z0-9ÑÁÉÍÓÚ]+", nombre.upper())
            if x and x not in vacias}


def _obra_de_ruta(ruta: list[str]) -> str:
    partes = []
    for x in ruta:
        y = re.sub(r"^\s*PROYECTO\s+", "", x.strip(), flags=re.I).strip()
        if y:
            partes.append(y.upper())
    return " · ".join(partes)


def _nombre_obra(archivo: str) -> str:
    """El nombre de la obra que hay adentro del nombre del archivo."""
    s = archivo.rsplit(".", 1)[0]
    for basura in ("Diagrama Gantt", "diagrama gantt", "DIAGRAMA GANTT",
                   "Cronograma", "CRONOGRAMA"):
        s = s.replace(basura, " ")
    s = re.sub(r"\d{1,2}[-/]\d{1,2}[-/]\d{2,4}", " ", s)
    s = " ".join(s.split()).strip(" -_")
    return (s or archivo.rsplit(".", 1)[0]).upper()


def calcular(hoy: dt.date | None = None) -> dict:
    """Los cronogramas publicados: los del Drive y los de la carpeta local."""
    h = pd.Timestamp(hoy or dt.date.today())

    with tempfile.TemporaryDirectory(prefix="cron_", ignore_cleanup_errors=True) as tmp:
        deldrive = _del_drive(Path(tmp))
        locales = (sorted(x for x in CARPETA.glob("*.xlsx")
                          if not x.name.startswith("~$")) if CARPETA.exists() else [])
        vistos = [_palabras(_nombre_obra(a.name)) for a in deldrive]
        archivos = list(deldrive)
        for a in locales:
            mias = _palabras(_nombre_obra(a.name))
            if mias and any(mias <= otras for otras in vistos):
                continue
            archivos.append(a)
        if not archivos:
            return {"hay": False,
                    "motivo": "todavía no hay ningún cronograma publicado"}

        obras, fallidos = [], []
        for a in archivos:
            r = _una_obra(a, h)
            if r is None:
                continue
            if r.get("error"):
                fallidos.append(f"{r['obra']}: {r['error']}")
            else:
                r["obra"] = _nombre_obra(a.name)
                r["origen"] = "Drive" if a in deldrive else "archivo local"
                obras.append(r)

    if not obras:
        return {"hay": False,
                "motivo": "ningún cronograma se pudo leer",
                "fallidos": fallidos}

    return {
        "hay": True,
        "obras": obras,
        "corte": h.strftime("%d/%m/%Y"),
        "en30": (h + pd.Timedelta(days=30)).strftime("%d/%m/%Y"),
        # lo que no se pudo leer se declara, no desaparece
        "fallidos": fallidos,
    }
