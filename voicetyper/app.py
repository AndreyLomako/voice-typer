"""Главный контроллер: связывает горячие клавиши, запись, распознавание и вставку."""
from __future__ import annotations

import logging
import os
import queue
import sys
import threading
import time
import winsound
from logging.handlers import RotatingFileHandler
from pathlib import Path

import customtkinter as ctk
import numpy as np
import pyperclip

from . import APP_NAME
from .audio import SAMPLE_RATE, Recorder
from .config import APPDATA_DIR, LOG_FILE, Settings
from .engines import CloudEngine, Transcriber
from .hotkeys import HotkeyManager, pretty
from .inserter import insert_text
from .overlay import Overlay
from .tray import Tray
from .ui import SettingsWindow
from .winutil import cursor_pos, set_autostart

log = logging.getLogger(APP_NAME)

MIN_SECONDS = 0.35
SILENCE_RMS = 0.0035


def resource_path(rel: str) -> str:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return str(base / rel)


def setup_logging() -> None:
    APPDATA_DIR.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(LOG_FILE, maxBytes=1_000_000, backupCount=2, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[handler])
    sys.excepthook = lambda *exc: log.critical("Необработанная ошибка", exc_info=exc)
    threading.excepthook = lambda a: log.critical("Ошибка в потоке", exc_info=(a.exc_type, a.exc_value, a.exc_traceback))


class App:
    def __init__(self, minimized: bool = False):
        self.settings = Settings.load()
        self.icon_path = resource_path("assets/icon.ico")
        self.history: list[tuple[float, str]] = []

        ctk.set_appearance_mode(self.settings.theme)
        ctk.set_default_color_theme("blue")
        self.root = ctk.CTk()
        self.root.withdraw()
        self._queue: queue.SimpleQueue = queue.SimpleQueue()

        self.recorder = Recorder()
        self.transcriber = Transcriber()
        self.state = "idle"            # idle | recording | processing | testing
        self._source = "hotkey"
        self._session = 0
        self._lock = threading.Lock()
        self._model_ready = False
        self._status = ("loading", "Запуск…")
        self._hidden_notice_shown = False

        self.overlay = Overlay(self.root)
        self.hotkeys = HotkeyManager(self._on_hold_start, self._on_hold_end, self._on_toggle, self._on_cancel)
        self.window = SettingsWindow(self)
        self.tray = Tray(
            on_settings=lambda: self.ui(self.window.show),
            on_toggle_record=lambda: self.toggle_recording("tray"),
            on_toggle_enabled=self._toggle_hotkeys_enabled,
            on_copy_last=self.copy_last,
            on_quit=lambda: self.ui(self.quit),
            is_enabled=lambda: self.settings.hotkeys_enabled,
        )

        self.apply_settings(save=False)
        self.hotkeys.start()
        self.tray.run()
        self.request_model_preload()

        if self.settings.first_run or not (minimized or self.settings.start_minimized):
            # после старта mainloop: CTk при первом запуске сам прячет окно, перекрашивая заголовок
            self.root.after(150, self.window.show)
        if self.settings.first_run:
            self.settings.first_run = False
            self.settings.save()
        self.root.after(30, self._poll_queue)

    # ------------------------------------------------------------ потоки → UI
    def ui(self, fn) -> None:
        """Выполнить fn в потоке интерфейса (Tk не потокобезопасен)."""
        self._queue.put(fn)

    def _poll_queue(self):
        try:
            while True:
                fn = self._queue.get_nowait()
                try:
                    fn()
                except Exception:
                    log.exception("Ошибка в UI-задаче")
        except queue.Empty:
            pass
        self.root.after(30, self._poll_queue)

    def run(self):
        self.root.mainloop()

    # ------------------------------------------------------------ статус
    def _set_status(self, state: str, text: str):
        self._status = (state, text)

        def apply():
            self.window.set_status(state, text)
            tray_state = {"recording": "recording", "processing": "processing", "loading": "processing"}.get(state)
            if tray_state is None:
                tray_state = "idle" if self.settings.hotkeys_enabled else "disabled"
            self.tray.set_state(tray_state, f"VoiceTyper hs — {text}")

        self.ui(apply)

    def _idle_status(self):
        if not self.settings.hotkeys_enabled:
            self._set_status("disabled", "Горячие клавиши выключены")
        elif self.settings.engine == "cloud":
            self._set_status("idle", "Готово · облако")
        elif self._model_ready:
            self._set_status("idle", f"Готово · модель {self.settings.local_model}")
        # иначе статус загрузки модели выставит request_model_preload

    # ------------------------------------------------------------ настройки
    def apply_settings(self, save: bool = True):
        s = self.settings
        if save:
            s.save()
        self.hotkeys.configure(s.hotkey_hold, s.hotkey_toggle, s.hotkey_cancel, s.hotkeys_enabled)
        try:
            set_autostart(s.autostart)
        except OSError:
            log.exception("Не удалось изменить автозапуск")
        if self.state == "idle":
            self._idle_status()

    def _toggle_hotkeys_enabled(self):
        def apply():
            self.window.switch_vars["hotkeys_enabled"].set(not self.settings.hotkeys_enabled)
            self.apply_settings()
        self.ui(apply)

    def request_model_preload(self):
        s = self.settings
        if s.engine != "local":
            self._idle_status()
            return
        key = (s.local_model, s.device)
        if self.transcriber.local._key == key and self.transcriber.local._model is not None:
            self._model_ready = True
            self._idle_status()
            return
        self._model_ready = False

        def work():
            try:
                self.transcriber.local.ensure_loaded(s, on_status=lambda t: self._set_status("loading", t))
                if (s.local_model, s.device) == key:
                    self._model_ready = True
                    if self.state == "idle":
                        self._idle_status()
            except Exception as exc:
                log.exception("Не удалось загрузить модель")
                self._set_status("error", f"Ошибка загрузки модели: {exc}")

        threading.Thread(target=work, daemon=True).start()

    def on_settings_hidden(self):
        if not self._hidden_notice_shown:
            self._hidden_notice_shown = True
            hk = pretty(self.settings.hotkey_hold or self.settings.hotkey_toggle)
            self.tray.notify(f"Программа работает в трее. Диктуйте с помощью {hk}.")

    # ------------------------------------------------------------ горячие клавиши
    def _on_hold_start(self):
        self.start_recording("hold")

    def _on_hold_end(self, interrupted: bool):
        if self.state == "recording" and self._source == "hold":
            if interrupted:
                self.cancel(silent=True)
            else:
                self.stop_recording()

    def _on_toggle(self):
        self.toggle_recording("toggle")

    def _on_cancel(self):
        if self.state in ("recording", "processing"):
            self.cancel()

    def toggle_recording(self, source: str):
        if self.state == "idle":
            self.start_recording(source)
        elif self.state == "recording":
            self.stop_recording()

    def toggle_recording_from_ui(self):
        self.toggle_recording("ui")

    # ------------------------------------------------------------ запись
    def start_recording(self, source: str):
        with self._lock:
            if self.state != "idle":
                return
            self.state = "recording"
            self._source = source
            self._session += 1
            session = self._session
        try:
            self.recorder.start(self.settings.microphone)
        except Exception as exc:
            log.exception("Микрофон недоступен")
            self.state = "idle"
            self._error(f"Микрофон недоступен: {exc}")
            return
        self._beep(880)
        self._set_status("recording", "Идёт запись…")
        if self.settings.show_overlay:
            self.ui(lambda: self.overlay.recording(lambda: self.recorder.level, lambda: self.recorder.seconds))
        threading.Timer(self.settings.max_seconds, self._auto_stop, args=(session,)).start()

    def _auto_stop(self, session: int):
        if self.state == "recording" and self._session == session:
            self.stop_recording()

    def stop_recording(self):
        with self._lock:
            if self.state != "recording":
                return
            self.state = "processing"
            session = self._session
            source = self._source
        mouse = cursor_pos()
        audio = self.recorder.stop()
        peak = self.recorder.peak
        self._beep(620)

        if len(audio) < MIN_SECONDS * SAMPLE_RATE:
            self._finish(session, None, "Слишком коротко")
            return
        if peak < SILENCE_RMS:
            self._finish(session, None, "Тишина — проверьте микрофон")
            return

        self._set_status("processing", "Распознаю…")
        if self.settings.show_overlay:
            self.ui(lambda: self.overlay.processing())
        threading.Thread(target=self._transcribe, args=(session, source, audio, mouse), daemon=True).start()

    def _transcribe(self, session: int, source: str, audio: np.ndarray, mouse):
        started = time.time()
        try:
            if self.settings.engine == "local" and not self._model_ready:
                self._set_status("processing", "Жду загрузку модели…")
                self.ui(lambda: self.overlay.processing("Загружаю модель…"))
            text = self.transcriber.transcribe(audio, self.settings)
            self._model_ready = self._model_ready or self.settings.engine == "local"
        except Exception as exc:
            log.exception("Ошибка распознавания")
            if self._session == session:
                self.state = "idle"
                self._error(f"Ошибка: {exc}")
            return
        log.info("Распознано за %.1f с (%.1f с аудио): %d символов",
                 time.time() - started, len(audio) / SAMPLE_RATE, len(text))
        if self._session != session:      # отменено, пока распознавали
            return
        if not text:
            self._finish(session, None, "Речь не распознана")
            return

        self.history.append((time.time(), text))
        self.history[:] = self.history[-100:]
        if source in ("ui", "tray"):
            pyperclip.copy(text.strip())
            self._finish(session, text, "Скопировано в буфер обмена")
        else:
            if self.settings.show_overlay:
                self.ui(self.overlay.hide)
                time.sleep(0.05)
            try:
                insert_text(text, self.settings, mouse)
            except Exception as exc:
                log.exception("Ошибка вставки")
                self.state = "idle"
                self._error(f"Не удалось вставить текст: {exc}")
                return
            self._finish(session, text, None)

    def _finish(self, session: int, text: str | None, message: str | None):
        if self._session != session:
            return
        self.state = "idle"
        self._idle_status()

        def apply():
            if message and self.settings.show_overlay:
                (self.overlay.done if text else self.overlay.error)(message)
            elif not self.settings.show_overlay or not message:
                if self.overlay.mode != "hidden":
                    self.overlay.hide()
            if text and self.window.root.winfo_viewable():
                self.window.refresh_history()

        self.ui(apply)

    def cancel(self, silent: bool = False):
        with self._lock:
            if self.state not in ("recording", "processing"):
                return
            was_recording = self.state == "recording"
            self._session += 1
            self.state = "idle"
        if was_recording:
            self.recorder.stop()
            if not silent:
                self._beep(440)
        self._idle_status()
        if self.settings.show_overlay:
            self.ui(self.overlay.hide if silent else (lambda: self.overlay.error("Запись отменена")))

    def _error(self, text: str):
        self._idle_status()
        if self.settings.show_overlay:
            self.ui(lambda: self.overlay.error(text))
        else:
            self.tray.notify(text)

    def _beep(self, freq: int):
        if self.settings.play_sounds:
            threading.Thread(target=winsound.Beep, args=(freq, 70), daemon=True).start()

    # ------------------------------------------------------------ прочее для UI
    def start_mic_test(self) -> bool:
        with self._lock:
            if self.state != "idle":
                return False
            self.state = "testing"
        try:
            self.recorder.start(self.settings.microphone)
            return True
        except Exception as exc:
            self.state = "idle"
            self._error(f"Микрофон недоступен: {exc}")
            return False

    def stop_mic_test(self):
        if self.state == "testing":
            self.recorder.stop()
            self.state = "idle"

    def test_cloud(self, callback):
        def work():
            try:
                CloudEngine().transcribe(np.zeros(SAMPLE_RATE, dtype=np.float32), self.settings)
                callback(True, "✓ Подключение работает")
            except Exception as exc:
                callback(False, str(exc)[:120])

        threading.Thread(target=work, daemon=True).start()

    def copy_last(self):
        if self.history:
            pyperclip.copy(self.history[-1][1].strip())
            self.tray.notify("Последний текст скопирован в буфер обмена")

    def quit(self):
        log.info("Выход")
        try:
            self.hotkeys.stop()
            self.recorder.stop()
            self.settings.save()
        finally:
            self.tray.stop()
            self.root.destroy()
            os._exit(0)
