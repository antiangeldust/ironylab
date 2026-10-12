"""Combines heuristic, semantic and LLM scores into one explainable result."""

from __future__ import annotations

from dataclasses import dataclass
import threading

from .analyzer import Analysis, analyze, level_for
from .llm import LLMResult, LocalLLM
from .semantic import SemanticAnalyzer, SemanticResult
from .settings import Settings

COMPONENT_NAMES = {"heuristic": "Эвристика", "semantic": "Семантика", "llm": "LLM"}


@dataclass(frozen=True)
class FullResult:
    text: str
    score: int
    level: str
    heuristic: Analysis
    semantic: SemanticResult | None
    llm: LLMResult | None
    used: dict          # компонент -> балл, вошедший в итог
    warnings: tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "text": self.text, "score": self.score, "level": self.level, "used": dict(self.used),
            "heuristic": self.heuristic.to_dict(),
            "semantic": self.semantic.to_dict() if self.semantic else None,
            "llm": self.llm.to_dict() if self.llm else None,
            "warnings": list(self.warnings),
        }


class Engine:
    """Owns the (expensive) models and turns text into a :class:`FullResult`.

    Thread-safe: analysis calls are serialized, so a GUI worker thread and a
    "test model" button cannot use a model at the same time.
    """

    def __init__(self, settings: Settings | None = None, *, semantic: SemanticAnalyzer | None = None,
                 llm: LocalLLM | None = None) -> None:
        self.settings = settings or Settings()
        self._semantic, self._llm = semantic, llm
        self._injected = semantic is not None or llm is not None
        self._lock = threading.RLock()

    def update_settings(self, settings: Settings) -> None:
        """Apply new settings; models are dropped (and lazily reloaded) only if their config changed."""
        with self._lock:
            old, self.settings = self.settings, settings
            if self._injected:
                return
            if (old.semantic_model, old.semantic_device) != (settings.semantic_model, settings.semantic_device):
                self._semantic = None
            llm_keys = ("llm_model_path", "llm_n_ctx", "llm_n_threads", "llm_n_gpu_layers",
                        "llm_temperature", "llm_max_tokens", "llm_samples", "llm_system_prompt")
            if any(getattr(old, k) != getattr(settings, k) for k in llm_keys):
                self._llm = None

    # -- lazily created components ---------------------------------------------
    def semantic_analyzer(self) -> SemanticAnalyzer:
        if self._semantic is None:
            s = self.settings
            self._semantic = SemanticAnalyzer(s.semantic_model, s.semantic_device)
        return self._semantic

    def llm(self) -> LocalLLM:
        if self._llm is None:
            s = self.settings
            self._llm = LocalLLM(s.llm_model_path, s.llm_n_ctx, s.llm_n_threads, s.llm_n_gpu_layers,
                                 s.llm_temperature, s.llm_max_tokens, s.llm_system_prompt,
                                 samples=s.llm_samples)
        return self._llm

    def check_semantic(self) -> str:
        with self._lock:
            result = self.semantic_analyzer().analyze("Ну да, конечно, прекрасная погода — опять ливень.")
            return f"Модель загружена. Тестовая фраза: {result.score}/100 ({result.explanation})"

    def check_llm(self) -> str:
        with self._lock:
            result = self.llm().analyze("Ну да, конечно, прекрасная погода — опять ливень.")
            return f"Модель загружена. Тестовая фраза: {result.score}/100. {result.explanation}"

    # -- main entry ------------------------------------------------------------
    def analyze(self, text: str) -> FullResult:
        with self._lock:
            s = self.settings
            text = text.strip()
            heuristic = analyze(text, s.thresholds)
            warnings: list[str] = []
            trimmed = text[: s.max_chars]
            if len(text) > s.max_chars:
                warnings.append(f"текст обрезан до {s.max_chars} символов для семантики/LLM")

            semantic = llm = None
            if text and s.use_semantic:
                try:
                    semantic = self.semantic_analyzer().analyze(trimmed)
                except Exception as exc:  # модель может отсутствовать, быть несовместимой и т. п.
                    warnings.append(f"семантика недоступна: {exc}")
            if text and s.use_llm:
                try:
                    llm = self.llm().analyze(trimmed)
                except Exception as exc:
                    warnings.append(f"LLM недоступна: {exc}")

            parts = []  # (имя, балл, вес)
            if s.use_heuristic:
                parts.append(("heuristic", heuristic.score, s.weight_heuristic))
            if semantic:
                parts.append(("semantic", semantic.score, s.weight_semantic))
            if llm:
                parts.append(("llm", llm.score, s.weight_llm))
            if not parts:
                parts.append(("heuristic", heuristic.score, 1))
                if not s.use_heuristic:
                    warnings.append("ни один компонент не дал оценку — использована эвристика")
            total_weight = sum(w for _, _, w in parts)
            if total_weight:
                final = sum(sc * w for _, sc, w in parts) / total_weight
            else:  # все веса нулевые — обычное среднее
                final = sum(sc for _, sc, _ in parts) / len(parts)
            score = round(min(100, max(0, final)))
            level = heuristic.level if not text else level_for(score, s.thresholds)
            return FullResult(text, score, level, heuristic, semantic, llm,
                              {name: sc for name, sc, _ in parts}, tuple(warnings))
