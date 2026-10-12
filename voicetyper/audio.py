"""Запись звука с микрофона в 16 кГц mono float32."""
from __future__ import annotations

import io
import threading
import wave

import numpy as np
import sounddevice as sd

SAMPLE_RATE = 16000


def list_microphones() -> list[str]:
    """Входные устройства через MME (без дублей WASAPI/WDM-KS, сам ресемплирует)."""
    names: list[str] = []
    try:
        mme = next((i for i, h in enumerate(sd.query_hostapis()) if "MME" in h["name"]), 0)
        for dev in sd.query_devices():
            if dev["max_input_channels"] > 0 and dev["hostapi"] == mme:
                name = dev["name"].strip()
                if name not in names and "Microsoft Sound Mapper" not in name and "Переназначение" not in name:
                    names.append(name)
    except Exception:
        pass
    return names


def _find_device(name: str):
    if not name:
        return None
    for idx, dev in enumerate(sd.query_devices()):
        if dev["max_input_channels"] > 0 and dev["name"].strip() == name:
            return idx
    return None


class Recorder:
    def __init__(self):
        self._chunks: list[np.ndarray] = []
        self._stream: sd.InputStream | None = None
        self._lock = threading.Lock()
        self.level = 0.0          # текущая громкость 0..1 для индикатора
        self.peak = 0.0           # максимальная громкость за запись

    @property
    def active(self) -> bool:
        return self._stream is not None

    def start(self, microphone: str = "") -> None:
        with self._lock:
            if self._stream is not None:
                return
            self._chunks = []
            self.level = self.peak = 0.0
            self._stream = sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="float32",
                device=_find_device(microphone),
                callback=self._callback,
                blocksize=1024,
            )
            self._stream.start()

    def _callback(self, indata, frames, time_info, status):
        chunk = indata[:, 0].copy()
        self._chunks.append(chunk)
        rms = float(np.sqrt(np.mean(chunk ** 2))) if len(chunk) else 0.0
        self.level = min(1.0, rms * 12)
        self.peak = max(self.peak, rms)

    def stop(self) -> np.ndarray:
        with self._lock:
            stream, self._stream = self._stream, None
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass
        self.level = 0.0
        if not self._chunks:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(self._chunks)

    @property
    def seconds(self) -> float:
        return sum(len(c) for c in self._chunks) / SAMPLE_RATE


def to_wav_bytes(audio: np.ndarray) -> bytes:
    pcm = (np.clip(audio, -1, 1) * 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(pcm.tobytes())
    return buf.getvalue()
