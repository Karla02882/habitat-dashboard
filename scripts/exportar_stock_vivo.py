"""EL STOCK EN VIVO."""
from __future__ import annotations

import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "scripts"))

from src import cambios_inventario, stock  # noqa: E402
import exportar_cambios_inventario as _carpeta  # noqa: E402


def _sin_nan(x):
    """Un NaN no es JSON y el navegador no lo lee: se manda como vacío."""
    if isinstance(x, float) and (x != x or x in (float("inf"), float("-inf"))):
        return None
    if isinstance(x, dict):
        return {k: _sin_nan(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_sin_nan(v) for v in x]
    return x


def destino() -> Path:
    """La misma carpeta que los demás archivos que sobreviven al despliegue."""
    return _carpeta.destino().parent / "stock_vivo.json"


def main() -> int:
    try:
        datos = stock.calcular()
    except Exception as e:  # noqa: BLE001 — AXION caído: queda el archivo anterior
        print(f"stock en vivo: AXION no respondió ({type(e).__name__}: {e}); "
              f"queda el archivo anterior")
        return 1
    if not datos.get("hay"):
        print(f"stock en vivo: no se publica ({datos.get('motivo')}); queda el archivo anterior")
        return 1
    fallas = stock.sin_datos_de_personas(datos)
    if fallas:
        print("stock en vivo NO publicado: " + " · ".join(fallas))
        return 1
    ruta = destino()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tmp = ruta.with_suffix(".tmp")
    tmp.write_text(json.dumps(_sin_nan(datos), ensure_ascii=False, allow_nan=False), encoding="utf-8")
    tmp.replace(ruta)
    t = datos["totales"]
    print(f"stock en vivo: {t['libres']} libres de {t['unidades']} unidades en "
          f"{t['proyectos']} tarjetas · leído {datos['leido']} · último cambio en AXION "
          f"{datos['ultima_edicion'] or '—'} · {ruta}")
    try:
        cambios_inventario.actualizar(_carpeta.destino())
    except Exception as e:  # noqa: BLE001 — el registro nunca tumba el stock
        print(f"  registro de cambios: no se renovó ({type(e).__name__}: {e})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
