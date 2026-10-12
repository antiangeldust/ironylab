"""Превращает файл Markdown в автономный HTML — открывается в браузере двойным щелчком.

Запуск:  python md_to_html.py INSTALL_RU.md [другой.md ...]
Результат: рядом появляется .html со встроенными стилями (ничего не нужно доустанавливать).
Используется markdown-it-py из окружения проекта; если его нет — скрипт об этом скажет.
"""

from __future__ import annotations

import html as html_module
import re
import sys
from pathlib import Path

CSS = """
:root { color-scheme: light; }
* { box-sizing: border-box; }
body {
  margin: 0; padding: 40px 20px 80px;
  background: #f3f4f6; color: #111827;
  font: 16px/1.65 -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
}
main {
  max-width: 960px; margin: 0 auto; padding: 44px 52px;
  background: #ffffff; border: 1px solid #e3e6eb; border-radius: 14px;
  box-shadow: 0 1px 3px rgba(17, 24, 39, .06);
}
h1 { font-size: 30px; line-height: 1.25; margin: 0 0 18px; }
h2 { font-size: 22px; margin: 44px 0 14px; padding-top: 20px; border-top: 1px solid #e3e6eb; }
h3 { font-size: 18px; margin: 30px 0 10px; }
h4 { font-size: 16px; margin: 24px 0 8px; }
p, li { margin: 10px 0; }
a { color: #4f46e5; text-decoration: none; }
a:hover { text-decoration: underline; }
code {
  background: #f3f4f6; border: 1px solid #e3e6eb; border-radius: 5px;
  padding: 1px 5px; font: 13.5px/1.5 "Cascadia Mono", Consolas, "Courier New", monospace;
}
pre {
  background: #f8f9fb; border: 1px solid #e3e6eb; border-left: 3px solid #4f46e5;
  border-radius: 8px; padding: 14px 18px; overflow-x: auto;
}
pre code { background: none; border: 0; padding: 0; font-size: 13.5px; }
blockquote {
  margin: 18px 0; padding: 12px 20px; background: #eef2ff;
  border-left: 3px solid #4f46e5; border-radius: 0 8px 8px 0; color: #312e81;
}
blockquote p { margin: 6px 0; }
.table-wrap { overflow-x: auto; margin: 18px 0; }
table { border-collapse: collapse; width: 100%; font-size: 14.5px; }
th, td { border: 1px solid #e3e6eb; padding: 8px 12px; text-align: left; vertical-align: top; }
th { background: #f8f9fb; font-weight: 600; }
tbody tr:nth-child(even) { background: #fcfcfd; }
hr { border: 0; border-top: 1px solid #e3e6eb; margin: 34px 0; }
img { max-width: 100%; border: 1px solid #e3e6eb; border-radius: 10px; margin: 12px 0; }
ul, ol { padding-left: 26px; }
li > ul, li > ol { margin: 6px 0; }
h1 + p, h2 + p { margin-top: 8px; }
@media print {
  body { background: #fff; padding: 0; }
  main { border: 0; box-shadow: none; padding: 0; max-width: none; }
  h2 { break-after: avoid; }
  table, pre, blockquote { break-inside: avoid; }
}
"""

TEMPLATE = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>{css}</style>
</head>
<body>
<main>
{body}
</main>
</body>
</html>
"""


def slugify(title: str) -> str:
    """Идентификатор заголовка в стиле GitHub — чтобы работали ссылки вида #9-macos-и-linux."""
    text = re.sub(r"[^\w\s\-]", "", title.lower(), flags=re.UNICODE)
    return re.sub(r"\s+", "-", text.strip())


def convert(source: Path) -> Path:
    try:
        from markdown_it import MarkdownIt
    except ImportError:
        raise SystemExit("Нужен markdown-it-py: python -m pip install markdown-it-py")

    md = MarkdownIt("commonmark").enable("table").enable("strikethrough")
    text = source.read_text(encoding="utf-8")

    tokens = md.parse(text)
    for index, token in enumerate(tokens):
        if token.type == "heading_open" and index + 1 < len(tokens):
            token.attrSet("id", slugify(tokens[index + 1].content))
    body = md.renderer.render(tokens, md.options, {})

    # широкие таблицы прокручиваются, а не ломают вёрстку
    body = body.replace("<table>", '<div class="table-wrap"><table>').replace("</table>", "</table></div>")

    title = next((line.lstrip("# ").strip() for line in text.splitlines() if line.startswith("# ")), source.stem)
    target = source.with_suffix(".html")
    target.write_text(
        TEMPLATE.format(title=html_module.escape(title), css=CSS, body=body), encoding="utf-8"
    )
    return target


def main() -> int:
    sources = [Path(arg) for arg in sys.argv[1:]] or [Path("INSTALL_RU.md")]
    for source in sources:
        if not source.is_file():
            print(f"Файл не найден: {source}")
            return 1
        print(f"{source} -> {convert(source)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
