"""Semantic scoring of ironic potential with sentence embeddings.

The heuristic analyzer looks at *surface* cues (fixed phrases, punctuation,
word lists).  This module looks at *meaning*: a multilingual sentence-embedding
model turns text into vectors, and two signals are derived from them:

1. **Полярный контраст** — the text is split into clauses; each clause gets a
   polarity (closer to «positive» or «negative» anchor sentences).  A clearly
   positive clause next to a clearly negative one is the classic
   «прекрасная погода — опять ливень» incongruity, even for words that are not
   in any word list.
2. **Сходство с прототипами** — similarity to a small set of typical ironic
   remarks versus literal, neutral statements.

Both numbers are *uncalibrated*: they are useful for ranking and for
experiments, not as probabilities.  The optional dependency
``sentence-transformers`` is imported lazily, so the rest of the program works
without it.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math
import re
from typing import Callable, Sequence

Encoder = Callable[[Sequence[str]], Sequence[Sequence[float]]]

POSITIVE_ANCHORS = (
    "Это прекрасно, я в восторге.", "Замечательный день, всё отлично.", "Мне очень нравится, спасибо большое.",
    "Великолепная работа, браво.", "This is wonderful, I love it.", "Great, everything is perfect.",
    "Thank you so much, this is amazing.", "What a brilliant idea.",
)
NEGATIVE_ANCHORS = (
    "Это ужасно, всё сломалось.", "Опять проблемы, я разочарован.", "Отвратительная погода, идёт ливень.",
    "Полный провал, я опоздал.", "This is terrible, everything is broken.", "Again a problem, I am disappointed.",
    "It is raining and I am late.", "What a complete failure.",
)
IRONIC_PROTOTYPES = (
    "Ну да, конечно, прекрасная погода — опять ливень.", "О, гениально, теперь всё сломалось окончательно.",
    "Спасибо, что предупредил заранее, очень вовремя.", "Просто замечательно, снова понедельник и снова дедлайн.",
    "Ага, конечно, так я тебе и поверил.", "Yeah right, that went really well.",
    "Oh great, another meeting that could have been an email.", "Thanks a lot, that was so helpful.",
)
LITERAL_PROTOTYPES = (
    "Заседание начинается в десять часов.", "Принтер находится в кабинете.", "Сегодня солнечно, температура двадцать градусов.",
    "Мне очень понравился фильм, рекомендую.", "Документ отправлен на согласование.",
    "The meeting starts at ten o'clock.", "The report is attached to this email.",
    "I really enjoyed the concert yesterday.",
)


@dataclass(frozen=True)
class SemanticResult:
    score: int
    contrast: int          # 0-100, полярный контраст между фрагментами
    prototype: int         # 0-100, близость к иронии против буквальных высказываний
    explanation: str

    def to_dict(self) -> dict:
        return asdict(self)


def _cos(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def _top_mean(sims: list[float], k: int = 3) -> float:
    best = sorted(sims, reverse=True)[:k]
    return sum(best) / len(best)


def split_clauses(text: str) -> list[str]:
    parts = re.split(r"[.!?…;:,]+\s+|\s+[—–-]+\s+|\n+", text)
    return [p.strip(" .!?…—–-\"«»") for p in parts if len(p.strip(" .!?…—–-\"«»")) >= 3][:8]


class SemanticAnalyzer:
    """Embedding-based analyzer.  *encoder* can be injected for tests."""

    def __init__(self, model: str = "", device: str = "cpu", encoder: Encoder | None = None) -> None:
        self.model_name = model
        self.device = device
        self._encoder = encoder
        self._anchors: dict[str, list[Sequence[float]]] | None = None

    def load(self) -> None:
        if self._encoder is None:
            if not self.model_name:
                raise RuntimeError("Не указана модель эмбеддингов (Настройки → Семантика).")
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:
                raise RuntimeError(
                    "Не установлен sentence-transformers. Выполните: pip install sentence-transformers"
                ) from exc
            try:  # без полос загрузки в консоли
                from transformers.utils import logging as transformers_logging

                transformers_logging.disable_progress_bar()
            except Exception:
                pass
            model = SentenceTransformer(self.model_name, device=self.device)

            def encode(texts: Sequence[str]):
                return model.encode(list(texts), convert_to_numpy=True, normalize_embeddings=True).tolist()

            self._encoder = encode
        if self._anchors is None:
            groups = {"pos": POSITIVE_ANCHORS, "neg": NEGATIVE_ANCHORS, "iro": IRONIC_PROTOTYPES, "lit": LITERAL_PROTOTYPES}
            self._anchors = {name: [list(v) for v in self._encoder(items)] for name, items in groups.items()}

    def _polarity(self, vec: Sequence[float]) -> float:
        pos = _top_mean([_cos(vec, a) for a in self._anchors["pos"]])
        neg = _top_mean([_cos(vec, a) for a in self._anchors["neg"]])
        return math.tanh(6.0 * (pos - neg))  # -1 … 1

    def analyze(self, text: str) -> SemanticResult:
        self.load()
        clauses = split_clauses(text) or [text.strip()]
        vectors = [list(v) for v in self._encoder([text.strip()] + clauses)]
        whole, clause_vecs = vectors[0], vectors[1:]

        # 1. полярный контраст между фрагментами
        contrast, note = 0, "фрагменты не противоречат друг другу по тональности"
        if len(clauses) > 1:
            pols = [self._polarity(v) for v in clause_vecs]
            hi, lo = max(pols), min(pols)
            if hi > 0.15 and lo < -0.15:
                contrast = round(100 * min(hi, -lo))
                note = (f"тональность фрагментов расходится: «{clauses[pols.index(hi)]}» (+) ↔ "
                        f"«{clauses[pols.index(lo)]}» (−)")

        # 2. сходство с ироничными и буквальными прототипами
        s_iro = _top_mean([_cos(whole, a) for a in self._anchors["iro"]])
        s_lit = _top_mean([_cos(whole, a) for a in self._anchors["lit"]])
        prototype = round(100 / (1 + math.exp(-12.0 * (s_iro - s_lit))))

        score = round(min(100, 0.6 * contrast + 0.4 * prototype + (10 if contrast >= 40 and prototype >= 50 else 0)))
        explanation = f"{note}; близость к ироничным образцам {prototype}/100"
        return SemanticResult(score, contrast, prototype, explanation)
