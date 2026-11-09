"""EL DETALLE DEL CRM **CON NOMBRES**, en un archivo que NO se comparte."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "scripts"))

from src import kommo  # noqa: E402
import exportar_clientes as clientes  # noqa: E402

SALIDA = RAIZ / "data" / "crm_leads.json"


def main() -> int:
    if not kommo.disponible():
        print("Kommo no está disponible: revisá KOMMO_SUBDOMINIO y KOMMO_TOKEN "
              "en .env. No se escribió nada.")
        return 1

    try:
        leads, _ = clientes._leads()
        contactos = clientes._contactos([f["_contacto"] for f in leads])
    except kommo.KommoNoResponde as e:
        print(f"Kommo no respondió ({e}). No se escribió nada: queda el archivo anterior.")
        return 1
    if not leads:
        print("Kommo devolvió 0 leads del embudo. No se escribió nada.")
        return 1
    nombres = {f["id"]: clientes.nombre_persona(f["_lead"], contactos.get(f["_contacto"]))
               for f in leads}

    from src import crm
    filas = crm.filas_leads(None, None)
    if not filas:
        print("La hoja CRM no tiene filas. No se escribió nada.")
        return 1
    for f in filas:
        f["nombre"] = nombres.get(f["id"], "")

    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    tmp = SALIDA.with_name(SALIDA.name + ".tmp")
    tmp.write_text(json.dumps(
        {"cuando": pd.Timestamp.now(tz="America/Lima").strftime("%Y-%m-%d %H:%M"),
         "leads": len(filas), "filas": filas},
        ensure_ascii=False), encoding="utf-8")
    tmp.replace(SALIDA)

    con = sum(1 for f in filas if f["nombre"])
    rotulo = sum(1 for f in filas if re.match(r"^lead\s*#", f["nombre"], re.I))
    sin_lectura = sum(1 for f in filas if f["id"] not in nombres)
    print(f"{len(filas):,} leads escritos en data/crm_leads.json")
    print(f"con nombre: {con:,} de {len(filas):,} · con el rótulo «Lead #…»: {rotulo:,} · "
          f"sin fila en la lectura de contactos: {sin_lectura:,}")
    print(f"peso: {SALIDA.stat().st_size / 1024:,.0f} KB")
    print("\nESTE ARCHIVO LLEVA NOMBRES DE CLIENTES DE HABITAT.")
    print("· NO entra a tablero_datos.json, que es el que se comparte")
    print("· vive en data/, que .gitignore excluye")
    print("· el servidor lo entrega solo con clave y nunca al rol externo")
    return 0


if __name__ == "__main__":
    sys.exit(main())
