"""Windows: WinAPI через ctypes, хук клавиатуры — библиотека keyboard."""
from __future__ import annotations

import base64
import ctypes
import os
import sys
import threading
import time
import winreg
from ctypes import wintypes
from pathlib import Path

from .. import APP_NAME

NAME = "windows"
UI_FONT = "Segoe UI"
SUPPORTS_CUDA = True
DEFAULT_HOLD = "right ctrl"
DEFAULT_TOGGLE = "ctrl+alt+space"
KEY_NAMES = {"windows": "Win", "left windows": "Win", "right windows": "Правый Win"}

# Собственные экземпляры DLL: argtypes не конфликтуют с другими библиотеками
_user32 = ctypes.WinDLL("user32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)

_V = ctypes.c_void_p
for _fn, _args, _res in [
    (_user32.OpenClipboard, [wintypes.HWND], wintypes.BOOL),
    (_user32.CloseClipboard, [], wintypes.BOOL),
    (_user32.EmptyClipboard, [], wintypes.BOOL),
    (_user32.EnumClipboardFormats, [wintypes.UINT], wintypes.UINT),
    (_user32.GetClipboardData, [wintypes.UINT], _V),
    (_user32.SetClipboardData, [wintypes.UINT, _V], _V),
    (_user32.RegisterClipboardFormatW, [wintypes.LPCWSTR], wintypes.UINT),
    (_user32.GetCursorPos, [ctypes.POINTER(wintypes.POINT)], wintypes.BOOL),
    (_user32.SetCursorPos, [ctypes.c_int, ctypes.c_int], wintypes.BOOL),
    (_user32.GetAsyncKeyState, [ctypes.c_int], ctypes.c_short),
    (_user32.MapVirtualKeyW, [wintypes.UINT, wintypes.UINT], wintypes.UINT),
    (_user32.GetParent, [wintypes.HWND], wintypes.HWND),
    (_user32.GetWindowLongW, [wintypes.HWND, ctypes.c_int], ctypes.c_long),
    (_user32.SetWindowLongW, [wintypes.HWND, ctypes.c_int, ctypes.c_long], ctypes.c_long),
    (_user32.MessageBoxW, [wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.UINT], ctypes.c_int),
    (_kernel32.GlobalAlloc, [wintypes.UINT, ctypes.c_size_t], _V),
    (_kernel32.GlobalLock, [_V], _V),
    (_kernel32.GlobalUnlock, [_V], wintypes.BOOL),
    (_kernel32.GlobalSize, [_V], ctypes.c_size_t),
    (_kernel32.GlobalFree, [_V], _V),
    (_kernel32.LocalFree, [_V], _V),
    (_kernel32.CreateMutexW, [_V, wintypes.BOOL, wintypes.LPCWSTR], wintypes.HANDLE),
]:
    _fn.argtypes, _fn.restype = _args, _res


# ---------------------------------------------------------------- пути
def config_dir() -> Path:
    return Path(os.environ.get("APPDATA", Path.home())) / APP_NAME


def data_dir() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", Path.home())) / APP_NAME


# ---------------------------------------------------------------- мышь
def cursor_pos() -> tuple[int, int]:
    pt = wintypes.POINT()
    _user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


def click_at(x: int, y: int) -> None:
    _user32.SetCursorPos(x, y)
    _user32.mouse_event(0x0002, 0, 0, 0, 0)  # LEFTDOWN
    _user32.mouse_event(0x0004, 0, 0, 0, 0)  # LEFTUP


# ---------------------------------------------------------------- клавиатура: ввод
def send_paste() -> None:
    import keyboard
    keyboard.send("ctrl+v")


def type_text(text: str) -> None:
    import keyboard
    keyboard.write(text, delay=0.005)


_MOD_VK = (0x10, 0x11, 0x12, 0x5B, 0x5C)  # Shift, Ctrl, Alt, LWin, RWin


def modifiers_down() -> bool:
    return any(_user32.GetAsyncKeyState(vk) & 0x8000 for vk in _MOD_VK)


# ---------------------------------------------------------------- клавиатура: хук
_VK = {
    "left ctrl": 0xA2, "right ctrl": 0xA3, "left alt": 0xA4, "right alt": 0xA5,
    "left shift": 0xA0, "right shift": 0xA1, "left windows": 0x5B, "right windows": 0x5C,
}


class KeyHook:
    """Отдаёт (имя, scan code, нажата) для каждого события клавиатуры."""
    permission_error: str | None = None

    def __init__(self, callback):
        self._callback = callback
        self._hook = None

    def start(self) -> None:
        import keyboard
        self._hook = keyboard.hook(
            lambda e: self._callback(e.name or "", e.scan_code, e.event_type == keyboard.KEY_DOWN))

    def stop(self) -> None:
        if self._hook is not None:
            import keyboard
            keyboard.unhook(self._hook)
            self._hook = None


def scan_codes(token: str) -> set[int]:
    import keyboard
    try:
        return set(keyboard.key_to_scan_codes(token))
    except ValueError:
        return set()


def physically_down(name: str, scan: int) -> bool:
    vk = _VK.get(name) or _user32.MapVirtualKeyW(scan, 3)  # MAPVK_VSC_TO_VK_EX
    return not vk or bool(_user32.GetAsyncKeyState(vk) & 0x8000)


# ---------------------------------------------------------------- буфер обмена
CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002
# GDI-дескрипторы и owner-display нельзя скопировать как память — пропускаем
_SKIP_FORMATS = {2, 3, 9, 14, 0x80, 0x82, 0x83, 0x8E}
_MAX_FORMAT_BYTES = 64 * 1024 * 1024


def _open_clipboard() -> bool:
    for _ in range(25):
        if _user32.OpenClipboard(None):
            return True
        time.sleep(0.02)
    return False


def _set_bytes(fmt: int, data: bytes) -> None:
    h = _kernel32.GlobalAlloc(GMEM_MOVEABLE, max(1, len(data)))
    if not h:
        return
    p = _kernel32.GlobalLock(h)
    if p:
        ctypes.memmove(p, data, len(data))
        _kernel32.GlobalUnlock(h)
    if not _user32.SetClipboardData(fmt, h):
        _kernel32.GlobalFree(h)


def _mark_private() -> None:
    """Не сохранять в журнал буфера Win+V, не синхронизировать в облако, скрыть от менеджеров буфера."""
    zero = (0).to_bytes(4, "little")
    _set_bytes(_user32.RegisterClipboardFormatW("ExcludeClipboardContentFromMonitorProcessing"), zero)
    _set_bytes(_user32.RegisterClipboardFormatW("CanIncludeInClipboardHistory"), zero)
    _set_bytes(_user32.RegisterClipboardFormatW("CanUploadToCloudClipboard"), zero)


def clipboard_snapshot():
    """Сохраняет все форматы, которые можно скопировать как память (текст, картинки, файлы)."""
    if not _open_clipboard():
        return None
    items: list[tuple[int, bytes]] = []
    try:
        fmt = 0
        while True:
            fmt = _user32.EnumClipboardFormats(fmt)
            if not fmt:
                break
            if fmt in _SKIP_FORMATS or 0x0300 <= fmt <= 0x03FF:
                continue
            h = _user32.GetClipboardData(fmt)
            if not h:
                continue
            size = _kernel32.GlobalSize(h)
            if not size or size > _MAX_FORMAT_BYTES:
                continue
            p = _kernel32.GlobalLock(h)
            if not p:
                continue
            try:
                items.append((fmt, ctypes.string_at(p, size)))
            finally:
                _kernel32.GlobalUnlock(h)
    finally:
        _user32.CloseClipboard()
    return items


def clipboard_restore(snapshot) -> None:
    if snapshot is None or not _open_clipboard():
        return
    try:
        _user32.EmptyClipboard()
        for fmt, data in snapshot:
            _set_bytes(fmt, data)
        _mark_private()  # исходное содержимое уже есть в журнале — не дублируем
    finally:
        _user32.CloseClipboard()


def clipboard_set_text(text: str, private: bool = True) -> None:
    if not _open_clipboard():
        raise OSError("Буфер обмена занят другой программой")
    try:
        _user32.EmptyClipboard()
        _set_bytes(CF_UNICODETEXT, text.encode("utf-16-le") + b"\0\0")
        if private:
            _mark_private()
    finally:
        _user32.CloseClipboard()


# ---------------------------------------------------------------- окна
def make_overlay_passive(toplevel) -> None:
    """Индикатор не забирает фокус, не виден в Alt+Tab и пропускает клики сквозь себя."""
    hwnd = _user32.GetParent(toplevel.winfo_id()) or toplevel.winfo_id()
    style = _user32.GetWindowLongW(hwnd, -20)  # GWL_EXSTYLE
    # LAYERED | TRANSPARENT | TOOLWINDOW | NOACTIVATE | TOPMOST
    style |= 0x00080000 | 0x00000020 | 0x00000080 | 0x08000000 | 0x00000008
    _user32.SetWindowLongW(hwnd, -20, style)


def message_box(text: str, title: str) -> None:
    _user32.MessageBoxW(None, text, title, 0x40)


def beep(freq: int) -> bool:
    import winsound
    threading.Thread(target=winsound.Beep, args=(freq, 70), daemon=True).start()
    return True


def restrict_file(path) -> None:
    pass  # %APPDATA% и так доступен только владельцу


def check_permissions() -> str | None:
    return None


def open_permission_settings() -> None:
    pass


# ---------------------------------------------------------------- один экземпляр
_mutex = None


def acquire_single_instance() -> bool:
    global _mutex
    # Local\ — в пределах сеанса пользователя: другой пользователь на этом ПК не может «занять» имя
    _mutex = _kernel32.CreateMutexW(None, False, f"Local\\{APP_NAME}_single_instance")
    return ctypes.get_last_error() != 183  # ERROR_ALREADY_EXISTS


# ---------------------------------------------------------------- автозапуск
_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


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


# ---------------------------------------------------------------- секреты (DPAPI)
class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


_ENTROPY = b"VoiceTyper-hs/cloud-api-key/v1"
_CRYPTPROTECT_UI_FORBIDDEN = 0x1


def _blob(data: bytes):
    buf = ctypes.create_string_buffer(data, len(data))
    return _Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), buf  # buf держим живым


def _take(blob: _Blob) -> bytes:
    data = ctypes.string_at(blob.pbData, blob.cbData)
    _kernel32.LocalFree(ctypes.cast(blob.pbData, _V))
    return data


def protect(text: str) -> str:
    if not text:
        return ""
    (src, _keep1), (ent, _keep2), out = _blob(text.encode("utf-8")), _blob(_ENTROPY), _Blob()
    if not _crypt32.CryptProtectData(ctypes.byref(src), None, ctypes.byref(ent), None, None,
                                     _CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(out)):
        return ""
    return base64.b64encode(_take(out)).decode("ascii")


def unprotect(encoded: str) -> str:
    if not encoded:
        return ""
    try:
        raw = base64.b64decode(encoded)
    except ValueError:
        return ""
    for entropy in (_ENTROPY, None):  # None — ключи, сохранённые версией 1.0/1.1
        (src, _keep1), out = _blob(raw), _Blob()
        ent_ref = None
        if entropy:
            ent, _keep2 = _blob(entropy)
            ent_ref = ctypes.byref(ent)
        if _crypt32.CryptUnprotectData(ctypes.byref(src), None, ent_ref, None, None,
                                       _CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(out)):
            try:
                return _take(out).decode("utf-8")
            except UnicodeDecodeError:
                return ""
    return ""
