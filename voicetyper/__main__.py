import sys


def _transcribe_file(src: str, dst: str) -> None:
    """Диагностика: VoiceTyper.exe --transcribe-file in.wav out.txt"""
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
    try:
        text = Transcriber().transcribe(audio, Settings.load())
    except Exception as exc:
        text = f"ERROR: {exc!r}"
    with open(dst, "w", encoding="utf-8") as f:
        f.write(text)


def main() -> None:
    if len(sys.argv) == 4 and sys.argv[1] == "--transcribe-file":
        _transcribe_file(sys.argv[2], sys.argv[3])
        return

    from .winutil import acquire_single_instance, message_box

    if not acquire_single_instance():
        message_box("VoiceTyper уже запущен — значок находится в системном трее (возле часов).")
        return

    from .app import App, setup_logging

    setup_logging()
    App(minimized="--minimized" in sys.argv).run()


if __name__ == "__main__":
    main()
