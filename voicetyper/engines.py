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
            try:  # сначала из кэша — без обращения к сети, работает офлайн
                path = download_model(name, local_files_only=True, cache_dir=str(MODELS_DIR))
            except Exception:
                if on_status:
                    on_status(f"Скачиваю модель «{name}» (один раз, может занять несколько минут)…")
                path = download_model(name, cache_dir=str(MODELS_DIR))
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
        import requests

        if not settings.cloud_api_key and "localhost" not in settings.cloud_base_url:
            raise TranscribeError("Не указан API-ключ (Настройки → Облако)")
        url = settings.cloud_base_url.rstrip("/") + "/audio/transcriptions"
        data = {"model": settings.cloud_model, "response_format": "json"}
        if settings.language != "auto":
            data["language"] = settings.language
        if settings.initial_prompt:
            data["prompt"] = settings.initial_prompt
        headers = {"Authorization": f"Bearer {settings.cloud_api_key}"} if settings.cloud_api_key else {}
        try:
            resp = requests.post(url, headers=headers, data=data, timeout=60,
                                 files={"file": ("audio.wav", to_wav_bytes(audio), "audio/wav")})
        except requests.RequestException as exc:
            raise TranscribeError(f"Сеть: {exc}") from exc
        if resp.status_code != 200:
            raise TranscribeError(f"API {resp.status_code}: {resp.text[:200]}")
        return resp.json().get("text", "")


class Transcriber:
    def __init__(self):
        self.local = LocalEngine()
        self.cloud = CloudEngine()

    def transcribe(self, audio: np.ndarray, settings: Settings) -> str:
        engine = self.cloud if settings.engine == "cloud" else self.local
        text = engine.transcribe(audio, settings)
        return postprocess(text, settings)


def postprocess(text: str, settings: Settings) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if not text or _HALLUCINATIONS.match(text):
        return ""
    if settings.strip_final_period and text.endswith(".") and not text.endswith("..."):
        text = text[:-1]
    if settings.trailing_space:
        text += " "
    return text
