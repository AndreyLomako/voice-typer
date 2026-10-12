"""Иконка в системном трее."""
from __future__ import annotations

from typing import Callable

import pystray
from PIL import Image, ImageDraw

from . import APP_TITLE

COLORS = {
    "idle": (77, 163, 255),
    "recording": (255, 77, 94),
    "processing": (255, 176, 32),
    "disabled": (130, 136, 145),
}


def draw_icon(color: tuple[int, int, int], size: int = 64) -> Image.Image:
    s = size / 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((0, 0, size - 1, size - 1), fill=color + (255,))
    white = (255, 255, 255, 255)
    # капсула микрофона
    d.rounded_rectangle((24 * s, 12 * s, 40 * s, 38 * s), radius=8 * s, fill=white)
    # дужка
    w = max(1, round(3.5 * s))
    d.arc((17 * s, 20 * s, 47 * s, 46 * s), start=0, end=180, fill=white, width=w)
    # ножка и основание
    d.line((32 * s, 46 * s, 32 * s, 52 * s), fill=white, width=w)
    d.line((24 * s, 53 * s, 40 * s, 53 * s), fill=white, width=w)
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
        self.icon = pystray.Icon("VoiceTyper", self._images["idle"], APP_TITLE, menu)

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
