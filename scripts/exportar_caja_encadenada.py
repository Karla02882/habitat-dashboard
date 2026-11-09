from __future__ import annotations

import json
import pathlib
import sys

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from src import caja_encadenada as ce  # noqa: E402

PROHIBIDAS = ("dni", "celular", "cliente", "telefono", "velasco", "yean",
              "gloria", "cuota", "lote", "escalar", "corporacion")


def main() -> int:
    datos = ce._de_excel()
    if not datos:
        print("ALTO: faltan archivos en data/raw_exports/:")
        for p in (ce.EXCEL_2025, ce.EXCEL_2026, ce.LIBRO_CMAC):
            print(f"      {'ok  ' if p.exists() else 'NO  '} {p.name}")
        return 1

    ce.CIERRES.parent.mkdir(parents=True, exist_ok=True)
    salida = dict(datos)
    salida["meses"] = {str(k): v for k, v in sorted(datos["meses"].items())}
    ce.CIERRES.write_text(json.dumps(salida, ensure_ascii=False, indent=1),
                          encoding="utf-8")

    a = datos["arranque"]
    print(f"{ce.CIERRES.relative_to(RAIZ)} · {len(datos['meses'])} meses")
    print(f"  {'ARRANQUE (cierre 2025)':24} {a['total']:>16,.2f}   "
          f"= {a['administracion']:,.2f} Administración + {a['cmac']:,.2f} CMAC")
    for m in sorted(datos["meses"].values(), key=lambda x: x["mes"]):
        print(f"  {m['nombre']:24} {m['real']:>16,.2f}   "
              f"= {m['administracion']:>14,.2f} + {m['cmac']:>14,.2f}   "
              f"({m['cuentas']} cuentas) · {m['fuente']}")
    print(f"  Libro Mayor generado el {datos.get('libro_generado') or '?'}")

    crudo = ce.CIERRES.read_text(encoding="utf-8").lower()
    sospechoso = [p for p in PROHIBIDAS if p in crudo]
    if sospechoso:
        print(f"\nALTO: el JSON contiene {sospechoso} — NO subirlo")
        return 1
    print("\n  sin nombres, sin cuentas, sin conceptos: se puede versionar")
    return 0


if __name__ == "__main__":
    sys.exit(main())
