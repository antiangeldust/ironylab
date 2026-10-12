"""Public API for IronyLab."""

from .analyzer import Analysis, Signal, analyze, level_for
from .engine import Engine, FullResult
from .export import export_csv, load_texts
from .settings import Settings, load_settings, save_settings

__all__ = [
    "Analysis", "Signal", "analyze", "level_for", "Engine", "FullResult",
    "export_csv", "load_texts", "Settings", "load_settings", "save_settings",
]
__version__ = "1.2.0"
