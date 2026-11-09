"""LOS ÍCONOS DE LA APP INSTALABLE."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

RAIZ = Path(__file__).resolve().parents[1]
LOGO = RAIZ / "assets" / "logo-white.png"
SALIDA = RAIZ / "pwa"
# El azul de la cabecera del cockpit (`--navy-700`).
AZUL = (22, 49, 128, 255)
FILAS_LOGO = (0, 325)


def _logo() -> Image.Image:
    im = Image.open(LOGO).convert("RGBA")
    return im.crop((0, FILAS_LOGO[0], im.width, FILAS_LOGO[1]))


def _icono(lado: int, ancho_logo: float, redondeado: bool) -> Image.Image:
    fondo = Image.new("RGBA", (lado, lado), AZUL)
    logo = _logo()
    w = round(lado * ancho_logo)
    h = round(logo.height * w / logo.width)
    logo = logo.resize((w, h), Image.LANCZOS)
    fondo.alpha_composite(logo, ((lado - w) // 2, (lado - h) // 2))
    if not redondeado:
        return fondo
    k = 4
    mascara = Image.new("L", (lado * k, lado * k), 0)
    ImageDraw.Draw(mascara).rounded_rectangle(
        (0, 0, lado * k - 1, lado * k - 1), radius=round(lado * k * 0.20), fill=255)
    mascara = mascara.resize((lado, lado), Image.LANCZOS)
    fondo.putalpha(mascara)
    return fondo


def main() -> int:
    SALIDA.mkdir(exist_ok=True)
    hechos = {
        "icono-192.png": _icono(192, 0.70, True),
        "icono-512.png": _icono(512, 0.70, True),
        "icono-maskable-512.png": _icono(512, 0.54, False),
        # iOS: sin transparencia (la pone negra) y el logo un poco más grande
        "apple-touch-icon.png": _icono(180, 0.66, False).convert("RGB"),
    }
    for nombre, im in hechos.items():
        im.save(SALIDA / nombre, optimize=True)
        print(f"  pwa/{nombre} · {im.width}x{im.height} · "
              f"{(SALIDA / nombre).stat().st_size:,} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
