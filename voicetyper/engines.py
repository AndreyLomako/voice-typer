"""Движки распознавания: локальный Whisper и OpenAI-совместимое облако."""
from __future__ import annotations

import logging
import os
import re
import threading

import numpy as np

# Протокол Xet у Hugging Face в части сетей зависает на скачивании model.bin,
# обычный HTTP работает везде.
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

from .audio import to_wav_bytes
from .config import MODELS_DIR, Settings

log = logging.getLogger(__name__)

# Типичные «галлюцинации» Whisper на тишине/шуме
_HALLUCINATIONS = re.compile(
    r"^(продолжение следует\.*|субтитры .*|редактор субтитров.*|спасибо за просмотр.*|"
    r"thank you\.?|thanks for watching.*|you)$",
    re.IGNORECASE,
)


# Модели закреплены по хешу коммита: если репозиторий на Hugging Face подменят или
# изменят, программа всё равно скачает именно проверенную версию файлов.
PINNED_MODELS = {
    "tiny": ("Systran/faster-whisper-tiny", "d90ca5fe260221311c53c58e660288d3deb8d356"),
    "base": ("Systran/faster-whisper-base", "ebe41f70d5b6dfa9166e2c581c45c9c0cfc57b66"),
    "small": ("Systran/faster-whisper-small", "536b0662742c02347bc0e980a01041f333bce120"),
    "medium": ("Systran/faster-whisper-medium", "08e178d48790749d25932bbc082711ddcfdfbc4f"),
    "large-v3": ("Systran/faster-whisper-large-v3", "edaa852ec7e145841d8ffdb056a99866b5f0a478"),
    "large-v3-turbo": ("dropbox-dash/faster-whisper-large-v3-turbo", "0a363e9161cbc7ed1431c9597a8ceaf0c4f78fcf"),
}

# Управляющие символы и невидимые символы смены направления текста (атака «Trojan Source»)
_UNSAFE_CHARS = re.compile(r"[\x00-\x08\x0b-\x1f\x7f\u200b-\u200f\u202a-\u202e\u2066-\u2069\ufeff]")
_LOOPBACK = {"localhost", "127.0.0.1", "::1"}


class TranscribeError(Exception):
    pass


class LocalEngine:
    def __init__(self):
        self._model = None
        self._key: tuple | None = None
        self._lock = threading.Lock()

    def ensure_loaded(self, settings: Settings, on_status=None) -> None:
        key = (settings.local_model, settings.device)
        with self._lock:
            if self._model is not None and self._key == key:
                return
            from faster_whisper import WhisperModel
            from faster_whisper.utils import download_model

            MODELS_DIR.mkdir(parents=True, exist_ok=True)
            name = settings.local_model
            if on_status:
                on_status(f"Загрузка модели «{name}»…")
            repo, revision = PINNED_MODELS[name]
            try:  # сначала из кэша — без обращения к сети, работает офлайн
                path = download_model(repo, local_files_only=True, cache_dir=str(MODELS_DIR), revision=revision)
            except Exception:
                if on_status:
                    on_status(f"Скачиваю модель «{name}» (один раз, может занять несколько минут)…")
                path = download_model(repo, cache_dir=str(MODELS_DIR), revision=revision)
            device = settings.device
            try:
                model = WhisperModel(path, device=device, compute_type="int8" if device == "cpu" else "float16")
            except Exception as exc:
                if device == "cpu":
                    raise
                log.warning("CUDA недоступна (%s), переключаюсь на CPU", exc)
                model = WhisperModel(path, device="cpu", compute_type="int8")
            self._model, self._key = model, key
            log.info("Модель %s загружена (%s)", settings.local_model, settings.device)

    def transcribe(self, audio: np.ndarray, settings: Settings) -> str:
        self.ensure_loaded(settings)
        segments, _info = self._model.transcribe(
            audio,
            language=None if settings.language == "auto" else settings.language,
            initial_prompt=settings.initial_prompt or None,
            beam_size=5,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 500},
            condition_on_previous_text=False,
        )
        return " ".join(seg.text.strip() for seg in segments)


class CloudEngine:
    def transcribe(self, audio: np.ndarray, settings: Settings) -> str:
        from urllib.parse import urlsplit

        import requests

        base = settings.cloud_base_url.strip()
        parts = urlsplit(base)
        loopback = (parts.hostname or "") in _LOOPBACK
        if parts.scheme not in ("https", "http") or not parts.hostname:
            raise TranscribeError("Неверный адрес API (нужен https://…)")
        if parts.scheme == "http" and settings.cloud_api_key and not loopback:
            raise TranscribeError("Ключ не отправляется по незашифрованному http:// — используйте https://")
        if not settings.cloud_api_key and not loopback:
            raise TranscribeError("Не указан API-ключ (Настройки → Облако)")
        url = base.rstrip("/") + "/audio/transcriptions"
        data = {"model": settings.cloud_model, "response_format": "json"}
        if settings.language != "auto":
            data["language"] = settings.language
        if settings.initial_prompt:
            data["prompt"] = settings.initial_prompt
        headers = {"Authorization": f"Bearer {settings.cloud_api_key}"} if settings.cloud_api_key else {}
        try:
            # без редиректов: ключ и аудио уходят только на указанный адрес
            resp = requests.post(url, headers=headers, data=data, timeout=60, allow_redirects=False,
                                 files={"file": ("audio.wav", to_wav_bytes(audio), "audio/wav")})
        except requests.RequestException as exc:
            raise TranscribeError(f"Сеть: {type(exc).__name__}") from exc
        if resp.status_code != 200:
            raise TranscribeError(f"API {resp.status_code}: {resp.text[:200]}")
        try:
            text = resp.json().get("text", "")
        except (ValueError, AttributeError) as exc:
            raise TranscribeError("API вернул неожиданный ответ") from exc
        return text if isinstance(text, str) else ""


class Transcriber:
    def __init__(self):
        self.local = LocalEngine()
        self.cloud = CloudEngine()

    def transcribe(self, audio: np.ndarray, settings: Settings) -> str:
        engine = self.cloud if settings.engine == "cloud" else self.local
        text = engine.transcribe(audio, settings)
        return postprocess(text, settings)


def postprocess(text: str, settings: Settings) -> str:
    text = _UNSAFE_CHARS.sub("", re.sub(r"\s+", " ", text)).strip()
    if not text or _HALLUCINATIONS.match(text):
        return ""
    if settings.strip_final_period and text.endswith(".") and not text.endswith("..."):
        text = text[:-1]
    if settings.trailing_space:
        text += " "
    return text
