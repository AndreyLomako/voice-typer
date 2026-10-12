"""Вставка распознанного текста в нужное место."""
from __future__ import annotations

import time

import keyboard
import pyperclip

from .config import Settings
from .winutil import click_at

_MODIFIERS = ("ctrl", "alt", "shift", "left windows", "right windows")


def _wait_modifiers_released(timeout: float = 2.0) -> None:
    """Иначе Ctrl+V превратится, например, в Ctrl+Alt+V."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not any(keyboard.is_pressed(m) for m in _MODIFIERS):
            return
        time.sleep(0.03)


def insert_text(text: str, settings: Settings, mouse_pos: tuple[int, int] | None) -> None:
    if not text:
        return
    _wait_modifiers_released()

    if settings.insert_target == "mouse" and mouse_pos is not None:
        click_at(*mouse_pos)
        time.sleep(0.12)

    if settings.insert_method == "type":
        keyboard.write(text, delay=0.005)
        return

    previous = None
    if settings.restore_clipboard:
        try:
            previous = pyperclip.paste()
        except Exception:
            previous = None
    pyperclip.copy(text)
    time.sleep(0.05)
    keyboard.send("ctrl+v")
    if previous is not None:
        time.sleep(0.35)
        try:
            pyperclip.copy(previous)
        except Exception:
            pass
