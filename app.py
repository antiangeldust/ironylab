"""Tkinter desktop interface for IronyLab: analysis, batch mode and settings.

Внешний вид собран из «карточек» на светлой теме. Шрифт — Inter (если он есть
в системе), навигация — сегментированный переключатель, балл показывается
круговым индикатором. Все цвета и размеры берутся из палитры ниже.
"""

from __future__ import annotations

import json
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter import font as tkfont

from ironylab import Engine, FullResult, Settings, export_csv, load_settings, load_texts, save_settings
from ironylab.engine import COMPONENT_NAMES
from ironylab.settings import CSV_DELIMITERS, CSV_ENCODINGS, DEVICES, config_path

APP_NAME = "IronyLab"
APP_TAGLINE = "объяснимая оценка иронического потенциала — не детектор истины"
APP_VERSION = "1.2"

# --------------------------------------------------------------------- палитра
BG = "#f4f5f7"          # фон окна
CARD = "#ffffff"        # карточки и поля ввода
BORDER = "#e4e7ec"      # рамки
TEXT = "#101828"        # основной текст
TEXT_SOFT = "#475467"
MUTED = "#667085"       # пояснения
ACCENT = "#4f46e5"      # акцент
ACCENT_HOVER = "#6366f1"
ACCENT_DARK = "#312e81"
ACCENT_SOFT = "#eef2ff"
SUCCESS = "#15803d"
WARN = "#b45309"
DANGER = "#b91c1c"
TRACK = "#eaecf0"       # жёлоб индикаторов
SEG_BG = "#eceef3"      # фон сегментированного переключателя

FONT_STACK = ("Inter", "Manrope", "Segoe UI Variable Text", "Segoe UI",
              "Noto Sans", "Roboto", "DejaVu Sans")
MONO_STACK = ("Cascadia Mono", "Consolas", "JetBrains Mono", "Courier New")

LEVEL_COLORS = {
    "низкий": SUCCESS, "умеренный": "#a16207", "повышенный": "#c2410c",
    "высокий": DANGER, "нет текста": MUTED,
}
LEVEL_BG = {
    "низкий": "#dcfce7", "умеренный": "#fef3c7", "повышенный": "#ffedd5",
    "высокий": "#fee2e2", "нет текста": "#f2f4f7",
}


def pick_family(root: tk.Misc, candidates: tuple[str, ...]) -> str:
    available = set(tkfont.families(root))
    for name in candidates:
        if name in available:
            return name
    return tkfont.nametofont("TkDefaultFont").cget("family")


class NavTabs(tk.Frame):
    """Переключатель разделов: горизонтальные «таблетки» или вертикальный список."""

    def __init__(self, master, fonts: dict, command=None, orientation: str = "horizontal") -> None:
        super().__init__(master, bg=BG if orientation == "horizontal" else CARD)
        self.orientation = orientation
        self.command = command
        self.fonts = fonts
        self._items: list[tk.Label] = []
        self._pages: list[tk.Frame] = []
        self._current = -1

        self.stack = ttk.Frame(self, style="Plain.TFrame")
        if orientation == "horizontal":
            self.strip = tk.Frame(self, bg=SEG_BG, padx=3, pady=3)
            self.strip.pack(fill="x")
            self.stack.pack(fill="both", expand=True, pady=(12, 0))
        else:
            self.strip = tk.Frame(self, bg=CARD, padx=10, pady=10)
            self.strip.pack(side="left", fill="y")
            self.stack.pack(side="left", fill="both", expand=True, padx=(16, 0))

    def add(self, page: tk.Frame, text: str) -> int:
        index = len(self._pages)
        self._pages.append(page)
        horizontal = self.orientation == "horizontal"
        label = tk.Label(self.strip, text=text, bg=self.strip["bg"], fg=MUTED,
                         font=self.fonts["tab"], cursor="hand2",
                         padx=18 if horizontal else 14, pady=7 if horizontal else 9,
                         anchor="center" if horizontal else "w",
                         justify="center" if horizontal else "left")
        label.pack(side="left" if horizontal else "top",
                   fill="none" if horizontal else "x", pady=0 if horizontal else 1)
        label.bind("<Button-1>", lambda _e, i=index: self.select(i))
        label.bind("<Enter>", lambda _e, i=index: self._hover(i, True))
        label.bind("<Leave>", lambda _e, i=index: self._hover(i, False))
        self._items.append(label)
        return index

    def select(self, index: int) -> None:
        if not self._pages or index == self._current:
            return
        for position, page in enumerate(self._pages):
            if position == index:
                page.pack(fill="both", expand=True)
            else:
                page.pack_forget()
        self._current = index
        self._paint()
        if self.command:
            self.command(index)

    def _hover(self, index: int, inside: bool) -> None:
        if index == self._current:
            return
        self._items[index].configure(bg=ACCENT_SOFT if inside else self.strip["bg"],
                                     fg=ACCENT_DARK if inside else MUTED)

    def set_fonts(self, fonts: dict) -> None:
        self.fonts = fonts
        self._paint()

    def _paint(self) -> None:
        for position, label in enumerate(self._items):
            active = position == self._current
            if self.orientation == "horizontal":
                label.configure(bg=CARD if active else self.strip["bg"],
                                fg=ACCENT_DARK if active else MUTED,
                                font=self.fonts["tab_active"] if active else self.fonts["tab"],
                                highlightthickness=1 if active else 0,
                                highlightbackground=BORDER, highlightcolor=BORDER)
            else:
                label.configure(bg=ACCENT_SOFT if active else self.strip["bg"],
                                fg=ACCENT_DARK if active else TEXT_SOFT,
                                font=self.fonts["tab_active"] if active else self.fonts["tab"])


class ScoreGauge(tk.Canvas):
    """Круговой индикатор балла 0–100."""

    def __init__(self, master, fonts: dict, size: int = 124, thickness: int = 13) -> None:
        super().__init__(master, width=size, height=size, bg=CARD, highlightthickness=0, bd=0)
        pad = thickness / 2 + 3
        box = (pad, pad, size - pad, size - pad)
        self.create_arc(*box, start=90, extent=359.9, style="arc", outline=TRACK, width=thickness)
        self._arc = self.create_arc(*box, start=90, extent=0, style="arc", outline=ACCENT, width=thickness)
        self._number = self.create_text(size / 2, size / 2 - 6, text="—", fill=MUTED, font=fonts["score"])
        self._caption = self.create_text(size / 2, size / 2 + 24, text="из 100", fill=MUTED, font=fonts["hint"])

    def set_value(self, score: int, color: str) -> None:
        value = max(0, min(100, score))
        self.itemconfigure(self._arc, extent=-359.9 * value / 100, outline=color)
        self.itemconfigure(self._number, text=str(score), fill=color)

    def set_fonts(self, fonts: dict) -> None:
        self.itemconfigure(self._number, font=fonts["score"])
        self.itemconfigure(self._caption, font=fonts["hint"])


class App(tk.Tk):
    def __init__(self) -> None:
        self.family = ""          # заполняется до создания окна
        self.mono = ""
        super().__init__()
        self.title(f"{APP_NAME} — анализ иронического потенциала")
        self.geometry("1100x920")
        self.minsize(900, 660)
        self.configure(background=BG)
        self.settings = load_settings()
        self.engine = Engine(self.settings)
        self.last_result: FullResult | None = None
        self.batch_results: list[FullResult] = []
        self.batch_source_rows: list[dict] = []
        self._events: queue.Queue = queue.Queue()
        self._busy = False
        self._cancel = threading.Event()
        self._action_buttons: list[ttk.Button] = []
        self._sort: tuple[str, bool] | None = None
        self._font_widgets: list[tuple[tk.Misc, str]] = []
        self.family = pick_family(self, FONT_STACK)
        self.mono = pick_family(self, MONO_STACK)
        self.fonts = self._make_fonts()
        self._init_style()
        self._build()
        self.after(100, self._poll)

    # ------------------------------------------------------------------ шрифты
    def font(self, delta: int = 0, weight: str = "normal", slant: str = "roman",
             mono: bool = False) -> tuple:
        family = self.mono if mono else self.family
        return (family, max(7, self.settings.font_size + delta), weight, slant)

    def _make_fonts(self) -> dict[str, tuple]:
        return {
            "h1": self.font(10, "bold"),
            "h2": self.font(1, "bold"),
            "body": self.font(),
            "small": self.font(-1),
            "hint": self.font(-2 if self.settings.font_size <= 12 else -1),
            "score": self.font(22, "bold"),
            "tab": self.font(-1, "bold"),
            "tab_active": self.font(-1, "bold"),
            "chip": self.font(-1, "bold"),
            "mono": self.font(-1, mono=True),
        }

    def _fonted(self, widget: tk.Misc, key: str) -> tk.Misc:
        """Запомнить виджет, чтобы при смене размера шрифта обновить и его."""
        widget.configure(font=self.fonts[key])
        self._font_widgets.append((widget, key))
        return widget

    def _apply_font(self) -> None:
        self.fonts = self._make_fonts()
        for widget, key in self._font_widgets:
            try:
                widget.configure(font=self.fonts[key])
            except tk.TclError:
                pass
        self._init_style()
        self.tabs.set_fonts(self.fonts)
        self.settings_tabs.set_fonts(self.fonts)
        self.gauge.set_fonts(self.fonts)
        self._init_output_tags(self.output)
        self._init_output_tags(self.batch_detail)
        if self.last_result is not None:
            self.show_result(self.last_result)

    # ------------------------------------------------------------------ стили
    def _init_style(self) -> None:
        base = self.settings.font_size
        for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont"):
            tkfont.nametofont(name).configure(family=self.family, size=base)
        style = ttk.Style(self)
        style.theme_use("clam")  # единственная тема, которую можно красить одинаково везде

        style.configure(".", background=BG, foreground=TEXT, font=self.fonts["body"],
                        bordercolor=BORDER, focuscolor=ACCENT)
        style.configure("TFrame", background=BG)
        style.configure("Card.TFrame", background=CARD, relief="solid", borderwidth=1)
        style.configure("Plain.TFrame", background=CARD)
        style.configure("TLabel", background=BG, foreground=TEXT)
        style.configure("Card.TLabel", background=CARD, foreground=TEXT)
        style.configure("CardMuted.TLabel", background=CARD, foreground=MUTED, font=self.fonts["small"])
        style.configure("Section.TLabel", background=CARD, foreground=TEXT, font=self.fonts["h2"])
        style.configure("Hint.TLabel", background=CARD, foreground=MUTED, font=self.fonts["hint"])
        style.configure("Status.TLabel", background=CARD, foreground=MUTED,
                        font=self.fonts["small"], padding=(4, 6))

        # --- кнопки ---------------------------------------------------------
        style.configure("TButton", background=CARD, foreground=TEXT, bordercolor=BORDER,
                        focuscolor=ACCENT_SOFT, relief="flat", padding=(14, 7), font=self.fonts["small"])
        style.map("TButton",
                  background=[("pressed", "#e9ebf0"), ("active", ACCENT_SOFT), ("disabled", "#f7f8fa")],
                  foreground=[("disabled", "#98a2b3")],
                  bordercolor=[("active", ACCENT)], relief=[("pressed", "flat")])
        style.configure("Accent.TButton", background=ACCENT, foreground="#ffffff",
                        bordercolor=ACCENT, font=self.fonts["h2"], padding=(20, 8))
        style.map("Accent.TButton",
                  background=[("pressed", ACCENT_DARK), ("active", ACCENT_HOVER), ("disabled", "#a5b4fc")],
                  foreground=[("disabled", "#eef2ff")], bordercolor=[("active", ACCENT_DARK)])

        # --- поля ввода и таблицы -------------------------------------------
        style.configure("TEntry", fieldbackground=CARD, bordercolor=BORDER, lightcolor=BORDER,
                        darkcolor=BORDER, insertcolor=TEXT, padding=5)
        style.map("TEntry", bordercolor=[("focus", ACCENT)])
        style.configure("TSpinbox", fieldbackground=CARD, bordercolor=BORDER, arrowcolor=MUTED,
                        insertcolor=TEXT, padding=4)
        style.map("TSpinbox", bordercolor=[("focus", ACCENT)])
        style.configure("TCombobox", fieldbackground=CARD, background=CARD, bordercolor=BORDER,
                        arrowcolor=MUTED, padding=4)
        style.map("TCombobox", fieldbackground=[("readonly", CARD)], bordercolor=[("focus", ACCENT)])
        self.option_add("*TCombobox*Listbox.background", CARD)
        self.option_add("*TCombobox*Listbox.foreground", TEXT)
        self.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
        self.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")

        style.configure("TCheckbutton", background=CARD, foreground=TEXT, focuscolor=CARD,
                        font=self.fonts["body"])
        style.map("TCheckbutton", background=[("active", CARD)], foreground=[("active", ACCENT_DARK)])

        style.configure("Treeview", background=CARD, fieldbackground=CARD, foreground=TEXT,
                        bordercolor=BORDER, borderwidth=0, rowheight=max(28, base + 16),
                        font=self.fonts["small"])
        style.map("Treeview", background=[("selected", ACCENT_SOFT)], foreground=[("selected", ACCENT_DARK)])
        style.configure("Treeview.Heading", background=BG, foreground=MUTED, relief="flat",
                        font=self.fonts["tab"], padding=(8, 7))
        style.map("Treeview.Heading", background=[("active", ACCENT_SOFT)], foreground=[("active", ACCENT_DARK)])

        style.configure("Horizontal.TProgressbar", background=ACCENT, troughcolor=TRACK,
                        bordercolor=TRACK, lightcolor=ACCENT, darkcolor=ACCENT, thickness=8)
        style.configure("Busy.Horizontal.TProgressbar", background=ACCENT, troughcolor=CARD,
                        bordercolor=CARD, lightcolor=ACCENT, darkcolor=ACCENT, thickness=6)
        style.configure("TScrollbar", background=BG, troughcolor=BG, bordercolor=BG,
                        arrowcolor=MUTED, relief="flat")
        style.map("TScrollbar", background=[("active", "#d0d5dd")])
        style.configure("TSeparator", background=BORDER)

    # ------------------------------------------------------------------ разметка
    def _build(self) -> None:
        footer = ttk.Frame(self, style="Card.TFrame")
        footer.pack(fill="x", side="bottom")
        inner = ttk.Frame(footer, style="Plain.TFrame", padding=(16, 2))
        inner.pack(fill="x")
        self.busy = ttk.Progressbar(inner, mode="indeterminate", length=140,
                                    style="Busy.Horizontal.TProgressbar")
        self.status = tk.StringVar()
        ttk.Label(inner, textvariable=self.status, style="Status.TLabel").pack(side="left", fill="x", expand=True)

        outer = ttk.Frame(self, padding=(18, 16, 18, 12))
        outer.pack(fill="both", expand=True)
        self._build_header(outer)

        self.tabs = NavTabs(outer, self.fonts, orientation="horizontal", command=self._on_tab_changed)
        self.tabs.pack(fill="both", expand=True)
        self.tab_single = ttk.Frame(self.tabs.stack)
        self.tab_batch = ttk.Frame(self.tabs.stack)
        self.tab_settings = ttk.Frame(self.tabs.stack, style="Card.TFrame")
        self.tabs.add(self.tab_single, "Анализ")
        self.tabs.add(self.tab_batch, "Пакетный анализ")
        self.tabs.add(self.tab_settings, "Настройки")
        self._build_single()
        self._build_batch()
        self._build_settings()
        self.tabs.select(0)
        self._refresh_status()
        self.bind("<Control-Return>", lambda _e: self.run_analysis())
        self.bind("<Escape>", lambda _e: self._cancel.set())

    def _build_header(self, parent) -> None:
        head = ttk.Frame(parent)
        head.pack(fill="x", pady=(0, 12))
        left = ttk.Frame(head)
        left.pack(side="left")
        title = ttk.Frame(left)
        title.pack(anchor="w")
        ttk.Label(title, text=APP_NAME, font=self.fonts["h1"]).pack(side="left")
        pilot = tk.Label(title, text="0–100", bg=ACCENT_SOFT, fg=ACCENT_DARK,
                         font=self.fonts["chip"], padx=10, pady=3)
        self._fonted(pilot, "chip")
        pilot.pack(side="left", padx=(10, 0), pady=(6, 0))
        ttk.Label(left, text=APP_TAGLINE, background=BG, foreground=MUTED,
                  font=self.fonts["small"]).pack(anchor="w", pady=(3, 0))
        self.methods_chip = tk.Label(head, text="методы: —", bg=ACCENT_SOFT, fg=ACCENT_DARK,
                                     font=self.fonts["chip"], padx=12, pady=6)
        self._fonted(self.methods_chip, "chip")
        self.methods_chip.pack(side="right", pady=(8, 0))

    def _card(self, parent, title: str = "", hint: str = "", pady=(0, 10)) -> ttk.Frame:
        card = ttk.Frame(parent, style="Card.TFrame", padding=16)
        card.pack(fill="x", pady=pady)
        if title:
            ttk.Label(card, text=title, style="Card.TLabel", font=self.fonts["h2"]).pack(anchor="w")
        if hint:
            ttk.Label(card, text=hint, style="Hint.TLabel", wraplength=900,
                      justify="left").pack(anchor="w", pady=(3, 10))
        elif title:
            ttk.Frame(card, height=10, style="Plain.TFrame").pack()
        return card

    def _on_tab_changed(self, index: int) -> None:
        self._refresh_status()

    # ---------------------------------------------------------------- вкладка «Анализ»
    def _build_single(self) -> None:
        f = self.tab_single
        card = self._card(f, "Текст для анализа",
                          "Вставьте фразу или откройте .txt. Ctrl+Enter — анализ.")
        self.input = tk.Text(card, height=5, wrap="word", undo=True, relief="flat",
                             background=CARD, foreground=TEXT, insertbackground=ACCENT,
                             selectbackground=ACCENT_SOFT, selectforeground=ACCENT_DARK,
                             highlightthickness=1, highlightbackground=BORDER, highlightcolor=ACCENT,
                             padx=12, pady=10, spacing1=2, spacing3=3)
        self._fonted(self.input, "body")
        self.input.pack(fill="x")
        self.input.insert("1.0", "Ну да, конечно, прекрасная погода — опять ливень 🙃")

        bar = ttk.Frame(f)
        bar.pack(fill="x", pady=(0, 12))
        self._button(bar, "Открыть TXT", self.open_file, side="left")
        self._button(bar, "Очистить", self.clear_input, busy_locked=False, side="left", padx=(8, 0))
        self.analyze_btn = self._button(bar, "Анализировать", self.run_analysis,
                                        side="right", style="Accent.TButton")
        self._button(bar, "Сохранить JSON", self.save_json, side="right", padx=(0, 8))
        self._button(bar, "Экспорт CSV", self.export_single_csv, side="right", padx=(0, 8))

        design = ttk.Frame(f)
        design.pack(fill="both", expand=True)
        score_card = ttk.Frame(design, style="Card.TFrame", padding=(20, 16))
        score_card.pack(fill="x")
        self.gauge = ScoreGauge(score_card, self.fonts)
        self.gauge.pack(side="left")
        info = ttk.Frame(score_card, style="Plain.TFrame")
        info.pack(side="left", fill="both", expand=True, padx=(22, 0), pady=(8, 0))
        top = ttk.Frame(info, style="Plain.TFrame")
        top.pack(fill="x")
        self.score_var = tk.StringVar(value="нет данных")
        self.level_chip = tk.Label(top, text="нет данных", bg=LEVEL_BG["нет текста"], fg=MUTED,
                                   font=self.fonts["chip"], padx=14, pady=6)
        self._fonted(self.level_chip, "chip")
        self.level_chip.pack(side="left")
        self.summary_var = tk.StringVar(
            value="Введите текст и нажмите «Анализировать» — здесь появится уровень и вклад методов.")
        summary = tk.Label(top, textvariable=self.summary_var, bg=CARD, fg=MUTED, font=self.fonts["small"],
                           justify="left", wraplength=560)
        self._fonted(summary, "small")
        summary.pack(side="left", padx=14)
        self.parts_var = tk.StringVar(value="")
        parts = tk.Label(info, textvariable=self.parts_var, bg=CARD, fg=TEXT_SOFT, font=self.fonts["small"],
                         justify="left", wraplength=640, anchor="w")
        self._fonted(parts, "small")
        parts.pack(fill="x", pady=(16, 0))

        out_card = ttk.Frame(design, style="Card.TFrame", padding=6)
        out_card.pack(fill="both", expand=True, pady=(12, 0))
        box = ttk.Frame(out_card, style="Plain.TFrame")
        box.pack(fill="both", expand=True)
        self.output = tk.Text(box, wrap="word", state="disabled", relief="flat", background=CARD,
                              foreground=TEXT, selectbackground=ACCENT_SOFT, selectforeground=ACCENT_DARK,
                              highlightthickness=0, padx=14, pady=12, spacing1=2, spacing3=3)
        self._fonted(self.output, "body")
        sb = ttk.Scrollbar(box, command=self.output.yview)
        self.output.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.output.pack(side="left", fill="both", expand=True)
        self._init_output_tags(self.output)
        self._set_text(self.output, "Результат появится здесь: найденные маркеры, семантика и мнение локальной модели.")

    def _init_output_tags(self, widget: tk.Text) -> None:
        widget.tag_configure("h", font=self.fonts["h2"], foreground=ACCENT_DARK, spacing1=14, spacing3=6)
        widget.tag_configure("bullet", lmargin1=8, lmargin2=26)
        widget.tag_configure("muted", foreground=MUTED, font=self.fonts["small"])
        widget.tag_configure("warn", foreground=WARN, lmargin1=8, lmargin2=26)
        widget.tag_configure("strong", font=self.fonts["h2"])
        widget.tag_configure("level", foreground=ACCENT, font=self.fonts["h2"])
        widget.configure(font=self.fonts["body"])

    def _button(self, parent, text, command, busy_locked=True, style="TButton", **pack) -> ttk.Button:
        b = ttk.Button(parent, text=text, command=command, style=style)
        b.pack(**pack)
        if busy_locked:
            self._action_buttons.append(b)
        return b

    def clear_input(self) -> None:
        self.input.delete("1.0", "end")
        self.input.focus_set()

    # ---------------------------------------------------------------- вкладка «Пакет»
    def _build_batch(self) -> None:
        f = self.tab_batch
        card = self._card(f, "Пакетная обработка файла",
                          "CSV/TSV: текст берётся из столбца, указанного в «Настройки → Экспорт» (по умолчанию text). "
                          "TXT: каждая непустая строка — отдельный текст. Щёлкните по заголовку столбца, чтобы отсортировать.")
        bar = ttk.Frame(card, style="Plain.TFrame")
        bar.pack(fill="x")
        self.batch_run_btn = self._button(bar, "Анализировать всё", self.run_batch,
                                          side="right", style="Accent.TButton")
        self.stop_btn = ttk.Button(bar, text="Остановить", command=self._cancel.set, state="disabled")
        self.stop_btn.pack(side="right", padx=(0, 10))
        self._button(bar, "Экспорт CSV", self.export_batch_csv, side="right", padx=(0, 8))
        self._button(bar, "Очистить", self.clear_batch, side="right", padx=(0, 8))
        self._button(bar, "Открыть CSV / TXT", self.load_batch, side="left")

        table_card = ttk.Frame(f, style="Card.TFrame", padding=6)
        table_card.pack(fill="both", expand=True)
        self.cols = ("n", "text", "score", "level", "heur", "sem", "llm")
        self.heads = {"n": "№", "text": "Текст", "score": "Итог", "level": "Уровень",
                      "heur": "Эвристика", "sem": "Семантика", "llm": "LLM"}
        widths = {"n": 46, "text": 360, "score": 62, "level": 108, "heur": 96, "sem": 96, "llm": 60}
        box = ttk.Frame(table_card, style="Plain.TFrame")
        box.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(box, columns=self.cols, show="headings", selectmode="browse")
        for c in self.cols:
            self.tree.heading(c, text=self.heads[c], anchor="w" if c == "text" else "center",
                              command=lambda c=c: self._sort_by(c))
            self.tree.column(c, width=widths[c], anchor="w" if c == "text" else "center", stretch=(c == "text"))
        sb = ttk.Scrollbar(box, command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)
        for level, color in LEVEL_COLORS.items():
            self.tree.tag_configure(level, foreground=color)
        self.tree.tag_configure("odd", background="#fafbfc")
        self.tree.tag_configure("even", background=CARD)
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)

        self.batch_progress = ttk.Progressbar(f, maximum=100)
        self.batch_progress.pack(fill="x", pady=(12, 6))
        self.batch_info = tk.StringVar(value="Файл не загружен")
        ttk.Label(f, textvariable=self.batch_info, background=BG, foreground=MUTED,
                  font=self.fonts["small"]).pack(anchor="w")
        detail_card = self._card(f, "Подробности выбранной строки", pady=(12, 0))
        self.batch_detail = tk.Text(detail_card, height=5, wrap="word", state="disabled", relief="flat",
                                    background=CARD, foreground=TEXT, highlightthickness=1,
                                    highlightbackground=BORDER, padx=12, pady=10,
                                    selectbackground=ACCENT_SOFT)
        self._fonted(self.batch_detail, "small")
        self.batch_detail.pack(fill="x")
        self._init_output_tags(self.batch_detail)

    # -------------------------------------------------------------- вкладка «Настройки»
    def _build_settings(self) -> None:
        self.vars: dict[str, tk.Variable] = {}
        f = self.tab_settings
        self.settings_tabs = NavTabs(f, self.fonts, orientation="vertical")
        self.settings_tabs.pack(fill="both", expand=True, padx=8, pady=8)
        pages = {}
        for name in ("Оценка", "Семантика", "Локальная LLM", "Экспорт", "Интерфейс"):
            page = ttk.Frame(self.settings_tabs.stack, style="Card.TFrame")
            page.columnconfigure(1, weight=1)
            self.settings_tabs.add(page, name)
            pages[name] = page

        p = pages["Оценка"]
        self._section(p, "Какие методы участвуют в итоговом балле",
                      "Эвристика всегда показывает маркеры; галочка решает, входит ли её балл в итог.")
        self._check(p, "use_heuristic", "Эвристика (словари, пунктуация, эмодзи)")
        self._check(p, "use_semantic", "Семантический анализатор (эмбеддинги) — см. раздел «Семантика»")
        self._check(p, "use_llm", "Локальная LLM — см. раздел «Локальная LLM»")
        self._section(p, "Веса методов при усреднении (0–100)",
                      "Итог = взвешенное среднее только тех методов, которые успешно отработали.")
        self._spin(p, "weight_heuristic", "Вес эвристики")
        self._spin(p, "weight_semantic", "Вес семантики")
        self._spin(p, "weight_llm", "Вес LLM")
        self._section(p, "Границы уровней",
                      "«низкий» — пока балл меньше 1-го порога, «умеренный» — до 2-го, "
                      "«повышенный» — до 3-го, дальше «высокий».")
        self._spin(p, "threshold_low", "Порог «низкий → умеренный»")
        self._spin(p, "threshold_moderate", "Порог «умеренный → повышенный»")
        self._spin(p, "threshold_high", "Порог «повышенный → высокий»")
        self._spin(p, "max_chars", "Макс. длина текста для семантики/LLM, символов", 100, 20000, 100)

        p = pages["Семантика"]
        self._section(p, "Модель эмбеддингов (sentence-transformers)",
                      "Нужен пакет sentence-transformers. Подойдёт любая многоязычная модель, например "
                      "paraphrase-multilingual-MiniLM-L12-v2 или LaBSE. Укажите папку со скачанной моделью "
                      "либо её имя на Hugging Face (тогда она скачается при первом запуске).")
        self._path(p, "semantic_model", "Папка / имя модели", folder=True)
        self._combo(p, "semantic_device", "Устройство", DEVICES)
        self.sem_test_lbl = self._test_row(p, "Проверить модель", self.test_semantic)

        p = pages["Локальная LLM"]
        self._section(p, "Модель",
                      "Файл .gguf запускается через llama-cpp-python, папка Hugging Face — через transformers. "
                      "Модель работает полностью локально, первая загрузка занимает время. "
                      "Ответ — класс A–D по примерам-якорям, балл считается в коде; при нескольких прогонах "
                      "берётся среднее, поэтому оценка получается дробнее (температура тогда не ниже 0,4). "
                      "Инструкция по установке — INSTALL_RU.md.")
        self._path(p, "llm_model_path", "Путь к модели", folder=True,
                   filetypes=[("GGUF-модель", "*.gguf"), ("Все файлы", "*.*")])
        self._spin(p, "llm_n_ctx", "Контекст (n_ctx), токенов", 256, 131072, 256)
        self._spin(p, "llm_n_threads", "Потоки CPU (0 = авто)", 0, 256)
        self._spin(p, "llm_n_gpu_layers", "Слоёв на GPU (0 = только CPU, -1 = все)", -1, 1000)
        self._spin(p, "llm_temperature", "Температура", 0.0, 2.0, 0.05, is_float=True)
        self._spin(p, "llm_max_tokens", "Макс. токенов ответа", 16, 4096, 16)
        self._spin(p, "llm_samples", "Прогонов на текст (1 — быстрее, 3 — дробнее)", 1, 7)
        ttk.Label(p, text="Своя инструкция (пусто = встроенная). Ответ — JSON с полем class (A/B/C/D) "
                          "или, если так удобнее, с числом score:",
                  style="Hint.TLabel").grid(column=0, columnspan=3, sticky="w", pady=(14, 5), padx=14)
        self.prompt_text = tk.Text(p, height=5, wrap="word", relief="flat", background=CARD, foreground=TEXT,
                                   insertbackground=ACCENT, highlightthickness=1, highlightbackground=BORDER,
                                   highlightcolor=ACCENT, padx=12, pady=10)
        self._fonted(self.prompt_text, "body")
        self.prompt_text.grid(column=0, columnspan=3, sticky="nsew", padx=14)
        self.prompt_text.insert("1.0", self.settings.llm_system_prompt)
        self.llm_test_lbl = self._test_row(p, "Проверить модель", self.test_llm)

        p = pages["Экспорт"]
        self._section(p, "CSV", "Русский Excel открывает CSV с разделителем «;» корректно, англоязычный — с «,».")
        self._combo(p, "csv_delimiter", "Разделитель", list(CSV_DELIMITERS), display=CSV_DELIMITERS)
        self._combo(p, "csv_encoding", "Кодировка", CSV_ENCODINGS)
        self._check(p, "csv_include_sentences", "Добавить столбец с оценкой каждого предложения")
        self._entry(p, "csv_text_column", "Столбец с текстом при импорте CSV")

        p = pages["Интерфейс"]
        self._section(p, "Внешний вид",
                      f"Шрифт интерфейса: {self.family}. Размер применяется сразу после сохранения настроек.")
        self._spin(p, "font_size", "Размер шрифта")
        ttk.Label(p, text=f"Файл настроек: {config_path()}", style="Hint.TLabel",
                  wraplength=820).grid(column=0, columnspan=4, sticky="w", pady=(18, 0), padx=14)

        bar = ttk.Frame(f, style="Plain.TFrame", padding=(10, 12, 10, 6))
        bar.pack(fill="x")
        ttk.Button(bar, text="Сохранить настройки", command=self.apply_settings,
                   style="Accent.TButton").pack(side="left")
        ttk.Button(bar, text="Сбросить к умолчанию", command=self.reset_settings).pack(side="left", padx=10)
        self.settings_msg = tk.StringVar()
        message = tk.Label(bar, textvariable=self.settings_msg, bg=CARD, fg=SUCCESS, font=self.fonts["small"])
        self._fonted(message, "small")
        message.pack(side="left", padx=12)
        self.settings_tabs.select(0)
        self._load_vars()

    # ------------------------------------------------------ помощники настроек
    def _row(self, parent) -> int:
        return parent.grid_size()[1]

    def _section(self, parent, title: str, hint: str = "") -> None:
        r = self._row(parent)
        ttk.Label(parent, text=title, style="Section.TLabel").grid(
            row=r, column=0, columnspan=4, sticky="w", pady=(18 if r else 6, 3), padx=14)
        if hint:
            ttk.Label(parent, text=hint, style="Hint.TLabel", wraplength=880,
                      justify="left").grid(row=r + 1, column=0, columnspan=4, sticky="w",
                                           pady=(0, 8), padx=14)
        ttk.Separator(parent, orient="horizontal").grid(row=r + (2 if hint else 1), column=0, columnspan=4,
                                                        sticky="ew", pady=(4, 10), padx=14)

    def _var(self, name: str, kind) -> tk.Variable:
        v = kind()
        self.vars[name] = v
        return v

    def _check(self, parent, name, label) -> None:
        ttk.Checkbutton(parent, text=label, variable=self._var(name, tk.BooleanVar)).grid(
            row=self._row(parent), column=0, columnspan=4, sticky="w", pady=3, padx=14)

    def _spin(self, parent, name, label, lo=None, hi=None, step=1, is_float=False) -> None:
        lo, hi = (lo, hi) if lo is not None else Settings.RANGES[name]
        r = self._row(parent)
        ttk.Label(parent, text=label, style="Card.TLabel").grid(row=r, column=0, sticky="w",
                                                                pady=4, padx=(14, 14))
        var = self._var(name, tk.DoubleVar if is_float else tk.IntVar)
        ttk.Spinbox(parent, from_=lo, to=hi, increment=step, textvariable=var, width=10).grid(
            row=r, column=1, sticky="w", pady=4)

    def _entry(self, parent, name, label) -> None:
        r = self._row(parent)
        ttk.Label(parent, text=label, style="Card.TLabel").grid(row=r, column=0, sticky="w",
                                                                pady=4, padx=(14, 14))
        ttk.Entry(parent, textvariable=self._var(name, tk.StringVar), width=26).grid(
            row=r, column=1, sticky="w", pady=4)

    def _combo(self, parent, name, label, values, display: dict | None = None) -> None:
        r = self._row(parent)
        ttk.Label(parent, text=label, style="Card.TLabel").grid(row=r, column=0, sticky="w",
                                                                pady=4, padx=(14, 14))
        var = self._var(name, tk.StringVar)
        shown = [display[v] for v in values] if display else list(values)
        box = ttk.Combobox(parent, values=shown, state="readonly", width=42 if display else 16)
        box.grid(row=r, column=1, sticky="w", pady=4)
        lookup = dict(zip(shown, values))
        # значение переменной — настоящее (например ";"), а в списке показывается подпись
        box.bind("<<ComboboxSelected>>", lambda _e: var.set(lookup[box.get()]))
        var.trace_add("write", lambda *_: box.set(dict(zip(values, shown)).get(var.get(), var.get())))

    def _path(self, parent, name, label, folder=False, filetypes=None) -> None:
        r = self._row(parent)
        ttk.Label(parent, text=label, style="Card.TLabel").grid(row=r, column=0, sticky="w",
                                                                pady=4, padx=(14, 14))
        var = self._var(name, tk.StringVar)
        ttk.Entry(parent, textvariable=var, font=self.fonts["mono"]).grid(
            row=r, column=1, sticky="ew", pady=4, padx=(0, 8))
        cell = ttk.Frame(parent, style="Plain.TFrame")
        cell.grid(row=r, column=2, padx=(0, 14))
        if filetypes:
            ttk.Button(cell, text="Файл…", command=lambda: var.set(filedialog.askopenfilename(filetypes=filetypes) or var.get())).pack(side="left")
        if folder:
            ttk.Button(cell, text="Папка…", command=lambda: var.set(filedialog.askdirectory() or var.get())).pack(side="left", padx=(4, 0))

    def _test_row(self, parent, text, command) -> tk.StringVar:
        r = self._row(parent)
        msg = tk.StringVar()
        cell = ttk.Frame(parent, style="Plain.TFrame")
        cell.grid(row=r, column=0, columnspan=4, sticky="w", pady=(16, 10), padx=14)
        btn = ttk.Button(cell, text=text, command=command)
        btn.pack(side="left")
        self._action_buttons.append(btn)
        label = tk.Label(cell, textvariable=msg, bg=CARD, fg=MUTED, font=self.fonts["small"],
                         justify="left", wraplength=700)
        self._fonted(label, "small")
        label.pack(side="left", padx=12)
        return msg

    def _load_vars(self) -> None:
        for name, var in self.vars.items():
            var.set(getattr(self.settings, name))
        self.prompt_text.delete("1.0", "end")
        self.prompt_text.insert("1.0", self.settings.llm_system_prompt)

    def _read_vars(self) -> Settings:
        data = {}
        for name, var in self.vars.items():
            try:
                data[name] = var.get()
            except tk.TclError:
                raise ValueError(f"Некорректное значение в поле «{name}»")
        data["llm_system_prompt"] = self.prompt_text.get("1.0", "end").strip()
        return Settings.from_dict(data)

    def apply_settings(self, quiet: bool = False) -> bool:
        try:
            new = self._read_vars()
        except ValueError as exc:
            messagebox.showerror("Настройки", str(exc))
            return False
        self.settings = new
        self.engine.update_settings(new)
        try:
            save_settings(new)
        except OSError as exc:
            messagebox.showerror("Не удалось сохранить настройки", str(exc))
            return False
        self._load_vars()  # показать значения после проверки/ограничения
        self._apply_font()
        self._refresh_status()
        if not quiet:
            self.settings_msg.set("✓ Сохранено")
            self.after(2500, lambda: self.settings_msg.set(""))
        return True

    def reset_settings(self) -> None:
        if messagebox.askyesno("Настройки", "Сбросить все настройки к значениям по умолчанию?"):
            self.settings = Settings()
            self._load_vars()
            self.apply_settings()

    def _refresh_status(self) -> None:
        s = self.settings
        parts = [name for flag, name in ((s.use_heuristic, "эвристика"), (s.use_semantic, "семантика"),
                                         (s.use_llm, "LLM")) if flag]
        active = ", ".join(parts) or "нет (будет использована эвристика)"
        self.status.set(f"Активные методы: {active}   ·   {APP_NAME} {APP_VERSION}   ·   "
                        f"Ctrl+Enter — анализ, Esc — остановить")
        self.methods_chip.configure(text="методы: " + (", ".join(parts) if parts else "эвристика"),
                                    bg=ACCENT_SOFT if parts else "#f2f4f7",
                                    fg=ACCENT_DARK if parts else MUTED)

    # ---------------------------------------------------------- фоновая работа
    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        state = "disabled" if busy else "normal"
        for b in self._action_buttons:
            b.configure(state=state)
        self.stop_btn.configure(state="normal" if busy and self._batch_running else "disabled")
        self.configure(cursor="watch" if busy else "")
        if busy:
            self.busy.pack(side="right", padx=(12, 0))
            self.busy.start(12)
        else:
            self.busy.stop()
            self.busy.pack_forget()

    _batch_running = False

    def _start(self, job, note: str = "") -> None:
        """Run *job(emit)* in a worker thread; emitted tuples are handled in the Tk thread by _poll."""
        if self._busy:
            return
        self._cancel.clear()
        self._set_busy(True)
        if note:
            self.status.set(note)

        def worker():
            try:
                job(lambda *event: self._events.put(event))
            except Exception as exc:  # показываем пользователю, а не роняем поток молча
                self._events.put(("error", exc))
            finally:
                self._events.put(("finished",))

        threading.Thread(target=worker, daemon=True).start()

    def _poll(self) -> None:
        try:
            while True:
                event = self._events.get_nowait()
                getattr(self, f"_on_{event[0]}")(*event[1:])
        except queue.Empty:
            pass
        self.after(100, self._poll)

    def _on_finished(self) -> None:
        self._batch_running = False
        self._set_busy(False)
        self._refresh_status()

    def _on_error(self, exc: Exception) -> None:
        messagebox.showerror("Ошибка", str(exc))

    def _on_single(self, result: FullResult) -> None:
        self.show_result(result)

    def _on_test(self, target: str, ok: bool, message: str) -> None:
        (self.sem_test_lbl if target == "semantic" else self.llm_test_lbl).set(("✔ " if ok else "✘ ") + message)

    def _on_row(self, index: int, total: int, result: FullResult) -> None:
        self.batch_results.append(result)
        self._insert_row(len(self.batch_results), result)
        self.batch_progress["value"] = 100 * index / total
        self.batch_info.set(f"Обработано {index} из {total}…")

    def _on_batch_done(self, done: int, total: int) -> None:
        self.batch_info.set(f"Готово: {done} из {total}" + (" (остановлено)" if done < total else "")
                            + ". Можно экспортировать в CSV.")

    # ---------------------------------------------------------------- «Анализ»
    def open_file(self) -> None:
        name = filedialog.askopenfilename(filetypes=[("Text", "*.txt"), ("All files", "*.*")])
        if name:
            try:
                text = Path(name).read_text(encoding="utf-8-sig")
            except (OSError, UnicodeError) as exc:
                messagebox.showerror("Не удалось открыть файл", str(exc))
                return
            self.input.delete("1.0", "end")
            self.input.insert("1.0", text)

    def run_analysis(self) -> None:
        text = self.input.get("1.0", "end").strip()
        note = "Анализ… (при первом запуске модели загрузка может занять время)"
        self._start(lambda emit: emit("single", self.engine.analyze(text)), note)

    def show_result(self, result: FullResult) -> None:
        self.last_result = result
        color = LEVEL_COLORS.get(result.level, TEXT)
        self.gauge.set_value(result.score, color)
        self.level_chip.configure(text=f"{result.level} · {result.score}/100",
                                  bg=LEVEL_BG.get(result.level, BG), fg=color)
        used = "   ·   ".join(f"{COMPONENT_NAMES[k]} {v}" for k, v in result.used.items())
        self.parts_var.set("Вклад методов:  " + used if used else "")
        self.summary_var.set("Оценка — взвешенное среднее включённых методов. Ниже пояснение по каждому."
                             if result.used else "Введите текст и нажмите «Анализировать»")

        h = result.heuristic
        out = self.output
        out.configure(state="normal")
        out.delete("1.0", "end")
        out.insert("end", "НАЙДЕННЫЕ МАРКЕРЫ\n", "h")
        if h.signals:
            for s in h.signals:
                out.insert("end", f"+{s.weight}  {s.name} — «{s.evidence}»\n", "strong")
                out.insert("end", f"      {s.explanation}\n", ("bullet", "muted"))
        else:
            out.insert("end", "Явные маркеры не найдены.\n", "muted")
        if result.semantic:
            out.insert("end", "\nСЕМАНТИКА\n", "h")
            out.insert("end", f"Балл {result.semantic.score}/100  ·  контраст тональности "
                              f"{result.semantic.contrast}/100  ·  близость к иронии "
                              f"{result.semantic.prototype}/100\n", "strong")
            out.insert("end", f"{result.semantic.explanation}\n", ("bullet", "muted"))
        if result.llm:
            out.insert("end", "\nМНЕНИЕ ЛОКАЛЬНОЙ LLM\n", "h")
            out.insert("end", f"Балл {result.llm.score}/100\n", "strong")
            out.insert("end", f"{result.llm.explanation or '(без пояснения)'}\n", ("bullet", "muted"))
        if result.warnings:
            out.insert("end", "\nПРЕДУПРЕЖДЕНИЯ\n", "h")
            for w in result.warnings:
                out.insert("end", f"⚠  {w}\n", "warn")
        out.insert("end", "\nПРЕДЛОЖЕНИЯ ПО УБЫВАНИЮ ОЦЕНКИ (эвристика)\n", "h")
        for sentence, score in h.sentences:
            out.insert("end", f"{score:>3}/100", "level")
            out.insert("end", f"   {sentence}\n", "bullet")
        out.insert("end", f"\n{h.disclaimer}\n", "muted")
        out.configure(state="disabled")

    @staticmethod
    def _set_text(widget: tk.Text, content: str) -> None:
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", content)
        widget.configure(state="disabled")

    def save_json(self) -> None:
        if self.last_result is None:
            messagebox.showinfo("Сохранить JSON", "Сначала выполните анализ.")
            return
        name = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON", "*.json")])
        if name:
            try:
                Path(name).write_text(json.dumps(self.last_result.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
            except OSError as exc:
                messagebox.showerror("Не удалось сохранить файл", str(exc))

    def export_single_csv(self) -> None:
        if self.last_result is None:
            messagebox.showinfo("Экспорт CSV", "Сначала выполните анализ.")
            return
        self._save_csv([self.last_result], None)

    def _save_csv(self, results: list[FullResult], extras: list[dict] | None) -> None:
        name = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")], initialfile="results.csv")
        if not name:
            return
        try:
            n = export_csv(results, Path(name), self.settings, extras)
        except OSError as exc:
            messagebox.showerror("Не удалось сохранить CSV", str(exc))
            return
        messagebox.showinfo("Экспорт CSV", f"Сохранено строк: {n}\n{name}")

    # ------------------------------------------------------------ «Пакетный анализ»
    def load_batch(self) -> None:
        name = filedialog.askopenfilename(filetypes=[("CSV / TXT", "*.csv *.tsv *.txt"), ("Все файлы", "*.*")])
        if not name:
            return
        try:
            rows = load_texts(Path(name), self.settings.csv_text_column)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Не удалось загрузить файл", str(exc))
            return
        self.clear_batch()
        self.batch_source_rows = rows
        for i, row in enumerate(rows, 1):
            self.tree.insert("", "end", iid=str(i),
                             values=(i, row["text"].replace("\n", " "), "", "", "", "", ""),
                             tags=("odd" if i % 2 else "even",))
        self.batch_info.set(f"Загружено текстов: {len(rows)} ({Path(name).name}). Нажмите «Анализировать всё».")

    def clear_batch(self) -> None:
        if self._busy and self._batch_running:
            return
        self.tree.delete(*self.tree.get_children())
        self.batch_results.clear()
        self.batch_source_rows = []
        self.batch_progress["value"] = 0
        self.batch_info.set("Файл не загружен")
        self._sort = None
        self._update_headings()
        self._set_text(self.batch_detail, "")

    def run_batch(self) -> None:
        if not self.batch_source_rows:
            messagebox.showinfo("Пакетный анализ", "Сначала откройте CSV или TXT.")
            return
        rows = list(self.batch_source_rows)
        self.batch_results.clear()
        self._sort = None
        self._update_headings()
        for i, iid in enumerate(self.tree.get_children(), 1):
            self.tree.item(iid, values=self.tree.item(iid, "values")[:2] + ("", "", "", "", ""),
                           tags=("odd" if i % 2 else "even",))
        self._batch_running = True

        def job(emit):
            done = 0
            for i, row in enumerate(rows, 1):
                if self._cancel.is_set():
                    break
                emit("row", i, len(rows), self.engine.analyze(row["text"]))
                done = i
            emit("batch_done", done, len(rows))

        self._start(job, "Пакетный анализ…")
        self.stop_btn.configure(state="normal")

    def _insert_row(self, n: int, r: FullResult) -> None:
        self.tree.item(str(n), values=(
            n, r.text.replace("\n", " "), r.score, r.level, r.heuristic.score,
            r.semantic.score if r.semantic else "—", r.llm.score if r.llm else "—"),
            tags=(r.level, "odd" if n % 2 else "even"))

    # сортировка таблицы по щелчку на заголовке ---------------------------------
    def _sort_by(self, column: str) -> None:
        if not self.batch_results:
            return
        reverse = True if self._sort is None or self._sort[0] != column else not self._sort[1]
        self._sort = (column, reverse)

        def key(iid: str):
            index = int(iid) - 1
            if not 0 <= index < len(self.batch_results):
                return -1
            r = self.batch_results[index]
            if column == "n":
                return index
            if column == "text":
                return r.text.lower()
            if column in ("score", "level"):
                return r.score
            if column == "heur":
                return r.heuristic.score
            if column == "sem":
                return r.semantic.score if r.semantic else -1
            return r.llm.score if r.llm else -1

        for position, iid in enumerate(sorted(self.tree.get_children(), key=key, reverse=reverse)):
            self.tree.move(iid, "", position)
        self._update_headings()

    def _update_headings(self) -> None:
        column, reverse = self._sort or ("", False)
        for c in self.cols:
            arrow = ("  ▼" if reverse else "  ▲") if c == column else ""
            self.tree.heading(c, text=self.heads[c] + arrow)

    def _on_tree_select(self, _event=None) -> None:
        sel = self.tree.selection()
        if not sel:
            return
        index = int(sel[0]) - 1
        if not 0 <= index < len(self.batch_results):
            return
        r = self.batch_results[index]
        lines = [r.text, ""]
        lines.append("Маркеры: " + ("; ".join(f"{s.name} («{s.evidence}»)" for s in r.heuristic.signals) or "не найдены"))
        if r.semantic:
            lines.append(f"Семантика: {r.semantic.explanation}")
        if r.llm:
            lines.append(f"LLM: {r.llm.explanation}")
        lines += [f"⚠ {w}" for w in r.warnings]
        self._set_text(self.batch_detail, "\n".join(lines))

    def export_batch_csv(self) -> None:
        if not self.batch_results:
            messagebox.showinfo("Экспорт CSV", "Нет результатов: загрузите файл и выполните анализ.")
            return
        extras = [{k: v for k, v in row.items() if k != "text"} for row in self.batch_source_rows[: len(self.batch_results)]]
        self._save_csv(self.batch_results, extras)

    # ------------------------------------------------------------ проверка моделей
    def _test(self, target: str, check) -> None:
        if not self.apply_settings(quiet=True):
            return
        (self.sem_test_lbl if target == "semantic" else self.llm_test_lbl).set("Загрузка…")

        def job(emit):
            try:
                emit("test", target, True, check())
            except Exception as exc:
                emit("test", target, False, str(exc))

        self._start(job, "Проверка модели…")

    def test_semantic(self) -> None:
        self._test("semantic", lambda: self.engine.check_semantic())

    def test_llm(self) -> None:
        self._test("llm", lambda: self.engine.check_llm())


if __name__ == "__main__":
    App().mainloop()
