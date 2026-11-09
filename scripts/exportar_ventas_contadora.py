"""Saca del Excel de la contadora los DOCE TOTALES y solo eso."""
from __future__ import annotations

import json
import pathlib
import sys

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from src import ventas_contadora as vc  # noqa: E402


def main() -> int:
    datos = vc._del_excel()
    if not datos:
        print(f"ALTO: no se pudo leer {vc.EXCEL}")
        print("      El Excel tiene que estar en data/raw_exports/ con ese nombre.")
        return 1

    vc.TOTALES.parent.mkdir(parents=True, exist_ok=True)
    vc.TOTALES.write_text(json.dumps(
        {"anio": 2025,
         "fuente": "REPORTE DE VENTAS 2025.xlsx · total por hoja",
         "meses": {str(k): v for k, v in sorted(datos.items())}},
        ensure_ascii=False, indent=1), encoding="utf-8")

    con = [m for m in datos.values() if m.get("monto")]
    print(f"{vc.TOTALES.relative_to(RAIZ)} · {len(datos)} meses, "
          f"{len(con)} con cifra")
    for m in sorted(datos.values(), key=lambda x: x["mes"]):
        cif = f"{m['monto']:,.2f}" if m.get("monto") else "#REF! (fórmula rota)"
        print(f"  {m['nombre']:11} {cif:>22}   {m['celda']}")
    print(f"  {'TOTAL':11} {sum(m['monto'] for m in con):>22,.2f}")

    crudo = vc.TOTALES.read_text(encoding="utf-8")
    sospechoso = [p for p in ("dni", "celular", "cliente", "telefono")
                  if p in crudo.lower()]
    if sospechoso:
        print(f"\nALTO: el JSON contiene {sospechoso} — NO subirlo")
        return 1
    print("\n  sin nombres, sin DNI, sin celulares: se puede versionar")
    return 0


if __name__ == "__main__":
    sys.exit(main())
