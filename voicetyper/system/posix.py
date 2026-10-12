"""Общее для macOS и Linux: блокировка единственного экземпляра, секреты, звук, буфер обмена."""
from __future__ import annotations

import base64
import logging
import os
from pathlib import Path

log = logging.getLogger(__name__)

_KEYRING_SERVICE = "VoiceTyper hs"
_KEYRING_USER = "cloud_api_key"
_lock_file = None


def acquire_single_instance(lock_dir: Path) -> bool:
    import fcntl

    global _lock_file
    lock_dir.mkdir(parents=True, exist_ok=True)
    _lock_file = open(lock_dir / "instance.lock", "w")
    try:
        fcntl.flock(_lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def message_box(text: str, title: str) -> None:
    import tkinter as tk
    from tkinter import messagebox

    root = tk.Tk()
    root.withdraw()
    messagebox.showinfo(title, text)
    root.destroy()


def beep(freq: int) -> bool:
    """Короткий тон через звуковую карту (системного Beep на macOS/Linux нет)."""
    try:
        import numpy as np
        import sounddevice as sd

        sr = 22050
        t = np.arange(int(sr * 0.07)) / sr
        tone = (0.18 * np.sin(2 * np.pi * freq * t) * np.hanning(len(t))).astype(np.float32)
        sd.play(tone, sr)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------- секреты
def protect(text: str) -> str:
    """Ключ — в системное хранилище (Keychain / Secret Service). Без него — в файле с правами 600."""
    if not text:
        try:
            import keyring
            keyring.delete_password(_KEYRING_SERVICE, _KEYRING_USER)
        except Exception:
            pass
        return ""
    try:
        import keyring
        keyring.set_password(_KEYRING_SERVICE, _KEYRING_USER, text)
        return "keyring:"
    except Exception as exc:
        log.warning("Системное хранилище паролей недоступно (%s), ключ сохранён в файле настроек", exc)
        return "file:" + base64.b64encode(text.encode("utf-8")).decode("ascii")


def unprotect(encoded: str) -> str:
    if encoded == "keyring:":
        try:
            import keyring
            return keyring.get_password(_KEYRING_SERVICE, _KEYRING_USER) or ""
        except Exception:
            return ""
    if encoded.startswith("file:"):
        try:
            return base64.b64decode(encoded[5:]).decode("utf-8")
        except ValueError:
            return ""
    return ""


def restrict_file(path: Path) -> None:
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


# ---------------------------------------------------------------- буфер обмена (только текст)
def clipboard_snapshot():
    import pyperclip
    try:
        return pyperclip.paste()
    except Exception:
        return None


def clipboard_restore(snapshot) -> None:
    if snapshot is None:
        return
    import pyperclip
    try:
        pyperclip.copy(snapshot)
    except Exception:
        pass


def clipboard_set_text(text: str, private: bool = True) -> None:
    import pyperclip
    pyperclip.copy(text)
