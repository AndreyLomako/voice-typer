"""Иконка в системном трее."""
from __future__ import annotations

from typing import Callable

import pystray
from PIL import Image, ImageDraw, ImageFont

from . import APP_TITLE

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


class Tray:
    def __init__(self, on_settings: Callable, on_toggle_record: Callable, on_toggle_enabled: Callable,
                 on_copy_last: Callable, on_quit: Callable, is_enabled: Callable[[], bool]):
        self._images = {k: draw_icon(v) for k, v in COLORS.items()}
        menu = pystray.Menu(
            pystray.MenuItem("Настройки", lambda: on_settings(), default=True),
            pystray.MenuItem("Запись в буфер обмена (старт / стоп)", lambda: on_toggle_record()),
            pystray.MenuItem("Скопировать последний текст", lambda: on_copy_last()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Горячие клавиши включены", lambda: on_toggle_enabled(),
                             checked=lambda item: is_enabled()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Выход", lambda: on_quit()),
        )
        self.icon = pystray.Icon("VoiceTyper hs", self._images["idle"], APP_TITLE, menu)

    def run(self):
        self.icon.run_detached()

    def set_state(self, state: str, tooltip: str | None = None):
        self.icon.icon = self._images.get(state, self._images["idle"])
        self.icon.title = tooltip or APP_TITLE
        try:
            self.icon.update_menu()
        except Exception:
            pass

    def notify(self, text: str):
        try:
            self.icon.notify(text, APP_TITLE)
        except Exception:
            pass

    def stop(self):
        try:
            self.icon.stop()
        except Exception:
            pass
