"""Настройки приложения: хранение в %APPDATA%\\VoiceTyper\\settings.json."""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from . import APP_NAME
from .vault import protect, unprotect

APPDATA_DIR = Path(os.environ.get("APPDATA", Path.home())) / APP_NAME
MODELS_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / APP_NAME / "models"
SETTINGS_FILE = APPDATA_DIR / "settings.json"
LOG_FILE = APPDATA_DIR / "voicetyper.log"

LOCAL_MODELS = ["tiny", "base", "small", "medium", "large-v3-turbo", "large-v3"]

LANGUAGES = {
    "auto": "Автоопределение",
    "ru": "Русский",
    "en": "English",
    "uk": "Українська",
    "be": "Беларуская",
    "kk": "Қазақша",
    "de": "Deutsch",
    "fr": "Français",
    "es": "Español",
    "it": "Italiano",
    "pl": "Polski",
    "tr": "Türkçe",
    "zh": "中文",
}

CLOUD_PRESETS = {
    "OpenAI": ("https://api.openai.com/v1", "gpt-4o-mini-transcribe"),
    "Groq": ("https://api.groq.com/openai/v1", "whisper-large-v3-turbo"),
    "Свой сервер": ("http://localhost:8000/v1", "whisper-1"),
}


@dataclass
class Settings:
    # Распознавание
    engine: str = "local"                 # local | cloud
    local_model: str = "small"
    device: str = "cpu"                   # cpu | cuda
    language: str = "ru"
    initial_prompt: str = ""
    cloud_preset: str = "OpenAI"
    cloud_base_url: str = "https://api.openai.com/v1"
    cloud_model: str = "gpt-4o-mini-transcribe"
    cloud_api_key: str = ""               # хранится зашифрованным (DPAPI)

    # Микрофон
    microphone: str = ""                  # пусто = системный по умолчанию
    max_seconds: int = 120

    # Горячие клавиши
    hotkey_hold: str = "right ctrl"
    hotkey_toggle: str = "ctrl+alt+space"
    hotkey_cancel: str = "esc"
    hotkeys_enabled: bool = True

    # Вставка
    insert_target: str = "mouse"          # mouse | focus
    insert_method: str = "paste"          # paste | type
    restore_clipboard: bool = True
    trailing_space: bool = True
    strip_final_period: bool = False

    # Интерфейс
    show_overlay: bool = True
    play_sounds: bool = True
    start_minimized: bool = False
    autostart: bool = False
    theme: str = "dark"                   # dark | light | system
    first_run: bool = True

    _extra: dict = field(default_factory=dict, repr=False)

    @classmethod
    def load(cls) -> "Settings":
        s = cls()
        try:
            data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return s
        known = {f.name for f in fields(cls)} - {"_extra"}
        for key, value in data.items():
            if key in known:
                setattr(s, key, value)
        s.cloud_api_key = unprotect(data.get("cloud_api_key_enc", ""))
        return s

    def save(self) -> None:
        APPDATA_DIR.mkdir(parents=True, exist_ok=True)
        data = asdict(self)
        data.pop("_extra", None)
        data["cloud_api_key_enc"] = protect(data.pop("cloud_api_key"))
        tmp = SETTINGS_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(SETTINGS_FILE)
