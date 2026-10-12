"""Значок программы (микрофон + бейдж «hs»): трей, окно, файлы .ico/.png."""
from __future__ import annotations

from PIL import Image, ImageDraw, ImageFont

COLORS = {
    "idle": (77, 163, 255),
    "recording": (255, 77, 94),
    "processing": (255, 176, 32),
    "disabled": (130, 136, 145),
}


def draw_icon(color: tuple[int, int, int], size: int = 64, badge: bool = True) -> Image.Image:
    """Микрофон в круге + бейдж «hs» в правом нижнем углу."""
    s = size / 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((0, 0, size - 1, size - 1), fill=color + (255,))
    white = (255, 255, 255, 255)
    dx = -5 * s if badge else 0          # микрофон чуть левее, чтобы не прятался под бейджем
    d.rounded_rectangle((24 * s + dx, 10 * s, 40 * s + dx, 36 * s), radius=8 * s, fill=white)
    w = max(1, round(3.5 * s))
    d.arc((17 * s + dx, 18 * s, 47 * s + dx, 44 * s), start=0, end=180, fill=white, width=w)
    d.line((32 * s + dx, 44 * s, 32 * s + dx, 50 * s), fill=white, width=w)
    d.line((24 * s + dx, 51 * s, 40 * s + dx, 51 * s), fill=white, width=w)
    if badge:
        bx0, by0, bx1, by1 = 34 * s, 38 * s, 64 * s - 1, 60 * s
        d.rounded_rectangle((bx0, by0, bx1, by1), radius=7 * s, fill=(24, 26, 31, 255),
                            outline=white, width=max(1, round(1.6 * s)))
        try:
            font = ImageFont.truetype("segoeuib.ttf", max(6, round(17 * s)))
        except OSError:
            font = ImageFont.load_default()
        d.text(((bx0 + bx1) / 2, (by0 + by1) / 2 - 0.5 * s), "hs", fill=white, font=font, anchor="mm")
    return img
