"""Корректный вывод русского текста и символов вроде «↔» в консоли Windows.

Консоль Windows по умолчанию работает в кодовой странице 866, поэтому печать
пояснений с символами «↔», «•», «⚠» заканчивается UnicodeEncodeError. Функция
переключает консоль в UTF-8, а если это не удалось — не даёт программе упасть:
непечатаемые символы заменяются.
"""

from __future__ import annotations

import os
import sys


def enable_utf8_console() -> None:
    """Вызывать один раз в начале работы консольной программы."""
    if os.name == "nt":
        try:
            import ctypes

            ctypes.windll.kernel32.SetConsoleOutputCP(65001)  # UTF-8 для вывода
        except Exception:  # консоли может не быть вовсе (перенаправление в файл)
            pass
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass
