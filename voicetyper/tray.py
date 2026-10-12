"""Иконка в системном трее."""
from __future__ import annotations

from typing import Callable

import pystray

from . import APP_TITLE
from .icon import COLORS, draw_icon


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
