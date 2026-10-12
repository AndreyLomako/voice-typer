"""Настройки приложения (JSON в папке настроек пользователя)."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields

from . import system

APPDATA_DIR = system.config_dir()
MODELS_DIR = system.data_dir() / "models"
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
    cloud_api_key: str = ""               # на диске — только в зашифрованном виде / в системном хранилище

    # Микрофон
    microphone: str = ""                  # пусто = системный по умолчанию
    max_seconds: int = 120

    # Горячие клавиши
    hotkey_hold: str = system.DEFAULT_HOLD
    hotkey_toggle: str = system.DEFAULT_TOGGLE
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
        if not isinstance(data, dict):
            return s
        for f in fields(cls):
            if f.name in ("_extra", "cloud_api_key") or f.name not in data:
                continue
            value, default = data[f.name], getattr(s, f.name)
            # Повреждённый или подправленный вручную файл не должен ломать программу
            if type(value) is type(default) or (isinstance(default, int) and type(value) is int):
                setattr(s, f.name, value)
        s.max_seconds = min(max(int(s.max_seconds), 5), 600)
        if s.local_model not in LOCAL_MODELS:
            s.local_model = "small"
        enc = data.get("cloud_api_key_enc", "")
        s.cloud_api_key = system.unprotect(enc) if isinstance(enc, str) else ""
        return s

    def save(self) -> None:
        APPDATA_DIR.mkdir(parents=True, exist_ok=True)
        data = asdict(self)
        data.pop("_extra", None)
        data["cloud_api_key_enc"] = system.protect(data.pop("cloud_api_key"))
        tmp = SETTINGS_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        system.restrict_file(tmp)
        tmp.replace(SETTINGS_FILE)
