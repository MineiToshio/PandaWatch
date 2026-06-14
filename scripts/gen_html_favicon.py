#!/usr/bin/env python3
"""Genera el favicon de la app HTML local (web/) a partir del logo del panda.

La app pública (Next.js) usa el panda "tal cual" sobre fondo transparente
(`web-next/app/icon.png` + `app/favicon.ico`). Para poder DIFERENCIAR las dos
apps en la barra de pestañas del navegador, el favicon de la app HTML local usa
el MISMO panda pero compuesto sobre un cuadrado redondeado del color de acento
de la app HTML (--accent: #d63384). Cambio mínimo, simple y on-brand.

Fuente única del logo: `web-next/app/icon.png` (1024×1024 RGBA).
Salidas (en `web/`):
  - favicon.ico          → multi-size ICO (16/32/48/64) para <link rel=icon>
  - apple-touch-icon.png → 180×180 para iOS / "Add to Home Screen"

Reproducible: si cambia el logo o el color, re-correr este script.

    .venv/bin/python scripts/gen_html_favicon.py
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "web-next" / "app" / "icon.png"
OUT_DIR = ROOT / "web"

# Color de acento de la app HTML (web/index.html → --accent). Único diferenciador
# frente al favicon público de Next.js (que va sobre fondo transparente).
BG_COLOR = (214, 51, 132, 255)  # #d63384

MASTER = 512          # lienzo de trabajo en alta resolución
RADIUS = 112          # radio del cuadrado redondeado (~22% → estilo "squircle")
PANDA_SCALE = 0.86    # fracción del lienzo que ocupa el panda recortado


def build_master() -> Image.Image:
    """Panda recortado y centrado sobre el cuadrado redondeado de acento."""
    # Lienzo con fondo de acento + esquinas redondeadas (vía máscara alpha).
    canvas = Image.new("RGBA", (MASTER, MASTER), BG_COLOR)
    mask = Image.new("L", (MASTER, MASTER), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, MASTER - 1, MASTER - 1), radius=RADIUS, fill=255
    )

    # Recortar el panda a su bounding box real (la fuente tiene mucho transparente
    # alrededor del "burst"); así llena el ícono y se lee a 16-32px.
    panda = Image.open(SOURCE).convert("RGBA")
    panda = panda.crop(panda.getbbox())

    # Escalar preservando aspecto para que entre en PANDA_SCALE del lienzo.
    target = int(MASTER * PANDA_SCALE)
    w, h = panda.size
    ratio = min(target / w, target / h)
    panda = panda.resize((max(1, round(w * ratio)), max(1, round(h * ratio))), Image.LANCZOS)

    # Centrar y pegar usando el alpha del panda.
    px = (MASTER - panda.width) // 2
    py = (MASTER - panda.height) // 2
    canvas.paste(panda, (px, py), panda)

    # Aplicar las esquinas redondeadas al resultado final.
    canvas.putalpha(mask)
    return canvas


def main() -> None:
    master = build_master()

    ico_path = OUT_DIR / "favicon.ico"
    master.save(ico_path, sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])

    apple = master.resize((180, 180), Image.LANCZOS)
    apple_path = OUT_DIR / "apple-touch-icon.png"
    apple.save(apple_path)

    print(f"wrote {ico_path.relative_to(ROOT)}  (16/32/48/64)")
    print(f"wrote {apple_path.relative_to(ROOT)}  (180×180)")


if __name__ == "__main__":
    main()
