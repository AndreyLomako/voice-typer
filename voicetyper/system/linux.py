"""Linux (сессия X11): хук и ввод через pynput, состояние клавиш через python-xlib.

Wayland не даёт программам перехватывать глобальные клавиши и вводить текст в чужие
окна, поэтому нужна сессия Xorg (на экране входа: «Ubuntu on Xorg» и т.п.).
"""
from __future__ import annotations

import os
import shlex
import sys
import threading
from pathlib import Path

from .. import APP_DISPLAY, APP_NAME
from . import posix
from .posix import (beep, clipboard_restore, clipboard_set_text, clipboard_snapshot, message_box,  # noqa: F401
                    protect, restrict_file, unprotect)

NAME = "linux"
UI_FONT = "DejaVu Sans"
SUPPORTS_CUDA = True
DEFAULT_HOLD = "right ctrl"
DEFAULT_TOGGLE = "ctrl+alt+space"
KEY_NAMES = {"windows": "Super", "left windows": "Super", "right windows": "Правый Super"}


def config_dir() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / APP_NAME


def data_dir() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / APP_NAME


def acquire_single_instance() -> bool:
    return posix.acquire_single_instance(config_dir())


def check_permissions() -> str | None:
    if os.environ.get("XDG_SESSION_TYPE") == "wayland" or (os.environ.get("WAYLAND_DISPLAY")
                                                            and not os.environ.get("DISPLAY")):
        return ("Сессия Wayland: глобальные клавиши и вставка работают только в сессии Xorg. "
                "Выйдите из системы и выберите «… on Xorg» на экране входа.")
    if not os.environ.get("DISPLAY"):
        return "Не найден X-сервер (переменная DISPLAY)."
    return None


def open_permission_settings() -> None:
    pass


# ---------------------------------------------------------------- мышь и ввод (pynput)
_mouse = _kbd = None


def _controllers():
    global _mouse, _kbd
    if _mouse is None:
        from pynput import keyboard, mouse
        _mouse, _kbd = mouse.Controller(), keyboard.Controller()
    return _mouse, _kbd


def cursor_pos() -> tuple[int, int]:
    x, y = _controllers()[0].position
    return int(x), int(y)


def click_at(x: int, y: int) -> None:
    from pynput.mouse import Button
    m = _controllers()[0]
    m.position = (x, y)
    m.click(Button.left)


def send_paste() -> None:
    from pynput.keyboard import Key
    k = _controllers()[1]
    with k.pressed(Key.ctrl):
        k.tap("v")


def type_text(text: str) -> None:
    _controllers()[1].type(text)


# ---------------------------------------------------------------- состояние клавиш (Xlib)
_display = None
_xlock = threading.Lock()   # одно соединение Xlib, а обращаются из разных потоков
_MOD_KEYSYMS = ("Control_L", "Control_R", "Alt_L", "Alt_R", "Shift_L", "Shift_R", "Super_L", "Super_R",
                "ISO_Level3_Shift")


def _keymap() -> bytes | None:
    global _display
    with _xlock:
        try:
            if _display is None:
                from Xlib import display
                _display = display.Display()
            return bytes(_display.query_keymap())
        except Exception:
            return None


def _keysym_to_keycode(keysym: int) -> int:
    with _xlock:
        try:
            return _display.keysym_to_keycode(keysym) or 0
        except Exception:
            return 0


def _keycode_down(keymap: bytes, keycode: int) -> bool:
    return bool(keymap[keycode // 8] & (1 << (keycode % 8)))


def modifiers_down() -> bool:
    km = _keymap()
    if km is None:
        return False
    from Xlib import XK
    for sym in _MOD_KEYSYMS:
        code = _keysym_to_keycode(XK.string_to_keysym(sym))
        if code and _keycode_down(km, code):
            return True
    return False


def physically_down(name: str, scan: int) -> bool:
    if not scan:
        return True
    km = _keymap()
    return True if km is None else _keycode_down(km, scan)


def scan_codes(token: str) -> set[int]:
    return set()


# ---------------------------------------------------------------- хук клавиатуры
_SPECIAL = {
    "ctrl": "left ctrl", "ctrl_l": "left ctrl", "ctrl_r": "right ctrl",
    "alt": "left alt", "alt_l": "left alt", "alt_r": "right alt", "alt_gr": "right alt",
    "shift": "left shift", "shift_l": "left shift", "shift_r": "right shift",
    "cmd": "left windows", "cmd_l": "left windows", "cmd_r": "right windows",
    "page_up": "page up", "page_down": "page down", "caps_lock": "caps lock",
    "scroll_lock": "scroll lock", "num_lock": "num lock", "print_screen": "print screen",
}


def _key_name(key) -> tuple[str, int]:
    from pynput.keyboard import Key, KeyCode

    if isinstance(key, Key):
        raw = key.name
        code = getattr(key.value, "vk", 0) or 0
        return _SPECIAL.get(raw, raw), _xkeycode(code)
    if isinstance(key, KeyCode):
        name = (key.char or "").lower()
        return name or f"vk{key.vk}", _xkeycode(key.vk or 0)
    return str(key), 0


def _xkeycode(keysym: int) -> int:
    """pynput на X11 отдаёт keysym; для проверки состояния нужен keycode."""
    if not keysym or _keymap() is None:
        return 0
    return _keysym_to_keycode(keysym)


class KeyHook:
    permission_error: str | None = None

    def __init__(self, callback):
        self._callback = callback
        self._listener = None

    def start(self) -> None:
        self.permission_error = check_permissions()
        if self.permission_error and "Wayland" not in self.permission_error:
            return
        from pynput import keyboard

        def on(down):
            def handler(key):
                name, code = _key_name(key)
                self._callback(name, code, down)
            return handler

        self._listener = keyboard.Listener(on_press=on(True), on_release=on(False))
        self._listener.daemon = True
        self._listener.start()

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None


def make_overlay_passive(toplevel) -> None:
    # overrideredirect-окна X11 не получают фокус; индикатор и так смещён от указателя
    pass


# ---------------------------------------------------------------- автозапуск
def _autostart_file() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "autostart" / "voicetyper-hs.desktop"


def set_autostart(enabled: bool) -> None:
    path = _autostart_file()
    if not enabled:
        path.unlink(missing_ok=True)
        return
    exe = os.environ.get("APPIMAGE") or (sys.executable if getattr(sys, "frozen", False) else None)
    cmd = shlex.quote(exe) if exe else f"{shlex.quote(sys.executable)} -m voicetyper"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name={APP_DISPLAY}\n"
        "Comment=Голосовой ввод в любое поле\n"
        f"Exec={cmd} --minimized\n"
        "X-GNOME-Autostart-enabled=true\n"
        "Terminal=false\n",
        encoding="utf-8",
    )
