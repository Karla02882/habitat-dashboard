"""CÁLCULO · LAS OBSERVACIONES ABIERTAS DE CAJA."""
from __future__ import annotations

UMBRAL = 1.0


def caja(cc: dict, cadena: dict, hasta: str = "") -> list:
    """La lista de observaciones abiertas del dinero."""
    obs = []
    cuentas = (cc or {}).get("cuentas") or []
    if not cuentas:
        return obs
    bh = (cc.get("banco_al_dia") or {})
    fecha_foto = bh.get("fecha") or ""

    def add(que, cifra, detalle, area, quien=""):
        obs.append({"n": len(obs) + 1, "que": que, "cifra": cifra,
                    "detalle": detalle, "area": area, "quien": quien})

    sin_foto = [c for c in cuentas
                if "bhoy" not in c and c["cu"] not in ("EFECTIVO", "SIN BANCO")]
    if sin_foto:
        add("Cuentas de banco sin captura del banco",
            f"{len(sin_foto)} de {len(cuentas)} cuentas",
            " · ".join(c["cu"] for c in sin_foto),
            "Administración",
            "sin su saldo real esas cuentas solo se pueden mirar por AXION")

    # 2 · una cifra del banco que no declara de dónde salió
    for c in [x for x in cuentas if x.get("bhoy_f")]:
        add("Saldo del banco sin declarar su origen",
            f"S/ {c['bhoy']:,.2f}",
            f"{c['cu']}: llegó sin captura, así que no se puede afirmar que "
            f"venga del banco",
            "Administración",
            "coincide al céntimo con lo que calcula AXION para esa cuenta")

    # 3 · el desfase entre la foto del banco y lo cargado en AXION
    if fecha_foto and hasta and fecha_foto > hasta:
        add("La foto del banco y AXION son de días distintos",
            f"banco {fecha_foto} · AXION {hasta}",
            "lo que se movió en el medio todavía no está cargado, así que la "
            "diferencia de cada cuenta incluye ese tramo",
            "Administración")

    dups = [(c["cu"], m["m"], m["dup"]) for c in cuentas
            for m in c.get("meses") or [] if m.get("dup")]
    if dups:
        add("Saldos cargados dos veces en el Registro",
            f"S/ {sum(d[2] for d in dups):,.2f} en {len(dups)} filas",
            " · ".join(f"{d[0]}: S/ {d[2]:,.2f}" for d in dups),
            "Administración",
            "el cockpit no las suma; la pantalla de AXION sí, y por eso infla")

    sb = next((c for c in cuentas if c["cu"] == "SIN BANCO"), None)
    if sb and sb.get("meses"):
        n = sum(m.get("n", 0) for m in sb["meses"])
        add("Movimientos sin cuenta asignada",
            f"S/ {sb['meses'][-1]['ax']:,.2f} en {n} movimientos",
            "no se pueden comparar contra ningún banco ni entran al cierre de "
            "Administración",
            "Administración")

    # 6 · el efectivo, que no tiene banco que lo compruebe
    ef = next((c for c in cuentas if c["cu"] == "EFECTIVO"), None)
    if ef and ef.get("meses"):
        add("Efectivo sin arqueo",
            f"S/ {ef['meses'][-1]['ax']:,.2f}",
            "su única prueba es contar la caja chica y compararla con el "
            "saldo del día",
            "Administración")

    # 7 · una cuenta de banco no puede quedar en negativo
    for c in cuentas:
        ms = c.get("meses") or []
        if ms and ms[-1]["ax"] < -UMBRAL and c["cu"] != "SIN BANCO":
            add("Cuenta de banco en negativo",
                f"S/ {ms[-1]['ax']:,.2f}",
                f"{c['cu']}: o falta cargar lo que entró, o hay salidas "
                f"cargadas de más",
                "Administración")

    # 8 · una cuenta sin saldo inicial declarado en AXION
    for c in cuentas:
        if c.get("ap") is None and c["cu"] != "SIN BANCO":
            add("Cuenta sin saldo inicial en AXION",
                "sin apertura",
                f"{c['cu']}: no tiene fila en la tabla SaldoInicial, así que "
                f"su saldo es solo lo que se movió",
                "Administración")

    difs = []
    for c in cuentas:
        if "bhoy" not in c or c.get("axb") is None:
            continue
        d = round(c["axb"] - c["bhoy"], 2)
        if abs(d) > UMBRAL:
            difs.append((c["cu"], d))
    if difs:
        difs.sort(key=lambda x: -abs(x[1]))
        add("El banco y AXION no dicen lo mismo",
            f"S/ {sum(d[1] for d in difs):,.2f} en {len(difs)} cuentas",
            f"al {fecha_foto}: " +
            " · ".join(f"{a}: S/ {b:,.2f}" for a, b in difs),
            "Administración",
            "a mitad de mes puede ser atraso de carga; al cierre del mes "
            "tiene que dar cero")

    # 10 · el cierre de Administración contra la cadena, con la misma población
    fuera = {m["m"]: m["ax"] for m in (sb.get("meses") or [])} if sb else {}
    ult_mes = None
    for m in (cadena or {}).get("meses") or []:
        if m.get("real") is not None:
            ult_mes = m
    if ult_mes:
        tot = 0.0
        for c in cuentas:
            ms = c.get("meses") or []
            v = next((x["ax"] for x in ms if x["m"] == ult_mes["mes"]), None)
            if v is None and ms and ms[-1]["m"] < ult_mes["mes"]:
                v = ms[-1]["ax"]
            tot += v or 0
        comparable = round(tot - fuera.get(ult_mes["mes"], 0), 2)
        d = round(ult_mes["real"] - comparable, 2)
        if abs(d) > UMBRAL:
            add("El cierre de Administración no coincide con AXION",
                f"S/ {d:,.2f}",
                f"{ult_mes['nombre']}: Administración S/ "
                f"{ult_mes['real']:,.2f} contra S/ {comparable:,.2f} de "
                f"AXION, sobre {ult_mes.get('cuentas') or '?'} cuentas",
                "Administración")

    eras = [(c["cu"], m["m"], m["era"], m["ax"]) for c in cuentas
            for m in c.get("meses") or [] if m.get("era") is not None]
    if eras:
        add("Meses ya cerrados que cambiaron después",
            f"{len(eras)} meses",
            " · ".join(f"{a} mes {b}: era S/ {c:,.2f} y hoy S/ {d:,.2f}"
                       for a, b, c, d in eras),
            "Administración")

    return obs
