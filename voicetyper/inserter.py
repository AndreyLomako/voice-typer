"""Вставка распознанного текста в нужное место."""
from __future__ import annotations

import time

from . import system
from .config import Settings


def _wait_modifiers_released(timeout: float = 2.0) -> None:
    """Иначе Ctrl+V превратится, например, в Ctrl+Alt+V."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not system.modifiers_down():
            return
        time.sleep(0.03)


def insert_text(text: str, settings: Settings, mouse_pos: tuple[int, int] | None) -> None:
    if not text:
        return
    _wait_modifiers_released()

    if settings.insert_target == "mouse" and mouse_pos is not None:
        system.click_at(*mouse_pos)
        time.sleep(0.12)

    if settings.insert_method == "type":
        system.type_text(text)
        return

    snapshot = system.clipboard_snapshot() if settings.restore_clipboard else None
    system.clipboard_set_text(text, private=True)
    time.sleep(0.05)
    system.send_paste()
    time.sleep(0.35)
    if settings.restore_clipboard:
        system.clipboard_restore(snapshot)
