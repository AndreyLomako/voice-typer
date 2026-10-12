"""Мелкие функции Windows: мышь, единственный экземпляр, автозапуск, окна без фокуса."""
from __future__ import annotations

import ctypes
import sys
import winreg
from ctypes import wintypes

from . import APP_DISPLAY, APP_NAME

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOPMOST = 0x00000008

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def cursor_pos() -> tuple[int, int]:
    pt = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


def click_at(x: int, y: int) -> None:
    user32.SetCursorPos(x, y)
    user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)


def make_click_through(hwnd: int) -> None:
    """Окно не забирает фокус, не видно в Alt+Tab и пропускает клики сквозь себя."""
    style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    style |= WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE | WS_EX_TOPMOST
    user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)


_mutex = None


def acquire_single_instance() -> bool:
    global _mutex
    _mutex = kernel32.CreateMutexW(None, False, f"Global\\{APP_NAME}_single_instance")
    return kernel32.GetLastError() != 183  # ERROR_ALREADY_EXISTS


def message_box(text: str, title: str = APP_DISPLAY) -> None:
    user32.MessageBoxW(None, text, title, 0x40)


def _launch_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --minimized'
    pythonw = sys.executable.replace("python.exe", "pythonw.exe")
    return f'"{pythonw}" -m voicetyper --minimized'


def set_autostart(enabled: bool) -> None:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, _launch_command())
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
            except FileNotFoundError:
                pass
