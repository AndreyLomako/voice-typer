"""macOS: Quartz Event Tap для клавиш, CGEvent для мыши и ввода.

Работаем только с кодами клавиш, без перевода в символы: функции раскладок (TSM)
на новых macOS разрешено вызывать лишь из главного потока, а хук живёт в фоновом.
Нужны разрешения «Универсальный доступ» (ввод) и «Мониторинг ввода» (хук).
"""
from __future__ import annotations

import os
import plistlib
import subprocess
import sys
import threading
from pathlib import Path

from .. import APP_NAME
from . import posix
from .posix import (clipboard_restore, clipboard_set_text, clipboard_snapshot, message_box, protect,  # noqa: F401
                    restrict_file, unprotect)

NAME = "macos"
UI_FONT = "Helvetica Neue"
SUPPORTS_CUDA = False
# На клавиатурах MacBook нет правого Ctrl — по умолчанию правый Option
DEFAULT_HOLD = "right alt"
DEFAULT_TOGGLE = "ctrl+alt+space"
KEY_NAMES = {
    "alt": "Option", "left alt": "Левый Option", "right alt": "Правый Option",
    "windows": "Cmd", "left windows": "Cmd", "right windows": "Правый Cmd",
}

_BUNDLE_ID = "com.andreylomako.voicetyper-hs"


def config_dir() -> Path:
    return Path.home() / "Library" / "Application Support" / APP_NAME


def data_dir() -> Path:
    return Path.home() / "Library" / "Application Support" / APP_NAME


def acquire_single_instance() -> bool:
    return posix.acquire_single_instance(config_dir())


# ---------------------------------------------------------------- коды клавиш (ANSI)
_KEYCODES = {
    0: "a", 1: "s", 2: "d", 3: "f", 4: "h", 5: "g", 6: "z", 7: "x", 8: "c", 9: "v", 11: "b", 12: "q",
    13: "w", 14: "e", 15: "r", 16: "y", 17: "t", 18: "1", 19: "2", 20: "3", 21: "4", 22: "6", 23: "5",
    24: "=", 25: "9", 26: "7", 27: "-", 28: "8", 29: "0", 30: "]", 31: "o", 32: "u", 33: "[", 34: "i",
    35: "p", 36: "enter", 37: "l", 38: "j", 39: "'", 40: "k", 41: ";", 42: "\\", 43: ",", 44: "/",
    45: "n", 46: "m", 47: ".", 48: "tab", 49: "space", 50: "`", 51: "backspace", 53: "esc",
    55: "left windows", 54: "right windows", 56: "left shift", 60: "right shift",
    58: "left alt", 61: "right alt", 59: "left ctrl", 62: "right ctrl", 57: "caps lock",
    122: "f1", 120: "f2", 99: "f3", 118: "f4", 96: "f5", 97: "f6", 98: "f7", 100: "f8", 101: "f9",
    109: "f10", 103: "f11", 111: "f12", 105: "f13", 107: "f14", 113: "f15", 106: "f16",
    115: "home", 116: "page up", 117: "delete", 119: "end", 121: "page down",
    123: "left", 124: "right", 125: "down", 126: "up",
}
# Флаги «конкретной» модификаторной клавиши (NX_DEVICE*KEYMASK): различают левую и правую
_MOD_DEVICE_MASK = {
    59: 0x01, 62: 0x2000,       # ctrl
    56: 0x02, 60: 0x04,         # shift
    55: 0x08, 54: 0x10,         # cmd
    58: 0x20, 61: 0x40,         # option
    57: 0x10000,                # caps lock (общий флаг)
}


def _q():
    import Quartz
    return Quartz


# ---------------------------------------------------------------- разрешения
def check_permissions() -> str | None:
    Q = _q()
    missing = []
    try:
        from ApplicationServices import AXIsProcessTrustedWithOptions, kAXTrustedCheckOptionPrompt
        if not AXIsProcessTrustedWithOptions({kAXTrustedCheckOptionPrompt: True}):
            missing.append("«Универсальный доступ»")
    except Exception:
        pass
    preflight = getattr(Q, "CGPreflightListenEventAccess", None)
    if preflight is not None and not preflight():
        request = getattr(Q, "CGRequestListenEventAccess", None)
        if request is not None:
            request()
        missing.append("«Мониторинг ввода»")
    if missing:
        return ("Разрешите VoiceTyper hs в Системных настройках → Конфиденциальность и безопасность → "
                + " и ".join(missing) + ", затем перезапустите программу.")
    return None


def open_permission_settings() -> None:
    subprocess.Popen(["open", "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"])


# ---------------------------------------------------------------- мышь и ввод
def cursor_pos() -> tuple[int, int]:
    Q = _q()
    loc = Q.CGEventGetLocation(Q.CGEventCreate(None))
    return int(loc.x), int(loc.y)


def click_at(x: int, y: int) -> None:
    Q = _q()
    for kind in (Q.kCGEventLeftMouseDown, Q.kCGEventLeftMouseUp):
        ev = Q.CGEventCreateMouseEvent(None, kind, (x, y), Q.kCGMouseButtonLeft)
        Q.CGEventPost(Q.kCGHIDEventTap, ev)


def send_paste() -> None:
    Q = _q()
    for down in (True, False):
        ev = Q.CGEventCreateKeyboardEvent(None, 9, down)  # 9 = V
        Q.CGEventSetFlags(ev, Q.kCGEventFlagMaskCommand)
        Q.CGEventPost(Q.kCGHIDEventTap, ev)


def type_text(text: str) -> None:
    import time
    Q = _q()
    for i in range(0, len(text), 16):
        chunk = text[i:i + 16]
        for down in (True, False):
            ev = Q.CGEventCreateKeyboardEvent(None, 0, down)
            Q.CGEventKeyboardSetUnicodeString(ev, len(chunk.encode("utf-16-le")) // 2, chunk)
            Q.CGEventPost(Q.kCGHIDEventTap, ev)
        time.sleep(0.01)


def modifiers_down() -> bool:
    Q = _q()
    flags = Q.CGEventSourceFlagsState(Q.kCGEventSourceStateHIDSystemState)
    mask = (Q.kCGEventFlagMaskCommand | Q.kCGEventFlagMaskAlternate | Q.kCGEventFlagMaskControl
            | Q.kCGEventFlagMaskShift)
    return bool(flags & mask)


def physically_down(name: str, scan: int) -> bool:
    Q = _q()
    return bool(Q.CGEventSourceKeyState(Q.kCGEventSourceStateHIDSystemState, scan))


def scan_codes(token: str) -> set[int]:
    return {code for code, name in _KEYCODES.items() if name == token}


# ---------------------------------------------------------------- хук клавиатуры
class KeyHook:
    permission_error: str | None = None

    def __init__(self, callback):
        self._callback = callback
        self._loop = None
        self._tap = None
        self._thread = None
        self._ready = threading.Event()

    def _handler(self, proxy, etype, event, refcon):
        Q = _q()
        if etype in (Q.kCGEventTapDisabledByTimeout, Q.kCGEventTapDisabledByUserInput):
            Q.CGEventTapEnable(self._tap, True)
            return event
        try:
            code = int(Q.CGEventGetIntegerValueField(event, Q.kCGKeyboardEventKeycode))
            if etype == Q.kCGEventFlagsChanged:
                mask = _MOD_DEVICE_MASK.get(code)
                if mask is None:
                    return event
                down = bool(Q.CGEventGetFlags(event) & mask)
            else:
                if etype == Q.kCGEventKeyDown and Q.CGEventGetIntegerValueField(event, Q.kCGKeyboardEventAutorepeat):
                    return event
                down = etype == Q.kCGEventKeyDown
            self._callback(_KEYCODES.get(code, f"key{code}"), code, down)
        except Exception:
            pass
        return event

    def _run(self):
        Q = _q()
        mask = (Q.CGEventMaskBit(Q.kCGEventKeyDown) | Q.CGEventMaskBit(Q.kCGEventKeyUp)
                | Q.CGEventMaskBit(Q.kCGEventFlagsChanged))
        self._tap = Q.CGEventTapCreate(Q.kCGSessionEventTap, Q.kCGHeadInsertEventTap,
                                       Q.kCGEventTapOptionListenOnly, mask, self._handler, None)
        if self._tap is None:
            self.permission_error = check_permissions() or "Нет разрешения «Мониторинг ввода»."
            self._ready.set()
            return
        source = Q.CFMachPortCreateRunLoopSource(None, self._tap, 0)
        self._loop = Q.CFRunLoopGetCurrent()
        Q.CFRunLoopAddSource(self._loop, source, Q.kCFRunLoopCommonModes)
        Q.CGEventTapEnable(self._tap, True)
        self._ready.set()
        Q.CFRunLoopRun()

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True, name="key-hook")
        self._thread.start()
        self._ready.wait(3)

    def stop(self) -> None:
        if self._loop is not None:
            _q().CFRunLoopStop(self._loop)
            self._loop = None


def make_overlay_passive(toplevel) -> None:
    try:  # окно-панель без тени и без активации приложения
        toplevel.tk.call("::tk::unsupported::MacWindowStyle", "style", toplevel._w, "help", "noActivates")
    except Exception:
        pass


_SOUNDS = {880: "Tink", 620: "Pop", 440: "Basso"}


def beep(freq: int) -> bool:
    name = _SOUNDS.get(freq, "Pop")
    try:
        subprocess.Popen(["afplay", f"/System/Library/Sounds/{name}.aiff"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except OSError:
        return posix.beep(freq)


# ---------------------------------------------------------------- автозапуск (LaunchAgent)
def _agent_file() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{_BUNDLE_ID}.plist"


def set_autostart(enabled: bool) -> None:
    path = _agent_file()
    if not enabled:
        path.unlink(missing_ok=True)
        return
    if getattr(sys, "frozen", False):
        args = [sys.executable, "--minimized"]
    else:
        args = [sys.executable, "-m", "voicetyper", "--minimized"]
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        plistlib.dump({"Label": _BUNDLE_ID, "ProgramArguments": args, "RunAtLoad": True,
                       "ProcessType": "Interactive"}, f)
    os.chmod(path, 0o644)
