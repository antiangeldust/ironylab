"""Explainable, dependency-free heuristic analysis of ironic potential."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import re


@dataclass(frozen=True)
class Signal:
    name: str
    evidence: str
    weight: int
    explanation: str


@dataclass(frozen=True)
class Analysis:
    score: int
    level: str
    signals: tuple[Signal, ...]
    sentences: tuple[tuple[str, int], ...]
    disclaimer: str = (
        "Эвристическая оценка, а не доказательство иронии: проверяйте контекст "
        "и согласие нескольких разметчиков."
    )

    def to_dict(self) -> dict:
        return asdict(self)


PHRASES = {
    "ну да": 14, "ну конечно": 20, "да конечно": 18,
    "ага конечно": 22, "как же": 18, "очень смешно": 14,
    "вот спасибо": 16, "просто прекрасно": 17, "просто замечательно": 17,
    "гениально": 9, "блестяще": 9, "удивительно": 7,
    "yeah right": 22, "as if": 20, "thanks a lot": 15,
    "just great": 17, "brilliant": 9, "what a surprise": 14,
}

POSITIVE = {
    "прекрасно", "прекрасный", "прекрасная", "прекрасное", "прекрасные",
    "замечательно", "замечательный", "замечательная", "отлично", "отличный", "великолепно",
    "гениально", "блестяще", "люблю", "обожаю", "спасибо", "счастье",
    "great", "wonderful", "excellent", "brilliant", "love", "perfect", "thanks",
}
NEGATIVE = {
    "опять", "сломался", "сломалась", "сломано", "ошибка", "провал", "ужас",
    "ненавижу", "дождь", "ливень", "опоздал", "опоздала", "проблема", "плохо",
    "again", "broken", "error", "failure", "awful", "hate", "late", "problem", "bad",
}
INTENSIFIERS = {"просто", "невероятно", "чрезвычайно", "буквально", "абсолютно", "totally", "literally", "absolutely"}


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-zа-яё]+", text.lower(), flags=re.IGNORECASE))


def _signals(text: str) -> list[Signal]:
    low = text.lower()
    words = _words(text)
    found: list[Signal] = []
    for phrase, weight in PHRASES.items():
        if phrase in low:
            found.append(Signal("лексическая формула", phrase, weight, "устойчивый иронический маркер"))

    pos = sorted(words & POSITIVE)
    neg = sorted(words & NEGATIVE)
    if pos and neg:
        evidence = f"{', '.join(pos[:2])} ↔ {', '.join(neg[:2])}"
        found.append(Signal("оценочный контраст", evidence, 28, "положительная оценка соседствует с негативной ситуацией"))

    quoted = re.findall(r"[«\"]([^»\"]{1,40})[»\"]", text)
    if quoted:
        found.append(Signal("кавычки", quoted[0], 8, "кавычки могут дистанцировать автора от буквального смысла"))
    if re.search(r"[!?]{2,}", text):
        mark = re.search(r"[!?]{2,}", text).group(0)
        found.append(Signal("экспрессивная пунктуация", mark, 7, "повтор знаков усиливает экспрессию"))
    if re.search(r"\.{3,}", text):
        found.append(Signal("многоточие", "...", 4, "пауза может сигнализировать имплицитную оценку"))
    if re.search(r"🙃|😏|😉|🤡|👏", text):
        emoji = re.search(r"🙃|😏|😉|🤡|👏", text).group(0)
        found.append(Signal("эмодзи", emoji, 13, "эмодзи часто меняет буквальное прочтение"))
    ints = sorted(words & INTENSIFIERS)
    if ints:
        found.append(Signal("интенсификатор", ints[0], 5, "усилитель может участвовать в гиперболе"))
    if re.search(r"\b(никогда|всегда|все|никто|миллион|сто раз|never|always|everyone|million)\b", low):
        found.append(Signal("возможная гипербола", re.search(r"\b(никогда|всегда|все|никто|миллион|сто раз|never|always|everyone|million)\b", low).group(0), 7, "крайняя формулировка может быть небуквальной"))
    return found


DEFAULT_THRESHOLDS = (20, 45, 70)


def level_for(score: int, thresholds: tuple[int, int, int] = DEFAULT_THRESHOLDS) -> str:
    """Map a 0-100 score to a level name; *thresholds* = (low, moderate, high) upper bounds."""
    low, moderate, high = thresholds
    if score < low:
        return "низкий"
    if score < moderate:
        return "умеренный"
    if score < high:
        return "повышенный"
    return "высокий"


def _level(score: int) -> str:
    return level_for(score)


def analyze(text: str, thresholds: tuple[int, int, int] = DEFAULT_THRESHOLDS) -> Analysis:
    """Return a transparent heuristic estimate for *text*."""
    clean = " ".join(text.split())
    if not clean:
        return Analysis(0, "нет текста", (), ())
    signals = _signals(clean)
    raw = sum(s.weight for s in signals)
    # Several independent cues matter more than one cue repeated many times.
    diversity_bonus = max(0, len({s.name for s in signals}) - 1) * 3
    score = min(100, raw + diversity_bonus)
    parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+|\n+", clean) if p.strip()]
    ranked = tuple((part, min(100, sum(s.weight for s in _signals(part)))) for part in parts)
    ranked = tuple(sorted(ranked, key=lambda item: item[1], reverse=True))
    return Analysis(score, level_for(score, thresholds), tuple(signals), ranked)
