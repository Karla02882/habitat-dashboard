"""Lectura estructural de un Excel de Habitat. Sin interpretar nada."""
from __future__ import annotations

import hashlib
import pickle
import re
import time
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
CRUDOS = RAIZ / "data" / "raw_exports"

# Los cuatro reportes financieros no son tablas: son pares concepto/monto.
TITULOS_REPORTE = ("ESTADO DE RESULTADOS", "SITUACION FINANCIERA",
                   "FLUJO DE EFECTIVO", "FLUJOS DE EFECTIVO",
                   "CAMBIOS EN EL PATRIMONIO", "ESTADOS FINANCIEROS")

RE_RUC = re.compile(r"R\.?U\.?C\.?\s*:?\s*(\d{8,11})")
_MESES = (r"ENERO|FEBRERO|MARZO|ABRIL|MAYO|JUNIO|JULIO|AGOSTO|SETIEMBRE"
          r"|SEPTIEMBRE|OCTUBRE|NOVIEMBRE|DICIEMBRE")
RE_PERIODO = re.compile(
    r"(Al\s+\d{1,2}\s+de\s+\w+\s+del?\s+\d{4}"
    r"|(?:ACUMULADO\s+)?AL\s+MES\s+DE\s+\w+"
    r"|DEL\s*:?\s*\d{1,2}/\d{1,2}\s+AL\s*:?\s*\d{1,2}/\d{1,2}"
    r"|PERIODO\s*:?\s*(?:" + _MESES + r")?\s*\d{4}"
    r"|EJERCICIO\s*:?\s*\d{4}"
    r"|MES\s+DE\s+(?:" + _MESES + r")\s*\d{0,4}"
    r"|(?:" + _MESES + r")\s+\d{4})", re.IGNORECASE)
RE_RAZON = re.compile(r"RAZ[ÓO]N\s+SOCIAL\s*:\s*(.+)", re.IGNORECASE)
RE_NO_EMPRESA = re.compile(
    r"^(FORMATO|EJERCICIO|PERIODO|R\.?U\.?C|APELLIDOS)", re.IGNORECASE)


@dataclass
class Hoja:
    """Una hoja leída, con lo que se sabe de ella y sin nada decidido."""
    archivo: str
    hoja: str
    forma: str                      # "tabla" · "reporte" · "sin forma de tabla"
    empresa: str | None
    ruc: str | None
    periodo: str | None
    titulo: str | None
    fila_encabezado: int | None     # 1-based, como lo muestra Excel
    datos: pd.DataFrame = field(default_factory=pd.DataFrame)
    crudo: pd.DataFrame = field(default_factory=pd.DataFrame)

    def __repr__(self) -> str:                     # pragma: no cover
        return (f"<Hoja {self.archivo}/{self.hoja} {self.forma} "
                f"{len(self.datos)} filas · {self.periodo}>")


def texto(v) -> str:
    return "" if pd.isna(v) else str(v).strip()


def es_numero(v) -> bool:
    if isinstance(v, bool) or pd.isna(v):
        return False
    if isinstance(v, (int, float)):
        return True
    try:
        float(str(v).replace(",", ""))
        return True
    except (TypeError, ValueError):
        return False


def normalizar(s: str) -> str:
    """Sin tildes, sin espacios repetidos, en mayúsculas. Para COMPARAR, nunca."""
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s).strip().upper()


def membrete(df: pd.DataFrame) -> dict:
    """Empresa, RUC, período y título, leídos de las primeras nueve filas."""
    cab = [texto(v) for _, fila in df.head(9).iterrows() for v in fila if texto(v)]
    ruc = next((m.group(1) for t in cab if (m := RE_RUC.search(t))), None)
    periodo = next((m.group(1).strip() for t in cab if (m := RE_PERIODO.search(t))), None)
    empresa = next((m.group(1).strip() for t in cab if (m := RE_RAZON.search(t))), None)
    if not empresa:
        empresa = next((t for t in cab
                        if not RE_RUC.search(t) and not RE_PERIODO.search(t)
                        and not RE_NO_EMPRESA.match(t)
                        and len(t) > 4 and not t.isdigit()), None)
    titulo = next((t for t in cab if any(k in t.upper() for k in TITULOS_REPORTE)
                   or any(k in t.upper() for k in
                          ("LIBRO", "REGISTRO", "PLAN DE CUENTAS", "ANALISIS",
                           "BALANCE"))), None)
    return {"empresa": empresa, "ruc": ruc, "periodo": periodo, "titulo": titulo}


def fila_encabezado(df: pd.DataFrame) -> int | None:
    """En qué fila (0-based) están los rótulos de las columnas."""
    LARGO_MAXIMO_ROTULO = 30

    def _es_rotulo(v) -> bool:
        if isinstance(v, pd.Timestamp) or not texto(v) or es_numero(v):
            return False
        return len(texto(v)) <= LARGO_MAXIMO_ROTULO

    candidatos = []
    for i in range(min(20, max(1, len(df)))):
        fila = df.iloc[i]
        if any(isinstance(v, pd.Timestamp) for v in fila):
            continue
        llenas = sum(1 for v in fila if texto(v))
        textos = sum(1 for v in fila if _es_rotulo(v))
        if llenas < 2 or textos < 2:
            continue
        if textos < 4:
            siguientes = sorted(sum(1 for v in df.iloc[j] if texto(v))
                                for j in range(i + 1, min(i + 7, len(df))))
            if not siguientes or siguientes[len(siguientes) // 2] < max(2, llenas // 3):
                continue
        candidatos.append((textos, -i, i, llenas))
    if not candidatos:
        return None

    def _ancho_del_cuerpo(i: int) -> float:
        anchos = [sum(1 for v in df.iloc[j] if texto(v))
                  for j in range(i + 1, min(i + 12, len(df)))]
        anchos = [a for a in anchos if a >= 2]
        return sorted(anchos)[len(anchos) // 2] if anchos else 0.0

    encajan = []
    for textos, neg_i, i, llenas in candidatos:
        cuerpo = _ancho_del_cuerpo(i)
        if not cuerpo:
            continue
        if llenas > cuerpo * 2:
            continue
        encajan.append((textos, neg_i, i))
    return max(encajan)[2] if encajan else max(candidatos)[2]


def _fila_encabezado_viejo(df: pd.DataFrame) -> int | None:
    """Se conserva solo para comparar contra el criterio anterior si hace."""
    for i in range(min(15, max(1, len(df)))):
        fila = df.iloc[i]
        llenas = sum(1 for v in fila if texto(v))
        textos = sum(1 for v in fila if texto(v) and not es_numero(v))
        if textos >= 4:
            return i
        if llenas < 2 or textos < 2:
            continue
        siguientes = sorted(sum(1 for v in df.iloc[j] if texto(v))
                            for j in range(i + 1, min(i + 7, len(df))))
        if siguientes and siguientes[len(siguientes) // 2] >= max(2, llenas // 3):
            return i
    return None


def _columnas(fila) -> list[str]:
    """Nombres de columna. ContaSis repite `FECHA` y `MONTO` en la misma hoja."""
    cols, vistos = [], {}
    for k, v in enumerate(fila):
        nombre = texto(v) or f"col{k}"
        if nombre in vistos:
            vistos[nombre] += 1
            nombre = f"{nombre} ({vistos[nombre]})"
        else:
            vistos[nombre] = 1
        cols.append(nombre)
    return cols


def leer_tabla(crudo: pd.DataFrame, i: int, archivo: str, hoja: str) -> pd.DataFrame:
    """El detalle de una hoja con forma de tabla, con TODO adentro."""
    cuerpo = crudo.iloc[i + 1:].copy()
    filas_excel = [n + 1 for n in cuerpo.index]     # Excel cuenta desde 1
    cuerpo.columns = _columnas(crudo.iloc[i])
    cuerpo = cuerpo.dropna(axis=1, how="all")
    cuerpo["_fila"] = filas_excel
    cuerpo = cuerpo[cuerpo.drop(columns=["_fila"]).notna().any(axis=1)]

    datos = cuerpo.drop(columns=["_fila"])
    COLS_DEL_ROTULO = 4
    LARGO_MAXIMO_ROTULO_TOTAL = 30

    def _dice_total(v) -> bool:
        t = texto(v).upper()
        return "TOTAL" in t and len(t) <= LARGO_MAXIMO_ROTULO_TOTAL

    izq = datos.iloc[:, :COLS_DEL_ROTULO] if datos.shape[1] else datos
    es_total = izq.map(_dice_total).any(axis=1)
    solo_una = datos.apply(lambda f: sum(1 for v in f if texto(v)) == 1, axis=1)
    cuerpo["_clase"] = "detalle"
    cuerpo.loc[solo_una, "_clase"] = "separador"
    cuerpo.loc[es_total, "_clase"] = "total"        # total gana sobre separador
    cuerpo["_archivo"] = archivo
    cuerpo["_hoja"] = hoja
    orden = ["_archivo", "_hoja", "_fila", "_clase"]
    return cuerpo[orden + [c for c in cuerpo.columns if c not in orden]] \
        .reset_index(drop=True)


def leer_reporte(crudo: pd.DataFrame, archivo: str, hoja: str) -> pd.DataFrame:
    """Las partidas de un estado financiero: cada rótulo con su monto."""
    inicio = next((k for k, (_, fila) in enumerate(crudo.iterrows())
                   if any(es_numero(v) for v in fila)), 0)
    filas = []
    for k, (idx, fila) in enumerate(crudo.iloc[inicio:].iterrows()):
        vals = list(fila)
        for c, v in enumerate(vals):
            rot = texto(v)
            if not rot or es_numero(v) or len(rot) < 3:
                continue
            monto = next((vals[j] for j in range(c + 1, min(c + 3, len(vals)))
                          if es_numero(vals[j])), None)
            filas.append({
                "_archivo": archivo, "_hoja": hoja, "_fila": idx + 1,
                "_columna": c, "_bloque": 1 if c <= len(vals) // 2 else 2,
                "partida": rot,
                "monto": float(str(monto).replace(",", "")) if monto is not None else None,
            })
    return pd.DataFrame(filas)


def leer_html_disfrazado(ruta: Path) -> Hoja | None:
    """Los exports POR PÁGINA de AXION bajan un HTML con extensión `.xls`."""
    cabeza = ruta.read_bytes()[:512].lstrip().lower()
    if not cabeza.startswith(b"<"):
        return None
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(ruta.read_text(encoding="utf-8", errors="replace"),
                         "html.parser")
    tabla = soup.find("table")
    archivo = str(ruta.relative_to(CRUDOS)) if CRUDOS in ruta.parents else ruta.name
    etiqueta = soup.find("x:name")
    nombre_hoja = etiqueta.get_text(strip=True) if etiqueta else "tabla HTML"
    if tabla is None:
        return Hoja(archivo=archivo, hoja=nombre_hoja,
                    forma="HTML sin ninguna tabla adentro", empresa=None,
                    ruc=None, periodo=None, titulo=None, fila_encabezado=None)

    filas = tabla.find_all("tr")
    cols = [c.get_text(strip=True) for c in filas[0].find_all(["th", "td"])]
    datos = [[c.get_text(strip=True) for c in f.find_all(["th", "td"])]
             for f in filas[1:]]
    df = pd.DataFrame(datos, columns=_columnas(cols))
    df.insert(0, "_clase", "detalle")
    df.insert(0, "_fila", range(2, len(df) + 2))
    df.insert(0, "_hoja", nombre_hoja)
    df.insert(0, "_archivo", archivo)
    df.loc[df.drop(columns=["_archivo", "_hoja", "_fila", "_clase"])
           .map(lambda v: "TOTAL" in texto(v).upper()).any(axis=1), "_clase"] = "total"
    return Hoja(archivo=archivo, hoja=nombre_hoja, forma="tabla (HTML)",
                empresa=None, ruc=None, periodo=None,
                titulo=nombre_hoja, fila_encabezado=1, datos=df,
                crudo=pd.DataFrame(datos))


def leer_hoja(ruta: Path, hoja: str) -> Hoja:
    """Una hoja, leída y clasificada por su forma. No interpreta su contenido."""
    archivo = str(ruta.relative_to(CRUDOS)) if CRUDOS in ruta.parents else ruta.name
    crudo = pd.read_excel(ruta, sheet_name=hoja, header=None)
    meta = membrete(crudo)
    base = dict(archivo=archivo, hoja=hoja, crudo=crudo, **meta)

    if any(k in f"{meta['titulo'] or ''} {ruta.name}".upper()
           for k in TITULOS_REPORTE):
        return Hoja(**base, forma="reporte", fila_encabezado=None,
                    datos=leer_reporte(crudo, archivo, hoja))

    i = fila_encabezado(crudo)
    if i is None:
        return Hoja(**base, forma="sin forma de tabla", fila_encabezado=None)
    return Hoja(**base, forma="tabla", fila_encabezado=i + 1,
                datos=leer_tabla(crudo, i, archivo, hoja))


def leer_archivo(ruta: Path) -> list[Hoja]:
    """Todas las hojas de un archivo. Si no es un Excel binario, se intenta."""
    disfrazado = leer_html_disfrazado(ruta)
    if disfrazado is not None:
        return [disfrazado]
    return [leer_hoja(ruta, h) for h in pd.ExcelFile(ruta).sheet_names]


_HOJAS: dict = {}


def _firma(carpeta: Path) -> tuple:
    """Qué archivos hay y cuándo se tocaron por última vez."""
    return tuple(sorted(
        (str(f), f.stat().st_mtime_ns, f.stat().st_size)
        for f in carpeta.rglob("*.xls*") if not f.name.startswith("~$")))


def limpiar_cache() -> None:
    """Olvida las hojas leídas. Para pruebas y para forzar una relectura."""
    _HOJAS.clear()


_DISCO = Path(__file__).resolve().parent.parent / "data" / "cache_excels"


def _ruta_cache(clave: tuple) -> Path:
    return _DISCO / (hashlib.sha256(
        repr(clave).encode("utf-8")).hexdigest()[:32] + ".pkl")


def leer_carpeta(carpeta: Path) -> list[Hoja]:
    """Todas las hojas de todos los Excels de una carpeta y sus subcarpetas."""
    try:
        clave = (str(carpeta), _firma(carpeta))
    except OSError:
        clave = None
    if clave is not None and clave in _HOJAS:
        return list(_HOJAS[clave])
    if clave is not None:
        f = _ruta_cache(clave)
        if f.exists():
            try:
                guardado = pickle.loads(f.read_bytes())
                _HOJAS[clave] = guardado
                return list(guardado)
            except Exception:  # noqa: BLE001
                try:
                    f.unlink()
                except OSError:
                    pass
    hojas: list[Hoja] = []
    for f in sorted(carpeta.rglob("*.xls*"), key=lambda p: str(p).lower()):
        if f.name.startswith("~$"):
            continue
        try:
            hojas += leer_archivo(f)
        except Exception as e:  # noqa: BLE001
            hojas.append(Hoja(archivo=str(f.relative_to(CRUDOS)), hoja="—",
                              forma=f"no se pudo leer: {type(e).__name__}",
                              empresa=None, ruc=None, periodo=None,
                              titulo=None, fila_encabezado=None))
    if clave is not None:
        _HOJAS[clave] = list(hojas)
        try:
            _DISCO.mkdir(parents=True, exist_ok=True)
            _ruta_cache(clave).write_bytes(pickle.dumps(hojas, protocol=5))
            vigente = _ruta_cache(clave).name
            for v in _DISCO.glob("*.pkl"):
                if v.name != vigente and v.stat().st_mtime < time.time() - 86400:
                    v.unlink(missing_ok=True)
        except Exception:  # noqa: BLE001 — no poder cachear no rompe nada
            pass
    return hojas
