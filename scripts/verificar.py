"""Comprobaciones que corren SOLAS después de cada edición (hook)."""
from __future__ import annotations

import importlib
import json
from datetime import datetime
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

CLAVE_PEGADA = re.compile(
    r"""(api[_-]?key|token|secret|password|passwd)\s*=\s*["'][^"']{12,}["']""",
    re.IGNORECASE)

FUERA_DE_GIT = (".env", "data/",
                "finanzas_datos.json",
                "obras_datos.json",
                "ventas_datos.json")

GENERADOS = ("docs/perfil_datos.md", "docs/perfil_excels.md")


def clave_en_el_codigo() -> list[str]:
    fallas = []
    for ruta in sorted(RAIZ.glob("**/*.py")):
        if {"venv", ".venv", "site-packages", "__pycache__"} & set(ruta.parts):
            continue
        for n, linea in enumerate(
                ruta.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if CLAVE_PEGADA.search(linea):
                rel = ruta.relative_to(RAIZ)
                fallas.append(f"{rel}:{n} — credencial escrita en el código")
    return fallas


def caracteres_de_control() -> list[str]:
    """Ningún carácter invisible en el código ni en las hojas."""
    GRUPOS = (("design", ("*.html", "*.js", "*.css")),
              ("src", ("*.py",)), ("scripts", ("*.py",)))
    # los prototipos generados y las copias de respaldo no son fuentes
    SALTAR = ("_tmp_", "propuesta-", "muestra", "_antes-de-")
    PERMITIDOS = {"\n", "\r", "\t"}
    fallas = []
    for carpeta, patrones in GRUPOS:
        for patron in patrones:
            for ruta in sorted((RAIZ / carpeta).glob(patron)):
                if any(s in ruta.name for s in SALTAR):
                    continue
                texto = ruta.read_text(encoding="utf-8", errors="replace")
                malos = {f"0x{ord(c):02x}" for c in texto
                         if ord(c) < 32 and c not in PERMITIDOS}
                if malos:
                    rel = ruta.relative_to(RAIZ)
                    fallas.append(
                        f"{rel} — carácter de control {', '.join(sorted(malos))} "
                        f"dentro del fuente: casi seguro un \\b que un shell "
                        f"convirtió en BACKSPACE. La línea se ve bien y no "
                        f"funciona.")
    return fallas


def data_publicada_vieja() -> list[str]:
    """El motor y lo publicado tienen que ser de la misma época."""
    fallas = []
    TOL = 2  # segundos de gracia por relojes de disco

    datos = RAIZ / "tablero_datos.json"
    if datos.exists():
        pub = datos.stat().st_mtime
        motor = [p for p in (RAIZ / "src").glob("*.py")] + \
                [RAIZ / "scripts" / "generar_tablero.py"]
        nuevo = max(motor, key=lambda p: p.stat().st_mtime)
        if nuevo.stat().st_mtime > pub + TOL:
            fallas.append(
                f"la data publicada quedó VIEJA: `{nuevo.relative_to(RAIZ)}` "
                f"cambió después de la última corrida de generar_tablero.py — "
                f"las cifras servidas salieron de un motor que ya no existe. "
                f"Regenerar antes de confiar en ellas.")

    cockpit = RAIZ / "design" / "cockpit.html"
    if cockpit.exists():
        armado = cockpit.stat().st_mtime
        SALTAR = ("_tmp_", "propuesta-", "muestra", "_antes-de-", "cockpit.html")
        piezas = [p for p in (RAIZ / "design").glob("*.html")
                  if not any(s in p.name for s in SALTAR)]
        piezas += [RAIZ / "design" / "cockpit.js", RAIZ / "design" / "cockpit.css"]
        piezas = [p for p in piezas if p.exists()]
        nuevo = max(piezas, key=lambda p: p.stat().st_mtime)
        if nuevo.stat().st_mtime > armado + TOL:
            fallas.append(
                f"el cockpit servido quedó VIEJO: `{nuevo.relative_to(RAIZ)}` "
                f"cambió después del último armado. Correr armar_cockpit.py.")
    return fallas


def cifras_que_se_contradicen_entre_hojas() -> list[str]:
    """La misma cifra tiene que decir lo mismo en todas las hojas."""
    datos = RAIZ / "tablero_datos.json"
    if not datos.exists():
        return []
    try:
        d = json.loads(datos.read_text(encoding="utf-8"))
        M = d["meses"]["None"]
        I = {x["indicador"]: x.get("valor") for x in M["indicadores"]}
        E = M.get("estructura") or {}
        R = {c["etiqueta"]: c["valor"] for c in (M.get("resultados") or [])}
    except Exception as e:  # noqa: BLE001
        return [f"no pude leer tablero_datos.json para el cuadre entre hojas: "
                f"{type(e).__name__}"]
    PARES = [
        ("Venta firmada del año (Scorecard)", I.get("Venta firmada del año"),
         "contratado (Resultados)", E.get("contratado")),
        ("N° de unidades vendidas (Scorecard)", I.get("N° de unidades vendidas"),
         "ventas (Resultados)", E.get("ventas")),
        ("Cartera por cobrar (Scorecard)", I.get("Cartera por cobrar"),
         "Por cobrar (Resultados)", R.get("Por cobrar")),
    ]
    fallas = []
    for na, va, nb, vb in PARES:
        if va is None or vb is None:
            fallas.append(f"cuadre entre hojas: falta «{na if va is None else nb}» "
                          f"en el payload — el control no puede comparar")
            continue
        if abs(float(va) - float(vb)) > 0.02:
            fallas.append(
                f"LAS HOJAS SE CONTRADICEN: {na} dice {va:,.2f} y {nb} dice "
                f"{vb:,.2f}. Una de las dos fórmulas está mal, y las dos "
                f"pantallas se están mostrando a la vez.")
    return fallas


def tarjeta_contra_su_propia_lista() -> list[str]:
    """Una tarjeta tiene que valer lo que suman las filas que ella abre."""
    datos = RAIZ / "tablero_datos.json"
    if not datos.exists():
        return []
    try:
        d = json.loads(datos.read_text(encoding="utf-8"))
        R = {c["etiqueta"]: c["valor"] for c in
             (d["meses"]["None"].get("resultados") or [])}
        crudas = d.get("crudas") or {}
        anio = str((d.get("flujo") or {}).get("anio") or "")
    except Exception as e:  # noqa: BLE001
        return [f"no pude leer tablero_datos.json para el cuadre de tarjeta "
                f"contra su lista: {type(e).__name__}"]
    if not anio:
        return ["cuadre tarjeta/lista: el payload no dice de qué año es el "
                "flujo — sin eso no se puede recortar la lista"]

    # (tarjeta de Resultados, bloque de filas) — solo conceptos mensuales.
    PARES = [("Vendido", "Vendido"), ("Cobrado", "Cobrado"),
             ("Gasto registrado", "Gasto")]
    fallas = []
    for tarjeta, bloque in PARES:
        val = R.get(tarjeta)
        blq = crudas.get(bloque)
        if val is None or not isinstance(blq, dict):
            fallas.append(f"cuadre tarjeta/lista: falta "
                          f"{'la tarjeta «' + tarjeta + '»' if val is None else 'el bloque de filas «' + bloque + '»'} "
                          f"en el payload — el control no puede comparar")
            continue
        if not blq.get("mensual"):
            continue
        fs = [x for x in (blq.get("filas") or [])
              if str(x.get("fecha") or "").startswith(anio)]
        suma = sum(float(x.get("monto") or 0) for x in fs)
        if abs(float(val) - suma) > 0.02:
            fallas.append(
                f"LA TARJETA NO VALE LO QUE SUMA SU PROPIA LISTA: «{tarjeta}» "
                f"publica {float(val):,.2f} y las {len(fs)} filas que abre "
                f"suman {suma:,.2f} ({suma - float(val):+,.2f}). El que hace "
                f"clic ve una cifra distinta de la que lo trajo.")

    try:
        _A = d["flujo"]["acumulado"]
        _g = ((d.get("movimientos") or {}).get("desglose_anio") or {}).get("gasto")
    except Exception:  # noqa: BLE001
        _A, _g = None, None
    if _A is None or _g is None:
        fallas.append("cuadre tarjeta/lista: falta «movimientos.desglose_anio» o "
                      "«flujo.acumulado» en el payload — el panel de «Salió» no "
                      "se puede comparar contra su tarjeta")
    else:
        _sm = sum(float(x.get("monto") or 0) for x in _g)
        _fl = sum(int(x.get("filas") or 0) for x in _g)
        if abs(_sm - float(_A.get("salio") or 0)) > 0.02:
            fallas.append(
                f"EL PANEL DE «SALIÓ» NO VALE LO QUE SU TARJETA: el desglose por "
                f"rótulo suma {_sm:,.2f} y la tarjeta publica "
                f"{float(_A.get('salio') or 0):,.2f} "
                f"({_sm - float(_A.get('salio') or 0):+,.2f}). El que hace clic "
                f"para ver de qué está hecha una cifra ve otra cifra.")
        if _fl != int(_A.get("filas_salio") or 0):
            fallas.append(
                f"EL PANEL DE «SALIÓ» CUENTA OTRAS FILAS QUE SU TARJETA: "
                f"{_fl} en el desglose contra {_A.get('filas_salio')} en la tarjeta.")

    # Y el mismo concepto en la hoja de área, que arma sus filas por otro lado.
    for x in (d.get("areas_filas") or {}).get("Cobranza") or []:
        if x.get("nombre") != "Cobrado":
            continue
        fs = [r for r in (x.get("filas") or [])
              if str(r.get("fecha") or "").startswith(anio)]
        suma = sum(float(r.get("monto") or 0) for r in fs)
        val = R.get("Cobrado")
        if val is not None and abs(float(val) - suma) > 0.02:
            fallas.append(
                f"LAS HOJAS SE CONTRADICEN: «Cobrado» vale {float(val):,.2f} "
                f"en Resultados y las filas de la hoja Cobranza suman "
                f"{suma:,.2f} ({suma - float(val):+,.2f}) para el mismo año.")
    return fallas


def detalle_del_mes_cuadra() -> list[str]:
    """Lo que muestra el detalle de un mes tiene que sumar lo que dice el mes."""
    datos = RAIZ / "tablero_datos.json"
    if not datos.exists():
        return []
    try:
        d = json.loads(datos.read_text(encoding="utf-8"))
        F = d["flujo"]
        meses = F["meses"]
        A = F["acumulado"]
    except Exception as e:  # noqa: BLE001
        return [f"no pude leer el flujo para el cuadre del detalle por mes: "
                f"{type(e).__name__}"]

    fallas: list[str] = []

    def cerca(a, b, tol=0.02):
        return abs(float(a) - float(b)) <= tol

    for m in meses:
        et = m.get("etiqueta", m.get("mes"))
        for clave, total, rot in (("top_cobros", m.get("entro"), "Entro"),
                                  ("top_gastos", m.get("salio"), "Salio")):
            t = m.get(clave)
            if not isinstance(t, dict):
                fallas.append(f"detalle de {et}: falta «{clave}» en el payload "
                              f"— el control no puede comparar")
                continue
            det = t.get("detalle") or []
            suma = sum(float(x.get("monto") or 0) for x in det)
            if not cerca(suma + float(t.get("resto") or 0), t.get("monto") or 0):
                fallas.append(
                    f"EL DETALLE DE {et} NO SUMA LO QUE DICE: los "
                    f"{len(det)} mayores de «{rot}» dan {suma:,.2f} y el resto "
                    f"declarado {float(t.get('resto') or 0):,.2f} — juntos "
                    f"{suma + float(t.get('resto') or 0):,.2f}, contra "
                    f"{float(t.get('monto') or 0):,.2f} que publica el bloque.")
            if len(det) + int(t.get("resto_filas") or 0) != int(t.get("filas") or 0):
                fallas.append(
                    f"EL DETALLE DE {et} CUENTA MAL SUS FILAS en «{rot}»: "
                    f"{len(det)} mostradas + {t.get('resto_filas')} del resto "
                    f"no dan las {t.get('filas')} que declara.")
            if total is not None and not cerca(t.get("monto") or 0, total):
                fallas.append(
                    f"EL DETALLE DE {et} CONTRADICE A SU PROPIA TARJETA: el "
                    f"bloque «{rot}» suma {float(t.get('monto') or 0):,.2f} y "
                    f"el mes publica {float(total):,.2f}.")

        rep = m.get("reparto_gasto") or {}
        for corte, xs in rep.items():
            if not xs:
                continue
            sm = sum(float(x.get("monto") or 0) for x in xs)
            fl = sum(int(x.get("filas") or 0) for x in xs)
            if not cerca(sm, m.get("salio") or 0):
                fallas.append(
                    f"EL REPARTO POR {corte.upper()} DE {et} NO REPARTE TODO: "
                    f"suma {sm:,.2f} y el mes salio {float(m.get('salio') or 0):,.2f}. "
                    f"La pantalla promete el mes completo y muestra una parte.")
            esperadas = int(((m.get("top_gastos") or {}).get("filas")) or 0)
            if esperadas and fl != esperadas:
                fallas.append(
                    f"EL REPARTO POR {corte.upper()} DE {et} PIERDE FILAS: "
                    f"reparte {fl} de {esperadas} movimientos.")

        ii, cc = m.get("entro_inicial"), m.get("entro_cuota")
        if ii is not None and cc is not None and m.get("entro") is not None:
            if not cerca(float(ii) + float(cc), m["entro"]):
                fallas.append(
                    f"EN {et} INICIAL + CUOTA NO DA «ENTRO»: "
                    f"{float(ii):,.2f} + {float(cc):,.2f} = "
                    f"{float(ii) + float(cc):,.2f} contra "
                    f"{float(m['entro']):,.2f}.")

    corrida = sum(float(m.get("entro") or 0) - float(m.get("salio") or 0)
                  for m in meses)
    if A.get("neto") is not None and not cerca(corrida, A["neto"]):
        fallas.append(
            f"EL ACUMULADO NO CIERRA: la suma corrida de los «Queda» da "
            f"{corrida:,.2f} y el año publica {float(A['neto']):,.2f}. La "
            f"ultima celda de la columna «Acumulado desde enero» tiene que ser "
            f"el total del año.")
    for k, rot in (("entro", "Entro"), ("salio", "Salio")):
        sm = sum(float(m.get(k) or 0) for m in meses)
        if A.get(k) is not None and not cerca(sm, A[k]):
            fallas.append(
                f"LOS DOCE MESES NO SUMAN EL AÑO EN «{rot}»: {sm:,.2f} contra "
                f"{float(A[k]):,.2f}.")
    return fallas


def cobranza_coherente() -> list[str]:
    """La hoja Cobranza no puede contradecirse consigo misma."""
    datos = RAIZ / "tablero_datos.json"
    if not datos.exists():
        return []
    try:
        V = json.loads(datos.read_text(encoding="utf-8"))["vencimientos"]
        CAR, COM, MES = V["cartera"], V["composicion"], V["meses"]
    except Exception as e:  # noqa: BLE001
        return [f"no pude leer «vencimientos» para el control de Cobranza: "
                f"{type(e).__name__}"]

    fallas = []
    if not MES:
        return ["Cobranza: el calendario mensual quedó vacío"]

    serie = sum(m["vencia"] - m["cobrado"] for m in MES)
    partes = COM["vencido"]["monto"] + COM["por_vencer"]["monto"]
    if abs(serie - partes) > 1.0:
        fallas.append(
            f"COBRANZA SE CONTRADICE: el calendario mensual deja "
            f"S/ {serie:,.2f} por cobrar y la composición dice "
            f"S/ {partes:,.2f} (vencido + por vencer). Difieren en "
            f"S/ {abs(serie - partes):,.2f} — son dos poblaciones distintas "
            f"en la misma hoja.")

    for fila in [CAR["total"]] + CAR["por_razon_social"] + CAR["por_obra"]:
        if "creditos_vivos" not in fila:
            fallas.append(
                f"Cobranza: la fila «{fila['nombre'][:40]}» no declara cuántos "
                f"créditos siguen debiendo — su «{fila['creditos']} créditos» "
                f"incluye los ya saldados")
            break
        if fila["creditos_vivos"] > fila["creditos"]:
            fallas.append(
                f"Cobranza: «{fila['nombre'][:40]}» dice {fila['creditos_vivos']} "
                f"créditos vivos sobre {fila['creditos']} históricos")

    suma = (COM["vencido"]["monto"] + COM["por_vencer"]["monto"]
            + COM["sin_cronograma"]["monto"])
    explicado = sum(float(d.get("dif") or 0) for d in (COM.get("descuadres") or []))
    residuo = (COM["cartera"] - suma) - explicado
    if abs(residuo) > 1.0:
        fallas.append(
            f"Cobranza: las partes suman S/ {suma:,.2f}, la cartera es "
            f"S/ {COM['cartera']:,.2f} y los créditos que no cuadran con su "
            f"cronograma explican S/ {explicado:,.2f}: quedan S/ {residuo:,.2f} "
            f"sin explicar")
    return fallas


def comercial_coherente() -> list[str]:
    """Comercial y Ventas no pueden contradecirse entre sí ni con su fuente."""
    datos = RAIZ / "tablero_datos.json"
    if not datos.exists():
        return []
    try:
        A = json.loads(datos.read_text(encoding="utf-8"))["areas"]
        C = {c["etiqueta"]: c["valor"] for c in A["Comercial"]}
        V = {c["etiqueta"]: c["valor"] for c in A["Ventas"]}
        NV = {c["etiqueta"]: c for c in A["Ventas"]}
    except Exception as e:  # noqa: BLE001
        return [f"no pude leer «areas» para el control de Comercial: "
                f"{type(e).__name__}"]

    fallas = []

    # el ticket sale de las MISMAS ventas que el vendido
    import re as _re
    m = _re.search(r"(\d+)\s+ventas", str(NV.get("Vendido", {}).get("formula") or ""))
    if m and V.get("Ticket promedio"):
        n_ventas = int(m.group(1))
        esperado = V["Vendido"] / n_ventas
        if abs(esperado - V["Ticket promedio"]) > 0.01:
            fallas.append(
                f"COMERCIAL SE CONTRADICE: el ticket promedio dice "
                f"S/ {V['Ticket promedio']:,.2f} pero el vendido "
                f"(S/ {V['Vendido']:,.2f}) entre las {n_ventas} ventas da "
                f"S/ {esperado:,.2f}. Las dos cifras tienen que salir de la "
                f"misma población.")

    if C.get("Leads en el embudo") and C.get("Leads marcados VENDIDO") is not None:
        esperado = 100.0 * C["Leads marcados VENDIDO"] / C["Leads en el embudo"]
        if abs(esperado - (C.get("Conversión del embudo (%)") or 0)) > 0.01:
            fallas.append(
                f"COMERCIAL SE CONTRADICE: la conversión dice "
                f"{C.get('Conversión del embudo (%)'):.4f}% y los "
                f"{C['Leads marcados VENDIDO']} vendidos sobre "
                f"{C['Leads en el embudo']} leads dan {esperado:.4f}%")

    # el % del inventario no puede pasar del 100 ni salir de la nada
    pct = V.get("Vendido del inventario (%)")
    if pct is not None and not (0 <= pct <= 100):
        fallas.append(
            f"Ventas: «vendido del inventario» da {pct:.2f}% — fuera de rango. "
            f"Casi seguro se cruzó por nombre de unidad sin la obra, y «LOTE 25» "
            f"existe en tres obras a la vez.")

    # las ventas caídas no pueden ser más que las cerradas
    if V.get("Ventas caídas") is not None and m:
        if V["Ventas caídas"] > int(m.group(1)):
            fallas.append("Ventas: las caídas superan a las cerradas")
    return fallas


def crm_coherente() -> list[str]:
    """La hoja CRM no puede contradecirse consigo misma, período por período."""
    datos = RAIZ / "tablero_datos.json"
    if not datos.exists():
        return []
    try:
        MESES = json.loads(datos.read_text(encoding="utf-8"))["meses"]
    except Exception as e:  # noqa: BLE001
        return [f"no pude leer «meses» para el control del CRM: {type(e).__name__}"]

    fallas: list[str] = []
    vistos = 0
    for clave, v in MESES.items():
        c = (v or {}).get("crm") or {}
        if not c.get("disponible"):
            continue
        a = c.get("atencion") or {}
        n = a.get("leads") or 0
        if not n:
            continue
        vistos += 1
        et = {x["valor"]: x["leads"] for x in (c.get("etapas") or [])}

        def mal(txt: str, _c=clave) -> None:
            fallas.append(f"CRM «{_c}»: {txt}")

        suma = ((a.get("con_llamada") or 0) + (a.get("sin_llamada") or 0)
                + (a.get("negativas") or 0))
        if suma != n:
            mal(f"con atención medible ({a.get('con_llamada')}) + sin llamada "
                f"({a.get('sin_llamada')}) + llamada anterior a la creación "
                f"({a.get('negativas')}) = {suma}, y los leads del período son "
                f"{n}. Los tres grupos tienen que repartir el embudo entero: "
                f"si no, alguna cifra de la hoja cuenta un lead dos veces o "
                f"ninguna")

        if (a.get("leads_habil") or 0) + (a.get("leads_finde") or 0) != n:
            mal(f"día hábil ({a.get('leads_habil')}) + fin de semana "
                f"({a.get('leads_finde')}) no dan los {n} leads del período")
        # …y la base de cada mediana reparte los medibles, no el embudo.
        if a.get("con_llamada_habil") is None or a.get("con_llamada_finde") is None:
            mal("las tarjetas de mediana por día hábil y por fin de semana no "
                "declaran de cuántos leads sale cada mediana. Sin eso la "
                "pantalla nombra los leads del corte entero al lado de una "
                "cifra calculada sobre menos")
        elif (a["con_llamada_habil"] + a["con_llamada_finde"]) != (a.get("con_llamada") or 0):
            mal(f"las bases de las dos medianas ({a['con_llamada_habil']} + "
                f"{a['con_llamada_finde']}) no suman los "
                f"{a.get('con_llamada')} leads con atención medible")

        for k in ("mediana", "promedio", "habil_mediana", "finde_mediana"):
            x = a.get(k)
            if x is not None and (x != x or x < 0):
                mal(f"«{k}» vale {x} — una mediana negativa o no numérica "
                    f"significa que los leads con la llamada fechada antes de "
                    f"su creación se colaron en el cálculo")

        # 4 · las tarjetas que salen de una etapa tienen que dar la etapa.
        if a.get("sin_gestionar") != et.get("ASIGNADO", 0):
            mal(f"«sin gestionar» dice {a.get('sin_gestionar')} y la etapa "
                f"ASIGNADO del embudo tiene {et.get('ASIGNADO', 0)}")
        if a.get("desestimados") != et.get("DESESTIMADO", 0):
            mal(f"«desestimados» dice {a.get('desestimados')} y la etapa "
                f"DESESTIMADO tiene {et.get('DESESTIMADO', 0)}")
        for k in ("desestimados_sin_llamada",):
            if (a.get(k) or 0) > (a.get("sin_llamada") or 0):
                mal(f"«{k}» ({a.get(k)}) supera a los {a.get('sin_llamada')} "
                    f"leads sin llamada, y es un subconjunto suyo")
        if (a.get("visitaron") or 0) > n:
            mal(f"«visitaron» ({a.get('visitaron')}) supera los {n} leads")

        cortes = [(nom, c.get(nom) or []) for nom in
                  ("etapas", "genero", "campanas", "proyectos")]
        cortes += [(f"extras · {e['titulo']}", e.get("items") or [])
                   for e in (c.get("extras") or [])]
        for nom, items in cortes:
            if not items:
                continue
            s = sum(x["leads"] for x in items)
            if s != n:
                mal(f"el corte «{nom}» reparte {s} leads y el período tiene "
                    f"{n}: o se escondieron los vacíos, o un lead entró en "
                    f"dos filas")
            for x in items:
                esperado = 100.0 * x["leads"] / n
                if abs(esperado - x["pct"]) > 0.0001:
                    mal(f"«{nom} · {str(x['valor'])[:30]}» publica "
                        f"{x['pct']:.4f}% y sus {x['leads']} leads sobre {n} "
                        f"dan {esperado:.4f}%")
                    break

        # 6 · los responsables reparten el embudo, y cada uno cuadra consigo.
        rs = c.get("responsables") or []
        if rs:
            if sum(r["leads"] for r in rs) != n:
                mal(f"los {len(rs)} responsables suman "
                    f"{sum(r['leads'] for r in rs)} leads y el período tiene {n}")
            if sum(r["vendidos"] for r in rs) != et.get("VENDIDO", 0):
                mal(f"los responsables suman {sum(r['vendidos'] for r in rs)} "
                    f"leads en VENDIDO y la etapa VENDIDO tiene "
                    f"{et.get('VENDIDO', 0)}")
            if sum(r["sin_gestionar"] for r in rs) != (a.get("sin_gestionar") or 0):
                mal(f"los responsables suman {sum(r['sin_gestionar'] for r in rs)} "
                    f"en ASIGNADO y la tarjeta dice {a.get('sin_gestionar')}")
            if sum(r["con_llamada"] for r in rs) != (a.get("con_llamada") or 0):
                mal(f"los responsables suman {sum(r['con_llamada'] for r in rs)} "
                    f"con atención medible y la hoja dice {a.get('con_llamada')}")
            for r in rs:
                if r["con_llamada"] > r["leads"] or r["leads_finde"] > r["leads"]:
                    mal(f"«{r['responsable'][:30]}» tiene {r['leads']} leads, "
                        f"{r['con_llamada']} con atención medible y "
                        f"{r['leads_finde']} de fin de semana — una parte "
                        f"supera a su total")
                    break
                for k in ("horas_mediana", "horas_promedio", "horas_habil",
                          "horas_finde"):
                    x = r.get(k)
                    if x is not None and (x != x or x < 0):
                        mal(f"«{r['responsable'][:30]}» publica {k}={x}. NaN no "
                            f"es JSON y una hora negativa no es un tiempo: la "
                            f"guarda de la mediana está mirando una población "
                            f"distinta de la que promedia")
                        break

    anio = ((MESES.get("None") or {}).get("crm") or {}).get("atencion") or {}
    if anio.get("leads"):
        suma = 0
        for k, v in MESES.items():
            if not (k.isdigit() and len(k) <= 2):
                continue
            suma += (((v or {}).get("crm") or {}).get("atencion") or {}).get("leads") or 0
        if suma != anio["leads"]:
            fallas.append(
                f"CRM: las columnas del gráfico mes a mes suman {suma} leads y "
                f"el acumulado del año publica {anio['leads']}. La hoja "
                f"mostraría dos totales distintos en la misma pantalla")
        hist = ((MESES.get("hist") or {}).get("crm") or {}).get("atencion") or {}
        if hist.get("leads") and hist["leads"] < anio["leads"]:
            fallas.append(
                f"CRM: el histórico publica {hist['leads']} leads y el año en "
                f"curso {anio['leads']}. La tarjeta de cohorte resta uno del "
                f"otro y daría una cantidad negativa de leads")
    if not vistos and MESES:
        return ["CRM: ningún período publicó embudo — o Kommo no respondió en "
                "la generación, y entonces la hoja entera está en su aviso de "
                "desconexión, o el bloque se dejó de escribir"]
    return fallas


def concept_coherente() -> list[str]:
    """El bloque Concept no puede contradecirse a si mismo."""
    datos = RAIZ / "tablero_datos.json"
    if not datos.exists():
        return []
    try:
        d = json.loads(datos.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        return [f"no pude leer tablero_datos.json para Concept: {type(e).__name__}"]
    c = d.get("crm_concept") or {}
    if not c.get("disponible"):
        return []
    fallas = []
    tot = int(c.get("total") or 0)
    for grupo, clave in (("etapas", "leads"), ("meses", "n")):
        xs = c.get(grupo) or []
        s = sum(int(x.get(clave) or 0) for x in xs)
        if s != tot:
            fallas.append(
                f"CRM Concept: la suma de {grupo} da {s} y el total publicado "
                f"dice {tot} — el bloque se contradice a si mismo")
    return fallas


def obra_coherente() -> list[str]:
    """La hoja Obra no puede contradecirse consigo misma ni mezclar ventanas."""
    datos = RAIZ / "tablero_datos.json"
    if not datos.exists():
        return []
    try:
        D = json.loads(datos.read_text(encoding="utf-8"))
        MOV = D["movimientos"]
        MESES, AVF = D["meses"], D["avance_fisico"]
    except Exception as e:  # noqa: BLE001
        return [f"no pude leer «movimientos» para el control de Obra: "
                f"{type(e).__name__}"]
    if not MOV.get("hay"):
        return ["Obra: el libro de caja no publicó nada — o MovimientoGasto no "
                "respondió, y entonces media hoja está en su aviso, o el "
                "bloque se dejó de escribir"]

    R = MOV.get("resumen") or {}
    G = R.get("gasto") or {}
    fallas = []

    # 1 · las dos mitades del gasto tienen que dar el gasto
    atr, sin_atr = R.get("gasto_atribuido"), R.get("gasto_sin_atribuir")
    if atr is None or sin_atr is None or not G.get("monto"):
        fallas.append("Obra: el resumen del libro de caja no trae gasto "
                      "atribuido y sin atribuir — el control no puede comparar")
    elif abs((atr + sin_atr) - G["monto"]) > 0.02:
        fallas.append(
            f"OBRA SE CONTRADICE: el gasto con obra (S/ {atr:,.2f}) más el que "
            f"no la tiene (S/ {sin_atr:,.2f}) da S/ {atr + sin_atr:,.2f}, y el "
            f"gasto del libro es S/ {G['monto']:,.2f}")

    POR = MOV.get("por_obra") or []
    if atr is not None:
        s = sum(x.get("gasto", 0) for x in POR)
        if abs(s - atr) > 0.02:
            fallas.append(
                f"OBRA SE CONTRADICE: las {len(POR)} obras del detalle suman "
                f"S/ {s:,.2f} y el resumen dice S/ {atr:,.2f}")
    mov_obra = sum(x.get("movimientos", 0) for x in POR)
    if G.get("filas") is not None and mov_obra > G["filas"]:
        fallas.append(
            f"Obra: las obras se llevan {mov_obra:,} movimientos y el gasto "
            f"entero tiene {G['filas']:,} — «movimientos sin obra» saldría "
            f"negativo")
    if R.get("obras_con_gasto") is not None and R["obras_con_gasto"] != len(POR):
        fallas.append(
            f"Obra: el resumen dice {R['obras_con_gasto']} obras con gasto y "
            f"el detalle trae {len(POR)}")

    hist = {x["obra"]: x for x in POR}
    for k, M in MESES.items():
        for o in (M.get("obras") or []):
            if o.get("costo") is None:
                continue
            h = hist.get(o["obra"])
            if not h:
                fallas.append(
                    f"OBRA SE CONTRADICE: «{o['obra']}» tiene "
                    f"S/ {o['costo']:,.2f} de costo en el período «{k}» y no "
                    f"aparece en el libro completo, que es su propio total")
                continue
            if o["costo"] > h["gasto"] + 0.02:
                fallas.append(
                    f"OBRA SE CONTRADICE: «{o['obra']}» tiene "
                    f"S/ {o['costo']:,.2f} en el período «{k}» y "
                    f"S/ {h['gasto']:,.2f} en el libro completo. Una parte no "
                    f"puede ser mayor que el todo: son dos ventanas distintas")

    for k, M in MESES.items():
        tot = None
        for x in (M.get("resultados") or []):
            if str(x.get("etiqueta")) in ("Gasto registrado", "Gasto del mes") \
                    and isinstance(x.get("valor"), (int, float)):
                tot = x["valor"]
        a = sum(o["costo"] for o in (M.get("obras") or [])
                if o.get("costo") is not None)
        if tot is None:
            if a:
                fallas.append(
                    f"Obra: el período «{k}» publica S/ {a:,.2f} de costo con "
                    f"obra y ningún gasto total — la tarjeta no puede decir "
                    f"qué parte del gasto no lleva obra")
            continue
        if a > tot + 0.02:
            fallas.append(
                f"OBRA SE CONTRADICE: en el período «{k}» el gasto CON obra "
                f"(S/ {a:,.2f}) supera al gasto total del período "
                f"(S/ {tot:,.2f}). El porcentaje que la tarjeta pone al lado "
                f"saldría negativo")

    ejec = [x for x in AVF if x.get("etapa") == "Ejecución"
            and x.get("pct") is not None]
    tarj = {c["etiqueta"]: c["valor"] for c in (D.get("areas", {}).get("Obra") or [])}
    if ejec and tarj.get("Avance de las obras en ejecución") is not None:
        esperado = sum(x["pct"] for x in ejec) / len(ejec)
        if abs(esperado - tarj["Avance de las obras en ejecución"]) > 0.01:
            fallas.append(
                f"OBRA SE CONTRADICE: el área publica "
                f"{tarj['Avance de las obras en ejecución']:.4f}% de avance y "
                f"las {len(ejec)} obras en ejecución promedian {esperado:.4f}%")
    if tarj.get("Obras en ejecución") is not None and \
            tarj["Obras en ejecución"] != len([x for x in AVF
                                               if x.get("etapa") == "Ejecución"]):
        fallas.append(
            f"OBRA SE CONTRADICE: el área dice {tarj['Obras en ejecución']} "
            f"obras en ejecución y el avance físico lista "
            f"{len([x for x in AVF if x.get('etapa') == 'Ejecución'])}")

    base = MESES.get("None") or {}
    n_obras = {o["obra"] for o in (base.get("obras") or [])}
    n_avf = {x["obra"] for x in AVF}
    if n_obras and n_avf != n_obras:
        falta = sorted(n_obras - n_avf) + sorted(n_avf - n_obras)
        fallas.append(
            f"Obra: los nombres de las obras y los del avance físico no son el "
            f"mismo juego — {falta[:4]}. La hoja los une por nombre: lo que no "
            f"empareja sale con raya en el avance")
    etapa_avf = {x["obra"]: x.get("etapa") for x in AVF}
    for o in (base.get("obras") or []):
        if o["obra"] in etapa_avf and o.get("etapa") != etapa_avf[o["obra"]]:
            fallas.append(
                f"OBRA SE CONTRADICE: «{o['obra']}» está en «{o.get('etapa')}» "
                f"en la tabla y en «{etapa_avf[o['obra']]}» en el avance físico")
            break

    P = R.get("presupuesto") or {}
    pa, pf = R.get("presupuesto_atribuido"), R.get("presupuesto_atribuido_filas")
    if pf is None or pa is None:
        fallas.append(
            "Obra: el resumen no dice cuánto presupuesto queda pegado a una "
            "obra.")
    else:
        if P.get("monto") is not None and pa > P["monto"] + 0.02:
            fallas.append(
                f"Obra: el presupuesto pegado a una obra (S/ {pa:,.2f}) supera "
                f"al presupuesto entero (S/ {P['monto']:,.2f})")
        if pf and not (R.get("presupuesto_obras") or []):
            fallas.append(
                f"Obra: {pf} movimientos de presupuesto quedan pegados a una "
                f"obra y no se dice a cuál — la frase sale con el paréntesis "
                f"vacío")

    no_obra = {x["proyecto"] for x in (MOV.get("sin_atribuir") or [])}
    listados = [x for x in ((MOV.get("desglose") or {}).get("gasto") or [])
                if x["clave"] in no_obra]
    cubre = sum(x["monto"] for x in listados)
    if sin_atr is not None and cubre > sin_atr + 0.02:
        fallas.append(
            f"Obra: los {len(listados)} rótulos listados suman S/ {cubre:,.2f} "
            f"y el gasto sin obra es S/ {sin_atr:,.2f} — «otros rótulos más "
            f"chicos» saldría negativo")
    return fallas


def finanzas_coherente() -> list[str]:
    """La hoja Finanzas (con Rentabilidad) no puede contradecirse ni consigo."""
    datos = RAIZ / "tablero_datos.json"
    if not datos.exists():
        return []
    try:
        d = json.loads(datos.read_text(encoding="utf-8"))
        F, MV = d["flujo"], d["movimientos"]
        I = {x["indicador"]: x for x in d["indicadores"]
             if x.get("perspectiva") == "Finanzas"}
        COM = d["vencimientos"]["composicion"]
        OBRAS = d["meses"]["None"]["obras"]
    except Exception as e:  # noqa: BLE001
        return [f"no pude leer el payload para el control de Finanzas: "
                f"{type(e).__name__}"]

    fallas: list[str] = []
    if not F.get("hay"):
        return ["Finanzas: el flujo de caja quedó vacío — la hoja entera "
                "se publica sin su bloque principal"]

    def val(nombre):
        return (I.get(nombre) or {}).get("valor")

    mor, cart = val("Morosidad de la cartera"), val("Cartera por cobrar")
    venc_cob = ((COM.get("vencido") or {}).get("monto"))
    if mor is not None and cart and venc_cob is not None:
        venc_fin = mor * cart / 100.0
        if abs(venc_fin - venc_cob) > 1.0:
            fallas.append(
                f"FINANZAS Y COBRANZA SE CONTRADICEN: la morosidad de "
                f"Finanzas ({mor:.2f}% de S/ {cart:,.2f}) implica "
                f"S/ {venc_fin:,.2f} de vencido, y Cobranza publica "
                f"S/ {venc_cob:,.2f}. Son dos poblaciones de «cuota que debe» "
                f"en el mismo tablero: casi seguro una cuenta por el estado "
                f"de la casilla y la otra por la plata que falta.")

    d90 = val("Saldo vencido a más de 90 días")
    if d90 is not None and venc_cob is not None and d90 > venc_cob + 1.0:
        fallas.append(
            f"Finanzas: «Saldo vencido a más de 90 días» (S/ {d90:,.2f}) "
            f"supera todo el vencido (S/ {venc_cob:,.2f}) — un subconjunto "
            f"no puede ser mayor que su conjunto")

    dp = F.get("diagnostico_presupuesto") or {}
    tot_dp, sin_obra = dp.get("total_filas"), dp.get("sin_obra")
    if tot_dp:
        if sin_obra is None or not (0 <= sin_obra <= tot_dp):
            fallas.append(
                f"Finanzas: «no llevan obra» dice {sin_obra} sobre "
                f"{tot_dp} filas de presupuesto — fuera de rango")
        elif sin_obra == 0 and (MV.get("resumen") or {}).get("pct_atribuido", 100) < 99:
            fallas.append(
                f"Finanzas: el bloque de presupuesto publica «0 de los "
                f"{tot_dp:,} no llevan obra» —o sea, el 100% rotulado— "
                f"mientras el gasto del mismo libro solo llega al "
                f"{MV['resumen']['pct_atribuido']:.1f}%. Esa cifra está "
                f"contando un rótulo literal, no los que no emparejan obra.")

    ac, ms = F.get("acumulado") or {}, F.get("meses") or []
    for campo in ("entro", "salio", "por_entrar"):
        s = sum(m.get(campo) or 0 for m in ms)
        if abs(s - (ac.get(campo) or 0)) > 0.02:
            fallas.append(
                f"Finanzas: los doce meses suman S/ {s:,.2f} en «{campo}» y "
                f"la tarjeta del año dice S/ {ac.get(campo):,.2f} — la tabla "
                f"y su total no son la misma lectura")
    if abs((ac.get("neto") or 0) - ((ac.get("entro") or 0) - (ac.get("salio") or 0))) > 0.02:
        fallas.append("Finanzas: «Queda» no es «Entró» menos «Salió»")

    an = MV.get("anio") or {}
    if an and abs((an.get("monto") or 0) - (ac.get("salio") or 0)) > 0.02:
        fallas.append(
            f"Finanzas: «Salió» del año dice S/ {ac.get('salio'):,.2f} y la "
            f"tabla por obra mide sobre S/ {an.get('monto'):,.2f}. El "
            f"porcentaje de gasto con obra se publica contra el denominador "
            f"equivocado — es el defecto del 19.2% contra el 3.7%.")
    s_obra = sum(x.get("gasto") or 0 for x in (MV.get("por_obra_anio") or []))
    if an and abs(s_obra - (an.get("atribuido") or 0)) > 0.02:
        fallas.append(
            f"Finanzas: la tabla por obra suma S/ {s_obra:,.2f} y el "
            f"atribuido del año dice S/ {an.get('atribuido'):,.2f}")
    for base, sub in (("resumen", None), ("anio", None)):
        b = MV.get(base) or {}
        tot = (b.get("gasto") or {}).get("monto") if base == "resumen" else b.get("monto")
        atr = b.get("gasto_atribuido") if base == "resumen" else b.get("atribuido")
        sin = b.get("gasto_sin_atribuir") if base == "resumen" else b.get("sin_atribuir")
        if None not in (tot, atr, sin) and abs(tot - (atr + sin)) > 0.02:
            fallas.append(
                f"Finanzas: en «{base}» el gasto (S/ {tot:,.2f}) no es la "
                f"suma del atribuido y el no atribuido")

    # 6 · RENTABILIDAD · los dos lados salen de la misma fuente y ventana.
    s_costo = sum(o["costo"] for o in OBRAS if o.get("costo") is not None)
    if an.get("atribuido") is not None and abs(s_costo - an["atribuido"]) > 0.02:
        fallas.append(
            f"RENTABILIDAD SE CONTRADICE CON FINANZAS: la columna Costo de "
            f"las obras suma S/ {s_costo:,.2f} y el gasto atribuido del año "
            f"dice S/ {an['atribuido']:,.2f}")
    s_cob = sum(o["cobrado"] for o in OBRAS if o.get("cobrado") is not None)
    if ac.get("entro") is not None and s_cob > ac["entro"] + 0.02:
        fallas.append(
            f"RENTABILIDAD: el cobrado repartido por obra suma S/ {s_cob:,.2f} "
            f"y el cobrado del año es S/ {ac['entro']:,.2f} — hay recibos "
            f"contados dos veces")

    ing = d.get("ingresos") or []
    emp = [x["monto"] for x in ing if "reconocido" in str(x.get("detalle"))]
    tot_g = next((x["monto"] for x in ing
                  if "total del grupo" in str(x.get("fuente"))), None)
    if emp and tot_g is not None and abs(sum(emp) - tot_g) > 0.02:
        fallas.append(
            f"Finanzas: el «total del grupo» de ContaSis dice S/ {tot_g:,.2f} "
            f"y las {len(emp)} empresas suman S/ {sum(emp):,.2f}")

    gf = d.get("gasto_fuera") or {}
    if gf.get("monto") and ac.get("salio") and gf["monto"] > ac["salio"] + 0.02:
        fallas.append(
            f"Finanzas: el gasto fuera de alcance (S/ {gf['monto']:,.2f}) "
            f"supera todo lo que salió en el año (S/ {ac['salio']:,.2f})")
    return fallas


def gitignore_incompleto() -> list[str]:
    gi = RAIZ / ".gitignore"
    if not gi.exists():
        return ["falta .gitignore — .env y data/ podrían subir a git"]
    txt = gi.read_text(encoding="utf-8", errors="replace")
    return [f".gitignore no excluye «{x}»" for x in FUERA_DE_GIT if x not in txt]


def generado_editado_a_mano() -> list[str]:
    """Los perfiles se regeneran con un script. Si alguien los edita, la."""
    fallas = []
    for rel in GENERADOS:
        ruta = RAIZ / rel
        if not ruta.exists():
            continue
        cabeza = ruta.read_text(encoding="utf-8", errors="replace")[:1200].lower()
        if "no se edita" not in cabeza and "generado" not in cabeza:
            fallas.append(f"{rel} — sin la marca de «documento generado»")
    return fallas


def excel_sin_leer_ni_descartar() -> list[str]:
    """Ningún Excel de Habitat puede quedar fuera sin que alguien lo decida."""
    crudos = RAIZ / "data" / "raw_exports"
    if not crudos.exists():
        return []
    cubiertas = {"contasis", "contasis_empresas", "gastos_manuales",
                 "marketing", "cronogramas", "contasis_mensual"}
    ignoradas_json = RAIZ / "config" / "fuentes_ignoradas.json"
    decididas: set[str] = set()
    if ignoradas_json.exists():
        try:
            datos = json.loads(ignoradas_json.read_text(encoding="utf-8"))
            decididas = {k.split("/", 1)[1] for k in datos
                         if k.startswith("Excel/")}
        except (json.JSONDecodeError, IndexError):
            return ["config/fuentes_ignoradas.json no se puede leer"]
    leidos = {"gastos_2026-07-22.xls", "SALDOS CAJA HUANCAYO.xlsx",
              "cabida_valle_alto.xlsx", "cabida_multifamiliar.xlsx",
              "egp_valle_alto.xlsx", "REPORTE DE VENTAS 2025.xlsx",
              "CONTROL DE GASTOS - LISBETH 2025.xlsx",
              "CONTROL DE GASTOS - LISBETH 2026.xlsx"}

    fallas = []
    for f in sorted(crudos.rglob("*.xls*")):
        if f.name.startswith("~$") or "_respaldo" in str(f):
            continue
        rel = f.relative_to(crudos)
        raiz = rel.parts[0]
        if raiz in cubiertas or raiz in decididas or f.name in decididas \
                or f.name in leidos:
            continue
        fallas.append(f"data/raw_exports/{rel} — ningún módulo lo lee y no "
                      f"hay motivo escrito en config/fuentes_ignoradas.json")
    return fallas


def ingesta_rota() -> list[str]:
    """Que los módulos de ingesta al menos IMPORTEN. Es barato y caza el error."""
    sys.path.insert(0, str(RAIZ))
    fallas = []
    for mod in ("src.lectura_excel", "src.contasis", "src.administracion",
                "src.exports_axion", "src.ingest"):
        try:
            importlib.import_module(mod)
        except Exception as e:  # noqa: BLE001
            fallas.append(f"{mod} no importa — {type(e).__name__}: {str(e)[:80]}")
    return fallas


def cifras_que_no_cuadran() -> list[str]:
    """Que el tablero no se contradiga a sí mismo."""
    sys.path.insert(0, str(RAIZ))
    try:
        from src import cuadre  # noqa: PLC0415
        return cuadre.comprobar()
    except Exception as e:  # noqa: BLE001
        return [f"no se pudo comprobar el cuadre de cifras — {type(e).__name__}: "
                f"{str(e)[:90]}"]


def hoja_sin_grupo() -> list[str]:
    """Una hoja publicada que no está en ningún grupo NO EXISTE para el que."""
    import re
    arm = RAIZ / "scripts" / "armar_cockpit.py"
    js = RAIZ / "design" / "cockpit.js"
    if not arm.exists() or not js.exists():
        return []
    t_arm = arm.read_text(encoding="utf-8")
    m = re.search(r"^HOJAS = \[(.*?)^\]", t_arm, re.S | re.M)
    if not m:
        return ["no encontré la lista HOJAS en scripts/armar_cockpit.py"]
    hojas = re.findall(r'\(\s*"([\w-]+)"\s*,\s*"[\w-]+"\s*,', m.group(1))
    t_js = js.read_text(encoding="utf-8")
    g = re.search(r"var GRUPOS = \[(.*?)^\];", t_js, re.S | re.M)
    if not g:
        return ["no encontré la lista GRUPOS en design/cockpit.js"]
    en_grupo = set(re.findall(r'"([\w-]+)"', g.group(1)))
    sueltas = [h for h in hojas if h not in en_grupo and h != "ventas-kpi"]
    malas = []
    if sueltas:
        malas.append(f"hojas publicadas que no están en ningún grupo de la "
                     f"barra, así que nadie puede llegar a ellas: "
                     f"{', '.join(sueltas)}")
    l = re.search(r"var HOJAS = \[(.*?)^\];", t_js, re.S | re.M)
    con_nombre = set(re.findall(r'id:\s*"([\w-]+)"', l.group(1))) if l else set()
    sin_nombre = [h for h in hojas if h not in con_nombre]
    if sin_nombre:
        malas.append(f"hojas sin nombre en la lista HOJAS de design/cockpit.js, "
                     f"así que la barra muestra su id: {', '.join(sin_nombre)}")
    return malas


def saldo_por_cuenta_cuadra() -> list[str]:
    """LA REGLA DEL SALDO, COMPROBADA."""
    ruta = RAIZ / "tablero_datos.json"
    if not ruta.exists():
        return []
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        return [f"no pude leer tablero_datos.json para el saldo por cuenta: "
                f"{type(e).__name__}"]
    cc = datos.get("control_cuentas") or {}
    cuentas = cc.get("cuentas") or []
    if not cuentas:
        return []
    L = ((datos.get("libro") or {}).get("filas")) or {}
    noms = L.get("cuenta") or []
    anio = str(cc.get("anio") or "")
    mov: dict[str, dict[int, float]] = {}
    saldos_fila: dict[str, dict[int, float]] = {}
    for r in L.get("f") or []:
        f = str(r[0] or "")
        if not f.startswith(anio):
            continue
        cu = str(noms[r[6]] or "") if r[6] is not None and r[6] < len(noms) else ""
        cu = cu or "SIN BANCO"
        m = int(f[5:7])
        con = str(r[3] or "").strip().upper()
        if r[7] == "presupuesto" and con.startswith("SALDO"):
            saldos_fila.setdefault(cu, {})[m] = saldos_fila.get(cu, {}).get(m, 0) + (r[4] or 0)
            continue
        signo = -1 if r[7] == "gasto" else 1
        mov.setdefault(cu, {})[m] = round(mov.get(cu, {}).get(m, 0) + signo * (r[4] or 0), 2)
    malas = []
    for c in cuentas:
        cu = c.get("cu") or ""
        saldo = c.get("ap")
        if saldo is None:
            saldo = 0.0
        for m in c.get("meses") or []:
            saldo = round(saldo + (mov.get(cu, {}).get(m["m"], 0)), 2)
            if abs(saldo - m["ax"]) > 0.01:
                malas.append(f"ESPEC_CAJA · «{cu[:34]}» mes {m['m']}: el tablero "
                             f"publica {m['ax']:,.2f} y la cadena da {saldo:,.2f}")
                break
            fila = saldos_fila.get(cu, {}).get(m["m"])
            if fila and abs(m["ax"] - (saldo + fila)) < 0.01:
                malas.append(f"ESPEC_CAJA · «{cu[:34]}» mes {m['m']}: la fila SALDO "
                             f"de {fila:,.2f} entró en la suma")
                break
    ent: dict[str, dict[int, float]] = {}
    sal: dict[str, dict[int, float]] = {}
    cuantos: dict[str, dict[int, int]] = {}
    for r in L.get("f") or []:
        f = str(r[0] or "")
        if not f.startswith(anio):
            continue
        cu = str(noms[r[6]] or "") if r[6] is not None and r[6] < len(noms) else ""
        cu = cu or "SIN BANCO"
        m = int(f[5:7])
        if r[7] == "presupuesto" and str(r[3] or "").strip().upper().startswith("SALDO"):
            continue
        if r[7] == "gasto":
            sal.setdefault(cu, {})[m] = round(sal.get(cu, {}).get(m, 0) + (r[4] or 0), 2)
        elif r[7] in ("venta", "presupuesto"):
            ent.setdefault(cu, {})[m] = round(ent.get(cu, {}).get(m, 0) + (r[4] or 0), 2)
        cuantos.setdefault(cu, {})[m] = cuantos.get(cu, {}).get(m, 0) + 1
    for c in cuentas:
        cu = c.get("cu") or ""
        for m in c.get("meses") or []:
            n = m["m"]
            for rot, publica, registro in (
                    ("entró", m.get("e", 0), ent.get(cu, {}).get(n, 0)),
                    ("salió", m.get("s", 0), sal.get(cu, {}).get(n, 0)),
                    ("cuántos", m.get("n", 0), cuantos.get(cu, {}).get(n, 0))):
                if abs(publica - registro) > 0.01:
                    malas.append(
                        f"ESPEC_CAJA · «{cu[:30]}» mes {n}: la celda publica "
                        f"{rot} {publica:,.2f} y el detalle del clic da "
                        f"{registro:,.2f}")
                    break
    ent_m: dict[int, float] = {}
    sal_m: dict[int, float] = {}
    for r in L.get("f") or []:
        f = str(r[0] or "")
        if not f.startswith(anio):
            continue
        if r[7] == "presupuesto" and str(r[3] or "").strip().upper().startswith("SALDO"):
            continue
        m = int(f[5:7])
        if r[7] == "gasto":
            sal_m[m] = round(sal_m.get(m, 0) + (r[4] or 0), 2)
        elif r[7] in ("venta", "presupuesto"):
            ent_m[m] = round(ent_m.get(m, 0) + (r[4] or 0), 2)
    cadena = sum(c.get("ap") or 0 for c in cuentas)
    for m in sorted(set(ent_m) | set(sal_m)):
        cadena = round(cadena + ent_m.get(m, 0) - sal_m.get(m, 0), 2)
        tot = 0.0
        for c in cuentas:
            ms = c.get("meses") or []
            val = next((x["ax"] for x in ms if x["m"] == m), None)
            if val is None and ms and ms[-1]["m"] < m:
                val = ms[-1]["ax"]
            tot += val or 0
        if abs(cadena - tot) > 0.01:
            malas.append(f"ESPEC_CAJA · mes {m}: «Caja neta · Saldo encadenado» "
                         f"llega a {cadena:,.2f} y la ventana del dinero dice "
                         f"{tot:,.2f} — dos saldos del grupo en la misma hoja")
            break
    # y la hoja tiene que seguir sumando los traspasos recibidos en la cadena
    h0 = RAIZ / "design" / "hoy.html"
    if h0.exists() and 'r[7] !== "venta" && r[7] !== "presupuesto"' not in h0.read_text(encoding="utf-8"):
        malas.append("ESPEC_CAJA · design/hoy.html: `entroDe` volvió a contar "
                     "solo la clase «venta», así que los traspasos entre "
                     "cuentas propias salen de la cadena y no vuelven a entrar")

    for hoja in ("hoy.html", "caja.html"):
        f = RAIZ / "design" / hoja
        if f.exists() and "CCm[cu]" not in f.read_text(encoding="utf-8"):
            malas.append(f"ESPEC_CAJA · design/{hoja} ya no lee el saldo de "
                         f"`control_cuentas`: volvió a calcularlo por su cuenta")
    # El panel del clic tiene que seguir existiendo y leyendo esas dos fuentes.
    h = (RAIZ / "design" / "hoy.html")
    if h.exists():
        txt = h.read_text(encoding="utf-8")
        if 'id.indexOf("cm-")' not in txt:
            malas.append("ESPEC_CAJA · design/hoy.html perdió el panel del mes "
                         "(el clic sobre una celda del mes a mes)")
        elif 'cQ.cu === "SIN BANCO" ? "" : cQ.cu' not in txt:
            malas.append("ESPEC_CAJA · design/hoy.html: el panel del mes dejó de "
                         "traducir «SIN BANCO» a la cuenta vacía del Registro, "
                         "así que esa fila saldría en cero")
    return malas[:6]


def reconciliacion_completa() -> list[str]:
    """Comprueba que `docs/perfil_excels.md` publicado coincida con lo que la."""
    sys.path.insert(0, str(RAIZ))
    from src import administracion as adm  # noqa: PLC0415
    from src import contasis  # noqa: PLC0415
    from src import lectura_excel as lx  # noqa: PLC0415

    doc = RAIZ / "docs" / "perfil_excels.md"
    if not doc.exists():
        return ["falta docs/perfil_excels.md: no hay contra qué reconciliar"]
    perfil = sum(int(x.replace(",", "")) for x in re.findall(
        r"([\d,]+) filas de detalle", doc.read_text(encoding="utf-8")))

    det = 0
    for df in (contasis.tablas(), adm.movimientos()):
        if not df.empty:
            det += int((df["_clase"] == "detalle").sum())
    hojas = lx.leer_carpeta(lx.CRUDOS / "cabidas")
    for f in sorted(lx.CRUDOS.glob("*.xls*")):
        hojas += lx.leer_archivo(f)
    for h in hojas:
        if h.forma == "tabla" and "_clase" in h.datos.columns:
            det += int((h.datos["_clase"] == "detalle").sum())

    if det != perfil:
        return [f"la ingesta cuenta {det:,} filas de detalle y el perfilador "
                f"{perfil:,} — difieren en {abs(det - perfil):,}"]
    print(f"  reconciliación: el documento publicado y la ingesta coinciden "
          f"en {det:,} filas de detalle (mismo parser: verifica que el "
          f"documento esté al día, no dos lecturas independientes)")
    return []


PORTADORES = {
    "ojo": "los avisos y hallazgos de cada cifra",
    "alerta": "las alertas con «qué pasó / cómo se cierra / quién responde»",
    "alc": "el alcance de cada indicador del Scorecard",
    "avlist": "la lista de avisos plegada de cada tarjeta",
    "motivo": "el motivo por el que una cifra no se puede calcular",
    "quien": "el área de Habitat que responde por el hallazgo",
    "nota": "la nota que explica de dónde sale cada bloque",
    "vacio": "el texto que aparece cuando una cifra no tiene data",
}

APAGONES = (
    (r"display\s*:\s*none", "lo oculta por completo"),
    (r"visibility\s*:\s*hidden", "lo deja invisible"),
    (r"font-size\s*:\s*0", "lo reduce a cero"),
    (r"opacity\s*:\s*0(?![.\d])", "lo vuelve transparente"),
    (r"max-height\s*:\s*0", "lo aplasta a cero de alto"),
    (r"content-visibility\s*:\s*hidden", "lo saca del renderizado"),
)


def diseno_esconde_hallazgos() -> list[str]:
    """¿El CSS está apagando alguno de los textos que son el producto?."""
    ruta = RAIZ / "assets" / "tablero.css"
    if not ruta.exists():
        return []
    css = ruta.read_text(encoding="utf-8", errors="replace")
    css = re.sub(r"/\*.*?\*/", " ", css, flags=re.S)
    fallas = []
    for bloque in re.finditer(r"([^{}]+)\{([^{}]*)\}", css):
        selector, cuerpo = bloque.group(1).strip(), bloque.group(2)
        for clase, que_es in PORTADORES.items():
            if not re.search(rf"\.{clase}\b[\w.:()\[\]-]*\s*(,|$)",
                             selector.replace("\n", " ")):
                continue
            for patron, efecto in APAGONES:
                if re.search(patron, cuerpo, re.I):
                    fallas.append(
                        f"assets/tablero.css esconde «{que_es}»: la regla "
                        f"«{selector[:60]}» {efecto}. Los textos pegados a "
                        f"cada cifra son el producto (regla 3 de "
                        f"docs/REGLAS_DISENO.md): se pueden plegar tras un "
                        f"clic, no apagar")
    return fallas


def escribir_acta(fallas: list[str], completo: bool, controles: int) -> None:
    """Deja constancia de la corrida en `data/acta_verificacion.json`."""
    acta = {
        "cuando": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "alcance": "completo" if completo else "rápido",
        "controles": controles,
        "resultado": "en verde" if not fallas else "en rojo",
        "fallas": fallas,
    }
    ruta = RAIZ / "data" / "acta_verificacion.json"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(acta, indent=1, ensure_ascii=False),
                    encoding="utf-8")


def main() -> int:
    completo = "--completo" in sys.argv
    controles = [clave_en_el_codigo, caracteres_de_control,
                 data_publicada_vieja, cifras_que_se_contradicen_entre_hojas,
                 tarjeta_contra_su_propia_lista,
                 detalle_del_mes_cuadra,
                 cobranza_coherente, comercial_coherente, crm_coherente,
                 obra_coherente, finanzas_coherente,
                 concept_coherente,
                 gitignore_incompleto,
                 generado_editado_a_mano, excel_sin_leer_ni_descartar,
                 ingesta_rota, cifras_que_no_cuadran,
                 saldo_por_cuenta_cuadra, hoja_sin_grupo,
                 diseno_esconde_hallazgos]
    fallas = [f for control in controles for f in control()]
    corridos = len(controles)
    if completo and not fallas:
        fallas += reconciliacion_completa()
        corridos += 1
    escribir_acta(fallas, completo, corridos)
    if fallas:
        print("VERIFICACIÓN EN ROJO:")
        for f in fallas:
            print(f"  · {f}")
        return 1
    alcance = ("credenciales, caracteres invisibles, data al día, cuadre entre "
               "hojas, tarjeta contra su propia lista, CUADRE DEL DETALLE POR "
               "MES, .gitignore, generados, "
               "cobertura de Excels, ingesta, "
               "CUADRE DE CIFRAS, SALDO POR CUENTA contra el motor único, "
               "coherencia de Cobranza, de Comercial, del CRM y "
               "de Obra, de Finanzas, hallazgos a la vista "
               "y reconciliación" if completo else
               "credenciales, caracteres invisibles, data al día, cuadre entre "
               "hojas, tarjeta contra su propia lista, CUADRE DEL DETALLE POR "
               "MES, .gitignore, generados, "
               "cobertura de Excels, ingesta, "
               "CUADRE DE CIFRAS, SALDO POR CUENTA contra el motor único, "
               "coherencia de Cobranza, de Comercial, del CRM, "
               "de Obra y de Finanzas, y hallazgos a la vista")
    print(f"verificación: sin hallazgos en {alcance}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
