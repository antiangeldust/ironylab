"""Reading tables/text files and exporting results to CSV."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable, Sequence

from .engine import FullResult
from .settings import Settings

_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def safe_cell(value):
    """Neutralise spreadsheet formula injection: a text cell starting with = + - @ gets a leading '."""
    if isinstance(value, str) and value.startswith(_FORMULA_PREFIXES):
        return "'" + value
    return value


def _read_text(path: Path) -> str:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "cp1251"):  # cp1251 — «CSV (разделители — запятые)» из русского Excel
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("Не удалось определить кодировку файла (ожидается UTF-8 или Windows-1251)")


def load_texts(path: Path, column: str = "text") -> list[dict]:
    """Return rows ``{"text": ..., <other columns>}`` from a .csv/.tsv or one text per line from a .txt."""
    content = _read_text(Path(path))
    if Path(path).suffix.lower() in {".csv", ".tsv"}:
        sample = content[:4096]
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(content.splitlines(), dialect=dialect)
        names = reader.fieldnames or []
        if column not in names:
            raise ValueError(f"В файле нет столбца «{column}». Найдены столбцы: {', '.join(names) or '—'}. "
                             "Название можно изменить в Настройки → Экспорт.")
        rows = []
        for row in reader:
            text = (row.get(column) or "").strip()
            if text:
                extra = {k: v for k, v in row.items() if k != column and k is not None}
                rows.append({"text": text, **extra})
        return rows
    return [{"text": line.strip()} for line in content.splitlines() if line.strip()]


def result_row(result: FullResult, settings: Settings, index: int | None = None, extra: dict | None = None) -> dict:
    row: dict = dict(extra or {})
    if index is not None:
        row = {"№": index, **row}
    row.update({
        "text": result.text,
        "score": result.score,
        "level": result.level,
        "heuristic_score": result.heuristic.score,
        "semantic_score": result.semantic.score if result.semantic else "",
        "llm_score": result.llm.score if result.llm else "",
        "signals": "; ".join(f"{s.name}: {s.evidence}" for s in result.heuristic.signals),
        "semantic_note": result.semantic.explanation if result.semantic else "",
        "llm_explanation": result.llm.explanation if result.llm else "",
        "warnings": "; ".join(result.warnings),
    })
    if settings.csv_include_sentences:
        row["sentences"] = " | ".join(f"{sc}: {sent}" for sent, sc in result.heuristic.sentences)
    return row


def export_csv(results: Sequence[FullResult], destination: Path, settings: Settings,
               extras: Sequence[dict] | None = None) -> int:
    """Write *results* to *destination* using the CSV options from *settings*; return the row count."""
    rows = [result_row(r, settings, i, extras[i - 1] if extras else None) for i, r in enumerate(results, 1)]
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with Path(destination).open("w", encoding=settings.csv_encoding, newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields or ["text", "score", "level"], delimiter=settings.csv_delimiter)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: safe_cell(v) for k, v in row.items()})
    return len(rows)
