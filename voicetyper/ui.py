"""Окно настроек."""
from __future__ import annotations

import os
import time
import tkinter as tk
from typing import TYPE_CHECKING

import customtkinter as ctk

from . import APP_TITLE, __version__
from .audio import list_microphones
from .config import APPDATA_DIR, CLOUD_PRESETS, LANGUAGES, MODELS_DIR
from .hotkeys import pretty

if TYPE_CHECKING:
    from .app import App

MODEL_INFO = {
    "tiny": "tiny — 75 МБ, мгновенно, точность низкая",
    "base": "base — 145 МБ, быстро, точность средняя",
    "small": "small — 480 МБ, баланс (рекомендуется)",
    "medium": "medium — 1.5 ГБ, точнее, медленнее",
    "large-v3-turbo": "large-v3-turbo — 1.6 ГБ, высокая точность",
    "large-v3": "large-v3 — 3 ГБ, максимум, очень медленно на CPU",
}
DEVICE_INFO = {"cpu": "Процессор (CPU)", "cuda": "Видеокарта NVIDIA (CUDA)"}
THEME_INFO = {"dark": "Тёмная", "light": "Светлая", "system": "Как в системе"}
DEFAULT_MIC = "Системный по умолчанию"

STATUS_COLORS = {
    "idle": "#3ecf8e", "loading": "#ffb020", "recording": "#ff4d5e",
    "processing": "#4da3ff", "error": "#ff4d5e", "disabled": "#8a9099",
}

NAV = [
    ("main", "Распознавание"),
    ("hotkeys", "Горячие клавиши"),
    ("insert", "Вставка текста"),
    ("cloud", "Облако (API)"),
    ("ui", "Интерфейс"),
    ("history", "История"),
]


def _inv(d: dict, value: str) -> str:
    return next((k for k, v in d.items() if v == value), value)


class SettingsWindow:
    def __init__(self, app: "App"):
        self.app = app
        self.s = app.settings
        self.root: ctk.CTk = app.root
        self._save_job = None
        self._vars: list[tk.Variable] = []
        self.switch_vars: dict[str, tk.BooleanVar] = {}
        self._capture_btn: ctk.CTkButton | None = None
        self._mic_test = False

        r = self.root
        r.title(APP_TITLE)
        r.geometry("900x620")
        r.minsize(780, 540)
        r.protocol("WM_DELETE_WINDOW", self.hide)
        try:
            r.iconbitmap(app.icon_path)
        except Exception:
            pass

        self.f_title = ctk.CTkFont("Segoe UI", 22, "bold")
        self.f_h = ctk.CTkFont("Segoe UI", 15, "bold")
        self.f_b = ctk.CTkFont("Segoe UI", 13)
        self.f_bb = ctk.CTkFont("Segoe UI", 13, "bold")
        self.f_s = ctk.CTkFont("Segoe UI", 12)

        r.grid_columnconfigure(1, weight=1)
        r.grid_rowconfigure(0, weight=1)
        self._build_sidebar()
        self.content = ctk.CTkFrame(r, fg_color="transparent")
        self.content.grid(row=0, column=1, sticky="nsew", padx=(0, 0))
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(0, weight=1)

        self.pages = {
            "main": self._page_main(),
            "hotkeys": self._page_hotkeys(),
            "insert": self._page_insert(),
            "cloud": self._page_cloud(),
            "ui": self._page_ui(),
            "history": self._page_history(),
        }
        self.show_page("main")

    # ------------------------------------------------------------------ каркас
    def _build_sidebar(self):
        sb = ctk.CTkFrame(self.root, width=220, corner_radius=0)
        sb.grid(row=0, column=0, sticky="nsw")
        sb.grid_propagate(False)
        sb.grid_rowconfigure(len(NAV) + 3, weight=1)

        ctk.CTkLabel(sb, text="🎙 VoiceTyper", font=self.f_title).grid(row=0, column=0, padx=20, pady=(22, 4), sticky="w")
        self.status_label = ctk.CTkLabel(sb, text="● Запуск…", font=self.f_s, text_color=STATUS_COLORS["loading"],
                                         wraplength=185, justify="left", anchor="w")
        self.status_label.grid(row=1, column=0, padx=22, pady=(0, 18), sticky="w")

        self.nav_buttons: dict[str, ctk.CTkButton] = {}
        for i, (key, title) in enumerate(NAV):
            b = ctk.CTkButton(sb, text=title, anchor="w", height=38, corner_radius=8, font=self.f_b,
                              fg_color="transparent", text_color=("gray10", "gray90"),
                              hover_color=("gray75", "gray25"), command=lambda k=key: self.show_page(k))
            b.grid(row=i + 2, column=0, padx=12, pady=2, sticky="ew")
            self.nav_buttons[key] = b

        self.record_btn = ctk.CTkButton(sb, text="● Начать запись", height=40, font=self.f_bb,
                                        fg_color="#d93a4a", hover_color="#b82f3d",
                                        command=self.app.toggle_recording_from_ui)
        self.record_btn.grid(row=len(NAV) + 4, column=0, padx=16, pady=(8, 6), sticky="ew")
        ctk.CTkLabel(sb, text=f"версия {__version__}", font=self.f_s, text_color="gray55").grid(
            row=len(NAV) + 5, column=0, padx=20, pady=(0, 14), sticky="w")

    def show_page(self, key: str):
        for k, page in self.pages.items():
            page.grid_forget()
        self.pages[key].grid(row=0, column=0, sticky="nsew", padx=18, pady=14)
        for k, b in self.nav_buttons.items():
            b.configure(fg_color=("gray78", "gray22") if k == key else "transparent")
        if key == "history":
            self.refresh_history()
        if key != "main" and self._mic_test:
            self._toggle_mic_test()

    def _page(self, title: str, subtitle: str) -> ctk.CTkScrollableFrame:
        page = ctk.CTkScrollableFrame(self.content, fg_color="transparent")
        page.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(page, text=title, font=self.f_title, anchor="w").grid(sticky="w", pady=(0, 2))
        ctk.CTkLabel(page, text=subtitle, font=self.f_s, text_color="gray60", anchor="w", justify="left",
                     wraplength=600).grid(sticky="w", pady=(0, 12))
        return page

    def _card(self, page, title: str | None = None) -> ctk.CTkFrame:
        card = ctk.CTkFrame(page, corner_radius=12)
        card.grid(sticky="ew", pady=(0, 12))
        card.grid_columnconfigure(0, weight=1)
        if title:
            ctk.CTkLabel(card, text=title, font=self.f_h, anchor="w").grid(
                row=0, column=0, columnspan=3, sticky="w", padx=16, pady=(12, 4))
        return card

    def _row(self, card, label: str, desc: str | None = None) -> ctk.CTkFrame:
        """Строка: слева подпись и пояснение, справа — контейнер под виджет."""
        row = card.grid_size()[1]
        box = ctk.CTkFrame(card, fg_color="transparent")
        box.grid(row=row, column=0, sticky="ew", padx=16, pady=7)
        box.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(box, text=label, font=self.f_b, anchor="w").grid(row=0, column=0, sticky="w")
        if desc:
            ctk.CTkLabel(box, text=desc, font=self.f_s, text_color="gray60", anchor="w", justify="left",
                         wraplength=380).grid(row=1, column=0, sticky="w")
        right = ctk.CTkFrame(box, fg_color="transparent")
        right.grid(row=0, column=1, rowspan=2, sticky="e", padx=(12, 0))
        return right

    # ---------------------------------------------------- привязка к настройкам
    def _bind(self, var: tk.Variable, attr: str, to_value=lambda v: v, after=None):
        self._vars.append(var)

        def on_change(*_):
            try:
                setattr(self.s, attr, to_value(var.get()))
            except (tk.TclError, ValueError):
                return
            if after:
                after()
            self._schedule_save()

        var.trace_add("write", on_change)
        return var

    def _switch(self, parent, attr: str, after=None):
        var = self._bind(tk.BooleanVar(value=getattr(self.s, attr)), attr, bool, after)
        self.switch_vars[attr] = var
        sw = ctk.CTkSwitch(parent, text="", variable=var, onvalue=True, offvalue=False, width=46)
        sw.pack()
        return sw

    def _schedule_save(self):
        if self._save_job:
            self.root.after_cancel(self._save_job)
        self._save_job = self.root.after(500, self._save)

    def _save(self):
        self._save_job = None
        self.app.apply_settings()

    # ------------------------------------------------------------ страницы
    def _page_main(self):
        p = self._page("Распознавание речи",
                       "Как пользоваться: наведите указатель мыши на нужное поле, зажмите горячую клавишу "
                       "и говорите. Отпустите — текст появится там, куда указывает мышь.")

        tip = self._card(p)
        self.tip_label = ctk.CTkLabel(tip, text="", font=self.f_b, justify="left", anchor="w", wraplength=600)
        self.tip_label.grid(sticky="w", padx=16, pady=12)
        self.update_tip()

        c = self._card(p, "Движок")
        right = self._row(c, "Где распознавать",
                          "Локально — бесплатно и без интернета. Облако — быстрее на слабых ПК, нужен API-ключ.")
        engine_var = tk.StringVar(value="Локально" if self.s.engine == "local" else "Облако")
        self._bind(engine_var, "engine", lambda v: "local" if v == "Локально" else "cloud", self._engine_changed)
        ctk.CTkSegmentedButton(right, values=["Локально", "Облако"], variable=engine_var, width=220).pack()

        right = self._row(c, "Модель Whisper", "Скачивается один раз при первом использовании.")
        model_var = tk.StringVar(value=MODEL_INFO.get(self.s.local_model, self.s.local_model))
        self._bind(model_var, "local_model", lambda v: _inv(MODEL_INFO, v), self._model_changed)
        self.model_menu = ctk.CTkOptionMenu(right, values=list(MODEL_INFO.values()), variable=model_var, width=330,
                                            dynamic_resizing=False)
        self.model_menu.pack()

        right = self._row(c, "Вычисления", "GPU требует видеокарту NVIDIA с установленными CUDA 12 и cuDNN.")
        dev_var = tk.StringVar(value=DEVICE_INFO.get(self.s.device, self.s.device))
        self._bind(dev_var, "device", lambda v: _inv(DEVICE_INFO, v), self._model_changed)
        self.device_menu = ctk.CTkOptionMenu(right, values=list(DEVICE_INFO.values()), variable=dev_var, width=330,
                                             dynamic_resizing=False)
        self.device_menu.pack()

        right = self._row(c, "Язык речи", "Явно заданный язык распознаётся точнее, чем автоопределение.")
        lang_var = tk.StringVar(value=LANGUAGES.get(self.s.language, self.s.language))
        self._bind(lang_var, "language", lambda v: _inv(LANGUAGES, v))
        ctk.CTkOptionMenu(right, values=list(LANGUAGES.values()), variable=lang_var, width=330,
                          dynamic_resizing=False).pack()

        right = self._row(c, "Подсказка-словарь",
                          "Имена, термины и бренды через запятую — модель будет писать их правильно.")
        prompt_var = tk.StringVar(value=self.s.initial_prompt)
        self._bind(prompt_var, "initial_prompt", str.strip)
        ctk.CTkEntry(right, textvariable=prompt_var, width=330, placeholder_text="Например: Bitrix, Аспро, JSON").pack()

        c = self._card(p, "Микрофон")
        right = self._row(c, "Устройство записи")
        mics = [DEFAULT_MIC] + list_microphones()
        mic_var = tk.StringVar(value=self.s.microphone or DEFAULT_MIC)
        self._bind(mic_var, "microphone", lambda v: "" if v == DEFAULT_MIC else v)
        box = ctk.CTkFrame(right, fg_color="transparent")
        box.pack()
        self.mic_menu = ctk.CTkOptionMenu(box, values=mics, variable=mic_var, width=286, dynamic_resizing=False)
        self.mic_menu.pack(side="left")
        ctk.CTkButton(box, text="⟳", width=36, command=self._refresh_mics).pack(side="left", padx=(8, 0))

        right = self._row(c, "Проверка микрофона", "Скажите что-нибудь — полоса должна двигаться.")
        box = ctk.CTkFrame(right, fg_color="transparent")
        box.pack()
        self.mic_bar = ctk.CTkProgressBar(box, width=200, progress_color="#3ecf8e")
        self.mic_bar.set(0)
        self.mic_bar.pack(side="left", padx=(0, 10))
        self.mic_btn = ctk.CTkButton(box, text="Проверить", width=120, command=self._toggle_mic_test)
        self.mic_btn.pack(side="left")
        self._engine_changed()
        return p

    def _page_hotkeys(self):
        p = self._page("Горячие клавиши",
                       "Нажмите на кнопку с комбинацией, затем нажмите новые клавиши и отпустите их. "
                       "Клавиши не блокируются для других программ, поэтому лучше выбирать редко "
                       "используемые: Правый Ctrl, Правый Alt, F9, Pause.")
        c = self._card(p, "Комбинации")
        self.hk_buttons = {}
        for attr, label, desc in [
            ("hotkey_hold", "Удерживать для записи",
             "Режим рации: держите — идёт запись, отпустили — текст вставлен. "
             "Если во время удержания нажать другую клавишу, запись отменяется."),
            ("hotkey_toggle", "Начать / остановить запись",
             "Нажали — запись пошла, нажали ещё раз — текст вставлен. Удобно для длинной диктовки."),
            ("hotkey_cancel", "Отменить запись", "Остановить запись без вставки текста."),
        ]:
            right = self._row(c, label, desc)
            box = ctk.CTkFrame(right, fg_color="transparent")
            box.pack()
            btn = ctk.CTkButton(box, text=pretty(getattr(self.s, attr)), width=210, height=34, font=self.f_bb,
                                fg_color=("gray80", "gray25"), text_color=("gray10", "gray95"),
                                hover_color=("gray70", "gray30"))
            btn.configure(command=lambda a=attr, b=btn: self._capture_hotkey(a, b))
            btn.pack(side="left")
            ctk.CTkButton(box, text="✕", width=34, height=34, fg_color="transparent", text_color="gray60",
                          hover_color=("gray80", "gray25"),
                          command=lambda a=attr, b=btn: self._set_hotkey(a, b, "")).pack(side="left", padx=(6, 0))
            self.hk_buttons[attr] = btn
        self.hk_warning = ctk.CTkLabel(c, text="", font=self.f_s, text_color="#ffb020", anchor="w")
        self.hk_warning.grid(sticky="w", padx=16, pady=(0, 10))

        c = self._card(p, "Поведение")
        right = self._row(c, "Горячие клавиши включены", "Быстро выключить можно и из меню значка в трее.")
        self._switch(right, "hotkeys_enabled")
        right = self._row(c, "Максимальная длительность записи", "Запись остановится автоматически.")
        box = ctk.CTkFrame(right, fg_color="transparent")
        box.pack()
        max_var = tk.IntVar(value=self.s.max_seconds)
        lbl = ctk.CTkLabel(box, text=self._fmt_secs(self.s.max_seconds), width=60, font=self.f_b)
        self._bind(max_var, "max_seconds", int, lambda: lbl.configure(text=self._fmt_secs(self.s.max_seconds)))
        ctk.CTkSlider(box, from_=10, to=600, number_of_steps=59, variable=max_var, width=200).pack(side="left")
        lbl.pack(side="left", padx=(8, 0))
        return p

    def _page_insert(self):
        p = self._page("Вставка текста", "Куда и каким способом попадает распознанный текст.")
        c = self._card(p, "Куда вставлять")
        target = tk.StringVar(value=self.s.insert_target)
        self._bind(target, "insert_target", after=self.update_tip)
        for value, title, desc in [
            ("mouse", "Туда, куда указывает мышь",
             "В момент окончания записи программа кликнет в точку под указателем и вставит текст. "
             "Можно диктовать в любое поле, не переключаясь на него заранее."),
            ("focus", "В активное поле ввода",
             "Текст вставится туда, где сейчас мигает текстовый курсор. Мышь не трогается."),
        ]:
            ctk.CTkRadioButton(c, text=title, value=value, variable=target, font=self.f_bb).grid(
                sticky="w", padx=16, pady=(8, 0))
            ctk.CTkLabel(c, text=desc, font=self.f_s, text_color="gray60", wraplength=560, justify="left",
                         anchor="w").grid(sticky="w", padx=44, pady=(0, 6))

        c = self._card(p, "Способ вставки")
        method = tk.StringVar(value=self.s.insert_method)
        self._bind(method, "insert_method")
        for value, title, desc in [
            ("paste", "Через буфер обмена (Ctrl+V)", "Быстро и надёжно. Рекомендуется."),
            ("type", "Эмуляция набора с клавиатуры",
             "Для программ, где вставка запрещена (некоторые терминалы, удалённые рабочие столы)."),
        ]:
            ctk.CTkRadioButton(c, text=title, value=value, variable=method, font=self.f_bb).grid(
                sticky="w", padx=16, pady=(8, 0))
            ctk.CTkLabel(c, text=desc, font=self.f_s, text_color="gray60", wraplength=560, justify="left",
                         anchor="w").grid(sticky="w", padx=44, pady=(0, 6))

        c = self._card(p, "Обработка текста")
        self._switch(self._row(c, "Восстанавливать буфер обмена",
                               "После вставки вернуть то, что было скопировано до этого."), "restore_clipboard")
        self._switch(self._row(c, "Пробел в конце",
                               "Чтобы следующая фраза не слипалась с предыдущей."), "trailing_space")
        self._switch(self._row(c, "Убирать точку в конце",
                               "Удобно для поисковых строк, имён файлов и коротких полей."), "strip_final_period")
        return p

    def _page_cloud(self):
        p = self._page("Облачное распознавание",
                       "Любой OpenAI-совместимый сервис (/audio/transcriptions). Ключ хранится на этом "
                       "компьютере в зашифрованном виде (Windows DPAPI). Включается в разделе «Распознавание».")
        c = self._card(p, "Подключение")
        right = self._row(c, "Провайдер", "Выбор заполнит адрес и модель значениями по умолчанию.")
        preset_var = tk.StringVar(value=self.s.cloud_preset)
        ctk.CTkOptionMenu(right, values=list(CLOUD_PRESETS), variable=preset_var, width=300,
                          command=self._preset_changed).pack()
        self._bind(preset_var, "cloud_preset")

        right = self._row(c, "Адрес API")
        self.url_var = self._bind(tk.StringVar(value=self.s.cloud_base_url), "cloud_base_url", str.strip)
        ctk.CTkEntry(right, textvariable=self.url_var, width=300).pack()

        right = self._row(c, "Модель", "OpenAI: gpt-4o-mini-transcribe, whisper-1. Groq: whisper-large-v3-turbo.")
        self.cmodel_var = self._bind(tk.StringVar(value=self.s.cloud_model), "cloud_model", str.strip)
        ctk.CTkEntry(right, textvariable=self.cmodel_var, width=300).pack()

        right = self._row(c, "API-ключ")
        box = ctk.CTkFrame(right, fg_color="transparent")
        box.pack()
        key_var = self._bind(tk.StringVar(value=self.s.cloud_api_key), "cloud_api_key", str.strip)
        key_entry = ctk.CTkEntry(box, textvariable=key_var, width=256, show="•")
        key_entry.pack(side="left")

        def toggle_show():
            key_entry.configure(show="" if key_entry.cget("show") else "•")

        ctk.CTkButton(box, text="👁", width=36, command=toggle_show).pack(side="left", padx=(8, 0))

        right = self._row(c, "Проверка", "Отправит секунду тишины, чтобы проверить адрес и ключ.")
        box = ctk.CTkFrame(right, fg_color="transparent")
        box.pack()
        self.cloud_result = ctk.CTkLabel(box, text="", font=self.f_s, wraplength=200)
        self.cloud_result.pack(side="left", padx=(0, 10))
        ctk.CTkButton(box, text="Проверить", width=120, command=self._test_cloud).pack(side="left")
        return p

    def _page_ui(self):
        p = self._page("Интерфейс", "Внешний вид и поведение программы.")
        c = self._card(p, "Оформление")
        right = self._row(c, "Тема")
        theme_var = tk.StringVar(value=THEME_INFO.get(self.s.theme, "Тёмная"))
        self._bind(theme_var, "theme", lambda v: _inv(THEME_INFO, v),
                   lambda: ctk.set_appearance_mode(self.s.theme))
        ctk.CTkSegmentedButton(right, values=list(THEME_INFO.values()), variable=theme_var).pack()
        self._switch(self._row(c, "Индикатор у курсора",
                               "Показывает запись, уровень громкости и статус распознавания."), "show_overlay")
        self._switch(self._row(c, "Звуковые сигналы", "Короткий сигнал при начале и конце записи."),
                     "play_sounds")

        c = self._card(p, "Запуск")
        self._switch(self._row(c, "Запускать вместе с Windows"), "autostart")
        self._switch(self._row(c, "Запускаться свёрнутым в трей",
                               "Окно настроек открывается двойным кликом по значку в трее."), "start_minimized")

        c = self._card(p, "Файлы")
        right = self._row(c, "Папка настроек и журнала", str(APPDATA_DIR))
        ctk.CTkButton(right, text="Открыть", width=120, command=lambda: self._open_dir(APPDATA_DIR)).pack()
        right = self._row(c, "Папка моделей", str(MODELS_DIR))
        ctk.CTkButton(right, text="Открыть", width=120, command=lambda: self._open_dir(MODELS_DIR)).pack()
        return p

    def _page_history(self):
        p = self._page("История", "Последние распознанные фразы за текущий сеанс.")
        c = self._card(p)
        bar = ctk.CTkFrame(c, fg_color="transparent")
        bar.grid(sticky="ew", padx=16, pady=(12, 6))
        ctk.CTkButton(bar, text="Скопировать последнее", command=self.app.copy_last).pack(side="left")
        ctk.CTkButton(bar, text="Очистить", fg_color="transparent", border_width=1, text_color=("gray10", "gray90"),
                      command=self._clear_history).pack(side="left", padx=8)
        self.history_box = ctk.CTkTextbox(c, height=380, font=self.f_b, wrap="word")
        self.history_box.grid(sticky="nsew", padx=16, pady=(0, 16))
        return p

    # ------------------------------------------------------------ действия
    def _engine_changed(self):
        local = self.s.engine == "local"
        state = "normal" if local else "disabled"
        if hasattr(self, "device_menu"):
            self.model_menu.configure(state=state)
            self.device_menu.configure(state=state)
        self.update_tip()
        if local:
            self._model_changed()

    def _model_changed(self):
        self.app.request_model_preload()

    def _preset_changed(self, name: str):
        url, model = CLOUD_PRESETS.get(name, ("", ""))
        self.url_var.set(url)
        self.cmodel_var.set(model)

    def _refresh_mics(self):
        self.mic_menu.configure(values=[DEFAULT_MIC] + list_microphones())

    def _toggle_mic_test(self):
        if self._mic_test:
            self._mic_test = False
            self.app.stop_mic_test()
            self.mic_btn.configure(text="Проверить")
            self.mic_bar.set(0)
            return
        if not self.app.start_mic_test():
            return
        self._mic_test = True
        self.mic_btn.configure(text="Стоп")
        self._poll_mic()

    def _poll_mic(self):
        if not self._mic_test:
            return
        self.mic_bar.set(self.app.recorder.level)
        if self.app.recorder.seconds > 15:
            self._toggle_mic_test()
            return
        self.root.after(60, self._poll_mic)

    def _capture_hotkey(self, attr: str, btn: ctk.CTkButton):
        if self._capture_btn is not None:
            self.app.hotkeys.cancel_capture()
            prev = self._capture_btn
            self._capture_btn = None
            prev.configure(text=pretty(getattr(self.s, prev._vt_attr)), fg_color=("gray80", "gray25"))
            if prev is btn:
                return
        btn._vt_attr = attr
        self._capture_btn = btn
        btn.configure(text="Нажмите клавиши…", fg_color=("#9cc9ff", "#1f5aa6"))
        self.app.hotkeys.capture(lambda chord: self.app.ui(lambda: self._set_hotkey(attr, btn, chord)))

    def _set_hotkey(self, attr: str, btn: ctk.CTkButton, chord: str):
        if self._capture_btn is btn:
            self._capture_btn = None
        setattr(self.s, attr, chord)
        btn.configure(text=pretty(chord), fg_color=("gray80", "gray25"))
        keys = [self.s.hotkey_hold, self.s.hotkey_toggle, self.s.hotkey_cancel]
        filled = [k for k in keys if k]
        if len(filled) != len(set(filled)):
            self.hk_warning.configure(text="⚠ Одна и та же комбинация назначена на несколько действий.")
        elif chord and "+" not in chord and len(chord) == 1:
            self.hk_warning.configure(text="⚠ Одиночная буква будет срабатывать при обычном наборе текста.")
        else:
            self.hk_warning.configure(text="")
        self.update_tip()
        self._schedule_save()

    def _test_cloud(self):
        self.cloud_result.configure(text="Проверяю…", text_color="gray60")

        def done(ok: bool, msg: str):
            self.cloud_result.configure(text=msg, text_color="#3ecf8e" if ok else "#ff4d5e")

        self.app.test_cloud(lambda ok, msg: self.app.ui(lambda: done(ok, msg)))

    def _clear_history(self):
        self.app.history.clear()
        self.refresh_history()

    @staticmethod
    def _open_dir(path):
        path.mkdir(parents=True, exist_ok=True)
        os.startfile(path)

    @staticmethod
    def _fmt_secs(sec: int) -> str:
        return f"{sec // 60}:{sec % 60:02d}" if sec >= 60 else f"{sec} с"

    # ------------------------------------------------------------ внешнее API
    def refresh_history(self):
        box = self.history_box
        box.configure(state="normal")
        box.delete("1.0", "end")
        if not self.app.history:
            box.insert("end", "Пока пусто. Продиктуйте что-нибудь!")
        for ts, text in reversed(self.app.history):
            box.insert("end", f"{time.strftime('%H:%M:%S', time.localtime(ts))}\n{text.strip()}\n\n")
        box.configure(state="disabled")

    def update_tip(self):
        if not hasattr(self, "tip_label"):
            return
        hold, toggle = self.s.hotkey_hold, self.s.hotkey_toggle
        where = ("туда, куда указывает мышь" if self.s.insert_target == "mouse"
                 else "в активное поле ввода")
        lines = []
        if hold:
            lines.append(f"🎙  Зажмите  {pretty(hold)}  и говорите — отпустите, и текст появится {where}.")
        if toggle:
            lines.append(f"⏯  Или нажмите  {pretty(toggle)}  один раз для начала и ещё раз для окончания.")
        if self.s.hotkey_cancel:
            lines.append(f"✕  {pretty(self.s.hotkey_cancel)} — отменить запись.")
        if not lines:
            lines.append("Горячие клавиши не заданы — назначьте их в разделе «Горячие клавиши».")
        self.tip_label.configure(text="\n".join(lines))

    def set_status(self, state: str, text: str):
        self.status_label.configure(text=f"● {text}", text_color=STATUS_COLORS.get(state, "gray60"))
        recording = state == "recording"
        self.record_btn.configure(text="■ Остановить и вставить" if recording else "● Начать запись")

    def show(self):
        self.root.deiconify()
        self.root.lift()
        self.root.attributes("-topmost", True)
        self.root.after(200, lambda: self.root.attributes("-topmost", False))
        self.root.focus_force()

    def hide(self):
        if self._mic_test:
            self._toggle_mic_test()
        if self._capture_btn is not None:
            self._capture_hotkey(self._capture_btn._vt_attr, self._capture_btn)
        if self._save_job:
            self.root.after_cancel(self._save_job)
            self._save()
        self.root.withdraw()
        self.app.on_settings_hidden()
