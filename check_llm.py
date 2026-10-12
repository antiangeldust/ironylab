"""Быстрая проверка локальной LLM: загрузка GGUF, генерация, разбор ответа.

Запуск:  python check_llm.py [путь-к-модели.gguf]
Скрипт сам подключает CUDA-библиотеки из пакетов nvidia-*-cu12, если они есть,
поэтому отдельная установка CUDA Toolkit не нужна.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
_HANDLES: list = []  # держим дескрипторы каталогов DLL, пока жив процесс


def add_cuda_dll_dirs() -> list[str]:
    """Сделать cudart64_12/cublas64_12 видимыми, если они поставлены через pip.

    Каталоги ищутся у того интерпретатора, которым запущен скрипт (и дополнительно
    в окружениях проекта), поэтому команда работает из любого окружения.
    Возвращённые дескрипторы нужно сохранить: как только объект-дескриптор
    уничтожается, каталог снова исключается из поиска DLL.
    """
    bases: list[str] = []
    try:
        import site

        bases.extend(site.getsitepackages())
        bases.append(site.getusersitepackages())
    except Exception:  # noqa: BLE001 — site может быть недоступен во встроенных сборках
        pass
    bases += [str(ROOT / "Lib" / "site-packages"), str(ROOT / ".venv" / "Lib" / "site-packages")]

    found: list[str] = []
    for base in dict.fromkeys(bases):  # без повторов, порядок сохраняется
        for sub in ("cublas", "cuda_runtime", "cuda_nvrtc"):
            candidate = Path(base) / "nvidia" / sub / "bin"
            if candidate.is_dir():
                _HANDLES.append(os.add_dll_directory(str(candidate)))
                found.append(str(candidate))
    return found


def main() -> int:
    from ironylab.console import enable_utf8_console

    enable_utf8_console()
    model = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "models" / "qwen2.5-1.5b-instruct-q4_k_m.gguf"
    if not model.is_file():
        print(f"Модель не найдена: {model}")
        print("Скачайте .gguf (см. INSTALL_RU.md) или укажите путь аргументом.")
        return 2

    dirs = add_cuda_dll_dirs()
    if dirs:
        print(f"CUDA-библиотеки из pip подключены ({len(dirs)} каталога)")

    from llama_cpp import Llama

    started = time.perf_counter()
    llm = Llama(model_path=str(model), n_ctx=2048, n_gpu_layers=-1, verbose=False)
    print(f"Модель загружена за {time.perf_counter() - started:.1f} с: {model.name}")

    from ironylab.llm import build_messages, parse_reply

    text = "Ну да, конечно, прекрасная погода — опять ливень."
    started = time.perf_counter()
    raw = llm.create_chat_completion(messages=build_messages(text), temperature=0.1, max_tokens=256)
    elapsed = time.perf_counter() - started
    reply = raw["choices"][0]["message"]["content"]
    result = parse_reply(reply)
    print(f"Генерация {elapsed:.1f} с -> {result.score}/100: {result.explanation}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
