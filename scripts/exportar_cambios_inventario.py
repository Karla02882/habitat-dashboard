"""LOS CAMBIOS DE STOCK Y DE PRECIO."""
from __future__ import annotations

import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from src import cambios_inventario  # noqa: E402


def destino() -> Path:
    """La misma regla de carpeta que `exportar_morosos.py` y `servidor.py`."""
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
    return base / "cambios_inventario.json"


def main() -> int:
    ruta = destino()
    primera = not ruta.exists()
    try:
        d = cambios_inventario.actualizar(ruta)
    except Exception as e:  # noqa: BLE001 — AXION caído o lectura mala: queda el anterior
        print(f"cambios de inventario: no se renovó ({type(e).__name__}: {e}); "
              f"queda el archivo anterior")
        return 1
    ev = d["eventos"]
    print(f"cambios de inventario: {d['unidades']} unidades · "
          + ("línea base fijada, el registro empieza ahora" if primera
             else f"{sum(1 for e in ev if e['t'] == d['ultima'])} cambios en esta lectura, "
                  f"{len(ev)} en total desde {d['base']}")
          + f" · {len(d['ventas'])} ventas en 30 días · {ruta}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
