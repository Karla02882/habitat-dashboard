"""LOS MOROSOS, CON NOMBRE Y TELÉFONO."""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from src import filas, ingest, reloj  # noqa: E402


def destino() -> Path:
    """La misma regla de carpeta que `exportar_clientes.py` y `servidor.py`."""
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
    return base / "morosos.json"


def _t(v) -> str:
    s = "" if v is None else str(v).strip()
    return "" if s.lower() in ("nan", "none", "nat", "<na>") else s


def _n(s) -> pd.Series:
    return pd.to_numeric(s, errors="coerce").fillna(0.0)


def _wa(tel: str) -> str:
    d = re.sub(r"\D", "", tel or "")
    if len(d) == 9 and d.startswith("9"):
        return "51" + d
    return d if len(d) >= 10 else ""


def _marcar(tel: str) -> str:
    w = _wa(tel)
    return ("+" + w) if w else re.sub(r"[^\d+]", "", tel or "")


def armar() -> dict:
    hoy = pd.Timestamp(reloj.ahora().date())
    cuotas = ingest.fetch_axion_entity("Installment", None, 5000)
    creditos = ingest.fetch_axion_entity("Credit", None, 5000)
    proyectos = ingest.fetch_axion_entity("Project", None, 500)
    tipo_de = {_t(r["name"]): _t(r.get("project_type")) or "(sin tipo)"
               for _, r in proyectos.iterrows()}

    cuotas = cuotas.assign(
        saldo=(_n(cuotas["monto_cuota"]) - _n(cuotas["monto_pagado"])).clip(lower=0),
        vence=pd.to_datetime(cuotas["fecha_vencimiento"], errors="coerce"))
    vencidas = cuotas[cuotas["estado"].apply(_t).eq("pendiente")
                      & (cuotas["vence"] < hoy) & (cuotas["saldo"] > 0)]

    por_id = {_t(r["id"]): r for _, r in creditos.iterrows()}
    filas_out, borrados = [], {"creditos": 0, "cuotas": 0, "vencido": 0.0}
    for cid, g in vencidas.groupby(vencidas["credit_id"].apply(_t)):
        desde = g["vence"].min()
        base = {"cuotas": int(len(g)), "vencido": round(float(g["saldo"].sum()), 2),
                "desde": desde.strftime("%Y-%m-%d"), "dias": int((hoy - desde).days)}
        c = por_id.get(cid)
        if c is None:
            borrados["creditos"] += 1
            borrados["cuotas"] += base["cuotas"]
            borrados["vencido"] = round(borrados["vencido"] + base["vencido"], 2)
            continue
        tel = _t(c.get("client_phone"))
        proyecto = _t(c.get("project"))
        filas_out.append({
            "id": cid,
            "cliente": _t(c.get("client_name")) or "(sin nombre)",
            "tel": tel, "marcar": _marcar(tel) if tel else "",
            "wa": _wa(tel) if tel else "",
            "proyecto": proyecto or "(sin obra)",
            "unidad": _t(c.get("unit")),
            "tipo": tipo_de.get(proyecto, "(sin tipo)"),
            "asesor": filas.asesor(c.get("advisor")),
            "estado": _t(c.get("estado")),
            "saldo": round(float(pd.to_numeric(c.get("saldo_pendiente"), errors="coerce") or 0.0), 2),
            "nota_axion": _t(c.get("notas")),
            "prorroga": None,
            **base,
        })
    filas_out.sort(key=lambda f: -f["dias"])
    return {
        "hay": True,
        "generado": reloj.sello(),
        "hoy": str(hoy.date()),
        "filas": filas_out,
        "tipos": sorted({f["tipo"] for f in filas_out}),
        "prorroga": "No existe en la API de AXION",
    }, borrados


def main() -> int:
    try:
        datos, borrados = armar()
    except Exception as e:  # noqa: BLE001 — AXION caído: queda el archivo anterior
        print(f"morosos: AXION no respondió ({type(e).__name__}: {e}); "
              f"queda el archivo anterior")
        return 1
    ruta = destino()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tmp = ruta.with_suffix(".tmp")
    tmp.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
    tmp.replace(ruta)
    f = datos["filas"]
    print(f"morosos: {len(f)} créditos con cuotas vencidas "
          f"({sum(x['cuotas'] for x in f)} cuotas · S/ {sum(x['vencido'] for x in f):,.2f}) · "
          f"{sum(1 for x in f if x['tipo'] == 'Lotes')} de lotes · "
          f"fuera: {borrados['cuotas']} cuotas vencidas de {borrados['creditos']} "
          f"créditos borrados en AXION (S/ {borrados['vencido']:,.2f}) · {ruta}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
