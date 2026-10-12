"""Разовая настройка: включить семантику и локальную LLM с уже скачанными моделями.

Запускается один раз после установки; старый файл настроек сохраняется рядом
с расширением .bak. Аргументы: путь к модели эмбеддингов, путь к .gguf.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from ironylab.settings import config_path, load_settings, save_settings  # noqa: E402


def main() -> int:
    embeddings = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "models" / "paraphrase-multilingual-MiniLM-L12-v2"
    gguf = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "models" / "qwen2.5-1.5b-instruct-q4_k_m.gguf"

    path = config_path()
    settings = load_settings()
    if path.exists():
        try:
            shutil.copy2(path, path.with_suffix(".json.bak"))
            print(f"Прежние настройки сохранены: {path.with_suffix('.json.bak')}")
        except OSError as exc:
            print(f"Не удалось сделать резервную копию настроек: {exc}")

    settings.semantic_model = str(embeddings) if embeddings.exists() else settings.semantic_model
    settings.use_semantic = True
    if gguf.is_file():
        settings.llm_model_path = str(gguf)
        settings.use_llm = True
        settings.llm_n_gpu_layers = -1 if "--cpu" not in sys.argv else 0

    saved = save_settings(settings)
    print(f"Настройки сохранены: {saved}")
    print(f"  эвристика={settings.use_heuristic} семантика={settings.use_semantic} LLM={settings.use_llm}")
    print(f"  модель эмбеддингов: {settings.semantic_model}")
    print(f"  модель LLM:         {settings.llm_model_path or '—'} (слоёв на GPU: {settings.llm_n_gpu_layers})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
