"""LA ESTRUCTURA DEL INGRESO."""
from __future__ import annotations

import pandas as pd

from . import ingest, periodo


COBRO_SOLO_CUENTAS_POR_COBRAR = True


def _n(s) -> pd.Series:
    return pd.to_numeric(s, errors="coerce").fillna(0)


def _doc(s) -> str:
    return "".join(c for c in str(s or "").upper() if c.isalnum())


def calcular(mes=None) -> dict:
    """Las tres cifras del período, más el reparto por modalidad."""
    sale = ingest.fetch_axion_entity("Sale", None, 5000)
    cred = ingest.fetch_axion_entity("Credit", None, 5000)
    cxc = ingest.fetch_axion_entity("CxCPayment", None, 5000)

    v = periodo.recortar(sale[sale["status"] == "Vendido"], "date", mes)
    if v.empty:
        return {"hay": False, "periodo": periodo.etiqueta(mes)}

    por_doc: dict[str, list] = {}
    por_obra_unidad: dict[tuple, list] = {}
    for _, cr in cred.iterrows():
        d = _doc(cr.get("client_document"))
        if d:
            por_doc.setdefault(d, []).append(cr)
        o = _doc(cr.get("project"))
        for u in {_doc(x) for x in str(cr.get("unit") or "").split("+") if _doc(x)}:
            por_obra_unidad.setdefault((o, u), []).append(cr)

    def _abonado_de(cr, vistos: set | None = None) -> float:
        """Lo que entró por este crédito, cada recibo UNA sola vez."""
        tot = 0.0
        for e in (cr.get("iniciales") or []):
            if not isinstance(e, dict):
                continue
            if "pendiente" in str(e.get("tipo") or "").lower():
                continue
            if vistos is not None:
                serie = str(e.get("serie") or "").strip()
                k = (serie if serie else
                     f"{e.get('tipo')}|{e.get('monto')}|{e.get('fecha')}")
                if k in vistos:
                    continue
                vistos.add(k)
            try:
                tot += float(str(e.get("monto", "")).replace(",", "") or 0)
            except ValueError:
                pass
        p = cxc[cxc["credit_id"] == cr["id"]]
        return tot + (float(_n(p["monto"]).sum()) if len(p) else 0.0)

    contratado = float(_n(v["sale_price"]).sum())
    entro = saldo = 0.0
    sin_credito, monto_sin = 0, 0.0
    compartido, monto_compartido = 0, 0.0
    usados: set = set()
    entro_por_venta: dict = {}
    detalle_por_venta: dict = {}
    for idx, r in v.iterrows():
        precio_v = float(_n(pd.Series([r["sale_price"]])).iloc[0])
        todos = por_doc.get(_doc(r.get("dni"))) or []
        if not todos:
            _o = _doc(r.get("project"))
            vistos_id, todos = set(), []
            for _u in {_doc(x) for x in str(r.get("unit") or "").split("+") if _doc(x)}:
                for cr in por_obra_unidad.get((_o, _u), []):
                    if cr["id"] in vistos_id:
                        continue
                    if _doc(cr.get("client_document")):
                        continue
                    vistos_id.add(cr["id"]); todos.append(cr)
        crs = [cr for cr in todos if cr["id"] not in usados]
        detalle_por_venta[idx] = {
            "cliente": str(r.get("client") or "—"),
            "obra": str(r.get("project") or "—"),
            "unidad": str(r.get("unit") or "—"),
            "fecha": str(r.get("date") or "")[:10],
            "banco": str(r.get("bank") or "").strip(),
            "asesor": str(r.get("advisor") or "").strip(),
            "precio": precio_v,
            "entro": 0.0,
            "falta": precio_v,
            "sin_credito": not todos,
            "credito_compartido": False,
            "creditos": 0,
            "entro_axion": float(_n(pd.Series([r.get("real_income")])).iloc[0]),
        }
        def _partes(u) -> set:
            return {_doc(x) for x in str(u or "").split("+") if _doc(x)}

        u_venta = _partes(r.get("unit"))
        o_venta = _doc(r.get("project"))
        _empareja = (lambda cr: bool(u_venta and (_partes(cr.get("unit")) & u_venta)
                                     and _doc(cr.get("project")) == o_venta))
        con_unidad = [cr for cr in crs if _empareja(cr)]
        elegidos = con_unidad
        if not elegidos:
            _habia = [cr for cr in todos if _empareja(cr)]
            if _habia:
                compartido += 1
                monto_compartido += precio_v
                detalle_por_venta[idx]["sin_credito"] = False
                detalle_por_venta[idx]["credito_compartido"] = True
                detalle_por_venta[idx]["creditos"] = len(_habia)
                detalle_por_venta[idx]["entro_de"] = "hermana"
            else:
                sin_credito += 1
                monto_sin += precio_v
                detalle_por_venta[idx]["sin_credito"] = True
            _ax = 0.0 if _habia else detalle_por_venta[idx]["entro_axion"]
            if _ax > 0:
                if COBRO_SOLO_CUENTAS_POR_COBRAR:
                    detalle_por_venta[idx]["entro"] = 0.0
                    detalle_por_venta[idx]["falta"] = precio_v
                    detalle_por_venta[idx]["entro_de"] = "sin_cargar"
                else:
                    entro += _ax
                    entro_por_venta[idx] = _ax
                    detalle_por_venta[idx]["entro"] = _ax
                    detalle_por_venta[idx]["falta"] = precio_v - _ax
                    detalle_por_venta[idx]["entro_de"] = "axion"
            continue
        abonado_v = 0.0
        vistos: set = set()
        for cr in elegidos:
            usados.add(cr["id"])
            abonado_v += _abonado_de(cr, vistos)
            saldo += float(_n(pd.Series([cr["saldo_pendiente"]])).iloc[0])
        _ax = detalle_por_venta[idx]["entro_axion"]
        if abonado_v < 0.01 and _ax > 0:
            if COBRO_SOLO_CUENTAS_POR_COBRAR:
                detalle_por_venta[idx]["entro_de"] = "sin_cargar"
            else:
                abonado_v = _ax
                detalle_por_venta[idx]["entro_de"] = "axion"
        else:
            detalle_por_venta[idx]["entro_de"] = "credito"
        entro += abonado_v
        entro_por_venta[idx] = abonado_v
        detalle_por_venta[idx]["entro"] = abonado_v
        detalle_por_venta[idx]["falta"] = precio_v - abonado_v
        detalle_por_venta[idx]["creditos"] = len(elegidos)

    _n_no_medible = _monto_no_medible = 0
    _n_solo_axion = _monto_solo_axion = 0
    _monto_sin_cargar = 0.0
    for _x in detalle_por_venta.values():
        if not _x.get("entro_de"):
            _n_no_medible += 1
            _monto_no_medible += _x["precio"]
        elif _x["entro_de"] in ("axion", "sin_cargar"):
            if _x["entro_de"] == "sin_cargar":
                _monto_sin_cargar += _x.get("entro_axion") or 0.0
            _n_solo_axion += 1
            _monto_solo_axion += _x["precio"]
    _monto_no_medible = float(_monto_no_medible)
    _monto_solo_axion = float(_monto_solo_axion)

    modalidad = []
    _mod = v["modality"].fillna("").astype(str).str.strip()
    _mod = _mod.where(_mod != "", "(sin modalidad cargada)")
    for m, g in v.groupby(_mod):
        filas = [detalle_por_venta[i] for i in g.index if i in detalle_por_venta]
        # De mayor a menor: el que abre el detalle busca primero las grandes.
        filas.sort(key=lambda x: -x["precio"])
        modalidad.append({
            "modalidad": m,
            "ventas": int(len(g)),
            "monto": float(_n(g["sale_price"]).sum()),
            "entro": float(sum(entro_por_venta.get(i, 0.0) for i in g.index)),
            "base": float(sum(
                detalle_por_venta[i]["precio"] for i in g.index
                if i in detalle_por_venta and detalle_por_venta[i].get("entro_de"))),
            "sin_credito": int(sum(
                1 for i in g.index
                if i in detalle_por_venta and not detalle_por_venta[i].get("entro_de"))),
            "detalle": filas,
            "ritmo": {
                "Contado": "entra completo al firmar",
                "Hipoteca": "entra cuando el banco desembolsa, no al firmar",
                "Crédito directo": "entra en cuotas, a lo largo de años",
            }.get(m, "sin modalidad declarada: no se sabe cómo entra"),
        })
    modalidad.sort(key=lambda x: -x["monto"])

    docs = v["dni"].map(_doc)
    repetidos = docs[docs != ""].value_counts()
    n_repes = int((repetidos > 1).sum())

    DIAS_GRACIA = 7
    hoy = pd.Timestamp.today().normalize()
    cont_flojas, cont_frescas = [], []
    for idx, r in v.iterrows():
        if str(r.get("modality") or "").strip().lower() != "contado":
            continue
        precio = float(_n(pd.Series([r["sale_price"]])).iloc[0])
        puesto = entro_por_venta.get(idx, 0.0)
        puesto_ax = float(_n(pd.Series([r.get("real_income")])).iloc[0])
        cubierto = max(puesto, puesto_ax)
        if precio - cubierto <= 1:
            continue
        f = pd.to_datetime(r.get("date"), errors="coerce")
        dias = None if pd.isna(f) else int((hoy - f.normalize()).days)
        fila = {
            "cliente": str(r.get("client") or "—"),
            "obra": str(r.get("project") or "—"),
            "unidad": str(r.get("unit") or "—"),
            "asesor": str(r.get("advisor") or "").strip() or "—",
            "precio": precio, "abonado": puesto,
            "abonado_axion": puesto_ax,
            "falta": precio - cubierto,
            "sin_credito": puesto == 0.0,
            "discrepan": abs(puesto - puesto_ax) > 1,
            "dias": dias,
        }
        (cont_frescas if (dias is not None and dias <= DIAS_GRACIA)
         else cont_flojas).append(fila)
    cont_flojas.sort(key=lambda x: -x["falta"])
    cont_frescas.sort(key=lambda x: -x["falta"])

    return {
        "hay": True,
        "periodo": periodo.etiqueta(mes),
        "ventas": int(len(v)),
        "contratado": contratado,
        "entro": entro,
        "falta": contratado - entro,
        "saldo": saldo,
        "pct_entro": ((100 * entro / (contratado - _monto_no_medible))
                      if (contratado - _monto_no_medible) > 0 else None),
        "pct_entro_sobre_todo": (100 * entro / contratado) if contratado else 0.0,
        "base_comparable": contratado - _monto_no_medible,
        "modalidad": modalidad,
        # Las que no tienen el cobro en NINGUNA de las dos partes.
        "sin_credito": _n_no_medible,
        "monto_sin_credito": _monto_no_medible,
        "sin_credito_con_ingreso": _n_solo_axion,
        "monto_sin_credito_con_ingreso": _monto_solo_axion,
        # lo que el módulo de ventas da por cobrado y cuentas por cobrar no
        "monto_sin_cargar": float(_monto_sin_cargar),
        "credito_compartido": compartido,
        "monto_credito_compartido": monto_compartido,
        "clientes_con_varias_ventas": n_repes,
        "contado_incompleto": cont_flojas,
        # Las de esta semana, aparte: se muestran, no se acusan.
        "contado_recien_firmado": cont_frescas,
        "dias_gracia": DIAS_GRACIA,
        "descuadre": (entro + saldo) - contratado,
    }
