"""LOS CLIENTES DE KOMMO, CON NOMBRE Y TELÉFONO."""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from src import kommo  # noqa: E402
from src.crm import ETAPAS_CALIFICADO  # noqa: E402

CERRADAS = ("DESESTIMADO", "VENDIDO")
SIN_LLAMADA = ("Numero incorrecto", "Lead Duplicado")
DIAS_FRIO = 30
DIAS_DESESTIMADO = 90
SEGUIMIENTOS = ("seguimiento_1", "seguimiento_2", "seguimiento_3")


def destino() -> Path:
    """La misma regla de carpeta que `generar_tablero.py` y `servidor.py`."""
    v = (os.getenv("TABLERO_DATOS_DIR") or "").strip()
    if v:
        base = Path(v)
    elif ((os.getenv("RENDER") or (os.getenv("PORT") and not os.getenv("TABLERO_PUERTO")))
          and Path("/var/data").is_dir()):
        base = Path("/var/data")
    else:
        base = RAIZ
    if base.resolve() == RAIZ.resolve():
        base = RAIZ / "data"
    return base / "clientes_kommo.json"


def _lima(ts) -> pd.Timestamp | None:
    if ts is None:
        return None
    try:
        if pd.isna(ts):
            return None
    except (TypeError, ValueError):
        pass
    ts = pd.Timestamp(ts)
    if ts.tzinfo is not None:
        ts = ts.tz_convert("America/Lima").tz_localize(None)
    return ts


def _dia(ts) -> str:
    return ts.strftime("%Y-%m-%d") if ts is not None else ""


def _wa(tel: str) -> str:
    d = re.sub(r"\D", "", tel or "")
    if len(d) == 9 and d.startswith("9"):
        return "51" + d
    return d if len(d) >= 10 else ""


def _marcar(tel: str) -> str:
    w = _wa(tel)
    return ("+" + w) if w else re.sub(r"[^\d+]", "", tel or "")


def _visible(tel: str) -> str:
    d = re.sub(r"\D", "", tel or "")
    if len(d) == 11 and d.startswith("51"):
        return f"+51 {d[2:5]} {d[5:8]} {d[8:]}"
    if len(d) == 9 and d.startswith("9"):
        return f"{d[0:3]} {d[3:6]} {d[6:]}"
    return (tel or "").strip()


def nombre_persona(nombre_lead: str, contacto: dict | None) -> str:
    """El nombre de la PERSONA: el del contacto; si el contacto no tiene, el."""
    n = str((contacto or {}).get("nombre") or "").strip()
    if n:
        return n
    s = str(nombre_lead or "").strip()
    return "" if re.match(r"^lead\s*#", s, re.I) else s


def _leads() -> tuple[list[dict], int]:
    """Los leads del embudo Habitat, con su contacto principal."""
    etapas = kommo._etapas()
    usuarios = kommo.usuarios()
    motivos = kommo.motivos_perdida()
    if not usuarios or not motivos:
        raise kommo.KommoNoResponde("Kommo no devolvió el catálogo de usuarios o de motivos")
    filas, leidos, pagina = [], 0, 1
    while pagina <= kommo.TOPE_PAGINAS:
        cuerpo = kommo._pedir("/api/v4/leads", {
            "page": pagina, "limit": kommo.POR_PAGINA, "with": "contacts"})
        time.sleep(kommo.PAUSA)
        if not cuerpo:
            break
        items = kommo._coleccion(cuerpo)
        if not items:
            break
        leidos += len(items)
        for x in items:
            pid = x.get("pipeline_id")
            if pid != kommo.EMBUDO_HABITAT:
                continue
            cs = x.get("_embedded", {}).get("contacts") or []
            principal = next((c["id"] for c in cs if c.get("is_main")),
                             cs[0]["id"] if cs else None)
            f = {
                "id": x.get("id"),
                "_lead": str(x.get("name") or "").strip(),
                "_contacto": principal,
                "etapa": etapas.get((pid, x.get("status_id")), ""),
                "asesor": usuarios.get(x.get("responsible_user_id"),
                                       "(sin responsable)"),
                "motivo": motivos.get(x.get("loss_reason_id")) or "",
                "_creado": kommo._momento(x.get("created_at")),
                "_cerrado": kommo._momento(x.get("closed_at")),
                "_tarea": kommo._momento(x.get("closest_task_at")),
            }
            for c in (x.get("custom_fields_values") or []):
                dst = kommo.CAMPOS.get(c.get("field_name") or "")
                if not dst:
                    continue
                vals = [v.get("value") for v in (c.get("values") or [])
                        if v.get("value") not in (None, "")]
                if not vals:
                    continue
                f[dst] = (kommo._momento(vals[0]) if dst in kommo.FECHAS
                          else " · ".join(str(v) for v in vals))
            filas.append(f)
        if not (cuerpo.get("_links") or {}).get("next"):
            break
        pagina += 1
    return filas, leidos


def _contactos(ids: list) -> dict:
    """{contacto_id: {nombre, tels, correo}} por lotes de 100."""
    out: dict = {}
    ids = list(dict.fromkeys(i for i in ids if i))
    for i in range(0, len(ids), 100):
        params: dict = {"limit": kommo.POR_PAGINA}
        params.update({f"filter[id][{j}]": cid
                       for j, cid in enumerate(ids[i:i + 100])})
        cuerpo = kommo._pedir("/api/v4/contacts", params)
        time.sleep(kommo.PAUSA)
        for c in kommo._coleccion(cuerpo or {}):
            tels, mails = [], []
            for cf in (c.get("custom_fields_values") or []):
                vals = [str(v.get("value")).strip() for v in (cf.get("values") or [])
                        if v.get("value")]
                if cf.get("field_code") == "PHONE":
                    tels += vals
                elif cf.get("field_code") == "EMAIL":
                    mails += vals
            out[c["id"]] = {"nombre": str(c.get("name") or "").strip(),
                            "tels": list(dict.fromkeys(tels)),
                            "correo": mails[0] if mails else ""}
    return out


def main() -> int:
    if not kommo.disponible():
        print("Kommo no está disponible: revisá KOMMO_SUBDOMINIO y KOMMO_TOKEN "
              "en .env. No se escribió nada.")
        return 1
    t0 = time.time()
    try:
        leads, leidos = _leads()
        contactos = _contactos([f["_contacto"] for f in leads])
    except kommo.KommoNoResponde as e:
        print(f"Kommo no respondió ({e}). No se escribió nada: queda el archivo anterior.")
        return 1
    if not leads:
        print("Kommo devolvió 0 leads del embudo. No se escribió nada.")
        return 1

    ahora = pd.Timestamp.now(tz="America/Lima").tz_localize(None)
    hoy = ahora.normalize()
    filas = []
    for f in leads:
        c = contactos.get(f["_contacto"]) or {}
        nombre = nombre_persona(f["_lead"], c)
        tels = [x for x in (c.get("tels") or []) if len(re.sub(r"\D", "", x)) >= 7]
        tel = tels[0] if tels else ""
        creado = _lima(f.get("_creado"))
        cerrado = _lima(f.get("_cerrado"))
        tarea = _lima(f.get("_tarea"))
        llamada = _lima(f.get("primera_llamada"))
        visita = _lima(f.get("visita_presencial"))
        segs = [_lima(f.get(k)) for k in SEGUIMIENTOS]
        toques = [t for t in [llamada, visita] + segs
                  if t is not None and t.normalize() <= hoy]
        ultimo = max(toques) if toques else None
        desde = ultimo if ultimo is not None else creado
        dias = int((hoy - desde.normalize()).days) if desde is not None else None
        etapa = f["etapa"]
        abierto = etapa not in CERRADAS
        nunca = llamada is None and visita is None and all(s is None for s in segs)

        seg = []
        if abierto and etapa in ETAPAS_CALIFICADO:
            seg.append("calificados")
        if etapa != "VENDIDO" and visita is not None and visita.normalize() <= hoy:
            seg.append("visitaron")
        if abierto and tarea is not None and tarea.normalize() < hoy:
            seg.append("tareas")
        if abierto and nunca:
            seg.append("nunca")
        if abierto and not nunca and dias is not None and dias >= DIAS_FRIO:
            seg.append("frios")
        if (etapa == "DESESTIMADO" and f["motivo"] not in SIN_LLAMADA
                and cerrado is not None
                and (hoy - cerrado.normalize()).days <= DIAS_DESESTIMADO):
            seg.append("desestimados")
        if etapa == "VENDIDO":
            seg.append("compraron")
        if abierto and not tel:
            seg.append("sintel")

        filas.append({
            "id": f["id"],
            "nombre": nombre,
            "tel": _visible(tel) if tel else "",
            "marcar": _marcar(tel) if tel else "",
            "wa": _wa(tel) if tel else "",
            "mas_tel": [_visible(t) for t in tels[1:]],
            "correo": c.get("correo", ""),
            "etapa": etapa,
            "asesor": f["asesor"],
            "proyecto": f.get("proyecto", ""),
            "campana": f.get("campana", ""),
            "producto": f.get("producto", ""),
            "interes": f.get("nivel_interes", ""),
            "motivo": f["motivo"],
            "creado": _dia(creado),
            "llamada": _dia(llamada),
            "seguimientos": sum(1 for s in segs if s is not None),
            "visita": _dia(visita),
            "ultimo": _dia(ultimo),
            "dias": dias,
            "tarea": _dia(tarea),
            "cerrado": _dia(cerrado),
            "abierto": abierto,
            "seg": seg,
        })

    out = destino()
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + ".tmp")
    tmp.write_text(json.dumps({
        "cuando": ahora.strftime("%Y-%m-%d %H:%M"),
        "hoy": hoy.strftime("%Y-%m-%d"),
        "embudo": "Ventas - Habitat Inmobiliaria",
        "leads": len(filas),
        "dias_frio": DIAS_FRIO,
        "dias_desestimado": DIAS_DESESTIMADO,
        "sin_llamada": list(SIN_LLAMADA),
        "filas": filas,
    }, ensure_ascii=False), encoding="utf-8")
    tmp.replace(out)

    print(f"{len(filas):,} leads del embudo Habitat (de {leidos:,} leídos en Kommo) "
          f"· {time.time() - t0:.0f} s")
    print(f"con nombre: {sum(1 for x in filas if x['nombre']):,} · "
          f"con teléfono: {sum(1 for x in filas if x['tel']):,} · "
          f"con WhatsApp armable: {sum(1 for x in filas if x['wa']):,} · "
          f"abiertos: {sum(1 for x in filas if x['abierto']):,}")
    for k in ("calificados", "visitaron", "tareas", "nunca", "frios",
              "desestimados", "compraron", "sintel"):
        print(f"  {k:<13} {sum(1 for x in filas if k in x['seg']):,}")
    print(f"escrito: {out} · {out.stat().st_size / 1024:,.0f} KB")
    print("LLEVA NOMBRES Y TELÉFONOS: fuera de git y solo para el rol admin.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
