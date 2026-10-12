"""Глобальные горячие клавиши поверх низкоуровневого хука библиотеки keyboard.

Своя логика сопоставления нужна, потому что keyboard не различает левый и правый
Ctrl/Alt/Shift в add_hotkey (одинаковый scan code), а для push-to-talk важно
отслеживать и нажатие, и отпускание.
"""
from __future__ import annotations

import ctypes
import logging
import threading
from typing import Callable

import keyboard

log = logging.getLogger(__name__)

# Имя события -> каноническое имя. Левые модификаторы keyboard называет без префикса.
_CANON = {
    "ctrl": "left ctrl", "control": "left ctrl",
    "alt": "left alt",
    "shift": "left shift",
    "windows": "left windows", "left win": "left windows",
    "alt gr": "right alt",
    "right win": "right windows",
}
_GENERIC = {
    "ctrl": {"left ctrl", "right ctrl"},
    "alt": {"left alt", "right alt"},
    "shift": {"left shift", "right shift"},
    "windows": {"left windows", "right windows"},
}
_MODIFIERS = set().union(*_GENERIC.values())
_ORDER = ["ctrl", "left ctrl", "right ctrl", "alt", "left alt", "right alt",
          "shift", "left shift", "right shift", "windows", "left windows", "right windows"]

_PRETTY = {
    "ctrl": "Ctrl", "alt": "Alt", "shift": "Shift", "windows": "Win",
    "left ctrl": "Левый Ctrl", "right ctrl": "Правый Ctrl",
    "left alt": "Левый Alt", "right alt": "Правый Alt",
    "left shift": "Левый Shift", "right shift": "Правый Shift",
    "left windows": "Win", "right windows": "Правый Win",
    "space": "Space", "esc": "Esc", "enter": "Enter", "caps lock": "Caps Lock",
    "tab": "Tab", "backspace": "Backspace", "pause": "Pause", "scroll lock": "Scroll Lock",
    "insert": "Insert", "delete": "Delete", "home": "Home", "end": "End",
    "page up": "PgUp", "page down": "PgDn",
}


_VK = {
    "left ctrl": 0xA2, "right ctrl": 0xA3, "left alt": 0xA4, "right alt": 0xA5,
    "left shift": 0xA0, "right shift": 0xA1, "left windows": 0x5B, "right windows": 0x5C,
}
_user32 = ctypes.windll.user32


def _physically_down(name: str, scan: int) -> bool:
    vk = _VK.get(name) or _user32.MapVirtualKeyW(scan, 3)  # MAPVK_VSC_TO_VK_EX
    return not vk or bool(_user32.GetAsyncKeyState(vk) & 0x8000)


def canon(name: str) -> str:
    name = (name or "").lower().strip()
    return _CANON.get(name, name)


def parse(hotkey: str) -> list[str]:
    return [t.strip().lower() for t in (hotkey or "").split("+") if t.strip()]


def pretty(hotkey: str) -> str:
    tokens = parse(hotkey)
    if not tokens:
        return "не задано"
    return " + ".join(_PRETTY.get(t, t.upper() if len(t) == 1 else t.capitalize()) for t in tokens)


def _format_chord(keys: list[str]) -> str:
    """Левые модификаторы сохраняем как обобщённые (Ctrl = любой Ctrl)."""
    out = []
    for k in keys:
        k = canon(k)
        if k.startswith("left ") and k[5:] in _GENERIC:
            k = k[5:]
        if k not in out:
            out.append(k)
    out.sort(key=lambda k: _ORDER.index(k) if k in _ORDER else len(_ORDER))
    return "+".join(out)


class _Chord:
    def __init__(self, hotkey: str):
        self.text = hotkey
        self.tokens = parse(hotkey)
        self.scan_codes: dict[str, set[int]] = {}
        for t in self.tokens:
            if t not in _GENERIC and canon(t) not in _MODIFIERS:
                try:
                    self.scan_codes[t] = set(keyboard.key_to_scan_codes(t))
                except ValueError:
                    self.scan_codes[t] = set()

    def _token_matches(self, token: str, name: str, scan: int) -> bool:
        if token in _GENERIC:
            return name in _GENERIC[token]
        if canon(token) in _MODIFIERS:
            return name == canon(token)
        return name == token or scan in self.scan_codes.get(token, ())

    def contains(self, name: str, scan: int) -> bool:
        return any(self._token_matches(t, name, scan) for t in self.tokens)

    def satisfied_exactly(self, pressed: dict[tuple[str, int], None]) -> bool:
        if not self.tokens:
            return False
        for t in self.tokens:
            if not any(self._token_matches(t, n, s) for n, s in pressed):
                return False
        return all(self.contains(n, s) for n, s in pressed)


class HotkeyManager:
    def __init__(self, on_hold_start: Callable[[], None], on_hold_end: Callable[[bool], None],
                 on_toggle: Callable[[], None], on_cancel: Callable[[], None]):
        self.on_hold_start = on_hold_start
        self.on_hold_end = on_hold_end
        self.on_toggle = on_toggle
        self.on_cancel = on_cancel
        self.enabled = True
        self._hold = _Chord("")
        self._toggle = _Chord("")
        self._cancel = _Chord("")
        self._pressed: dict[tuple[str, int], None] = {}
        self._hold_active = False
        self._hold_interrupted = False
        self._capture: Callable[[str], None] | None = None
        self._capture_keys: list[str] = []
        self._lock = threading.Lock()
        self._hook = None

    def start(self) -> None:
        if self._hook is None:
            self._hook = keyboard.hook(self._on_event)

    def stop(self) -> None:
        if self._hook is not None:
            keyboard.unhook(self._hook)
            self._hook = None

    def configure(self, hold: str, toggle: str, cancel: str, enabled: bool) -> None:
        with self._lock:
            self._hold, self._toggle, self._cancel = _Chord(hold), _Chord(toggle), _Chord(cancel)
            self.enabled = enabled

    def capture(self, callback: Callable[[str], None]) -> None:
        """Записать следующую комбинацию: результат придёт, когда все клавиши отпущены."""
        with self._lock:
            self._capture_keys = []
            self._capture = callback

    def cancel_capture(self) -> None:
        with self._lock:
            self._capture = None

    def _on_event(self, e: keyboard.KeyboardEvent) -> None:
        try:
            self._handle(canon(e.name), e.scan_code, e.event_type == keyboard.KEY_DOWN)
        except Exception:
            log.exception("Ошибка обработки клавиши")

    def _handle(self, name: str, scan: int, down: bool) -> None:
        key = (name, scan)
        actions: list[Callable[[], None]] = []
        with self._lock:
            if down:
                if key in self._pressed:      # автоповтор
                    return
                # Клавиши, отпускание которых мы пропустили (Win+L, UAC и т.п.)
                for stale in [k for k in self._pressed if not _physically_down(*k)]:
                    del self._pressed[stale]
                self._pressed[key] = None
            else:
                self._pressed.pop(key, None)

            if self._capture is not None:
                if down:
                    if name not in self._capture_keys:
                        self._capture_keys.append(name)
                elif not self._pressed and self._capture_keys:
                    cb, self._capture = self._capture, None
                    chord = _format_chord(self._capture_keys)
                    actions.append(lambda: cb(chord))
            elif self.enabled:
                if down:
                    if self._hold_active and not self._hold.contains(name, scan):
                        self._hold_interrupted = True
                    elif not self._hold_active and self._hold.satisfied_exactly(self._pressed):
                        self._hold_active, self._hold_interrupted = True, False
                        actions.append(self.on_hold_start)
                    if self._toggle.satisfied_exactly(self._pressed):
                        actions.append(self.on_toggle)
                    if self._cancel.satisfied_exactly(self._pressed):
                        actions.append(self.on_cancel)
                elif self._hold_active and self._hold.contains(name, scan):
                    self._hold_active = False
                    interrupted = self._hold_interrupted
                    actions.append(lambda: self.on_hold_end(interrupted))
            elif self._hold_active and not down:
                self._hold_active = False
                actions.append(lambda: self.on_hold_end(True))

        for action in actions:
            try:
                action()
            except Exception:
                log.exception("Ошибка обработчика горячей клавиши")
