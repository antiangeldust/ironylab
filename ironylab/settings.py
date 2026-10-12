"""Persistent user settings for IronyLab.

Settings are stored as JSON in the user's config directory
(``%APPDATA%\\IronyLab`` on Windows, ``~/.config/ironylab`` elsewhere).
Loading is forgiving: unknown keys are ignored, wrong types fall back to
defaults and numbers are clamped to sane ranges, so a hand-edited or
corrupted file can never crash the application.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
import json
import os
from pathlib import Path

CSV_DELIMITERS = {";": "точка с запятой ( ; ) — для русского Excel", ",": "запятая ( , )", "\t": "табуляция"}
CSV_ENCODINGS = ("utf-8-sig", "utf-8", "cp1251")
DEVICES = ("cpu", "cuda", "mps")


@dataclass
class Settings:
    # --- итоговая оценка ---------------------------------------------------
    use_heuristic: bool = True
    use_semantic: bool = False
    use_llm: bool = False
    weight_heuristic: int = 40
    weight_semantic: int = 25
    weight_llm: int = 35
    threshold_low: int = 20        # ниже — «низкий»
    threshold_moderate: int = 45   # ниже — «умеренный»
    threshold_high: int = 70       # ниже — «повышенный», иначе «высокий»
    max_chars: int = 2000          # длиннее текст обрезается перед семантикой/LLM
    # --- семантический анализатор -------------------------------------------
    # Имя модели на Hugging Face (скачается при первом запуске) или путь к папке с моделью.
    semantic_model: str = "paraphrase-multilingual-MiniLM-L12-v2"
    semantic_device: str = "cpu"
    # --- локальная LLM ---------------------------------------------------------
    llm_model_path: str = ""       # файл .gguf или папка модели Hugging Face
    llm_n_ctx: int = 2048
    llm_n_threads: int = 0         # 0 = автоматически
    llm_n_gpu_layers: int = 0      # 0 = только CPU, -1 = всё на GPU
    llm_temperature: float = 0.1
    llm_max_tokens: int = 256
    llm_samples: int = 3           # сколько раз спросить модель; балл — среднее прогонов
    llm_system_prompt: str = ""    # пусто = встроенная инструкция
    # --- экспорт / импорт ------------------------------------------------------
    csv_delimiter: str = ";"
    csv_encoding: str = "utf-8-sig"
    csv_include_sentences: bool = False
    csv_text_column: str = "text"
    # --- интерфейс -------------------------------------------------------------
    font_size: int = 12

    # Диапазоны для числовых полей: (минимум, максимум).
    RANGES = {
        "weight_heuristic": (0, 100), "weight_semantic": (0, 100), "weight_llm": (0, 100),
        "threshold_low": (1, 98), "threshold_moderate": (2, 99), "threshold_high": (3, 100),
        "max_chars": (100, 20000), "llm_n_ctx": (256, 131072), "llm_n_threads": (0, 256),
        "llm_n_gpu_layers": (-1, 1000), "llm_temperature": (0.0, 2.0),
        "llm_max_tokens": (16, 4096), "font_size": (8, 28), "llm_samples": (1, 7),
    }

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Settings":
        """Build validated settings; anything invalid falls back to the default."""
        base = cls()
        values = {}
        for f in fields(cls):
            if f.name not in data:
                continue
            default = getattr(base, f.name)
            raw = data[f.name]
            try:
                if isinstance(default, bool):
                    value = raw if isinstance(raw, bool) else str(raw).strip().lower() in {"1", "true", "yes", "да"}
                elif isinstance(default, int):
                    value = int(float(raw))
                elif isinstance(default, float):
                    value = float(raw)
                else:
                    value = str(raw)
            except (TypeError, ValueError):
                continue
            if f.name in cls.RANGES:
                lo, hi = cls.RANGES[f.name]
                value = min(max(value, lo), hi)
            values[f.name] = value
        s = cls(**values)
        if s.csv_delimiter not in CSV_DELIMITERS:
            s.csv_delimiter = base.csv_delimiter
        if s.csv_encoding not in CSV_ENCODINGS:
            s.csv_encoding = base.csv_encoding
        if s.semantic_device not in DEVICES:
            s.semantic_device = base.semantic_device
        # Пороги уровней обязаны строго возрастать.
        low, mod, high = sorted((s.threshold_low, s.threshold_moderate, s.threshold_high))
        mod = max(mod, low + 1)
        high = max(high, mod + 1)
        s.threshold_low, s.threshold_moderate, s.threshold_high = low, mod, min(high, 100)
        s.llm_model_path = s.llm_model_path.strip().strip('"')
        s.semantic_model = s.semantic_model.strip().strip('"')
        s.csv_text_column = s.csv_text_column.strip() or base.csv_text_column
        if not s.semantic_model:
            # Пустое значение (в том числе из старого файла настроек) — это «модель по умолчанию».
            s.semantic_model = base.semantic_model
        return s

    @property
    def thresholds(self) -> tuple[int, int, int]:
        return (self.threshold_low, self.threshold_moderate, self.threshold_high)


def config_path() -> Path:
    override = os.environ.get("IRONYLAB_CONFIG")
    if override:
        return Path(override)
    if os.name == "nt" and os.environ.get("APPDATA"):
        return Path(os.environ["APPDATA"]) / "IronyLab" / "settings.json"
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "ironylab" / "settings.json"


def load_settings(path: Path | None = None) -> Settings:
    path = path or config_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("settings root must be an object")
        return Settings.from_dict(data)
    except (OSError, ValueError):
        return Settings()


def save_settings(settings: Settings, path: Path | None = None) -> Path:
    path = path or config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return path
