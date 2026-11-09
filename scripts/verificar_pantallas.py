# -*- coding: utf-8 -*-
"""Recorre TODOS los estados de una hoja y comprueba lo que la vista afirma."""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import time

RAIZ = pathlib.Path(__file__).resolve().parent.parent
CHROME = pathlib.Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")

PUERTO_PROPIO = 8799
URL = f"http://localhost:{PUERTO_PROPIO}"


def _responde_sin_clave(url: str) -> bool:
    """¿Hay un servidor ahi que entregue el cockpit sin pedir credenciales?."""
    import urllib.error
    import urllib.request
    try:
        with urllib.request.urlopen(url + "/design/cockpit.html", timeout=4) as r:
            return r.status == 200
    except (urllib.error.HTTPError, urllib.error.URLError, OSError):
        return False


def _levantar_servidor():
    """Arranca `servidor.py` sin clave en `PUERTO_PROPIO`. Devuelve el proceso."""
    import os
    import time
    if _responde_sin_clave(URL):
        return None
    entorno = {
        **os.environ,
        "TABLERO_PUERTO": str(PUERTO_PROPIO),
        "TABLERO_CLAVE": "",
        "TABLERO_USUARIOS": "",
        "TABLERO_REFRESCO_MIN": "0",
        "CONTROLES_CADA_HORAS": "0",
    }
    proc = subprocess.Popen(
        [sys.executable, "-X", "utf8", str(RAIZ / "scripts" / "servidor.py")],
        cwd=str(RAIZ), env=entorno,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    for _ in range(40):                     # hasta 20 s
        if _responde_sin_clave(URL):
            return proc
        time.sleep(0.5)
    proc.terminate()
    raise RuntimeError(
        f"el barrido no pudo levantar su servidor en {URL}. Sin el no hay nada "
        f"que medir: se corta en vez de dar un verde vacio.")

HOJAS = ["hoy", "caja", "gasto-d", "compras", "contasis", "ratios-axion", "comparativo", "comercial-d", "asesores", "crm", "crm-informe", "informe-quincenal", "marketing",
         "obras-d", "cabidas", "bitacora", "contratos", "cotizaciones", "atencion",
         "cronogramas",
         "stock", "cambios-stock", "clientes", "morosos", "observaciones", "estado"]

TECNICO = re.compile(
    r"\b(sale_price|status|Sale|Credit|Installment|CxCPayment|Unit|Project|"
    r"Advisor|MovimientoGasto|Moroso|monto_cuota|monto_pagado|saldo_pendiente|"
    r"credit_id|fecha_vencimiento|real_income|marketing_source|price_per_m2|"
    r"modality)\b")

RUIDO = re.compile(
    r"externally_managed|InstallWebApp|gcm|voice_transcription|"
    r"registration_request|DEPRECATED|Fontconfig|GPU|Vulkan|dbus|"
    r"policy_logger|chrome_crashpad|DevTools listening|"
    r"os_integration|Can't perform OS|"
    r"device_event_log|usb_service|"
    r"interface_endpoint_client|rejected by interface|mojo.public|"
    r"external_registry_loader|"
    r"web_app_icon_manager|Could not write icon|load_error_reporter|"
    r"Extension error|No se pudo instalar el paquete|"
    r"disk_cache|download_db_cache|first_party_sets|Unable to create cache|"
    r"Failed to access storage|importScripts|"
    r"updater\\ipc|update_service_dialer|named pipe server process", re.I)

BARRIDO = r"""
<!doctype html><meta charset="utf-8"><title>barrido</title>
<style>html,body{margin:0}#f{width:1440px;height:2400px;border:0}</style>
<iframe id="f" src="__URL__/design/cockpit.html#__HOJA__"></iframe>
<script>
var R = [];
function limpio(s){ return String(s||"").replace(/\s+/g," ").trim(); }

function crudo(el){
  var c = el.cloneNode(true);
  c.querySelectorAll("script, style").forEach(function(e){ e.remove(); });
  c.querySelectorAll("[data-tecnico]").forEach(function(e){ e.remove(); });
  return limpio(c.textContent);
}

function sinLiterales(texto, raiz){
  [].slice.call(raiz.querySelectorAll("[data-literal]")).forEach(function(e){
    var x = limpio(e.innerText || e.textContent);
    if (!x) return;
    var k = texto.indexOf(x);
    if (k >= 0) texto = texto.slice(0, k) + " " + texto.slice(k + x.length);
  });
  return texto;
}

function recortesDe(raiz, doc){
  var malos = [];
  var vw = doc.defaultView;
  raiz.querySelectorAll("td, th, span").forEach(function(e){
    if (e.clientWidth > 0 && e.scrollWidth > e.clientWidth + 4){
      if (e.closest(".envoltura-tabla, .graf-caja, .riel-obra")) return;
      var cs = vw.getComputedStyle(e);
      if (cs.whiteSpace.indexOf("nowrap") >= 0)
        malos.push(limpio(e.textContent).slice(0, 60));
    }
  });
  return malos;
}

function foto(d, periodo, area){
  var hoja = d.getElementById("hoja") || d.body;
  var secs = [];
  hoja.querySelectorAll("section").forEach(function(s){
    var h2 = s.querySelector("h2");
    if (!h2) return;
    var cab = h2.parentNode;
    var sub = limpio(cab.textContent).replace(limpio(h2.textContent), "");
    var qs = [];
    var th = [].slice.call(s.querySelectorAll("table.datos thead th"));
    var iq = -1;
    th.forEach(function(t,i){ if (/^qui[eé]n$/i.test(limpio(t.textContent))) iq = i; });
    if (iq >= 0) s.querySelectorAll("table.datos tbody tr").forEach(function(tr){
      var td = tr.children[iq];
      if (td) qs.push(limpio(td.textContent));
    });
    secs.push({
      titulo: limpio(h2.textContent),
      sub: limpio(sub),
      quien: qs,
      filas: s.querySelectorAll("table.datos tbody tr").length
    });
  });
  var parrafos = [];
  var cand = [].slice.call(hoja.querySelectorAll("p, .linea-meta, .hallazgo"));
  cand.forEach(function(e){
    var anida = cand.some(function(o){ return o !== e && e.contains(o); });
    if (anida) return;
    var t = limpio(e.textContent);
    if (t.length > 60) parrafos.push(t);
  });
  var rec = recortesDe(hoja, d);
  if (d.documentElement.scrollWidth > d.documentElement.clientWidth + 4)
    rec.push("LA PAGINA scrollea horizontal: algo desborda el ancho");

  var etiquetas = [];
  hoja.querySelectorAll(".tarjeta, .detalle, .franja, .sol").forEach(function(cj){
    cj.querySelectorAll("p, .n, .exacta, .regla, td").forEach(function(el){
      var tx = (el.textContent || "");
      var m = tx.match(/<\/?(b|i|em|strong|span|br|div)\b[^>]*>/i);
      if (!m) return;
      var rot = cj.querySelector(".overline, h3, .k");
      etiquetas.push("«" + ((rot && rot.textContent) || "?").trim().slice(0, 46) +
        "» muestra la etiqueta " + m[0] + " ESCRITA en pantalla: al texto le falta "
        + "crudo:true, o le sobra el marcado");
    });
  });

  var mudas = [];
  hoja.querySelectorAll(".tarjeta").forEach(function(tj){
    var rot = tj.querySelector(".overline");
    var cif = tj.querySelector(".cifra-g, .cifra");
    if (!rot || !cif) return;
    var txt = (cif.textContent || "").replace(/\s+/g, " ").trim();
    if (["—", "-", "–", ""].indexOf(txt) < 0) return;
    var riel = tj.querySelector(".riel > span, .riel span[style]");
    var an = riel ? parseFloat((riel.getAttribute("style") || "").replace(/.*width:\s*/, "")) : 0;
    if (an > 0.01)
      mudas.push("«" + (rot.textContent || "").trim() + "» no muestra cifra pero su "
                 + "riel dibuja " + an.toFixed(2) + "% de ancho: el motor tenia el "
                 + "valor y la tarjeta lo perdio");
  });

  return {periodo: periodo, area: area, secciones: secs, parrafos: parrafos,
          texto: sinLiterales(limpio(hoja.innerText), hoja), crudo: crudo(hoja), recortes: rec,
          mudas: mudas, etiquetas: etiquetas};
}

function esperar(ms){ return new Promise(function(r){ setTimeout(r, ms); }); }

setTimeout(async function(){
  var w = document.getElementById("f").contentWindow, d = w.document;
  var pedida = "__HOJA__";
  var real = (w.HOJA && w.HOJA.id) ? String(w.HOJA.id) : "";
  if (pedida && real !== pedida) {
    var aviso = document.createElement("pre");
    aviso.id = "salida";
    aviso.textContent = JSON.stringify([{hoja_equivocada: real || "(ninguna)",
                                         pedida: pedida}]);
    document.body.appendChild(aviso);
    document.title = "listo";
    return;
  }
  var sp = d.getElementById("f-periodo"), sa = d.getElementById("f-area");
  var periodos = sp ? [].slice.call(sp.options).map(function(o){return o.value;}) : [""];
  var areas    = sa ? [].slice.call(sa.options).map(function(o){return o.value;}) : [""];
  if (!areas.length) areas = [""];
  for (var i = 0; i < periodos.length; i++){
    if (sp){ sp.value = periodos[i]; sp.dispatchEvent(new w.Event("change")); await esperar(320); }
    for (var j = 0; j < areas.length; j++){
      if (sa && areas[j] !== "" || (sa && areas.length > 1)){
        sa = d.getElementById("f-area");
        if (sa.options.length){
          var hay = [].slice.call(sa.options).some(function(o){return o.value === areas[j];});
          if (!hay) continue;
          sa.value = areas[j]; sa.dispatchEvent(new w.Event("change")); await esperar(260);
        }
      }
      R.push(foto(d, periodos[i], areas[j]));
    }
    if (sa){ sa = d.getElementById("f-area"); sa.value = "";
             sa.dispatchEvent(new w.Event("change")); await esperar(280); }
    var abr = [].slice.call(d.querySelectorAll("[data-abre]"));
    for (var k = 0; k < abr.length; k++){
      var el = abr[k], da = el.getAttribute("data-abre") || "";
      el.click(); await esperar(150);
      var caja = d.getElementById("det-" + da) || d.getElementById("det-ind");
      if (caja && caja.classList.contains("on")){
        var rot = [].slice.call(caja.querySelectorAll(".overline"))
                    .map(function(e){ return limpio(e.textContent); });
        var pp = [];
        caja.querySelectorAll("p, .hallazgo, .que-falta").forEach(function(e){
          var x = limpio(e.textContent); if (x.length > 60) pp.push(x); });
        R.push({periodo: periodos[i],
                area: "(abre) " + limpio(el.getAttribute("data-ind") ||
                                         el.getAttribute("data-area") || da),
                secciones: [], parrafos: pp, texto: sinLiterales(limpio(caja.innerText), caja),
                crudo: crudo(caja), rotulos: rot,
                recortes: recortesDe(caja, d)});
      }
      el.click(); await esperar(80);
    }
  }
  var pre = document.createElement("pre");
  pre.id = "salida"; pre.textContent = JSON.stringify(R);
  document.body.appendChild(pre);
  document.title = "LISTO";
}, 7000);
</script>
"""


def _chrome(harness: pathlib.Path, err: pathlib.Path, ms: int) -> str:
    perfil = pathlib.Path(tempfile.mkdtemp(prefix="barrido_"))
    try:
        out = subprocess.run(
            [str(CHROME), "--headless=new", "--disable-gpu",
             f"--user-data-dir={perfil}", "--enable-logging=stderr", "--v=0",
             f"--virtual-time-budget={ms}", "--window-size=1440,2400",
             "--dump-dom", f"{URL}/{harness.name}"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=ms / 1000 + 180)
        err.write_text(out.stderr or "", encoding="utf-8")
        return out.stdout or ""
    finally:
        _borrar_perfil(perfil)


def _borrar_perfil(perfil: pathlib.Path) -> None:
    """EL PERFIL SE BORRA DE VERDAD, O EL CONTROL LLENA EL DISCO."""
    for espera in (0.0, 0.5, 2.0):
        if espera:
            time.sleep(espera)
        shutil.rmtree(perfil, ignore_errors=True)
        if not perfil.exists():
            return
    print(f"  aviso: no se pudo borrar el perfil temporal {perfil} — "
          f"revisa {perfil.parent} por carpetas «barrido_*» acumuladas")


def _cortada(texto: str) -> list:
    malas = []
    for m in re.finditer(r"(\w{2,})(?:…|\.\.\.)", texto):
        pal = m.group(1)
        if len(pal) >= 3 and not re.search(
                r"(ar|er|ir|ado|ido|ando|iendo|ci[oó]n|dad|mente|"
                r"[aeiouáéíóúns rlyzxdj])$", pal, re.I):
            malas.append(m.group(0))
    return malas


def revisar(fotos: list) -> list:
    """Las cinco reglas, sobre cada estado. Devuelve la lista de hallazgos."""
    hall = []

    def h(estado, regla, detalle):
        hall.append({"estado": estado, "regla": regla, "detalle": detalle})

    for f in fotos:
        est = f"periodo={f['periodo'] or 'todos'} · area={f['area'] or 'todas'}"

        for s in f["secciones"]:
            if s["quien"]:
                dice = re.search(
                    r"l[oa]s? destraban? ([^·]+)$|lo destraba ([^·]+)$", s["sub"])
                if dice:
                    nom = (dice.group(1) or dice.group(2) or "")
                    nombrados = {x.strip().lower() for x in nom.split("·")
                                 if x.strip()}
                    reales = {x.strip().lower() for x in s["quien"] if x.strip()}
                    if nombrados != reales:
                        h(est, "subtitulo vs columna Quien",
                          f"{s['titulo']}: el subtitulo nombra {sorted(nombrados)} "
                          f"y la columna muestra {sorted(reales)}")
                else:
                    cuenta = re.search(r"(\d+)\s+[aá]reas?\s+l[oa]s?\s+destraban?",
                                       s["sub"])
                    if cuenta:
                        reales = {x.strip().lower() for x in s["quien"] if x.strip()}
                        if int(cuenta.group(1)) != len(reales):
                            h(est, "subtitulo vs columna Quien",
                              f"{s['titulo']}: el subtitulo dice "
                              f"{cuenta.group(1)} y la columna muestra "
                              f"{len(reales)} distintos: {sorted(reales)}")

        tot = set()
        for s in f["secciones"]:
            for x in re.findall(r"de l[oa]s (\d+) indicadores", s["sub"]):
                tot.add(int(x))
            for x in re.findall(r"^Los (\d+) indicadores", s["titulo"]):
                tot.add(int(x))
        for x in re.findall(r"de sus (\d+) indicadores", f["texto"]):
            tot.add(int(x))
        if len(tot) > 1:
            h(est, "la pantalla afirma dos totales distintos",
              f"los indicadores son {sorted(tot)} segun donde se lea")

        ps = f["parrafos"]
        for a in range(len(ps)):
            for b in range(a + 1, len(ps)):
                x, y = ps[a][:110].lower(), ps[b][:110].lower()
                if x and x == y:
                    h(est, "parrafo repetido", ps[a][:120])
                    continue
                if len(x) > 80 and (ps[a] in ps[b] or ps[b] in ps[a]):
                    h(est, "un parrafo contiene al otro", ps[a][:120])

        for c in _cortada(f["texto"]):
            h(est, "texto cortado a mitad de palabra", c)

        rot = f.get("rotulos") or []
        rep_ = {r for r in rot if rot.count(r) > 1}
        for r in sorted(rep_):
            h(est, "dos bloques con el mismo rotulo", r)

        for r_ in (f.get("recortes") or []):
            h(est, "texto que no entra en su lugar", r_)

        for m_ in (f.get("mudas") or []):
            h(est, "tarjeta sin cifra", m_)

        for e_ in (f.get("etiquetas") or []):
            h(est, "etiqueta HTML escrita en pantalla", e_)

        for t in sorted(set(TECNICO.findall(f.get("crudo") or f["texto"]))):
            h(est, "nombre de campo o tabla de AXION en pantalla", t)

    vistos, unicos = {}, []
    for x in hall:
        k = (x["regla"], x["detalle"])
        if k in vistos:
            vistos[k]["estados"].append(x["estado"])
        else:
            vistos[k] = {"regla": x["regla"], "detalle": x["detalle"],
                         "estados": [x["estado"]]}
            unicos.append(vistos[k])
    return unicos


ANCHOS = [1440, 1280, 1024, 900, 820, 390]

ARNES_ANCHO = r"""
<!doctype html><meta charset="utf-8"><title>anchos</title>
<style>html,body{margin:0}#f{border:0}</style>
<iframe id="f"></iframe><pre id="salida"></pre>
<script>
var HOJAS = __HOJAS__, W = __ANCHOS__, R = [], i = 0, j = 0;
var f = document.getElementById("f");
function paso(){
  if (i >= HOJAS.length){
    document.getElementById("salida").textContent = JSON.stringify(R);
    document.title = "LISTO"; return;
  }
  if (j >= W.length){ j = 0; i++; return paso(); }
  f.style.width = W[j] + "px"; f.style.height = "2600px";
  f.src = "__URL__/design/cockpit.html#" + HOJAS[i];
  setTimeout(function(){
    var d, w;
    try { d = f.contentDocument; w = f.contentWindow; } catch(e){ j++; return setTimeout(paso, 40); }
    var b = d.body, des = b.scrollWidth - b.clientWidth, malos = [];
    [].slice.call(d.querySelectorAll("#hoja *")).forEach(function(el){
      if (el.clientWidth > 0 &&
          el.scrollWidth - el.clientWidth > Math.max(4, el.clientWidth * 0.10)){
        var cs = w.getComputedStyle(el);
        if (cs.overflowX === "visible")
          malos.push((el.tagName.toLowerCase()) + "." +
            String(el.className || "").trim().split(/\s+/)[0] +
            " (" + el.clientWidth + "<" + el.scrollWidth + ") " +
            String(el.textContent || "").replace(/\s+/g, " ").trim().slice(0, 44));
      }
    });
    if (des > 2 || malos.length)
      R.push({hoja: HOJAS[i], ancho: W[j], desborde: des, malos: malos.slice(0, 4),
              cuantos: malos.length});
    j++; setTimeout(paso, 60);
  }, 2600);
}
setTimeout(paso, 1200);
</script>
"""


def barrer_anchos(hojas: list, ms: int = 420000) -> list:
    """Devuelve la lista de (hoja, ancho) donde la pagina no entra."""
    arnes = RAIZ / "_barrido_anchos.html"
    err = RAIZ / "_barrido_anchos_err.txt"
    arnes.write_text(
        ARNES_ANCHO.replace("__HOJAS__", json.dumps(hojas))
                   .replace("__ANCHOS__", json.dumps(ANCHOS))
                   .replace("__URL__", URL), encoding="utf-8")
    try:
        dom = _chrome(arnes, err, ms)
        m = re.search(r'<pre id="salida">(.*?)</pre>', dom, re.S)
        if not m:
            return [{"hoja": "(todas)", "ancho": 0, "desborde": -1,
                     "malos": ["el arnes de anchos no devolvio salida — "
                               "no se pudo medir"], "cuantos": 1}]
        import html as _html
        return json.loads(_html.unescape(m.group(1)) or "[]")
    finally:
        arnes.unlink(missing_ok=True)
        err.unlink(missing_ok=True)


ESPEJO = r"""
<!doctype html><meta charset="utf-8"><title>espejo</title>
<style>html,body{margin:0}#f{width:1440px;height:2400px;border:0}</style>
<iframe id="f" src="__URL__/design/cockpit.html#hoy"></iframe>
<pre id="out"></pre>
<script>
function esperar(ms){ return new Promise(function(r){ setTimeout(r, ms); }); }
function num(s){ s = String(s||"").replace(/[^0-9.\-]/g, ""); return s ? parseFloat(s) : null; }
setTimeout(async function(){
  var f = document.getElementById("f"), d = f.contentDocument, R = {ok: false};
  try {
    for (var i = 0; i < 80 && !d.querySelector('[data-abre="d-saldo"]'); i++) await esperar(500);
    var s = d.querySelector('[data-abre="d-saldo"]');
    if (!s) throw new Error("la tarjeta del dinero no aparecio");
    s.click(); await esperar(1200);
    var m = d.querySelector('[data-abre="d-mesmes"]');
    if (!m) throw new Error("falta el boton del mes a mes");
    m.click(); await esperar(1500);
    var tablas = d.querySelectorAll('#det-d-saldo table.datos, #det-d-mesmes table.datos');
    var arriba = d.querySelector('#det-d-saldo > .envoltura-tabla table.datos') || tablas[0];
    var abajo = d.querySelector('#det-d-mesmes table.datos');
    var filaTot = function (tb) {
      var rs = tb.querySelectorAll("tr.total"); return rs[rs.length - 1]; };
    var celdas = function (tr) {
      return [].slice.call(tr.querySelectorAll("td")).map(function (c) {
        var q = c.cloneNode(true);
        [].slice.call(q.querySelectorAll(".ob-sub")).forEach(function (e) { e.remove(); });
        return num(q.textContent); }); };
    var ta = celdas(filaTot(arriba)), tb = celdas(filaTot(abajo));
    var ths = [].slice.call(arriba.querySelectorAll("thead th")).map(function (t) {
      return (t.textContent || "").replace(/\s+/g, " ").trim(); });
    var col = function (re) {
      for (var j = 0; j < ths.length; j++) if (re.test(ths[j])) return j;
      return -1; };
    var iIni = col(/^Inici/i), iHoy = col(/^Hoy/i), iIng = col(/^Ingresos/i), iEgr = col(/^Egresos/i);
    if (iIni < 0 || iHoy < 0) throw new Error("no encontre las columnas «Inicio» y «Hoy» de la tabla de arriba: " + ths.join(" | "));
    var nb = tb.length - 1;    var M3 = {ENE:1, FEB:2, MAR:3, ABR:4, MAY:5, JUN:6, JUL:7, AGO:8, SET:9, SEP:9, OCT:10, NOV:11, DIC:12};
    var NOM = {enero:1, febrero:2, marzo:3, abril:4, mayo:5, junio:6, julio:7, agosto:8,
               setiembre:9, septiembre:9, octubre:10, noviembre:11, diciembre:12};
    var thsAb = [].slice.call(abajo.querySelectorAll("thead th")).map(function (t) {
      return (t.textContent || "").replace(/\s+/g, " ").trim(); });
    var mesCorte = NOM[String(ths[iIni] || "").replace(/^Inici[oó]\s*/i, "").trim().toLowerCase()];
    var iAnt = nb - 1;
    if (mesCorte) {
      var buscado = -1;
      for (var q = 0; q < thsAb.length; q++) {
        var cab = thsAb[q].toUpperCase();
        if (mesCorte === 1 ? /^31-DIC/.test(cab) : M3[cab] === mesCorte - 1) { buscado = q; break; }
      }
      if (buscado >= 0 && buscado < tb.length) iAnt = buscado;
    }
    R = {ok: true, cierre: ta[iIni], hoy: ta[iHoy],
         mesAnterior: tb[iAnt], ultimoMes: tb[nb]};
    if (iIng >= 0 && iEgr >= 0)
      R.suma = {ini: ta[iIni], ing: ta[iIng], egr: ta[iEgr], hoy: ta[iHoy]};
    var celdasMes = [].slice.call(d.querySelectorAll('#det-d-mesmes [data-abre^="cm-"]'));
    R.paneles = celdasMes.length;
    R.malos = [];
    for (var k = 0; k < celdasMes.length; k++) {
      var cel = celdasMes[k], idp = cel.getAttribute("data-abre");
      var q = cel.cloneNode(true);
      [].slice.call(q.querySelectorAll(".ob-sub")).forEach(function (e) { e.remove(); });
      var vCelda = num(q.textContent);
      cel.click(); await esperar(120);
      var pan = d.getElementById("det-" + idp);
      if (!pan || !pan.classList.contains("on")) { R.malos.push(idp + ": no abrio"); cel.click(); continue; }
      var trs = [].slice.call(pan.querySelectorAll("table.datos tr"));
      var cerro = null, cobros = null, trasp = null, salidas = null, totE = null, totS = null;
      trs.forEach(function (tr) {
        var c = tr.querySelectorAll("td"); if (!c.length) return;
        var q0 = c[0].cloneNode(true);
        [].slice.call(q0.querySelectorAll(".ob-sub")).forEach(function (e) { e.remove(); });
        var rot = (q0.textContent || "").replace(/\s+/g, " ").trim();
        if (rot === "Con cuanto cerro" || rot === "Con cuánto cerró") cerro = num(c[1].textContent);
        else if (rot === "Cobros") cobros = num(c[1].textContent);
        else if (rot === "Traspasos recibidos") trasp = num(c[1].textContent);
        else if (rot === "Salidas") salidas = num(c[1].textContent);
        else if (rot === "TOTAL" && c.length >= 5) { totE = num(c[3].textContent); totS = num(c[4].textContent); }
      });
      if (cerro === null || vCelda === null || Math.abs(cerro - vCelda) > 0.01)
        R.malos.push(idp + ": la celda dice " + vCelda + " y el panel " + cerro);
      if (totE !== null && cobros !== null && trasp !== null &&
          Math.abs(totE - (cobros + trasp)) > 0.01)
        R.malos.push(idp + ": entro " + (cobros + trasp) + " arriba y " + totE + " en la lista");
      if (totS !== null && salidas !== null && Math.abs(totS - Math.abs(salidas)) > 0.01)
        R.malos.push(idp + ": salio " + Math.abs(salidas) + " arriba y " + totS + " en la lista");
      cel.click(); await esperar(40);
      if (R.malos.length > 6) break;
    }
  } catch (e) { R = {ok: false, error: String(e && e.message || e)}; }
  document.getElementById("out").textContent = "ESPEJO" + JSON.stringify(R) + "OJEPSE";
  document.title = "listo";
}, 1500);
</script>
"""


def espejo_caja(ms: int = 120000) -> list:
    """Los dos totales de la ventana del dinero tienen que dar igual."""
    arnes = RAIZ / "_barrido_espejo.html"
    err = RAIZ / "_barrido_espejo_err.txt"
    arnes.write_text(ESPEJO.replace("__URL__", URL), encoding="utf-8")
    try:
        dom = _chrome(arnes, err, ms)
    finally:
        arnes.unlink(missing_ok=True)
        err.unlink(missing_ok=True)
    m = re.search(r"ESPEJO(\{.*?\})OJEPSE", dom, re.S)
    if not m:
        return ["espejo de la ventana del dinero: el arnes no devolvio salida"]
    import html as _h
    r = json.loads(_h.unescape(m.group(1)))
    if not r.get("ok"):
        return [f"espejo de la ventana del dinero: {r.get('error')}"]
    malas = []
    for rot, a, b in (("cierre del mes anterior", r.get("cierre"), r.get("mesAnterior")),
                      ("saldo de hoy", r.get("hoy"), r.get("ultimoMes"))):
        if a is None or b is None or abs(a - b) > 0.01:
            malas.append(f"espejo de la ventana del dinero · {rot}: la tabla de "
                         f"arriba dice {a} y el mes a mes dice {b}")
    su = r.get("suma")
    if su and None not in su.values() and abs(su["ini"] + su["ing"] - su["egr"] - su["hoy"]) > 0.01:
        malas.append(f"espejo de la ventana del dinero · la fila TOTAL no cierra: "
                     f"inicio {su['ini']} + ingresos {su['ing']} − egresos "
                     f"{su['egr']} ≠ hoy {su['hoy']}")
    if not r.get("paneles"):
        malas.append("espejo de la ventana del dinero: no encontro ningun panel "
                     "de mes (`cm-`) para abrir")
    for m in (r.get("malos") or [])[:4]:
        malas.append(f"espejo · panel de mes · {m}")
    return malas

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hoja", default="todas",
                    help="una hoja, o «todas» (por defecto)")
    ap.add_argument("--ms", type=int, default=480000)
    a = ap.parse_args()

    if not CHROME.exists():
        print(f"no encuentro Chrome en {CHROME}")
        return 2

    hojas = HOJAS if a.hoja == "todas" else [a.hoja]
    try:
        _srv = _levantar_servidor()
    except RuntimeError as e:
        print(e)
        return 2
    if _srv is not None:
        print(f"servidor propio del barrido en {URL} (sin clave, efimero)")
    try:
        total_estados, total_hall, resumen = 0, 0, []
        for _h_ in hojas:
            n_est, n_hall, det = _barrer_hoja(_h_, a.ms)
            total_estados += n_est
            total_hall += n_hall
            resumen.append((_h_, n_est, n_hall, det))

        anchos_mal = barrer_anchos(hojas, a.ms)
        total_hall += len(anchos_mal)

        espejo_mal = espejo_caja() if "hoy" in hojas else []
        total_hall += len(espejo_mal)
        if espejo_mal:
            resumen.append(("espejo", 1, len(espejo_mal), espejo_mal))
        elif "hoy" in hojas:
            resumen.append(("espejo", 1, 0, []))
    finally:
        if _srv is not None:
            _srv.terminate()

    print(f"barrido de {len(hojas)} hoja{'s' if len(hojas) != 1 else ''}: "
          f"{', '.join(hojas)}")
    for nom, n_est, n_hall, det in resumen:
        marca = "  " if not n_hall else "!!"
        print(f"  {marca} {nom.ljust(12)} {n_est:>4} estados · "
              f"{n_hall} hallazgo{'s' if n_hall != 1 else ''}")
        for d in det:
            print(f"       · {d[:170]}")

    if anchos_mal:
        print(f"  !! ANCHOS · {len(anchos_mal)} de "
              f"{len(hojas) * len(ANCHOS)} combinaciones no entran:")
        for x in anchos_mal[:12]:
            print(f"       · {x['hoja']} a {x['ancho']}px · la pagina se corre "
                  f"{x['desborde']}px de costado · "
                  f"{'; '.join(x['malos'][:2]) if x['malos'] else '-'}")
    else:
        print(f"  {len(hojas) * len(ANCHOS)} combinaciones de hoja x ancho "
              f"({', '.join(str(w) for w in ANCHOS)} px): todas entran")

    import datetime
    acta = RAIZ / "data" / "acta_pantallas.json"
    acta.parent.mkdir(exist_ok=True)
    acta.write_text(json.dumps({
        "cuando": datetime.datetime.now().isoformat(timespec="seconds"),
        "hojas": hojas,
        "estados": total_estados,
        "anchos": ANCHOS,
        "anchos_con_desborde": anchos_mal[:12],
        "hallazgos": total_hall,
        "detalle": [d for _, _, _, ds in resumen for d in ds][:20],
        "mide": ["subtitulo vs columna Quien", "totales que se contradicen",
                 "parrafos repetidos", "dos bloques con el mismo rotulo",
                 "texto cortado a mitad de palabra",
                 "etiqueta HTML escrita en pantalla",
                 "nombres de tabla o campo de AXION", "errores de consola",
                 "que los dos totales de la ventana del dinero den igual", "que cada panel de mes de lo mismo que su celda",
                 "que la pagina no se corra de costado a 1440, 1280, 1024, "
                 "900, 820 y 390 px"],
        "no_mide": ["si las cifras estan bien (eso es el cuadre de verificar.py)",
                    "la composicion pixel a pixel (el desborde horizontal y el "
                    "texto recortado SI se miden)",
                    "el detalle de una fila de las tablas que no son de "
                    "mes ni de area"],
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    if not total_hall:
        print(f"  {total_estados} estados en total · sin hallazgos en: "
              "subtitulo vs columna Quien · totales que se contradicen · "
              "parrafos repetidos · dos bloques con el mismo rotulo · texto "
              "cortado · texto que no entra en su caja · TARJETAS SIN CIFRA "
          "· ETIQUETAS HTML ESCRITAS "
              "· nombres de AXION · consola · paneles de area y DETALLE "
              "POR MES incluidos")
        print("  NO mide: si las CIFRAS estan bien —eso es el cuadre de "
              "verificar.py— ni la composicion pixel a pixel (el desborde y "
              "el texto recortado SI).")
    return 0 if not total_hall else 1


def _barrer_hoja(hoja: str, ms: int):
    """Recorre una hoja. Devuelve (estados, hallazgos, lineas de detalle)."""
    harness = RAIZ / "_barrido.html"
    err = RAIZ / "_barrido_err.txt"
    harness.write_text(BARRIDO.replace("__URL__", URL).replace("__HOJA__", hoja),
                       encoding="utf-8")
    dom = ""
    for intento, presupuesto in ((1, ms), (2, ms * 2)):
        try:
            dom = _chrome(harness, err, presupuesto)
        finally:
            if intento == 2:
                harness.unlink(missing_ok=True)
        m = re.search(r'<pre id="salida">(.*?)</pre>', dom, re.S)
        if m:
            break
        if intento == 1:
            print(f"     {hoja}: no llego al final con {presupuesto // 1000} s "
                  f"de tiempo virtual — reintento con el doble")
    harness.unlink(missing_ok=True)

    m = re.search(r'<pre id="salida">(.*?)</pre>', dom, re.S)
    if not m:
        err.unlink(missing_ok=True)
        return 0, 1, [f"la hoja «{hoja}» no llego al final del barrido en dos "
                      f"intentos — ¿existe ese id en la barra, y esta el servidor?"]
    import html as _h
    fotos = json.loads(_h.unescape(m.group(1)))
    # El arnes avisa cuando el cockpit cayo en otra hoja (hash inexistente).
    if len(fotos) == 1 and isinstance(fotos[0], dict) and "hoja_equivocada" in fotos[0]:
        err.unlink(missing_ok=True)
        return 0, 1, [f"la hoja «{hoja}» no existe en la barra: el cockpit "
                      f"abrio «{fotos[0]['hoja_equivocada']}» en su lugar"]

    consola = [l for l in (err.read_text(encoding="utf-8", errors="replace")
                           .splitlines())
               if re.search(r"ERROR|Uncaught|is not a function|not defined|"
                            r"Cannot read", l) and not RUIDO.search(l)]
    err.unlink(missing_ok=True)

    hall = revisar(fotos)

    if not fotos:
        return 0, 1, [f"la hoja «{hoja}» no dejo NI UN estado para revisar: "
                      f"no se barrio, no es que este limpia"]

    det = [f"{x['regla']}: {x['detalle']} [{len(x['estados'])} estado(s)]"
           for x in hall]
    det += [f"consola: {l[:130]}" for l in consola[:4]]
    return len(fotos), len(hall) + len(consola), det


if __name__ == "__main__":
    sys.exit(main())
