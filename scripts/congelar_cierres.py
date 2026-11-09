# -*- coding: utf-8 -*-
"""Congela el cierre de cada cuenta en los meses YA CERRADOS."""
from __future__ import annotations

import datetime
import json
import pathlib
import sys

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from src import control_cuentas, movimientos  # noqa: E402


def main() -> int:
    rehacer = "--rehacer" in sys.argv
    destino = control_cuentas.CONGELADOS
    previo = {}
    if destino.exists() and not rehacer:
        previo = (json.loads(destino.read_text(encoding="utf-8")).get("cierres") or {})
    cc = control_cuentas.control(movimientos.crudo())
    hoy = datetime.date.today()
    mes_en_curso = hoy.month if hoy.year == control_cuentas.ANIO else 13
    cierres, nuevos = {}, 0
    for c in cc["cuentas"]:
        ya = dict(previo.get(c["cu"]) or {})
        for f in c["meses"]:
            if f["m"] >= mes_en_curso:
                continue
            k = str(f["m"])
            if k not in ya:
                ya[k] = f["ax"]
                nuevos += 1
        if ya:
            cierres[c["cu"]] = ya
    destino.write_text(json.dumps({
        "_que_es": "El cierre de cada cuenta en los meses ya cerrados, tal como "
                   "lo daba AXION el día que se congeló. Lo compara "
                   "src/control_cuentas.py en cada corrida.",
        "anio": control_cuentas.ANIO,
        "congelado_el": hoy.isoformat(),
        "cierres": cierres,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    tot = {}
    for meses in cierres.values():
        for k, v in meses.items():
            tot[int(k)] = round(tot.get(int(k), 0) + v, 2)
    print(f"cierres congelados: {len(cierres)} cuentas · {nuevos} cierres nuevos")
    for m in sorted(tot):
        print(f"   mes {m:>2} · total {tot[m]:>14,.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
