"""Смоук-тест окна: строим интерфейс, рисуем полный результат, сортируем таблицу.

Запуск: python smoke_gui.py   (окно скрыто, диалоги заглушены)
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import tkinter.messagebox as mb

mb.showinfo = lambda *a, **k: None
mb.showerror = lambda *a, **k: print("ОШИБКА:", a)
mb.askyesno = lambda *a, **k: True

import app as appmod  # noqa: E402


def main() -> int:
    window = appmod.App()
    window.withdraw()
    window.update_idletasks()

    # обычный результат (эвристика + семантика + LLM, если они включены в настройках)
    result = window.engine.analyze("Ну да, конечно, прекрасная погода — опять ливень 🙃")
    window.show_result(result)
    window._refresh_status()
    window.update_idletasks()

    # таблица пакетного анализа: строки, сортировка, выбор
    window.batch_source_rows = [{"text": t} for t in
                                ("Привет", "Ну да, конечно!", "Заседание в десять часов.")]
    for i, row in enumerate(window.batch_source_rows, 1):
        window.tree.insert("", "end", iid=str(i), values=(i, row["text"], "", "", "", "", ""))
    for i, row in enumerate(window.batch_source_rows, 1):
        window._on_row(i, 3, window.engine.analyze(row["text"]))
    for column in ("score", "score", "text", "level", "sem", "llm", "n", "heur"):
        window._sort_by(column)
        window.update_idletasks()
    window.tree.selection_set("2")
    window._on_tree_select()
    window.update_idletasks()

    # настройки: сохранение, сброс, переключение всех вкладок
    # (пишем в файл рядом с проектом, чтобы тест не трогал настройки пользователя)
    os.environ["IRONYLAB_CONFIG"] = os.path.join(os.path.dirname(os.path.abspath(__file__)), "smoke-settings.json")
    assert window.apply_settings(quiet=True), "настройки не сохранились"
    window.reset_settings()
    for tab in range(3):
        window.tabs.select(tab)
        window.update_idletasks()
    for page in range(5):
        window.settings_tabs.select(page)
        window.update_idletasks()
    window.tabs.select(0)
    window.update_idletasks()

    window.clear_batch()
    window.update_idletasks()
    print(f"SMOKE OK: балл {result.score}, уровень «{result.level}», строк в таблице {len(window.batch_results)}")
    window.destroy()
    # убираем служебный файл настроек, созданный тестом
    for leftover in ("smoke-settings.json", "smoke-settings.json.bak"):
        try:
            os.remove(os.path.join(os.path.dirname(os.path.abspath(__file__)), leftover))
        except OSError:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
