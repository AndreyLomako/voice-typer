import sys


def _transcribe_file(src: str, dst: str, model: str | None = None) -> None:
    """Диагностика: VoiceTyper-hs --transcribe-file in.wav out.txt [модель]"""
    import wave

    import numpy as np

    from .config import Settings
    from .engines import Transcriber

    with wave.open(src) as w:
        sr, ch = w.getframerate(), w.getnchannels()
        audio = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
    if ch > 1:
        audio = audio.reshape(-1, ch).mean(axis=1)
    if sr != 16000:
        audio = np.interp(np.arange(0, len(audio), sr / 16000), np.arange(len(audio)), audio).astype(np.float32)
    settings = Settings.load()
    settings.engine = "local"
    if model:
        settings.local_model = model
    try:
        text = Transcriber().transcribe(audio, settings)
    except Exception as exc:
        text = f"ERROR: {exc!r}"
    with open(dst, "w", encoding="utf-8") as f:
        f.write(text)


def main() -> None:
    if len(sys.argv) in (4, 5) and sys.argv[1] == "--transcribe-file":
        _transcribe_file(*sys.argv[2:])
        return

    from . import APP_DISPLAY, system

    if not system.acquire_single_instance():
        where = "в Dock" if system.IS_MAC else "в системном трее (возле часов)"
        system.message_box(f"{APP_DISPLAY} уже запущен — значок находится {where}.", APP_DISPLAY)
        return

    from .app import App, setup_logging

    setup_logging()
    App(minimized="--minimized" in sys.argv).run()


if __name__ == "__main__":
    main()
