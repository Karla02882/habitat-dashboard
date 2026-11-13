"use strict";

var D = null, P = "None", OBRA = "", RS = "", AREA = "", ASESOR = "", TIPO = "",
    BANCO = "";
var NAN_CORREGIDOS = 0;

function soles(n){
  if (n === null || n === undefined || isNaN(n)) return "—";
  return "S/ " + Number(n).toLocaleString("es-PE", {minimumFractionDigits: 2, maximumFractionDigits: 2});
}
function solesM(n){
  if (n === null || n === undefined || isNaN(n)) return "—";
  var a = Math.abs(n);
  if (a >= 1e6) return "S/ " + (n / 1e6).toFixed(2) + "M";
  if (a >= 1e4) return "S/ " + (n / 1e3).toFixed(1) + "K";
  return soles(n);
}
function pct(n){ return (n === null || n === undefined || isNaN(n)) ? "—" : Number(n).toFixed(1) + "%"; }
function fmt1(n){ return (n === null || n === undefined || isNaN(n)) ? "—" : Number(n).toFixed(1); }
function ent(n){ return (n === null || n === undefined || isNaN(n)) ? "—" : Number(n).toLocaleString("es-PE"); }
function esc(s){
  return String(s === null || s === undefined ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}
function num(v){ var x = parseFloat(String(v).replace(/[^\d.\-]/g, "")); return isNaN(x) ? null : x; }

function obrasDeRS(){
  if (!RS) return null;
  var m = D.empresa_de_obra || {}, r = [];
  Object.keys(m).forEach(function(o){ if (m[o] === RS) r.push(o); });
  return r;
}
function obrasDeTipo(){
  if (!TIPO) return null;
  var m = D.tipo_de_obra || {}, r = [];
  Object.keys(m).forEach(function(o){ if (m[o] === TIPO) r.push(o); });
  return r;
}
function entraObra(nombre){
  if (OBRA) return nombre === OBRA;
  var r = obrasDeRS(), t = obrasDeTipo();
  if (r && r.indexOf(nombre) < 0) return false;
  if (t && t.indexOf(nombre) < 0) return false;
  return true;
}
function alcanceTexto(){
  var p = [];
  if (OBRA) p.push("la obra «" + OBRA + "»");
  else {
    if (RS) { var l = obrasDeRS(); p.push("la razón social «" + RS + "» · " + (l ? l.length : 0) + " obras"); }
    if (TIPO) { var t = obrasDeTipo(); p.push("el tipo «" + TIPO + "» · " + (t ? t.length : 0) + " obras"); }
  }
  if (ASESOR) p.push("el vendedor «" + ASESOR + "»");
  return p.join(" · ");
}

function cifraDe(res, nombres){
  for (var i = 0; i < nombres.length; i++)
    if (res[nombres[i]] && res[nombres[i]].valor !== null && res[nombres[i]].valor !== undefined)
      return res[nombres[i]].valor;
  return null;
}
function fichaDe(res, nombres){
  for (var i = 0; i < nombres.length; i++) if (res[nombres[i]]) return res[nombres[i]];
  return null;
}
function porEtiqueta(lista){
  var m = {}; (lista || []).forEach(function(c){ m[c.etiqueta] = c; }); return m;
}
function tablaObra(cols, filas, vacio){
  if (!filas || !filas.length) return '<p class="mas">' + esc(vacio) + '</p>';
  var h = '<div class="envoltura-tabla"><table class="datos"><thead><tr>';
  (cols || []).forEach(function(c){
    var num = filas.some(function(f){ return typeof f[cols.indexOf(c)] === "number"; });
    h += '<th' + (num ? ' class="num"' : '') + '>' + esc(c) + '</th>';
  });
  h += '</tr></thead><tbody>';
  filas.forEach(function(f){
    h += '<tr>';
    f.forEach(function(v, i){
      var esNum = typeof v === "number";
      if (v === null || v === undefined || v === "") {
        h += '<td class="num">—</td>';
      } else if (esNum) {
        h += '<td class="num">' +
          (String(cols[i]).indexOf("S/") >= 0 ? soles(v) : ent(v)) + '</td>';
      } else {
        h += '<td' + (i === 0 ? ' class="obra"' : '') + '>' + esc(v) + '</td>';
      }
    });
    h += '</tr>';
  });
  return h + '</tbody></table></div>';
}

var OTROS_N = 0;
function filaOtros(rotulo, celdasResto, hijas, claseTd){
  var id = "ot" + (++OTROS_N);
  var h = '<tr class="otros-desplegar" data-otros="' + id +
    '" tabindex="0" role="button" aria-expanded="false">' +
    '<td class="' + (claseTd || 'obra') + '">' + rotulo +
    ' <span class="otros-flecha">▾</span></td>' + (celdasResto || '') + '</tr>';
  (hijas || []).forEach(function(celdas){
    h += '<tr class="otros-hijo otros-cerrado ' + id + '">' + celdas + '</tr>';
  });
  return h;
}
function textoOtros(items, n, sep){
  sep = sep || ' · ';
  var L = items || [];
  if (L.length <= n) return L.join(sep);
  return L.slice(0, n).join(sep) +
    ' <span class="otros-mas" tabindex="0" role="button" aria-expanded="false">y ' +
    ent(L.length - n) + ' más <span class="otros-flecha">▾</span></span>' +
    '<span class="otros-resto" hidden>' + sep + L.slice(n).join(sep) + '</span>';
}
function otrosAlternar(t){
  var abrir = t.getAttribute("aria-expanded") !== "true";
  t.setAttribute("aria-expanded", abrir ? "true" : "false");
  if (t.tagName === "TR") {
    var id = t.getAttribute("data-otros");
    [].forEach.call(t.parentNode.querySelectorAll("tr." + id), function(f){
      f.classList.toggle("otros-cerrado", !abrir);
    });
  } else {
    var r = t.nextElementSibling;
    if (r && r.classList.contains("otros-resto")) r.hidden = !abrir;
  }
  var fl = t.querySelector(".otros-flecha");
  if (fl) fl.textContent = abrir ? "▴" : "▾";
}
document.addEventListener("click", function(ev){
  var t = ev.target && ev.target.closest ? ev.target.closest("tr.otros-desplegar, .otros-mas") : null;
  if (!t) return;
  ev.stopPropagation(); ev.preventDefault();
  otrosAlternar(t);
}, true);
document.addEventListener("keydown", function(ev){
  var t = ev.target;
  if (!t || !t.matches || !t.matches("tr.otros-desplegar, .otros-mas")) return;
  if (ev.key !== "Enter" && ev.key !== " ") return;
  ev.preventDefault(); ev.stopPropagation();
  otrosAlternar(t);
}, true);

function conectarObra(H, idBusca){
  document.querySelectorAll("#hoja .st-tarj").forEach(function(el){
    var abrir = function(){
      var id = el.getAttribute("data-obra");
      H._abierto = (H._abierto === id) ? "" : id;
      pintar();
      if (H._abierto) setTimeout(function(){
        var l = document.querySelector("#hoja .st-lista");
        if (l) l.scrollIntoView({behavior: "smooth", block: "start"});
      }, 60);
    };
    el.addEventListener("click", abrir);
    el.addEventListener("keydown", function(e){
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); abrir(); }
    });
  });
  document.querySelectorAll("#hoja .st-pill[data-est]").forEach(function(el){
    el.addEventListener("click", function(){
      H._estado = el.getAttribute("data-est") || "";
      pintar();
    });
  });
  var b = document.getElementById(idBusca);
  if (b) b.addEventListener("input", function(){
    H._busca = b.value;
    var pos = b.selectionStart;
    pintar();
    var n = document.getElementById(idBusca);
    if (n) { n.focus(); try { n.setSelectionRange(pos, pos); } catch(e){} }
  });
  var x = document.querySelector("#hoja .st-cerrar");
  if (x) x.addEventListener("click", function(){ H._abierto = ""; pintar(); });
}

function drillDe(M, nombres){
  var dr = M.drills || {};
  for (var i = 0; i < nombres.length; i++) if (dr[nombres[i]]) return nombres[i];
  return null;
}
function drillActual(clave){
  var M = D.meses[P] || D.meses["None"];
  return (M.drills || {})[clave];
}
function colDe(dr, nombres){
  var c = dr.cols || [];
  for (var i = 0; i < c.length; i++)
    for (var j = 0; j < nombres.length; j++)
      if (String(c[i]).toLowerCase().indexOf(nombres[j]) >= 0) return i;
  return -1;
}
function sumaFiltrada(M, clave){
  var dr = (M.drills || {})[clave];
  if (!dr || !dr.filas || !dr.filas.length) return null;
  var iObra = colDe(dr, ["obra"]);
  if (iObra < 0) return null;
  var ult = (dr.cols || []).length - 1, s = 0;
  dr.filas.forEach(function(r){
    if (!entraObra(String(r[iObra]))) return;
    var n = num(r[ult]); if (n !== null) s += n;
  });
  return s;
}

function cifraDoble(v, moneda){
  if (v === null || v === undefined || isNaN(v)) return '<div class="cifra-g raya">—</div>';
  if (moneda === false) return '<div class="cifra-g">' + ent(v) + '</div>';
  return '<div class="cifra-g' + (v < 0 ? ' neg' : '') + '">' + solesM(v) + '</div>' +
         '<div class="exacta">' + soles(v) + '</div>';
}
function tarjetaSimple(k, v, n, opc){
  opc = opc || {};
  var cuerpo = opc.html !== undefined ? opc.html : cifraDoble(v, opc.moneda);
  return '<div class="tarjeta"><span class="overline">' + esc(k) + '</span>' +
    cuerpo + (n ? '<p style="color:var(--texto-suave)">' +
      (opc.crudo ? n : esc(n)) + '</p>' : '') + '</div>';
}
function perPartes(){
  var s = String(P);
  if (s === "hist") return {hist: true, anio: null, mes: null};
  var t = /^(\d{4})(?:-(\d{1,2}))?$/.exec(s);
  if (t) return {hist: false, anio: Number(t[1]), mes: t[2] ? Number(t[2]) : null};
  var a = Number(String(((D || {}).flujo || {}).anio || "")) ||
          (new Date()).getFullYear();
  if (s === "None" || P === null || P === undefined)
    return {hist: false, anio: a, mes: null};
  if (/^\d{1,2}$/.test(s)) return {hist: false, anio: a, mes: Number(s)};
  return {hist: false, anio: a, mes: null};
}
function filasCRMEmpresa(D, P, empresa){
  if (empresa === "concept"){
    var cc = ((D.crm_concept || {}).filas) || [];
    return _recortarPeriodo(cc, D, P);
  }
  return filasCRM(D, P);
}
function _recortarPeriodo(todas, D, P){
  if (!todas.length || P === "hist") return todas;
  var ac = "";
  for (var i = 0; i < todas.length; i++){
    var a = String(todas[i].creado || "").slice(0, 4);
    if (a > ac) ac = a;
  }
  if (!ac) return todas;
  if (P === "None" || P === null || P === undefined)
    return todas.filter(function(f){ return String(f.creado||"").slice(0,4) === ac; });
  var t = /^(\d{4})(?:-(\d{1,2}))?$/.exec(String(P));
  if (t){
    if (!t[2])
      return todas.filter(function(f){ return String(f.creado||"").slice(0,4) === t[1]; });
    var am = t[1] + "-" + ("0" + t[2]).slice(-2);
    return todas.filter(function(f){ return String(f.creado||"").slice(0,7) === am; });
  }
  if (!/^\d{1,2}$/.test(String(P))) return todas;
  var mm = ac + "-" + (String(P).length === 1 ? "0" + P : P);
  return todas.filter(function(f){ return String(f.creado||"").slice(0,7) === mm; });
}
function filasCRM(D, P){
  var todas = ((D.meses || {})["hist"] || {}).crm_filas || [];
  if (!todas.length || P === "hist") return todas;
  var ac = "";
  for (var i = 0; i < todas.length; i++){
    var a = String(todas[i].creado || "").slice(0, 4);
    if (a > ac) ac = a;
  }
  if (!ac) return todas;
  if (P === "None" || P === null || P === undefined)
    return todas.filter(function(f){ return String(f.creado||"").slice(0,4) === ac; });
  var t = /^(\d{4})(?:-(\d{1,2}))?$/.exec(String(P));
  if (t){
    if (!t[2])
      return todas.filter(function(f){ return String(f.creado||"").slice(0,4) === t[1]; });
    var am = t[1] + "-" + ("0" + t[2]).slice(-2);
    return todas.filter(function(f){ return String(f.creado||"").slice(0,7) === am; });
  }
  if (!/^\d{1,2}$/.test(String(P))) return todas;
  var mm = ac + "-" + (String(P).length === 1 ? "0" + P : P);
  return todas.filter(function(f){ return String(f.creado||"").slice(0,7) === mm; });
}
function hs(n){
  if (n === null || n === undefined || isNaN(n)) return "—";
  if (Math.abs(n) >= 48) return (n / 24).toFixed(1) + " días";
  if (Math.abs(n) < 1) return Math.round(n * 60) + " min";
  return Number(n).toFixed(1) + " h";
}
function contarPor(filas, campo){
  var n = filas.length, g = {};
  filas.forEach(function(f){
    var v = f[campo]; if (v === undefined || v === null || v === "") v = "(sin dato)";
    v = String(v);
    g[v] = (g[v] || 0) + 1;
  });
  return Object.keys(g).map(function(v){
    return {valor: v, leads: g[v], pct: n ? 100 * g[v] / n : 0};
  }).sort(function(a, b){ return b.leads - a.leads; });
}
function medianaDe(vals){
  if (!vals.length) return null;
  var s = vals.slice().sort(function(a, b){ return a - b; });
  var m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}
function atencionDe(filas){
  var con = 0, neg = 0, buenas = [];
  filas.forEach(function(f){
    var h = f.horas_atencion;
    if (h === null || h === undefined) return;
    con++;
    if (h < 0) neg++; else buenas.push(h);
  });
  var prom = buenas.length
    ? buenas.reduce(function(s, x){ return s + x; }, 0) / buenas.length : null;
  return {
    con_llamada: con,
    promedio_h: prom,
    mediana_h: medianaDe(buenas),
    llamada_antes_de_crear: neg,
  };
}
function panelArrastre(D){
  var arr = ((D.flujo || {}).arrastre) || {};
  var F = ((D.libro || {}).filas) || {};
  var anios = arr.anios || [];
  if (!anios.length || !(F.f || []).length)
    return '<button class="cerrar">Cerrar</button>' +
      '<p>No hay años anteriores en el libro de esta lectura.</p>';
  var h = '<button class="cerrar">Cerrar</button>' +
    '<h3>' + esc(anios.join(" y ")) + ', mes a mes · la vara del libro</h3>' +
    '<div class="regla">«Entró» son las ventas que Administración anotó en su Registro ' +
    'de Movimientos y «Salió» los gastos del mismo registro — los dos lados del mismo ' +
    'cuaderno, el mismo SALDO que publica la pestaña Gastos con ' + esc(anios.join(" y ")) +
    ' elegido. El presupuesto no entra: es un plan, no plata que se movió. Ojo: los meses ' +
    'de ' + esc(String((D.flujo || {}).anio || "")) + ' de la tabla grande miden otra vara ' +
    '—Cobranzas contra libro— y por eso no se comparan fila contra fila.</div>';

  var meses = {}, tot = {e: 0, s: 0};
  (F.f || []).forEach(function (r) {
    var a = String(r[0] || "").slice(0, 4);
    if (anios.indexOf(Number(a)) < 0) return;
    var k = String(r[0] || "").slice(0, 7);
    var m = meses[k] = meses[k] || {e: 0, s: 0};
    if (r[7] === "venta") { m.e += r[4] || 0; tot.e += r[4] || 0; }
    else if (r[7] === "gasto") { m.s += r[4] || 0; tot.s += r[4] || 0; }
  });
  var claves = Object.keys(meses).sort();
  h += '<div class="envoltura-tabla"><table class="datos"><thead><tr>' +
    '<th>Mes</th><th class="num">Entró</th><th class="num">Salió</th>' +
    '<th class="num">Queda</th><th class="num">Acumulado</th></tr></thead><tbody>';
  var ac = 0;
  claves.forEach(function (k) {
    var m = meses[k], q = m.e - m.s; ac += q;
    var nom = (MES_LARGO[Number(k.slice(5, 7))] || k) + " " + k.slice(0, 4);
    h += '<tr class="fila-obra abrible" data-abre="arrmes-' + k + '" ' +
      'aria-expanded="false" tabindex="0" role="button">' +
      '<td class="obra"><span class="ob-nom">' + esc(nom) + '</span>' +
      '<span class="ob-sub">clic para ver qué entró y qué salió</span></td>' +
      '<td class="num">' + soles(m.e) + '</td>' +
      '<td class="num">' + soles(m.s) + '</td>' +
      '<td class="num"><b' + (q < 0 ? ' style="color:var(--rojo)"' : '') + '>' +
        soles(q) + '</b></td>' +
      '<td class="num"><b' + (ac < 0 ? ' style="color:var(--rojo)"' : '') + '>' +
        soles(ac) + '</b></td></tr>';
  });
  h += '<tr class="total"><td class="obra">TOTAL ' + esc(anios.join(" y ")) + '</td>' +
    '<td class="num">' + soles(tot.e) + '</td>' +
    '<td class="num">' + soles(tot.s) + '</td>' +
    '<td class="num"><b' + (tot.e - tot.s < 0 ? ' style="color:var(--rojo)"' : '') + '>' +
      soles(tot.e - tot.s) + '</b></td>' +
    '<td class="num"><b' + (tot.e - tot.s < 0 ? ' style="color:var(--rojo)"' : '') + '>' +
      soles(tot.e - tot.s) + '</b></td></tr>' +
    '</tbody></table></div>' +
    claves.map(function (k) {
      return '<div class="detalle" id="det-arrmes-' + k + '"></div>';
    }).join("");

  if (Math.abs((tot.e - tot.s) - (arr.monto || 0)) > 0.5 || (F.recortado || 0) > 0)
    h += '<p class="linea-meta"><b>Este panel suma ' + soles(tot.e - tot.s) +
      ' y la fila del arrastre dice ' + soles(arr.monto) + '.</b>' +
      ((F.recortado || 0) > 0 ? ' El libro viajó recortado (' + ent(F.recortado) +
        ' movimientos afuera por el tope), y esa es la causa probable.' : '') +
      ' Manda la fila, que sale del motor.</p>';

  var tops = function (clase, titulo) {
    var fs = (F.f || []).filter(function (r) {
      return r[7] === clase && anios.indexOf(Number(String(r[0]).slice(0, 4))) >= 0;
    }).sort(function (a, b) { return (b[4] || 0) - (a[4] || 0); }).slice(0, 10);
    if (!fs.length) return "";
    var t = '<span class="overline" style="display:block;margin-top:var(--e3)">' +
      esc(titulo) + '</span>' +
      '<div class="envoltura-tabla"><table class="datos"><thead><tr>' +
      '<th>Fecha</th><th>Concepto</th><th>Obra</th><th class="num">Monto</th>' +
      '</tr></thead><tbody>';
    fs.forEach(function (r) {
      t += '<tr><td>' + esc(r[0]) + '</td>' +
        '<td>' + esc(String(r[3] || "—").slice(0, 70)) + '</td>' +
        '<td class="obra">' + (F.obra[r[5]] ? esc(F.obra[r[5]]) : '<span class="raya">—</span>') + '</td>' +
        '<td class="num">' + soles(r[4]) + '</td></tr>';
    });
    return t + '</tbody></table></div>';
  };
  h += tops("gasto", "Los 10 gastos más grandes de " + anios.join(" y "));
  h += tops("venta", "Los 10 ingresos más grandes de " + anios.join(" y "));
  h += '<p class="mas">Para buscarlo movimiento por movimiento —con filtros de tipo, ' +
    'banco y texto— está la pestaña <b>Finanzas · Gastos</b> con ' +
    esc(anios.join(" y ")) + ' elegido en el período.</p>';
  return h;
}
function panelArrastreMes(D, clave){
  var F = ((D.libro || {}).filas) || {};
  var nom = (MES_LARGO[Number(String(clave).slice(5, 7))] || clave) + " " +
    String(clave).slice(0, 4);
  var del = (F.f || []).filter(function (r) {
    return String(r[0] || "").slice(0, 7) === clave;
  });
  if (!del.length)
    return '<button class="cerrar">Cerrar</button><p>Ese mes no está en el libro.</p>';
  var e = 0, g = 0, ne = 0, ng = 0;
  del.forEach(function (r) {
    if (r[7] === "venta") { e += r[4] || 0; ne++; }
    else if (r[7] === "gasto") { g += r[4] || 0; ng++; }
  });
  var h = '<button class="cerrar">Cerrar</button>' +
    '<h3>' + esc(nom) + ' · la vara del libro</h3>' +
    '<div class="regla">Entró ' + soles(e) + ' en ' + ent(ne) + ' ventas del Registro de ' +
    'Movimientos y salió ' + soles(g) + ' en ' + ent(ng) + ' gastos del mismo registro: ' +
    'el mes quedó en <b>' + soles(e - g) + '</b>. El presupuesto no entra: es un plan.</div>';
  var lado = function (cl, titulo, tope) {
    var fs = del.filter(function (r) { return r[7] === cl; })
      .sort(function (a, b) { return (b[4] || 0) - (a[4] || 0); });
    if (!fs.length) return '<span class="overline" style="display:block;margin-top:var(--e3)">' +
      esc(titulo) + '</span><p style="color:var(--texto-suave)">Sin movimientos.</p>';
    var t = '<span class="overline" style="display:block;margin-top:var(--e3)">' +
      esc(titulo) + (fs.length > tope ? ' · los ' + tope + ' más grandes de ' + ent(fs.length) : '') +
      '</span>' +
      '<div class="envoltura-tabla"><table class="datos"><thead><tr>' +
      '<th>Fecha</th><th>Concepto</th><th>Obra</th><th class="num">Monto</th>' +
      '</tr></thead><tbody>';
    fs.slice(0, tope).forEach(function (r) {
      t += '<tr><td>' + esc(r[0]) + '</td>' +
        '<td>' + esc(String(r[3] || "—").slice(0, 70)) + '</td>' +
        '<td class="obra">' + (F.obra[r[5]] ? esc(F.obra[r[5]]) : '<span class="raya">—</span>') + '</td>' +
        '<td class="num">' + soles(r[4]) + '</td></tr>';
    });
    var suma = fs.reduce(function (a, r) { return a + (r[4] || 0); }, 0);
    t += '<tr class="total"><td colspan="3">TOTAL · ' + ent(fs.length) +
      ' movimientos</td><td class="num">' + soles(suma) + '</td></tr>';
    return t + '</tbody></table></div>';
  };
  h += lado("gasto", "Qué salió", 15);
  h += lado("venta", "Qué entró", 15);
  h += '<p class="mas">Movimiento por movimiento, con filtros y buscador: la pestaña ' +
    '<b>Finanzas · Gastos</b> con el período ' + esc(nom) + '.</p>';
  return h;
}
function tarjetaAbrible(id, k, v, n, rotulo, clave, opc){
  opc = opc || {};
  return '<div class="tarjeta abrible" data-abre="' + id + '"' +
    (clave ? ' data-drill="' + esc(clave) + '"' : '') +
    (opc.extra || '') +
    ' aria-expanded="false" tabindex="0" role="button">' +
    '<span class="overline">' + esc(k) + '</span>' +
    (opc.html !== undefined && opc.html !== null
      ? opc.html
      : (v === undefined ? '' : cifraDoble(v, opc.moneda))) +
    '<p style="color:var(--texto-suave)">' + (opc.crudo ? n : esc(n)) + '</p>' +
    (rotulo ? '<div class="abrir"><span>' + esc(rotulo) + '</span><span class="flecha">▸</span></div>' : '') +
    '</div>';
}
function cabSeccion(titulo, apostilla, id){
  return '<section class="seccion"' + (id ? ' id="' + id + '"' : '') + '><div class="seccion-cab">' +
    '<h2>' + esc(titulo) + '</h2>' +
    (apostilla ? '<span class="apostilla">' + esc(apostilla) + '</span>' : '') + '</div>';
}
function filaRiel(o){
  var p = o.pct === undefined ? (o.total ? 100 * o.parte / o.total : 0) : o.pct;
  return '<tr class="fila-obra' + (o.abre ? ' abrible' : '') + '"' +
    (o.abre ? ' data-abre="' + o.abre + '" ' + (o.datos || '') +
              ' aria-expanded="false" tabindex="0" role="button"' : '') + '>' +
    '<td class="obra"><span class="ob-nom">' + esc(o.nombre) + (o.marca || '') + '</span>' +
      (o.sub ? '<span class="ob-sub">' + esc(o.sub) + '</span>' : '') + '</td>' +
    '<td><span class="riel-obra" style="width:' + Math.max(3, o.ancho) + '%">' +
      '<span class="lleno" style="width:' + Math.max(p > 0 ? 1.5 : 0, Math.min(100, p)) + '%"></span></span></td>' +
    (o.celdas || []).map(function(c){ return '<td class="num">' + c + '</td>'; }).join("") +
    '<td class="num"><b class="pct-obra' + (p >= 80 ? ' alto' : p < 15 ? ' bajo' : '') + '">' +
      pct(p) + '</b></td></tr>';
}
function avisoAlcance(queSigue, queNo, queNoVendedor){
  if (!OBRA && !RS && !ASESOR && !TIPO) return "";
  var h = '<div class="aviso-obra"><b>Filtrado por ' + esc(alcanceTexto()) + '.</b> ';
  if (OBRA || RS || TIPO) {
    h += 'Siguen al filtro de obra: ' + esc(queSigue) + '.';
    if (queNo) h += ' <b>No lo siguen</b> ' + esc(queNo) + ': la fuente no los desagrega ' +
                    'por obra, así que se muestran del período completo.';
  }
  if (ASESOR && queNoVendedor)
    h += (OBRA || RS ? ' ' : '') + '<b>No siguen al filtro de vendedor</b> ' +
         esc(queNoVendedor) + '.';
  return h + '</div>';
}
function faltaDato(titulo, porQue, requiere, area, tecnico){
  return '<div class="falta"><div class="rayon"></div>' +
    '<div class="titulo">' + esc(titulo) + '</div><p>' + esc(porQue) + '</p>' +
    '<div class="req"><span class="k">Requiere</span> <span class="v"' +
    (tecnico ? ' data-tecnico="' + esc(tecnico) + '"' : '') + '>' +
    esc(requiere) + '</span><br>' +
    '<span class="a">' + esc(area) + '</span></div></div>';
}

var YO = {usuario: "", rol: "admin", vedadas: [], puede_actualizar: true};
function puedeVer(id){ return (YO.vedadas || []).indexOf(id) < 0; }

fetch("/quien", {cache: "no-store"})
  .then(function(r){ return r.ok ? r.json() : null; })
  .then(function(q){
    if (q) YO = q;
    var sal = document.getElementById("salir");
    if (sal && YO.usuario) sal.hidden = false;
    if (window.HOJA) pintarCabDer(window.HOJA);
  })
  .catch(function(){ })
  .then(function(){ return fetch("/tablero_datos.json", {cache: "no-cache"}); })
  .then(function(r){ if (!r.ok) throw new Error("HTTP " + r.status); return r.text(); })
  .then(function(t){
    return JSON.parse(t);
  })
  .then(function(j){ D = j; iniciar(); })
  .catch(function(e){
    var c = document.getElementById("cargando");
    if (!c) return;
    c.innerHTML = "leyendo <code>tablero_datos.json</code>…";
    fetch("/generando", {cache: "no-store"})
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (g) {
        if (g && g.generando) {
          var min = Math.max(1, Math.round(g.segundos / 60));
          c.innerHTML = "<b>El tablero se está preparando.</b><br>" +
            "Está leyendo AXION y Kommo para armar las cifras del día — " +
            "va " + min + (min === 1 ? " minuto" : " minutos") + " y suele tardar " +
            "entre 5 y 10.<br>Esta página se actualiza sola cuando termine; " +
            "no hace falta hacer nada.";
          setTimeout(function () { location.reload(); }, 45000);
          return;
        }
        if (g && !g.hay_datos) {
          c.innerHTML = "<b>El tablero todavía no tiene datos.</b><br>" +
            "El servidor está arriba pero la lectura de AXION no llegó a " +
            "completarse. Se vuelve a intentar solo; si en 15 minutos sigue " +
            "así, avisá a quien lo administra.";
          setTimeout(function () { location.reload(); }, 60000);
          return;
        }
        c.innerHTML = "<b>No se pudo leer <code>tablero_datos.json</code>.</b><br>" +
          esc(e.message) + "<br>Hay que servir esta página, no abrirla con doble clic:<br>" +
          "Si es local, inicia el servidor con:<br>" +
          "<code>python -X utf8 scripts/servidor.py</code>";
      })
      .catch(function () {
        c.innerHTML = "<b>No se pudo leer <code>tablero_datos.json</code>.</b><br>" +
          esc(e.message);
      });
  });

function iniciar(){
  acomodarBotonActualizar();
  if (hayRegistro()) {
    var pedida = (location.hash || "").replace("#", "");
    /* una hoja que salió de la barra lleva a su reemplazo (`REDIRIGE`) */
    if (typeof REDIRIGE !== "undefined" && REDIRIGE[pedida]) {
      pedida = REDIRIGE[pedida];
      history.replaceState(null, "", "#" + pedida);
    }
    if (pedida && !puedeVer(pedida)) pedida = "";
    var aterrizaje = null;
    HOJAS.forEach(function (hh) {
      if (!aterrizaje && window.REGISTRO[hh.id] && puedeVer(hh.id))
        aterrizaje = window.REGISTRO[hh.id];
    });
    window.HOJA = window.REGISTRO[pedida] || aterrizaje ||
                  window.REGISTRO[Object.keys(window.REGISTRO)[0]];
    window.addEventListener("hashchange", function(){
      irAHoja((location.hash || "").replace("#", ""));
    });
  }
  var H = window.HOJA || {};
  document.title = (H.nombre || "Cockpit") + " · Habitat Control";
  var nom = document.getElementById("hoja-nombre");
  if (nom) nom.textContent = H.nombre || "";
  pintarCabDer(H);
  pintarNav(H.id);

  var sp = document.getElementById("f-periodo");
  Object.keys(D.nombres_mes).forEach(function(k){
    var o = document.createElement("option"); o.value = k; o.textContent = D.nombres_mes[k]; sp.appendChild(o);
  });
  sp.value = "None";
  armarSelectorFecha(sp);

  var sr = document.getElementById("f-rs");
  sr.innerHTML = '<option value="">Todas las razones sociales</option>';
  (D.razones_filtro || []).forEach(function(r){
    var x = document.createElement("option"); x.value = r; x.title = r;
    x.textContent = r.replace(/ SOCIEDAD ANONIMA CERRADA$/, " S.A.C.")
                     .replace(/ EMPRESA INDIVIDUAL DE RESPONSABILIDAD LIMITADA$/, " E.I.R.L.");
    sr.appendChild(x);
  });

  var so = document.getElementById("f-obra");
  var llenarObras = function(){
    var lr = obrasDeRS(), lt = obrasDeTipo(), sel = so.value;
    var lista = (lr || lt)
      ? (D.obras_filtro || []).filter(function(o){
          return (!lr || lr.indexOf(o) >= 0) && (!lt || lt.indexOf(o) >= 0); })
      : null;
    so.innerHTML = '<option value="">Todos los proyectos</option>';
    (lista || (D.obras_filtro || []))
      .forEach(function(o){
        var x = document.createElement("option"); x.value = o; x.textContent = o; so.appendChild(x);
      });
    so.value = [].slice.call(so.options).some(function(o){ return o.value === sel; }) ? sel : "";
    OBRA = so.value;
  };
  llenarObras();
  window.__llenarObras = llenarObras;

  var MESES_TXT = /\b(enero|febrero|marzo|abril|mayo|junio|julio|agosto|setiembre|septiembre|octubre|noviembre|diciembre)\b/gi;
  function _bloques(){
    var todos = [].slice.call(document.querySelectorAll(
      "#hoja .seccion, #hoja .d-carta, #hoja .tarjeta"));
    return todos.filter(function (n) {
      return !todos.some(function (m) { return m !== n && n.contains(m); });
    });
  }
  function _clave(nodo, i){
    var t = nodo.querySelector("h2, h3, .d-tit, .d-preg, .overline");
    if (!t) return "#" + i;
    return t.textContent.replace(MESES_TXT, "").replace(/[\d.,%·:()]/g, "")
      .replace(/\s+/g, " ").trim().slice(0, 60).toLowerCase() || ("#" + i);
  }
  function _topeBarra(){
    var b = document.querySelector(".barra-fija");
    return b ? b.getBoundingClientRect().bottom : 0;
  }
  function _anclaVisible(){
    var y0 = _topeBarra(), ns = _bloques();
    for (var i = 0; i < ns.length; i++){
      var r = ns[i].getBoundingClientRect();
      if (r.bottom > y0 + 4)
        return {clave: _clave(ns[i], i), i: i, delta: r.top - y0};
    }
    return null;
  }
  function _volverAlAncla(a){
    if (!a) return false;
    var y0 = _topeBarra(), ns = _bloques(), destino = null;
    for (var i = 0; i < ns.length; i++){
      if (_clave(ns[i], i) === a.clave){ destino = ns[i]; break; }
    }
    if (!destino && ns[a.i]) destino = ns[a.i];
    if (!destino) return false;
    var r = destino.getBoundingClientRect();
    window.scrollBy({top: Math.round(r.top - y0 - a.delta), behavior: "instant"});
    return true;
  }
  function pintarPorFiltro(){
    var ancla = _anclaVisible();
    var y = window.scrollY || 0;
    pintar();
    if (_volverAlAncla(ancla)) return;
    var tope = Math.max(0, document.documentElement.scrollHeight - window.innerHeight);
    window.scrollTo({top: Math.min(y, tope), behavior: "instant"});
  }
  var sa = document.getElementById("f-area");
  if (sa) sa.addEventListener("change", function(){ AREA = sa.value; pintarPorFiltro(); });
  var sv = document.getElementById("f-asesor");
  if (sv) sv.addEventListener("change", function(){ ASESOR = sv.value; pintarPorFiltro(); });
  var sb = document.getElementById("f-banco");
  if (sb) sb.addEventListener("change", function(){ BANCO = sb.value; pintarPorFiltro(); });

  sp.addEventListener("change", function(){ P = sp.value; pintarPorFiltro(); });
  sr.addEventListener("change", function(){ RS = sr.value; llenarObras(); pintarPorFiltro(); });
  var st = document.getElementById("f-tipo");
  if (st) st.addEventListener("change", function(){ TIPO = st.value; llenarObras(); pintarPorFiltro(); });
  so.addEventListener("change", function(){ OBRA = so.value; pintarPorFiltro(); });
  var fd = document.getElementById("f-desde");
  var fh = document.getElementById("f-hasta");
  var fx = document.getElementById("f-fechas-limpiar");
  if (fd && fh) {
    var porFecha = function(){
      DESDE = fd.value || ""; HASTA = fh.value || "";
      if (DESDE && HASTA && DESDE > HASTA) { HASTA = DESDE; fh.value = HASTA; }
      pintarPorFiltro();
    };
    fd.addEventListener("change", porFecha);
    fh.addEventListener("change", porFecha);
  }
  var ff = document.getElementById("f-fuente");
  if (ff) {
    ff.addEventListener("change", function(){
      FUENTE = ff.value || ""; pintarPorFiltro();
    });
    if (fx) fx.addEventListener("click", function(){
      fd.value = ""; fh.value = ""; DESDE = ""; HASTA = ""; pintarPorFiltro();
    });
  }

  document.getElementById("cargando").hidden = true;
  document.getElementById("hoja").hidden = false;
  pintarFuentes(H.fuentes);
  pintar();
  vigilar();
}

var GRUPOS = [
  {nombre: "Resumen",   hojas: ["hoy"]},
  {nombre: "Finanzas",  hojas: ["caja", "gasto-d", "compras", "contasis", "ratios-axion", "comparativo"]},
  {nombre: "Comercial", hojas: ["comercial-d", "asesores", "crm", "crm-informe", "marketing", "stock", "cambios-stock", "clientes", "morosos"]},
  {nombre: "Obras",     hojas: ["obras-d", "cabidas", "bitacora", "contratos", "cotizaciones", "atencion", "cronogramas"]},
  {nombre: "Informes",  hojas: ["informe-quincenal"]},
  {nombre: "Estado",    hojas: ["observaciones", "estado"]}
];

(function(){
  var e = document.getElementById("pie-grupos");
  if (e) e.textContent = GRUPOS.length + " grupos";
})();

function grupoDe(id){
  for (var i = 0; i < GRUPOS.length; i++)
    if (GRUPOS[i].hojas.indexOf(id) >= 0) return GRUPOS[i];
  return null;
}

var HOJAS = [
  {id: "hoy",          nombre: "Resumen",      arch: "hoy.html"},
  {id: "caja",         nombre: "Caja",         arch: "caja.html"},
  {id: "comercial-d",  nombre: "Ventas",       arch: "comercial-d.html"},
  {id: "gasto-d",      nombre: "Gasto",        arch: "gasto-d.html"},
  {id: "obras-d",      nombre: "Obras",        arch: "obras-d.html"},
  {id: "compras",      nombre: "Compras",      arch: "compras.html"},
  {id: "contasis",     nombre: "ContaSis",     arch: "contasis.html"},
  {id: "ratios-axion", nombre: "Ratios AXION", arch: "ratios-axion.html"},
  {id: "comparativo",  nombre: "Comparativo",  arch: "comparativo.html"},
  {id: "ventas-kpi",   nombre: "Ventas KPI",   arch: "ventas-kpi.html"},
  {id: "asesores",     nombre: "Asesores KPI", arch: "asesores.html"},
  {id: "crm",          nombre: "CRM",          arch: "crm.html"},
  {id: "crm-informe",  nombre: "Informe",      arch: "crm-informe.html"},
  {id: "informe-quincenal", nombre: "Informe mensual", arch: "informe-quincenal.html"},
  {id: "marketing",    nombre: "Marketing",    arch: "marketing.html"},
  {id: "cabidas",      nombre: "Cabidas",      arch: "cabidas.html"},
  {id: "bitacora",     nombre: "Bitácora",     arch: "bitacora.html"},
  {id: "contratos",    nombre: "Contratos",    arch: "contratos.html"},
  {id: "cotizaciones", nombre: "Cotizaciones", arch: "cotizaciones.html"},
  {id: "atencion",     nombre: "Atención al cliente", arch: "atencion.html"},
  {id: "cronogramas",  nombre: "Cronogramas",  arch: "cronogramas.html"},
  {id: "stock",        nombre: "Stock",        arch: "stock.html"},
  {id: "cambios-stock", nombre: "Cambios de stock", arch: "cambios-stock.html"},
  {id: "clientes",     nombre: "Clientes",     arch: "clientes.html"},
  {id: "morosos",      nombre: "Morosos",      arch: "morosos.html"},
  {id: "observaciones", nombre: "Observaciones", arch: "observaciones.html"},
  {id: "estado",       nombre: "Estado",       arch: "estado.html"}
];

window.REGISTRO = window.REGISTRO || {};
function hayRegistro(){ return Object.keys(window.REGISTRO).length > 1; }

function medirFiltrosTabla(){
  document.querySelectorAll(".tarjeta > .filtros-det").forEach(function(f){
    f.parentElement.style.setProperty("--alto-filtros", f.offsetHeight + "px");
  });
}

function pintarCabDer(H){
  var der = document.getElementById("cab-der");
  if (!der) return;
  var ver = (YO && YO.version) || der.getAttribute("data-version") || "";
  var piezas = [];
  if (YO && YO.usuario) piezas.push('<span class="cab-quien">' +
    esc(YO.usuario) + '</span>');
  if (ver && ver.indexOf("__") !== 0) piezas.push('<span class="cab-version">' +
    esc(ver) + '</span>');
  piezas.push('<span class="cab-datos">datos al ' +
    esc(D.publicado || D.generado || "") + '</span>');
  der.innerHTML = piezas.join('<span class="cab-sep"> · </span>');
}

function pintarNav(activa){
  var n = document.getElementById("nav");
  if (!n) return;
  var junto = hayRegistro();
  if (!junto) {
    n.innerHTML = HOJAS.map(function(h){
      return '<a href="' + h.arch + '" data-hoja="' + h.id + '"' +
        (h.id === activa ? ' class="activa"' : '') + '>' + esc(h.nombre) + '</a>';
    }).join("");
    return;
  }
  var gActivo = grupoDe(activa);
  n.innerHTML = GRUPOS.filter(function(g){
    return g.hojas.some(function(id){ return window.REGISTRO[id] && puedeVer(id); });
  }).map(function(g){
    var primera = g.hojas.filter(function(id){
      return window.REGISTRO[id] && puedeVer(id); })[0];
    return '<a href="#' + primera + '" data-hoja="' + primera + '"' +
      (g === gActivo ? ' class="activa"' : '') + '>' + esc(g.nombre) + '</a>';
  }).join("");
  n.querySelectorAll("a").forEach(function(a){
    a.addEventListener("click", function(e){
      e.preventDefault();
      irAHoja(a.getAttribute("data-hoja"));
    });
  });
  pintarSubnav(activa);
}

function pintarSubnav(activa){
  var s = document.getElementById("subnav");
  if (!s) return;
  var g = grupoDe(activa);
  var vivas = g ? g.hojas.filter(function(id){
    return window.REGISTRO[id] && puedeVer(id); }) : [];
  if (!g || vivas.length < 2) { s.innerHTML = ""; s.style.display = "none"; return; }
  s.style.display = "";
  s.innerHTML = vivas.map(function(id){
    var h = HOJAS.filter(function(x){ return x.id === id; })[0] || {nombre: id};
    return '<a href="#' + id + '" data-hoja="' + id + '"' +
      (id === activa ? ' class="activa"' : '') + '>' + esc(h.nombre) + '</a>';
  }).join("");
  s.querySelectorAll("a").forEach(function(a){
    a.addEventListener("click", function(e){
      e.preventDefault();
      irAHoja(a.getAttribute("data-hoja"));
    });
  });
}

var REDIRIGE = {"ventas-kpi": "asesores"};
function irAHoja(id){
  id = REDIRIGE[id] || id;
  var H = window.REGISTRO[id];
  if (!H || !puedeVer(id)) return;
  window.HOJA = H;
  document.title = (H.nombre || "Cockpit") + " · Habitat Control";
  var nom = document.getElementById("hoja-nombre");
  if (nom) nom.textContent = H.nombre || "";
  pintarCabDer(H);
  pintarNav(id);
  if (location.hash !== "#" + id) history.replaceState(null, "", "#" + id);
  pintarFuentes(H.fuentes);
  pintar();
  window.scrollTo({top: 0, behavior: "instant"});
}

function pintarFuentes(cuales){
  var f = document.getElementById("fuentes");
  if (!f) return;
  var quiere = cuales || ["AXION"];
  var h = '<span class="fuentes-rotulo">Fuentes de esta hoja</span>';
  (D.fuentes || []).filter(function(x){
    return quiere.some(function(n){ return String(x.nombre).toUpperCase().indexOf(n) >= 0; });
  }).forEach(function(x){
    var dd = diasDesde(x.fecha);
    var cls = !x.conectada ? "mal" : (dd !== null && dd >= 3 ? "viejo" : "ok");
    h += '<span class="fuente"><i class="punto ' + cls + '"></i>' + esc(x.nombre) +
         ' <span class="cuando">' + esc(x.fecha || "sin lectura") + '</span></span>';
  });
  f.innerHTML = h + '<span class="sello" id="sello" style="display:none"></span>';
}
function diasDesde(f){
  if (!f) return null;
  var t = Date.parse(String(f).replace(" ", "T"));
  return isNaN(t) ? null : Math.floor((Date.now() - t) / 86400000);
}
function sello(texto, destinoId){
  var s = document.getElementById("sello");
  if (!s) return;
  if (!texto) { s.style.display = "none"; return; }
  s.style.display = ""; s.textContent = texto;
  s.classList.toggle("clicable", !!destinoId);
  s.onclick = destinoId ? function(){
    var d = document.getElementById(destinoId);
    if (d) d.scrollIntoView({behavior: "smooth", block: "start"});
  } : null;
}

function avisoMesEnCurso(){
  var ms = ((D.flujo || {}).meses) || [];
  var enc = null;
  for (var i = 0; i < ms.length; i++) if (ms[i].en_curso) { enc = ms[i]; break; }
  if (!enc || String(enc.mes) !== String(P)) return "";
  var f = String(D.publicado || D.generado || "").slice(0, 10);
  var t = f.split("-");
  if (t.length < 3) return "";
  var dia = Number(t[2]), dias = new Date(Number(t[0]), Number(t[1]), 0).getDate();
  if (!dia || !dias) return "";
  return '<p class="linea-meta"><b>' + enc.etiqueta + '</b> · día ' + dia +
    ' de ' + dias + ' · data al ' + f + '</p>';
}

function pintar(){
  var abiertos = [].slice.call(document.querySelectorAll(
    '[data-abre][aria-expanded="true"]')).map(function(el){
      return el.getAttribute("data-abre"); });
  var y = window.scrollY || document.documentElement.scrollTop || 0;
  modalSoltar(true);

  var M = D.meses[P] || D.meses["None"];
  var H = window.HOJA || {};
  ajustarFiltroArea(M, H);
  ajustarFiltroTipo(M, H);
  ajustarFiltroAsesor(M, H);
  ajustarFiltroBanco(M, H);
  ajustarFiltroRSObra(H);
  ajustarFiltroPeriodo(H);
  ajustarFiltroFechas(H);
  ajustarFiltroFuente(M, H);
  ajustarBandaFiltros();
  resumirFiltros();
  document.getElementById("hoja").innerHTML =
    avisoMesEnCurso() + (H.pintar ? H.pintar(M, D) : "");
  conectarAbribles();
  if (H.conectar) H.conectar(M, D);
  medirFiltrosTabla();
  var lista = document.querySelector("#hoja .st-lista");
  if (lista) modalMostrar(lista, null, true);

  abiertos.forEach(function(id){
    var el = document.querySelector('[data-abre="' + id + '"]');
    if (el && el.getAttribute("aria-expanded") !== "true") alternar(el, id);
  });
  if (y) window.scrollTo(0, y);
}

function armarSelectorFecha(sp){
  var pills = document.getElementById("pills-anio"), sm = document.getElementById("f-mes");
  if (!pills || !sm) return;

  var porAnio = {}, anios = [], hist = null;
  [].slice.call(sp.options).forEach(function(o){
    if (o.textContent === "Todos los años") { hist = o.value; return; }
    var m = /^(\d{4}) · (.+)$/.exec(o.textContent);
    if (!m) return;
    var anio = m[1], resto = m[2];
    if (!porAnio[anio]) { porAnio[anio] = {full: null, meses: []}; anios.push(anio); }
    if (resto === "Acumulado del año" || resto === "Año completo")
      porAnio[anio].full = {valor: o.value, etiqueta: resto};
    else
      porAnio[anio].meses.push({valor: o.value, etiqueta: resto});
  });
  anios.sort(function(a, b){ return b - a; });

  function pintarMes(anio){
    sm.innerHTML = "";
    var A = porAnio[anio];
    if (A.full){
      var o = document.createElement("option");
      o.value = A.full.valor; o.textContent = A.full.etiqueta;
      sm.appendChild(o);
    }
    A.meses.forEach(function(mm){
      var o = document.createElement("option");
      o.value = mm.valor; o.textContent = mm.etiqueta;
      sm.appendChild(o);
    });
  }
  function elegir(valor){
    sp.value = valor;
    sp.dispatchEvent(new Event("change"));
  }
  var sa = document.getElementById("f-anio-m");
  if (!sa) {
    sa = document.createElement("select");
    sa.id = "f-anio-m"; sa.className = "solo-movil"; sa.setAttribute("aria-label", "Año");
    pills.parentNode.insertBefore(sa, pills);
  }
  function marcarActivo(clave){
    [].slice.call(pills.children).forEach(function(b){
      b.classList.toggle("activo", b.getAttribute("data-anio") === clave);
    });
    if (sa) sa.value = clave;
  }

  anios.forEach(function(anio){
    var b = document.createElement("button");
    b.type = "button"; b.className = "pill-anio"; b.textContent = anio;
    b.setAttribute("data-anio", anio);
    b.addEventListener("click", function(){
      if (b.classList.contains("activo")) return;
      marcarActivo(anio);
      pintarMes(anio);
      var A = porAnio[anio];
      elegir(A.full ? A.full.valor : A.meses[0].valor);
    });
    pills.appendChild(b);
  });
  if (hist !== null){
    var bh = document.createElement("button");
    bh.type = "button"; bh.className = "pill-anio"; bh.textContent = "Todos";
    bh.setAttribute("data-anio", "hist");
    bh.addEventListener("click", function(){
      if (bh.classList.contains("activo")) return;
      marcarActivo("hist");
      sm.innerHTML = '<option value="' + esc(hist) + '">Todos los años</option>';
      elegir(hist);
    });
    pills.appendChild(bh);
  }
  sa.innerHTML = "";
  anios.forEach(function(anio){
    var oa = document.createElement("option");
    oa.value = anio; oa.textContent = anio; sa.appendChild(oa);
  });
  if (hist !== null){
    var oh = document.createElement("option");
    oh.value = "hist"; oh.textContent = "Todos los años"; sa.appendChild(oh);
  }
  sa.addEventListener("change", function(){
    var pb = pills.querySelector('[data-anio="' + sa.value + '"]');
    if (pb) pb.click();
  });
  sm.addEventListener("change", function(){ elegir(sm.value); });

  marcarActivo(anios[0]);
  pintarMes(anios[0]);
  sm.value = sp.value;
}

function ajustarFiltroTipo(M, H){
  var caja = document.getElementById("caja-tipo"), st = document.getElementById("f-tipo");
  if (!caja || !st) return;
  var usa = (H.filtros || []).indexOf("tipo") >= 0;
  caja.style.display = usa ? "" : "none";
  if (!usa) { TIPO = ""; return; }
  var lista = (D.tipos_filtro || []).slice();
  if (!lista.length) { caja.style.display = "none"; TIPO = ""; return; }
  var previo = st.value;
  st.innerHTML = '<option value="">Todos los tipos</option>' +
    lista.map(function(t){ return '<option value="' + esc(t) + '">' + esc(t) + '</option>'; }).join("");
  st.value = lista.indexOf(previo) >= 0 ? previo : "";
  TIPO = st.value;
}

var DESDE = "", HASTA = "";

var FUENTE = "";

function ajustarFiltroFuente(M, H){
  var caja = document.getElementById("caja-fuente");
  var sv = document.getElementById("f-fuente");
  if (!caja || !sv) return;
  var usa = (H.filtros || []).indexOf("fuente") >= 0;
  caja.style.display = usa ? "" : "none";
  if (!usa) { FUENTE = ""; return; }
  var vistas = {};
  filasCRM(D, P).forEach(function (f) {
    (f.etiquetas || []).forEach(function (x) { vistas[x] = 1; });
  });
  var lista = Object.keys(vistas).sort();
  if (!lista.length) { caja.style.display = "none"; FUENTE = ""; return; }
  var previo = sv.value;
  sv.innerHTML = '<option value="">Todas las fuentes</option>' +
    lista.map(function (x) {
      return '<option value="' + esc(x) + '">' + esc(x) + '</option>';
    }).join("") + '<option value="(sin etiqueta)">(sin etiqueta)</option>';
  sv.value = (lista.indexOf(previo) >= 0 || previo === "(sin etiqueta)")
    ? previo : "";
  FUENTE = sv.value;
}

function ajustarFiltroFechas(H){
  var caja = document.getElementById("caja-fechas");
  if (!caja) return;
  var usa = (H.filtros || []).indexOf("fechas") >= 0;
  caja.style.display = usa ? "" : "none";
  if (!usa) { DESDE = ""; HASTA = ""; return; }
  var d = document.getElementById("f-desde"), h = document.getElementById("f-hasta");
  if (d) d.value = DESDE;
  if (h) h.value = HASTA;
}

function ajustarFiltroAsesor(M, H){
  var caja = document.getElementById("caja-asesor"), sv = document.getElementById("f-asesor");
  if (!caja || !sv) return;
  var usa = (H.filtros || []).indexOf("asesor") >= 0;
  caja.style.display = usa ? "" : "none";
  if (!usa) { ASESOR = ""; return; }
  var lista = (D.asesores_filtro || []).slice();
  if (!lista.length) { caja.style.display = "none"; ASESOR = ""; return; }
  var previo = sv.value;
  sv.innerHTML = '<option value="">Todos los vendedores</option>' +
    lista.map(function(a){ return '<option value="' + esc(a) + '">' + esc(a) + '</option>'; }).join("");
  sv.value = lista.indexOf(previo) >= 0 ? previo : "";
  ASESOR = sv.value;
}

function entraAsesor(nombre){
  if (!ASESOR) return true;
  return String(nombre || "").trim() === ASESOR;
}

function ajustarFiltroBanco(M, H){
  var caja = document.getElementById("caja-banco"), sb = document.getElementById("f-banco");
  if (!caja || !sb) return;
  var usa = (H.filtros || []).indexOf("banco") >= 0;
  caja.style.display = usa ? "" : "none";
  if (!usa) { BANCO = ""; return; }
  var vistos = {}, lista = [];
  ((((D || {}).libro || {}).filas || {}).cuenta || []).forEach(function(c){
    var b = String(c || "").split(" - ")[0] || "(sin cuenta)";
    if (!vistos[b]) { vistos[b] = true; lista.push(b); }
  });
  lista.sort(ordenBanco);
  if (!lista.length) { caja.style.display = "none"; BANCO = ""; return; }
  var previo = sb.value;
  sb.innerHTML = '<option value="">Todos los bancos</option>' +
    lista.map(function(b){ return '<option value="' + esc(b) + '">' + esc(b) + '</option>'; }).join("");
  sb.value = lista.indexOf(previo) >= 0 ? previo : "";
  BANCO = sb.value;
}

var ORDEN_CUENTAS = [
  "BCP - CORPORACION HABITAT SAC", "BCP - CONSTRUCTORA VELASCO LEON SAC",
  "BCP - YEAN WILLIAM VELASCO LEON",
  "BBVA - HABITAT BIENES RAICES EIRL", "BBVA - CORPORACION HABITAT SAC",
  "BBVA - HABITAT LEON SAC",
  "CMAC HUANCAYO - CORPORACION HABITAT SAC - GLORIA",
  "CMAC HUANCAYO - CORPORACION HABITAT SAC - YEAN",
  "CMAC HUANCAYO - HABITAT BIENES RAICES EIRL",
  "CMAC HUANCAYO - ESCALAR Y HABITAT GRUPO INMOBILIARIO SAC",
  "EFECTIVO"];
var ORDEN_BANCOS = ["BCP", "BBVA", "CMAC HUANCAYO", "EFECTIVO"];
function _normCta(s){
  return String(s || "").toUpperCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "")
    .replace(/\s+/g, " ").trim();
}
function _rangoBanco(b){
  b = _normCta(b);
  if (!b || b === "SIN BANCO" || b === "(SIN CUENTA)") return 99;
  var i = ORDEN_BANCOS.indexOf(b);
  return i < 0 ? 90 : i;
}
function ordenCuenta(a, b){
  var na = _normCta(a), nb = _normCta(b);
  var ba = _rangoBanco(na.split(" - ")[0]), bb = _rangoBanco(nb.split(" - ")[0]);
  if (ba !== bb) return ba - bb;
  var ia = ORDEN_CUENTAS.indexOf(na), ib = ORDEN_CUENTAS.indexOf(nb);
  ia = ia < 0 ? 999 : ia; ib = ib < 0 ? 999 : ib;
  if (ia !== ib) return ia - ib;
  return na < nb ? -1 : (na > nb ? 1 : 0);
}
function ordenBanco(a, b){
  var ra = _rangoBanco(a), rb = _rangoBanco(b);
  if (ra !== rb) return ra - rb;
  return _normCta(a) < _normCta(b) ? -1 : 1;
}

function entraBanco(cuenta){
  if (!BANCO) return true;
  return (String(cuenta || "").split(" - ")[0] || "(sin cuenta)") === BANCO;
}

function ajustarFiltroArea(M, H){
  var caja = document.getElementById("caja-area"), sa = document.getElementById("f-area");
  if (!caja || !sa) return;
  var usa = (H.filtros || []).indexOf("area") >= 0;
  caja.style.display = usa ? "" : "none";
  if (!usa) { AREA = ""; return; }
  var opciones = (typeof H.areas === "function") ? H.areas(M, D) : [];
  if (!opciones.length) { caja.style.display = "none"; AREA = ""; return; }
  var previo = sa.value;
  sa.innerHTML = '<option value="">Todas las áreas</option>' +
    opciones.map(function(o){
      return '<option value="' + esc(o.area) + '">' + esc(o.area) + ' · ' + o.n + '</option>';
    }).join("");
  var areas = opciones.map(function(o){ return o.area; });
  sa.value = areas.indexOf(previo) >= 0 ? previo : "";
  AREA = sa.value;
}

function ajustarFiltroRSObra(H){
  var cRS = document.getElementById("caja-rs"), cOb = document.getElementById("caja-obra");
  if (!cRS || !cOb) return;
  var oculto = H.sinRazonObra === true;
  cRS.style.display = oculto ? "none" : "";
  cOb.style.display = oculto ? "none" : "";
  if (oculto) { RS = ""; OBRA = ""; }
}

function ajustarBandaFiltros(){
  var fil = document.getElementById("filtros");
  var barra = document.querySelector(".barra-fija");
  if (!fil || !barra) return;
  var alguno = [].some.call(fil.children, function(c){
    return c.classList.contains("filtro") && window.getComputedStyle(c).display !== "none";
  });
  barra.classList.toggle("sin-filtros", !alguno);
  if (!alguno) {
    barra.classList.remove("filtros-abiertos");
    var t = document.getElementById("filtros-toggle");
    if (t) t.setAttribute("aria-expanded", "false");
  }
}

function ajustarFiltroPeriodo(H){
  var caja = document.querySelector(".filtro-fecha");
  if (!caja) return;
  var oculto = H.sinPeriodo === true;
  caja.style.display = oculto ? "none" : "";
}

function conectarAbribles(raiz){
  (raiz || document).querySelectorAll(".abrible").forEach(function(el){
    if (el.getAttribute("data-enganchado") === "1") return;
    el.setAttribute("data-enganchado", "1");
    var f = function(ev){
      if (ev) ev.stopPropagation();      // no dispares al abrible que lo contiene
      alternar(el, el.getAttribute("data-abre"));
    };
    el.addEventListener("click", f);
    el.addEventListener("keydown", function(e){
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); f(e); }
    });
  });
}
function filtroVisible(s){
  var c = s && s.closest ? s.closest(".filtro") : null;
  return !!c && c.style.display !== "none";
}

function resumirFiltros(){
  var r = document.getElementById("ft-resumen");
  if (!r) return;
  var partes = [];
  ["f-periodo", "f-rs", "f-obra", "f-tipo", "f-asesor", "f-area"].forEach(function(id){
    var s = document.getElementById(id);
    if (!s || !s.options.length || !filtroVisible(s)) return;
    var o = s.options[s.selectedIndex];
    if (o) partes.push((o.textContent || "").trim());
  });
  r.textContent = partes.join(" · ");
}

(function(){
  var b = document.getElementById("filtros-toggle");
  var barra = document.querySelector(".barra-fija");
  var panel = document.getElementById("filtros");
  if (!b || !barra || !panel) return;
  function poner(on){
    barra.classList.toggle("filtros-abiertos", on);
    b.setAttribute("aria-expanded", on ? "true" : "false");
    b.querySelector(".ft-rotulo").textContent = on ? "Ocultar" : "Filtros";
    b.querySelector(".ft-flecha").textContent = on ? "▴" : "▾";
  }
  b.addEventListener("click", function(){
    poner(!barra.classList.contains("filtros-abiertos"));
  });
  panel.addEventListener("change", function(){
    if (getComputedStyle(b).display !== "none") poner(false);
  });
})();

function tarjetizar(tabla){
  if (tabla.getAttribute("data-tarjetas")) return;
  tabla.setAttribute("data-tarjetas", "1");
  var thead = tabla.tHead || tabla.querySelector("thead");
  if (!thead) return;
  var ths = [].slice.call(thead.querySelectorAll("th"));
  if (!ths.length) return;
  var rot = ths.map(function(th){
    var corto = th.getAttribute("data-m");
    if (corto) return corto;
    var c = th.cloneNode(true);
    [].slice.call(c.querySelectorAll("br")).forEach(function(b){
      b.parentNode.replaceChild(document.createTextNode(" · "), b);
    });
    return (c.textContent || "").replace(/\s+/g, " ").trim()
      .replace(/^·\s*/, "").replace(/\s*·$/, "");
  });
  var iTit = -1, iObra = -1, iUni = -1;
  rot.forEach(function(r, i){
    var t = r.toLowerCase();
    if (iTit < 0 && /cliente|nombre|\blead\b|asesor|vendedor/.test(t)) iTit = i;
    if (iObra < 0 && /^(obra|proyecto)\b/.test(t)) iObra = i;
    if (iUni < 0 && /unidad/.test(t)) iUni = i;
  });
  if (iTit < 0) iTit = (ths[0] && ths[0].classList.contains("num")) ? -1 : 0;
  var filas = [].slice.call(tabla.tBodies.length ? tabla.tBodies[0].rows : []);
  tabla.classList.add("tarjetas");
  filas.forEach(function(tr){
    var celdas = [].slice.call(tr.cells), j = 0;
    celdas.forEach(function(td){
      var i = j; j += td.colSpan || 1;
      var r = rot[i] || "";
      if (i === iObra && iUni >= 0) r = (rot[iObra] || "Obra") + " · " + (rot[iUni] || "Unidad");
      td.setAttribute("data-rot", r);
      td.style.removeProperty("width");
      if ((td.textContent || "").trim() === "" && !td.querySelector("span,div,b,a")) td.classList.add("tj-vacia");
      if (i === iTit && celdas.length > 1) td.classList.add("tj-titulo");
    });
    if (iObra >= 0 && iUni >= 0 && celdas[iObra] && celdas[iUni] && celdas.length > Math.max(iObra, iUni)) {
      var u = (celdas[iUni].textContent || "").trim();
      if (u) {
        var s = document.createElement("span");
        s.className = "tj-unidad"; s.textContent = " · " + u;
        celdas[iObra].appendChild(s);
      }
      celdas[iUni].classList.add("tj-oculta");
    }
  });
}
function tarjetizarTodo(raiz){
  [].slice.call((raiz || document).querySelectorAll("table.datos")).forEach(tarjetizar);
}

function quitarHallazgos(raiz){
  if ((window.HOJA || {}).id === "estado") return;
  [].slice.call((raiz || document).querySelectorAll(".hallazgo")).forEach(function(h){
    h.remove();
  });
}

(function(){
  if (!window.MutationObserver) return;
  var ob = new MutationObserver(function(muts){
    var hay = false;
    muts.forEach(function(m){ if (m.addedNodes && m.addedNodes.length) hay = true; });
    if (hay) { tarjetizarTodo(document); quitarHallazgos(document); }
  });
  document.addEventListener("DOMContentLoaded", function(){
    tarjetizarTodo(document);
    quitarHallazgos(document);
    ob.observe(document.body, {childList: true, subtree: true});
  });
})();

function lineaFiltros(caja, id){
  var partes = [];
  [["f-periodo", "Período"], ["f-rs", "Razón social"], ["f-obra", "Obra"],
   ["f-tipo", "Tipo"], ["f-asesor", "Vendedor"], ["f-area", "Área"]
  ].forEach(function(par){
    var s = document.getElementById(par[0]);
    if (!s || !s.options.length || !filtroVisible(s)) return;
    var o = s.options[s.selectedIndex];
    if (!o) return;
    var v = (o.textContent || "").trim();
    if (/^(Todas|Todos)\b/i.test(v)) return;
    partes.push(par[1] + ": <b>" + esc(v) + "</b>");
  });

  var ov = caja.querySelector("[data-ventana]");
  var aviso = ov ? ov.getAttribute("data-ventana")
                 : ((window.HOJA || {}).ventanas || {})[id] || "";
  if (!partes.length && !aviso) return "";
  return '<div class="filtros-panel">' +
    (aviso ? '<b class="ojo">' + esc(aviso) + '</b>' +
             (partes.length ? ' <span class="sep">·</span> ' : "") : "") +
    partes.join(" <span class=\"sep\">·</span> ") +
    '</div>';
}

var REFILTRO = {};
function refiltro(id){ return REFILTRO[id] || ""; }

function filtroAnioPanel(caja, id){
  if (id === "obra") return;
  if (caja.querySelector(".fd-anio") || caja.querySelector(".fd-mes")) return;
  var tablas = caja.querySelectorAll("table");
  if (tablas.length !== 1) return;
  var tabla = tablas[0];
  var ths = tabla.querySelectorAll("thead th");
  var todas = [].slice.call(tabla.querySelectorAll("tbody tr"));
  var pieT = todas.filter(function(tr){
    return tr.classList.contains("total") || tr.classList.contains("gt-total");
  });
  var filas = todas.filter(function(tr){ return pieT.indexOf(tr) < 0; });
  if (filas.length < 2) return;

  var col = -1;
  for (var c = 0; c < (ths.length || 1); c++){
    for (var r = 0; r < filas.length; r++){
      var td = filas[r].children[c];
      var tx = td ? (td.textContent || "").trim() : "";
      if (!tx || tx === "—") continue;
      if (/^\d{4}-\d{2}/.test(tx)) col = c;
      break;
    }
    if (col >= 0) break;
  }
  if (col < 0) return;

  var anios = {}, dato = [];
  filas.forEach(function(tr){
    var td = tr.children[col];
    var a = td ? (td.textContent || "").trim().slice(0, 4) : "";
    a = /^\d{4}$/.test(a) ? a : "";
    dato.push(a);
    if (a) anios[a] = (anios[a] || 0) + 1;
  });
  var ks = Object.keys(anios).sort().reverse();
  if (ks.length < 2) return;                    /* un solo anio: no hay que elegir */

  var colNum = -1;
  for (var c2 = (filas[0].children.length - 1); c2 >= 0; c2--){
    var t0 = (filas[0].children[c2].textContent || "").replace(/[^\d.,\-]/g, "");
    if (t0 && /\d/.test(t0)) { colNum = c2; break; }
  }
  var num = function(tr){
    if (colNum < 0) return 0;
    var s = (tr.children[colNum].textContent || "").replace(/[^\d.,\-]/g, "").replace(/,/g, "");
    var v = parseFloat(s);
    return isNaN(v) ? 0 : v;
  };
  var totalTodo = filas.reduce(function(s, tr){ return s + num(tr); }, 0);

  var sel = document.createElement("div");
  sel.className = "refiltro";
  var opc = '<option value="">Todos los años · ' + filas.length + '</option>';
  ks.forEach(function(a){ opc += '<option value="' + a + '">' + a + ' · ' + anios[a] + '</option>'; });
  sel.innerHTML = '<label>Año dentro de este panel <select class="fd-anio-dom">' +
    opc + '</select></label> <span class="fd-cuenta"></span>';
  var ancla = caja.querySelector(".regla") || caja.querySelector("h3");
  if (ancla) ancla.insertAdjacentElement("afterend", sel);
  else caja.insertBefore(sel, caja.firstChild);

  var cuenta = sel.querySelector(".fd-cuenta");
  var resumen = caja.querySelector(".resumen-det .suma") ||
                caja.querySelector(".resumen-det");
  var s = sel.querySelector("select");
  s.addEventListener("click", function(e){ e.stopPropagation(); });
  s.addEventListener("change", function(e){
    e.stopPropagation();
    var a = s.value, vistas = 0, suma = 0;
    filas.forEach(function(tr, i){
      var entra = !a || dato[i] === a;
      tr.style.display = entra ? "" : "none";
      if (entra) { vistas++; suma += num(tr); }
    });
    pieT.forEach(function(tr){ tr.style.display = a ? "none" : ""; });
    cuenta.textContent = a
      ? vistas + " de " + filas.length + " filas" +
        (colNum >= 0 && totalTodo ? " · suman " + suma.toLocaleString("es-PE",
          {minimumFractionDigits: 2, maximumFractionDigits: 2}) : "")
      : "";
    if (resumen && a) resumen.setAttribute("data-recortado", "1");
    else if (resumen) resumen.removeAttribute("data-recortado");
  });
}

var GT = {};
var GT_SVG_G = '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M2.5 13.5h11M4.75 11V7.5M8 11V4.5M11.25 11V8.75" ' +
  'stroke="currentColor" stroke-width="1.8" stroke-linecap="round" fill="none"/></svg>';
var GT_SVG_T = '<svg viewBox="0 0 16 16" aria-hidden="true"><rect x="2.5" y="3" width="11" height="10" rx="1.6" ' +
  'stroke="currentColor" stroke-width="1.5" fill="none"/><path d="M2.5 6.6h11M6.6 6.6V13" stroke="currentColor" ' +
  'stroke-width="1.5" fill="none"/></svg>';

function gtBotones(clave){
  var t = GT[clave] === "tabla";
  var b = function(v, on, rot, svg){
    return '<button type="button" class="gt-btn' + (on ? ' on' : '') + '" data-gt-clave="' + clave +
      '" data-gt-v="' + v + '" aria-pressed="' + (on ? 'true' : 'false') + '" title="' + rot +
      '" aria-label="' + rot + '">' + svg + '</button>';
  };
  return '<div class="gt-botones" role="group" aria-label="Ver como">' +
    b("graf", !t, "Ver como gráfico", GT_SVG_G) + b("tabla", t, "Ver como tabla", GT_SVG_T) + '</div>';
}

function gtCaja(clave, graf, tabla){
  var t = GT[clave] === "tabla";
  return '<div class="gt" data-gt="' + clave + '">' +
    '<div class="gt-graf"' + (t ? ' hidden' : '') + '>' + graf + '</div>' +
    '<div class="gt-tabla"' + (t ? '' : ' hidden') + '>' + tabla + '</div></div>';
}

function gtTabla(cols, filas, total){
  var celda = function(x, i, fuerte){
    var v = fuerte ? '<b>' + x + '</b>' : x;
    return i === 0 ? '<td class="obra">' + v + '</td>' : '<td class="num">' + v + '</td>';
  };
  return '<div class="envoltura-tabla"><table class="datos gt-t"><thead><tr>' +
    cols.map(function(c){ return '<th' + (c.num ? ' class="num"' : '') + '>' + esc(c.rot) + '</th>'; }).join('') +
    '</tr></thead><tbody>' +
    filas.map(function(f){
      return '<tr>' + f.map(function(x, i){ return celda(x, i, false); }).join('') + '</tr>';
    }).join('') +
    (total ? '<tr class="gt-total">' + total.map(function(x, i){ return celda(x, i, true); }).join('') + '</tr>' : '') +
    '</tbody></table></div>';
}

document.addEventListener("click", function(ev){
  var b = ev.target && ev.target.closest ? ev.target.closest(".gt-btn") : null;
  if (!b) return;
  ev.stopPropagation();
  var k = b.getAttribute("data-gt-clave"), v = b.getAttribute("data-gt-v");
  GT[k] = v;
  var tabla = (v === "tabla");
  document.querySelectorAll('.gt[data-gt="' + k + '"]').forEach(function(g){
    var gr = g.querySelector(":scope > .gt-graf"), tb = g.querySelector(":scope > .gt-tabla");
    if (gr) gr.hidden = tabla;
    if (tb) tb.hidden = !tabla;
  });
  document.querySelectorAll('[data-gt-graf="' + k + '"]').forEach(function(e){ e.hidden = tabla; });
  document.querySelectorAll('[data-gt-tabla="' + k + '"]').forEach(function(e){ e.hidden = !tabla; });
  document.querySelectorAll('.gt-btn[data-gt-clave="' + k + '"]').forEach(function(x){
    var on = x.getAttribute("data-gt-v") === v;
    x.classList.toggle("on", on);
    x.setAttribute("aria-pressed", on ? "true" : "false");
  });
}, true);

function modalSerie(ch){
  var serie;
  try { serie = JSON.parse(decodeURIComponent(ch.getAttribute("data-serie") || "")); }
  catch (e) { return null; }
  if (!serie || !serie.length) return null;
  var fmt = ch.getAttribute("data-fmt") || "soles";
  var rot = ch.getAttribute("data-rot") || "Monto";
  var eje = ch.getAttribute("data-eje") || "Mes";
  var largo = function(v){ return fmt === "pct" ? fmt1(v) + "%" : (fmt === "n" ? ent(v) : soles(v)); };
  var corto = function(v){
    if (fmt === "pct") return fmt1(v) + "%";
    if (fmt === "n") return ent(v);
    var a = Math.abs(v);
    return (v < 0 ? "−" : "") + (a >= 995000 ? (a / 1e6).toFixed(2) + "M" : Math.round(a / 1e3) + "K");
  };
  var xRot = ch.getAttribute("data-extra-rot") || "";
  var xFmt = ch.getAttribute("data-extra-fmt") || "soles";
  var hayX = !!xRot && serie.some(function(s){ return s.length > 4; });
  var largoX = function(v){ return xFmt === "pct" ? fmt1(v) + "%" : (xFmt === "n" ? ent(v) : soles(v)); };
  var totX = 0;
  serie.forEach(function(s){ totX += Number(s[4]) || 0; });
  var mx = 1, tot = 0;
  serie.forEach(function(s){ mx = Math.max(mx, Math.abs(s[1])); tot += s[1]; });
  var graf = '<div class="d-grafico ancho gt-mini">' + serie.map(function(s){
    return '<div class="d-mes' + (s[2] ? ' actual' : '') + '">' +
      '<div class="d-bval"><b>' + corto(s[1]) + '</b></div>' +
      '<div class="d-barras"><i class="d-b' + (s[3] ? ' neg' : '') + '" style="height:' +
      Math.max(3, Math.round(132 * Math.abs(s[1]) / mx)) + 'px"></i></div>' +
      '<span>' + esc(String(s[0])) + '</span></div>';
  }).join('') + '</div>';
  var filas = serie.map(function(s){
    return hayX ? [esc(String(s[0])), largoX(Number(s[4]) || 0), largo(s[1])]
                : [esc(String(s[0])), largo(s[1])]; });
  var total = hayX ? ["Total", largoX(totX), (fmt === "pct") ? "" : largo(tot)]
                   : ((fmt === "pct") ? null : ["Total", largo(tot)]);
  var colsS = hayX ? [{rot: eje}, {rot: xRot, num: true}, {rot: rot, num: true}]
                   : [{rot: eje}, {rot: rot, num: true}];
  var div = document.createElement("div");
  div.className = "modal-serie";
  div.innerHTML = '<div class="gt-cab"><span class="overline">' + esc(rot) + ', ' +
    (eje === "Año" ? "año a año" : "mes a mes") + '</span>' + gtBotones("serie") + '</div>' +
    gtCaja("serie", graf, gtTabla(colsS, filas, total));
  return div;
}

var MODAL = {fondo: null, caja: null, cuerpo: null, hojaTxt: null, titulo: null,
             filtros: null, nodo: null, marca: null, el: null, lista: false,
             origenes: [], extra: null};

function modalArmar(){
  if (MODAL.fondo) return;
  var f = document.createElement("div");
  f.className = "modal-fondo";
  f.hidden = true;
  f.innerHTML =
    '<div class="modal-caja" role="dialog" aria-modal="true" aria-labelledby="modal-titulo" tabindex="-1">' +
      '<div class="modal-cab">' +
        '<div class="modal-cab-txt">' +
          '<span class="modal-hoja"></span>' +
          '<h2 class="modal-titulo" id="modal-titulo"></h2>' +
          '<div class="modal-filtros"></div>' +
        '</div>' +
        '<button type="button" class="modal-x" aria-label="Cerrar (Esc)" title="Cerrar (Esc)">' +
          '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3.5 3.5l9 9M12.5 3.5l-9 9" ' +
          'stroke="currentColor" stroke-width="1.8" stroke-linecap="round" fill="none"/></svg>' +
        '</button>' +
      '</div>' +
      '<div class="modal-cuerpo"></div>' +
    '</div>';
  document.body.appendChild(f);
  MODAL.fondo = f;
  MODAL.caja = f.querySelector(".modal-caja");
  MODAL.cuerpo = f.querySelector(".modal-cuerpo");
  MODAL.hojaTxt = f.querySelector(".modal-hoja");
  MODAL.titulo = f.querySelector(".modal-titulo");
  MODAL.filtros = f.querySelector(".modal-filtros");
  f.addEventListener("click", function(ev){ if (ev.target === f) modalCerrar(); });
  f.querySelector(".modal-x").addEventListener("click", function(ev){
    ev.stopPropagation(); modalCerrar();
  });
  document.addEventListener("keydown", function(ev){
    if (ev.key === "Escape" && MODAL.fondo && !MODAL.fondo.hidden) modalCerrar();
  });
}

function modalTitulo(nodo, el, esLista){
  var t = nodo.querySelector(esLista ? ":scope > .overline" : ":scope > h3");
  if (t) { t.classList.add("modal-origen"); MODAL.origenes.push(t); return t.innerHTML; }
  var s = el && el.querySelector(".d-preg, .overline, .st-nom, .obra");
  var txt = s ? s.textContent : (el ? el.textContent : "");
  txt = String(txt || "").replace(/\s+/g, " ").trim();
  return esc(txt.length > 90 ? txt.slice(0, 88) + "…" : (txt || "Detalle"));
}

function modalMostrar(nodo, el, esLista){
  modalArmar();
  modalSoltar(true);
  var marca = document.createComment("ventana");
  nodo.parentNode.insertBefore(marca, nodo);
  MODAL.cuerpo.appendChild(nodo);
  MODAL.nodo = nodo; MODAL.marca = marca; MODAL.el = el || null; MODAL.lista = !!esLista;
  var ch = (el && el.querySelector) ? el.querySelector(".d-chispa[data-serie]") : null;
  var extra = ch ? modalSerie(ch) : null;
  if (extra) { MODAL.cuerpo.insertBefore(extra, nodo); MODAL.extra = extra; }

  MODAL.caja.classList.toggle("ancha",
    !!(nodo.querySelector && nodo.querySelector("[data-modal-ancho]")));

  MODAL.hojaTxt.textContent = String(document.title || "").split("·")[0].trim();
  MODAL.titulo.innerHTML = modalTitulo(nodo, el, esLista);
  var fp = nodo.querySelector(":scope > .filtros-panel");
  if (fp) {
    fp.classList.add("modal-origen"); MODAL.origenes.push(fp);
    MODAL.filtros.innerHTML = fp.innerHTML;
    MODAL.filtros.hidden = false;
  } else {
    MODAL.filtros.innerHTML = "";
    MODAL.filtros.hidden = true;
  }

  MODAL.fondo.hidden = false;
  MODAL.cuerpo.scrollTop = 0;
  document.documentElement.classList.add("con-modal");
  void MODAL.fondo.offsetWidth;
  MODAL.fondo.classList.add("abierta");
  try { MODAL.caja.focus({preventScroll: true}); } catch (e) {}
}

function modalSoltar(sinFoco){
  if (!MODAL.fondo) return;
  var el = MODAL.el;
  MODAL.origenes.forEach(function(o){ o.classList.remove("modal-origen"); });
  MODAL.origenes = [];
  if (MODAL.extra && MODAL.extra.parentNode) MODAL.extra.parentNode.removeChild(MODAL.extra);
  MODAL.extra = null;
  if (MODAL.nodo) {
    if (MODAL.marca && MODAL.marca.parentNode) {
      MODAL.marca.parentNode.insertBefore(MODAL.nodo, MODAL.marca);
      MODAL.marca.parentNode.removeChild(MODAL.marca);
    } else if (MODAL.nodo.parentNode) {
      MODAL.nodo.parentNode.removeChild(MODAL.nodo);
    }
  }
  MODAL.nodo = MODAL.marca = MODAL.el = null;
  MODAL.lista = false;
  MODAL.caja.classList.remove("ancha");
  MODAL.titulo.innerHTML = ""; MODAL.filtros.innerHTML = ""; MODAL.hojaTxt.textContent = "";
  MODAL.fondo.classList.remove("abierta");
  MODAL.fondo.hidden = true;
  document.documentElement.classList.remove("con-modal");
  if (!sinFoco && el && document.contains(el)) {
    try { el.focus({preventScroll: true}); } catch (e) {}
  }
}

function modalCerrar(){
  if (!MODAL.nodo) { modalSoltar(); return; }
  if (MODAL.lista) {
    var x = MODAL.nodo.querySelector(".st-cerrar");
    if (x) x.click();
    modalSoltar();
    return;
  }
  var el = MODAL.el;
  if (el && el.getAttribute("aria-expanded") === "true")
    alternar(el, el.getAttribute("data-abre"));
  else modalSoltar();
}

function alternar(el, id){
  var caja = (MODAL.nodo && MODAL.el === el) ? MODAL.nodo
    : document.getElementById("det-" + id);
  if (!caja) return;
  var adentro = !!(MODAL.caja && MODAL.caja.contains(el));
  if (el.getAttribute("aria-expanded") === "true") {
    var enVentana = (MODAL.nodo === caja);
    if (enVentana) modalSoltar();
    caja.classList.remove("on"); caja.innerHTML = "";
    el.setAttribute("aria-expanded", "false");
    if (enVentana) return;
    var r = el.getBoundingClientRect();
    if (r.top < 0 || r.bottom > window.innerHeight)
      el.scrollIntoView({behavior: "smooth", block: "center"});
    return;
  }
  document.querySelectorAll('.abrible[aria-expanded="true"]').forEach(function (otro) {
    if (otro === el) return;
    var otroId = otro.getAttribute("data-abre");
    var otraCaja = otroId && document.getElementById("det-" + otroId);
    if (otraCaja && otraCaja.contains(el)) return;
    if (otraCaja && MODAL.nodo === otraCaja) modalSoltar(true);
    if (otraCaja) { otraCaja.classList.remove("on"); otraCaja.innerHTML = ""; }
    otro.setAttribute("aria-expanded", "false");
  });
  el.setAttribute("aria-expanded", "true");
  var clave = el.getAttribute("data-drill");
  var H = window.HOJA || {};
  var html = null;
  if (typeof H.detalle === "function") {
    try { html = H.detalle.call(H, id, el); }
    catch (e) {
      html = '<button class="cerrar">Cerrar</button>' +
        '<p><b>La hoja no pudo armar este detalle.</b><br>' + esc(e.message) + '</p>';
    }
  }
  caja.innerHTML = (html !== null && html !== undefined) ? html : detalleDrill(clave, id);
  filtroAnioPanel(caja, id);
  caja.querySelectorAll("[data-refiltra]").forEach(function(x){
    x.addEventListener("click", function(e){ e.stopPropagation(); });
    x.addEventListener("change", function(e){
      e.stopPropagation();
      REFILTRO[id] = x.value;
      var abierto = el.getAttribute("aria-expanded") === "true";
      if (abierto) { alternar(el, id); alternar(el, id); }
    });
  });
  var lf = lineaFiltros(caja, id);
  if (lf) {
    var h3 = caja.querySelector("h3");
    if (h3) h3.insertAdjacentHTML("afterend", lf);
    else caja.insertAdjacentHTML("afterbegin", lf);
  }
  caja.classList.add("on");
  caja.querySelectorAll(".cerrar").forEach(function(b){
    b.addEventListener("click", function(ev){ ev.stopPropagation(); alternar(el, id); });
  });
  conectarAbribles(caja);          // los abribles que trae el detalle adentro
  conectarFiltrosDetalle(caja, clave);
  if (adentro) caja.scrollIntoView({behavior: "smooth", block: "nearest"});
  else modalMostrar(caja, el, false);
}

function conectarFiltrosDetalle(caja, clave){
  var f = caja.querySelector(".filtros-det");
  if (!f || !clave) return;
  var repintar = function(){
    var cuerpo = caja.querySelector(".cuerpo-det");
    if (cuerpo) cuerpo.innerHTML = cuerpoDrill(clave, {
      obra: (caja.querySelector(".fd-obra") || {}).value || "",
      mes:  (caja.querySelector(".fd-mes") || {}).value || "",
      txt:  ((caja.querySelector(".fd-txt") || {}).value || "").trim().toLowerCase(),
      ase:  (caja.querySelector(".fd-ase") || {}).value || ""
    });
    acomodarResumen(caja);
  };
  f.querySelectorAll("select, input").forEach(function(x){
    x.addEventListener("change", repintar);
    x.addEventListener("input", repintar);
    x.addEventListener("click", function(e){ e.stopPropagation(); });
  });
  var enganchaTira = function(){
    caja.querySelectorAll(".tira-meses .tm").forEach(function(b){
      b.addEventListener("click", function(e){
        e.stopPropagation();
        var sm = caja.querySelector(".fd-mes");
        if (!sm) return;
        var k = b.getAttribute("data-mes");
        sm.value = (sm.value === k) ? "" : k;
        repintar();
      });
    });
  };
  var _rep = repintar;
  repintar = function(){ _rep(); enganchaTira(); };
  enganchaTira();

  var lim = caja.querySelector(".fd-limpiar");
  if (lim) lim.addEventListener("click", function(e){
    e.stopPropagation();
    f.querySelectorAll("select").forEach(function(s){ s.value = ""; });
    f.querySelectorAll("input").forEach(function(i){ i.value = ""; });
    repintar();
  });
  acomodarResumen(caja);
}

function detalleDrill(clave, id){
  var dr = drillActual(clave);
  if (!dr) return '<button class="cerrar">Cerrar</button>' +
    '<p>Este período no trae detalle para «' + esc(clave || id || "") + '».</p>';
  var iObra = colDe(dr, ["obra"]), iFecha = colDe(dr, ["fecha", "vence", "vencimiento", "inicio"]);
  var iAse = colDe(dr, ["asesor", "vendedor"]);
  var obras = [], meses = [], asesores = [];
  (dr.filas || []).forEach(function(r){
    if (iObra >= 0 && r[iObra] && obras.indexOf(r[iObra]) < 0) obras.push(r[iObra]);
    if (iFecha >= 0 && r[iFecha]) {
      var m = String(r[iFecha]).slice(0, 7);
      if (/^\d{4}-\d{2}$/.test(m) && meses.indexOf(m) < 0) meses.push(m);
    }
  });
  if (iAse >= 0) (dr.filas || []).forEach(function(r){
    var a = String(r[iAse] || "").trim();
    if (a && asesores.indexOf(a) < 0) asesores.push(a);
  });
  obras.sort(); meses.sort(); asesores.sort();
  var h = '<button class="cerrar">Cerrar</button><h3>' + esc(dr.titulo || "Detalle") + '</h3>' +
    (dr.regla ? '<div class="regla">' + esc(dr.regla) + '</div>' : '') +
    '<div class="cab-det"><div class="filtros-det">';
  if (obras.length > 1) h += selDet("fd-obra", "Obra", obras, OBRA);
  if (meses.length > 1) h += selDet("fd-mes", "Período", meses, "", mesLargo);
  if (asesores.length > 1) h += selDet("fd-ase", "Vendedor", asesores, ASESOR);
  h += '<label class="fd"><span>Buscar</span><input class="fd-txt" type="search" ' +
       'placeholder="cliente, unidad, asesor…"></label>' +
       '<button class="fd-limpiar" type="button">Limpiar</button></div>' +
       '<div class="resumen-slot"></div></div>' +
       '<div class="cuerpo-det">' +
       cuerpoDrill(clave, {obra: OBRA, mes: "", txt: "", ase: ASESOR}) + '</div>';
  return h;
}

function acomodarResumen(caja){
  var slot = caja.querySelector(".resumen-slot");
  var r = caja.querySelector(".cuerpo-det .resumen-det");
  if (!slot) return;
  slot.innerHTML = r ? r.outerHTML : "";
  if (r) r.parentNode.removeChild(r);
  var cab = caja.querySelector(".cab-det");
  if (cab) caja.style.setProperty("--alto-cab", cab.offsetHeight + "px");
}
var MES_LARGO = ["", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio",
                 "Agosto", "Setiembre", "Octubre", "Noviembre", "Diciembre"];
function mesLargo(v){
  var m = /^(\d{4})-(\d{2})$/.exec(String(v));
  return m ? (MES_LARGO[+m[2]] || v) + " " + m[1] : v;
}
function selDet(cls, rot, vals, sel, rotular){
  var h = '<label class="fd"><span>' + esc(rot) + '</span><select class="' + cls + '">' +
          '<option value="">Todas</option>';
  vals.forEach(function(v){
    h += '<option value="' + esc(v) + '"' + (v === sel ? " selected" : "") + '>' +
         esc(rotular ? rotular(v) : v) + '</option>';
  });
  return h + '</select></label>';
}
function cuerpoDrill(clave, f){
  var dr = drillActual(clave);
  if (!dr) return "";
  var cols = dr.cols || [], ult = cols.length - 1;
  var iObra = colDe(dr, ["obra"]), iFecha = colDe(dr, ["fecha", "vence", "vencimiento", "inicio"]);
  var iAse = colDe(dr, ["asesor", "vendedor"]);
  var todas = dr.filas || [];
  var filas = todas.filter(function(r){
    if (iObra >= 0 && !entraObra(String(r[iObra]))) return false;
    if (f.obra && iObra >= 0 && String(r[iObra]) !== f.obra) return false;
    if (f.mes && iFecha >= 0 && String(r[iFecha]).slice(0, 7) !== f.mes) return false;
    if (f.ase && iAse >= 0 && String(r[iAse]).trim() !== f.ase) return false;
    if (f.txt && r.join(" ").toLowerCase().indexOf(f.txt) < 0) return false;
    return true;
  });
  var suma = 0, hay = false;
  filas.forEach(function(r){ var n = num(r[ult]); if (n !== null) { suma += n; hay = true; } });
  var TOPE = 250;
  var h = '<div class="resumen-det"><span>' + filas.length + ' de ' + todas.length + ' filas</span>' +
    (hay ? '<span class="suma">Suma de la selección · <b>' + soles(suma) + '</b></span>' : '') +
    (filas.length !== todas.length && dr.total !== null && dr.total !== undefined
      ? '<span>Total sin filtrar · ' + soles(dr.total) + '</span>' : '') + '</div>';
  if (!filas.length) return h + '<p class="mas">Ninguna fila cumple ese filtro.</p>';

  if (iFecha >= 0) {
    var pm = {}, orden = [];
    filas.forEach(function(r){
      var k = String(r[iFecha] || "").slice(0, 7);
      if (!/^\d{4}-\d{2}$/.test(k)) return;
      if (!pm[k]) { pm[k] = {n: 0, s: 0}; orden.push(k); }
      pm[k].n++;
      var v = num(r[ult]); if (v !== null) pm[k].s += v;
    });
    orden.sort();
    if (orden.length > 1) {
      h += '<div class="tira-meses"><span class="tm-rot">De qué períodos son</span>';
      orden.forEach(function(k){
        h += '<button class="tm" type="button" data-mes="' + esc(k) + '">' +
          '<span class="tm-mes">' + esc(mesLargo(k)) + '</span>' +
          '<span class="tm-n">' + pm[k].n + (pm[k].n === 1 ? ' fila' : ' filas') + '</span>' +
          (hay ? '<span class="tm-s">' + solesM(pm[k].s) + '</span>' : '') + '</button>';
      });
      h += '</div>';
    }
  }
  h += '<div class="envoltura-tabla"><table class="datos"><thead><tr>';
  cols.forEach(function(c, i){ h += '<th' + (i === ult ? ' class="num"' : '') + '>' + esc(c) + '</th>'; });
  h += '</tr></thead><tbody>';
  filas.slice(0, TOPE).forEach(function(r){
    h += '<tr>';
    cols.forEach(function(c, i){
      var v = r[i], n = num(v);
      h += '<td' + (i === ult ? ' class="num"' : (i === iObra ? ' class="obra"' : '')) + '>' +
        (i === ult && n !== null ? soles(n) : esc(v)) + '</td>';
    });
    h += '</tr>';
  });
  h += '</tbody></table></div>';
  if (filas.length > TOPE)
    h += '<p class="mas">Se muestran las primeras ' + TOPE + ' de ' + filas.length +
         ' filas que cumplen el filtro. La suma de arriba las incluye todas.</p>';
  return h;
}

(function(){
  var aviso = null;
  var yaEsApp = function(){
    try {
      return window.matchMedia("(display-mode: standalone)").matches ||
             window.navigator.standalone === true;
    } catch (e) { return false; }
  };
  var pintarBoton = function(){
    var b = document.getElementById("btn-instalar");
    if (b) b.hidden = !(aviso && !yaEsApp());
    var cab = document.querySelector(".cabecera");
    if (cab && b) cab.classList.toggle("con-instalar", !b.hidden);
  };
  window.addEventListener("beforeinstallprompt", function(e){
    e.preventDefault();
    aviso = e;
    pintarBoton();
  });
  window.addEventListener("appinstalled", function(){ aviso = null; pintarBoton(); });
  document.addEventListener("DOMContentLoaded", function(){
    var b = document.getElementById("btn-instalar");
    if (b) b.addEventListener("click", function(){
      if (!aviso) return;
      aviso.prompt();
      aviso.userChoice.then(function(){ aviso = null; pintarBoton(); },
                            function(){ /* cerró el aviso: el botón sigue */ });
    });
    pintarBoton();
  });
  if ("serviceWorker" in navigator) {
    window.addEventListener("load", function(){
      navigator.serviceWorker.register("/sw.js", {scope: "/", updateViaCache: "none"})
        .catch(function(){ /* sin HTTPS ni localhost no hay service worker: la app igual abre */ });
    });
  }
})();

function acomodarBotonActualizar(){
  var b = document.getElementById("btn-act");
  if (b && !YO.puede_actualizar) b.style.display = "none";
}

document.addEventListener("DOMContentLoaded", function(){
  var b = document.getElementById("btn-act");
  if (!b) return;
  b.addEventListener("click", function(){
    b.disabled = true; b.textContent = "regenerando…";
    fetch("/actualizar", {method: "POST"})
      .then(function(r){ if (!r.ok) throw new Error("HTTP " + r.status); esperar(b); })
      .catch(function(){ b.disabled = false; b.textContent = "no se pudo — reintentar"; });
  });
});
function esperar(b){
  var t = setInterval(function(){
    fetch("/estado", {cache: "no-store"}).then(function(r){ return r.json(); }).then(function(s){
      if (s.corriendo) { b.textContent = "regenerando… " + (s.va_min !== null ? s.va_min + " min" : ""); return; }
      clearInterval(t); b.disabled = false; b.textContent = "Actualizar ahora";
      refrescarDatos();
    }).catch(function(){ clearInterval(t); b.disabled = false; b.textContent = "Actualizar ahora"; });
  }, 4000);
}

function refrescarDatos(cb){
  var y = window.scrollY;
  fetch("/tablero_datos.json", {cache: "no-cache"})
    .then(function(r){ if (!r.ok) throw new Error("HTTP " + r.status); return r.text(); })
    .then(function(t){ return JSON.parse(t); })
    .then(function(j){
      D = j;
      pintarCabDer(window.HOJA || {});
      if (window.__llenarObras) window.__llenarObras();
      pintarFuentes((window.HOJA || {}).fuentes);
      pintar();
      window.scrollTo({top: y, behavior: "instant"});
      if (cb) cb();
    })
    .catch(function(){ });
}

function avisoDatosAplicados(){
  if (document.getElementById("aviso-datos")) return;
  var d = document.createElement("div");
  d.id = "aviso-datos";
  d.textContent = "Se cargó una lectura más nueva del motor.";
  document.body.appendChild(d);
  setTimeout(function(){
    var el = document.getElementById("aviso-datos");
    if (el && el.parentNode) el.parentNode.removeChild(el);
  }, 6000);
}

/* Vigila si el motor publicó algo nuevo. Si hay, la trae y repinta SOLA. */
function vigilar(){
  var visto = null;
  setInterval(function(){
    fetch("/tablero_datos.json", {method: "HEAD", cache: "no-store"}).then(function(r){
      var m = r.headers.get("last-modified");
      if (visto && m && m !== visto) refrescarDatos(avisoDatosAplicados);
      if (m) visto = m;
    }).catch(function(){});
  }, 5000);
}

if (window.REALTIME) {
  window.REALTIME.on("actualizacion", function (evento) {
    if (!evento || evento.canal !== "tablero" || !evento.datos) return;
    D = evento.datos;
    pintarCabDer(window.HOJA || {});
    if (window.__llenarObras) window.__llenarObras();
    pintarFuentes((window.HOJA || {}).fuentes);
    pintar();
    avisoDatosAplicados();
  });
}

function _valorCelda(td) {
  if (!td) return null;
  var s = (td.textContent || "").replace(/ /g, " ").trim();
  if (s === "" || s === "—" || s === "-") return null;
  var n = s.replace(/S\/\s*/g, "").replace(/,/g, "").replace(/%/g, "").trim();
  if (/^-?\d+(\.\d+)?$/.test(n)) return parseFloat(n);
  return null;
}

function ordenarTabla(tabla, col, desc) {
  var cuerpo = tabla.tBodies[0];
  if (!cuerpo) return;
  [].forEach.call(cuerpo.querySelectorAll("tr.otros-desplegar"), function (d) {
    d.parentNode.removeChild(d); });
  [].forEach.call(cuerpo.querySelectorAll("tr.otros-hijo"), function (f) {
    f.classList.remove("otros-hijo", "otros-cerrado"); });
  var filas = [].slice.call(cuerpo.rows);
  var esPie = function (f) { return f.classList.contains("total") || f.classList.contains("gt-total"); };
  var pie = filas.filter(esPie);
  var datos = filas.filter(function (f) { return !esPie(f); });
  var numerica = datos.some(function (f) { return _valorCelda(f.cells[col]) !== null; });
  var clave = function (c) { return (c && c.hasAttribute("data-orden")) ? c.getAttribute("data-orden") : null; };
  var porClave = datos.some(function (f) { return clave(f.cells[col]) !== null; });
  datos.sort(function (a, b) {
    var x = a.cells[col], y = b.cells[col];
    if (porClave) {
      var kx = clave(x) || "", ky = clave(y) || "";
      if (!kx && !ky) return 0;
      if (!kx) return 1;
      if (!ky) return -1;
      return desc ? ky.localeCompare(kx) : kx.localeCompare(ky);
    }
    if (numerica) {
      var vx = _valorCelda(x), vy = _valorCelda(y);
      if (vx === null && vy === null) return 0;
      if (vx === null) return 1;          /* los vacíos, siempre al final */
      if (vy === null) return -1;
      return desc ? vy - vx : vx - vy;
    }
    var sx = (x ? x.textContent : "").trim(), sy = (y ? y.textContent : "").trim();
    return desc ? sy.localeCompare(sx, "es") : sx.localeCompare(sy, "es");
  });
  datos.forEach(function (f) { cuerpo.appendChild(f); });
  pie.forEach(function (f) { cuerpo.appendChild(f); });
  [].forEach.call(tabla.tHead ? tabla.tHead.rows[0].cells : [], function (th, i) {
    th.classList.remove("ord-asc", "ord-desc");
    if (i === col) th.classList.add(desc ? "ord-desc" : "ord-asc");
  });
}

document.addEventListener("click", function (e) {
  var th = e.target.closest ? e.target.closest("table.datos thead th") : null;
  if (!th) return;
  var tabla = th.closest("table");
  if (!tabla || !tabla.tBodies[0] || tabla.tBodies[0].rows.length < 2) return;
  if (tabla.classList.contains("sin-orden")) return;
  var col = [].indexOf.call(th.parentNode.cells, th);
  var desc = !th.classList.contains("ord-desc");
  ordenarTabla(tabla, col, desc);
  e.stopPropagation();   /* que no cierre el panel donde vive la tabla */
});

function _adelantar(el){
  document.querySelectorAll(".adelante").forEach(function(x){
    if (x !== el) x.classList.remove("adelante");
  });
  if (el) el.classList.add("adelante");
}

document.addEventListener("click", function(e){
  if (!e.target.closest) return;
  if (e.target.closest("select, input, textarea, .cerrar, .nav, .subnav, .filtros")) return;
  var cand = e.target.closest(".d-carta, .tarjeta");
  if (!cand) return;
  var dentro = cand.querySelector(".d-carta, .tarjeta");
  while (dentro && dentro.contains(e.target)) {
    cand = dentro;
    dentro = cand.querySelector(".d-carta, .tarjeta");
  }
  _adelantar(cand);
}, true);

if (window.REALTIME) {
  REALTIME.suscribir("tablero", function(datos) {
    D = datos;
    pintarCabDer(window.HOJA || {});
    if (window.__llenarObras) window.__llenarObras();
    pintarFuentes((window.HOJA || {}).fuentes);
    pintar();
  });
}

