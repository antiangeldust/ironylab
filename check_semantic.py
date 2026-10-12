"""Быстрая проверка семантического анализатора (sentence-transformers).

Запуск:  python check_semantic.py [модель]
Модель — имя на Hugging Face или путь к папке. По умолчанию берётся значение
из настроек программы (Настройки -> Семантика).
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ironylab.console import enable_utf8_console  # noqa: E402
from ironylab.settings import load_settings  # noqa: E402
from ironylab.semantic import SemanticAnalyzer  # noqa: E402

SAMPLES = (
    "Ну да, конечно, прекрасная погода — опять ливень.",
    "Заседание начинается в десять часов.",
)


def main() -> int:
    enable_utf8_console()
    settings = load_settings()
    model = sys.argv[1] if len(sys.argv) > 1 else settings.semantic_model
    if not model:
        print("Модель не указана: задайте её в Настройки -> Семантика или аргументом.")
        return 2
    local = ROOT / "models" / "paraphrase-multilingual-MiniLM-L12-v2"
    if model == "paraphrase-multilingual-MiniLM-L12-v2" and local.is_dir():
        model = str(local)  # локальная копия: работает без сети
        print("Использую локальную копию модели:", model)

    try:
        from sentence_transformers import SentenceTransformer  # noqa: F401
    except ImportError:
        print("Не установлен sentence-transformers. Выполните: python -m pip install sentence-transformers")
        return 2

    analyzer = SemanticAnalyzer(model, settings.semantic_device)
    started = time.perf_counter()
    try:
        analyzer.load()
    except Exception as exc:
        print(f"Не удалось загрузить модель: {exc}")
        return 1
    print(f"Модель загружена за {time.perf_counter() - started:.1f} с")
    for text in SAMPLES:
        result = analyzer.analyze(text)
        print(f"  {result.score:>3}/100 (контраст {result.contrast}, прототипы {result.prototype}) — {text}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
