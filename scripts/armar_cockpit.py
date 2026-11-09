"""Junta las ocho hojas en UN SOLO archivo: `design/cockpit.html`."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DESTINO = RAIZ / "design"

# id → (archivo, nombre). El orden es el de la barra.
HOJAS = [
    ("hoy", "hoy", "Resumen"),
    ("caja", "caja", "Caja"),
    ("comercial-d", "comercial-d", "Ventas"),
    ("gasto-d", "gasto-d", "Gasto"),
    ("obras-d", "obras-d", "Obras"),
    ("compras", "compras", "Compras"),
    ("contasis", "contasis", "ContaSis"),
    ("ratios-axion", "ratios-axion", "Ratios AXION"),
    ("comparativo", "comparativo", "Comparativo"),
    ("ventas-kpi", "ventas-kpi", "Ventas KPI"),
    ("asesores", "asesores", "Asesores KPI"),
    ("crm", "crm", "CRM"),
    ("crm-informe", "crm-informe", "Informe"),
    ("informe-quincenal", "informe-quincenal", "Informe mensual"),
    ("marketing", "marketing", "Marketing"),
    ("cabidas", "cabidas", "Cabidas"),
    ("bitacora", "bitacora", "Bitácora"),
    ("contratos", "contratos", "Contratos"),
    ("cotizaciones", "cotizaciones", "Cotizaciones"),
    ("atencion", "atencion", "Atención al cliente"),
    ("cronogramas", "cronogramas", "Cronogramas"),
    ("stock", "stock", "Stock"),
    ("cambios-stock", "cambios-stock", "Cambios de stock"),
    ("clientes", "clientes", "Clientes"),
    ("morosos", "morosos", "Morosos"),
    ("observaciones", "observaciones", "Observaciones"),
    ("estado", "estado", "Estado"),
]


PLANTILLA = """<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Cockpit · Habitat Control</title>
<meta name="theme-color" content="#163180">
<link rel="manifest" href="/manifest.webmanifest">
<link rel="icon" href="/icono-192.png" sizes="192x192" type="image/png">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="Habitat">
<link rel="stylesheet" href="cockpit.css?v=__V__">
</head>
<body>
<div class="envoltorio">

  <header class="cabecera">
    <div class="cabecera-fila">
      <img class="logo" src="data:image/png;base64,__LOGO__"
           alt="Habitat Inmobiliaria">
      <div class="hoja-nombre" id="hoja-nombre">Cockpit</div>
      <div class="cabecera-der" id="cab-der"
           data-version="__VERSION__">cargando…</div>
      <button class="btn-act" id="btn-act" title="Actualizar ahora" aria-label="Actualizar ahora">Actualizar ahora</button>
      <button class="btn-instalar" id="btn-instalar" type="button" title="Instalar la app" aria-label="Instalar la app" hidden>Instalar app</button>
      <a class="salir" id="salir" href="/salir" hidden>Salir</a>
    </div>
  </header>

  <div class="barra-fija">
    <nav class="nav" id="nav"></nav>
    <nav class="subnav" id="subnav" style="display:none"></nav>

    <button class="filtros-toggle" id="filtros-toggle" type="button" aria-expanded="false"
            aria-controls="filtros">
      <span class="ft-rotulo">Filtros</span>
      <span class="ft-resumen" id="ft-resumen"></span>
      <span class="ft-flecha" aria-hidden="true">▾</span>
    </button>
    <div class="filtros" id="filtros">
      <div class="filtro filtro-fecha">
        <label for="f-mes">Período</label>
        <select id="f-periodo" class="periodo-oculto" aria-hidden="true" tabindex="-1"></select>
        <div class="pills-anio" id="pills-anio"></div>
        <select id="f-mes"></select>
      </div>
      <div class="filtro" id="caja-rs"><label for="f-rs">Razón social</label><select id="f-rs"></select></div>
      <div class="filtro" id="caja-obra"><label for="f-obra">Proyecto</label><select id="f-obra"></select></div>
      <div class="filtro" id="caja-tipo" style="display:none"><label for="f-tipo">Tipo de obra</label><select id="f-tipo"></select></div>
      <div class="filtro" id="caja-area" style="display:none"><label for="f-area">Área</label><select id="f-area"></select></div>
      <div class="filtro" id="caja-asesor" style="display:none"><label for="f-asesor">Vendedor</label><select id="f-asesor"></select></div>
      <div class="filtro" id="caja-banco" style="display:none"><label for="f-banco">Banco</label><select id="f-banco"></select></div>
      <div class="filtro" id="caja-fuente" style="display:none"><label for="f-fuente">Fuente</label><select id="f-fuente"></select></div>
      <div class="filtro" id="caja-fechas" style="display:none"><label for="f-desde">Fechas</label><span class="par-fechas"><input type="date" id="f-desde" aria-label="Desde"><input type="date" id="f-hasta" aria-label="Hasta"><button type="button" id="f-fechas-limpiar" title="Quitar el rango">&times;</button></span></div>
    </div>
  </div>

  <div class="fuentes" id="fuentes"></div>

  <div id="cargando">leyendo <code>tablero_datos.json</code>…</div>
  <div id="hoja" hidden></div>

  <p class="pie-pagina" hidden>Cockpit de Rentabilidad · Habitat Inmobiliaria ·
    <span id="pie-grupos">los grupos</span> en un solo archivo<br>
    Las cifras salen de AXION y de Kommo: las lee <code>generar_tablero.py</code>
    y las deja en <code>tablero_datos.json</code>, con la fecha que dice
    «DATOS AL» arriba. Si el motor publica una lectura más nueva, esta
    pantalla lo avisa; no se recarga sola.</p>
</div>

<script>
"use strict";
window.REGISTRO = {};
__HOJAS__
</script>
<script src="cockpit.js?v=__V__"></script>
</body>
</html>
"""

ENVOLTORIO = """
(function () {
  var __anterior = window.HOJA;
%(js)s
  window.REGISTRO["%(id)s"] = window.HOJA;
  window.HOJA = __anterior;
})();
"""


def _js_de(archivo: str) -> str:
    """Saca el bloque de JavaScript de una hoja ya armada."""
    s = (DESTINO / f"{archivo}.html").read_text(encoding="utf-8")
    m = re.search(r"<script>\n(.*?)\n</script>", s, re.S)
    if not m:
        raise SystemExit(f"no encontré el <script> de {archivo}.html")
    return m.group(1)


def _logo_b64() -> str:
    """El logo REAL de Habitat, embebido en base64."""
    import base64
    f = RAIZ / "assets" / "logo-white.png"
    return base64.b64encode(f.read_bytes()).decode() if f.exists() else ""


def _version_cockpit() -> str:
    """La versión del cockpit, sacada de git."""
    def git(*args: str) -> str:
        try:
            r = subprocess.run(["git", *args], cwd=str(RAIZ), text=True,
                               capture_output=True, timeout=15)
            return r.stdout.strip() if r.returncode == 0 else ""
        except Exception:  # noqa: BLE001
            return ""
    n = git("rev-list", "--count", "HEAD")
    h = git("log", "-1", "--format=%h")
    f = git("log", "-1", "--format=%cd", "--date=format:%Y-%m-%d")
    if not h:
        return "sin versión"
    return f"v{n} · {h}" + (f" · {f}" if f else "")


def _version_compartidos() -> str:
    """La fecha del CSS y el JS compartidos, para colgarla como ?v=."""
    d = DESTINO
    t = max((d / "cockpit.css").stat().st_mtime, (d / "cockpit.js").stat().st_mtime)
    return str(int(t))


def main() -> int:
    trozos, faltan = [], []
    for hid, archivo, nombre in HOJAS:
        p = DESTINO / f"{archivo}.html"
        if not p.exists():
            faltan.append(archivo)
            continue
        js = _js_de(archivo)
        # dos espacios de sangría para que se lea dentro del envoltorio
        js = "\n".join("  " + ln if ln.strip() else ln for ln in js.splitlines())
        trozos.append(ENVOLTORIO % {"nombre": nombre, "id": hid, "js": js})
        print(f"  {nombre:<14} {len(js) // 1024:>3} KB")

    if faltan:
        print(f"\n  FALTAN: {', '.join(faltan)}")

    html = (PLANTILLA
            .replace("__HOJAS__", "\n".join(trozos))
            .replace("__V__", _version_compartidos())
            .replace("__VERSION__", _version_cockpit())
            .replace("__LOGO__", _logo_b64()))
    out = DESTINO / "cockpit.html"
    out.write_text(html, encoding="utf-8")
    print(f"\n  {out.name} · {out.stat().st_size // 1024} KB · {len(trozos)} hojas")
    print(f"  http://localhost:8777/design/{out.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
