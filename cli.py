"""Command-line interface for IronyLab."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from ironylab import Engine, export_csv, load_settings, load_texts
from ironylab.console import enable_utf8_console


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Объяснимая оценка иронического потенциала текста")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--text", help="текст в кавычках")
    source.add_argument("--file", type=Path, help="TXT-файл (UTF-8)")
    source.add_argument("--csv", type=Path, help="CSV со столбцом text (имя столбца — в настройках или --column)")
    parser.add_argument("--json", type=Path, help="сохранить одиночный результат в JSON")
    parser.add_argument("--out", type=Path, help="результат пакетного анализа CSV (по умолчанию results.csv)")
    parser.add_argument("--column", help="столбец с текстом в CSV (по умолчанию из настроек)")
    parser.add_argument("--settings", type=Path, help="файл настроек JSON (по умолчанию тот же, что у окна программы)")
    parser.add_argument("--llm", metavar="PATH", help="включить локальную LLM: файл .gguf или папка модели")
    parser.add_argument("--semantic", metavar="MODEL", help="включить семантику: папка/имя модели sentence-transformers")
    parser.add_argument("--no-llm", action="store_true", help="выключить LLM независимо от настроек")
    parser.add_argument("--no-semantic", action="store_true", help="выключить семантику независимо от настроек")
    return parser.parse_args()


def print_result(data: dict) -> None:
    print(f"Оценка: {data['score']}/100 ({data['level']})")
    parts = ", ".join(f"{k}={v}" for k, v in data["used"].items())
    print(f"Вклад методов: {parts}")
    if data["heuristic"]["signals"]:
        print("Маркеры:")
        for item in data["heuristic"]["signals"]:
            print(f"  +{item['weight']:>2} {item['name']}: {item['evidence']}")
    else:
        print("Явные маркеры не найдены.")
    if data["semantic"]:
        print(f"Семантика: {data['semantic']['score']}/100 — {data['semantic']['explanation']}")
    if data["llm"]:
        print(f"LLM: {data['llm']['score']}/100 — {data['llm']['explanation']}")
    for warning in data["warnings"]:
        print(f"Предупреждение: {warning}", file=sys.stderr)
    print(f"Важно: {data['heuristic']['disclaimer']}")


def main() -> int:
    enable_utf8_console()
    args = parse_args()
    settings = load_settings(args.settings)
    if args.llm:
        settings.use_llm, settings.llm_model_path = True, args.llm
    if args.semantic:
        settings.use_semantic, settings.semantic_model = True, args.semantic
    if args.no_llm:
        settings.use_llm = False
    if args.no_semantic:
        settings.use_semantic = False
    engine = Engine(settings)
    try:
        if args.csv:
            rows = load_texts(args.csv, args.column or settings.csv_text_column)
            output = args.out or Path("results.csv")
            results = []
            for i, row in enumerate(rows, 1):
                results.append(engine.analyze(row["text"]))
                print(f"\r{i}/{len(rows)}", end="", file=sys.stderr, flush=True)
            print(file=sys.stderr)
            extras = [{k: v for k, v in row.items() if k != "text"} for row in rows]
            export_csv(results, output, settings, extras)
            print(f"Готово: {output.resolve()}")
            return 0
        text = args.text if args.text is not None else args.file.read_text(encoding="utf-8-sig")
        result = engine.analyze(text).to_dict()
        print_result(result)
        if args.json:
            args.json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"JSON сохранён: {args.json.resolve()}")
        return 0
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
