from ironylab import analyze


def test_empty_text():
    result = analyze("   ")
    assert result.score == 0
    assert result.level == "нет текста"


def test_neutral_text_is_low():
    assert analyze("Заседание начинается в десять часов.").score < 20


def test_contrast_scores_higher_than_neutral():
    ironic = analyze("Прекрасно, опять сломался принтер!")
    neutral = analyze("Принтер находится в кабинете.")
    assert ironic.score > neutral.score
    assert any(signal.name == "оценочный контраст" for signal in ironic.signals)


def test_score_is_bounded():
    text = "Ну да, конечно! Просто прекрасно!!! Опять всё сломано 🙃"
    assert 0 <= analyze(text).score <= 100


def test_english_marker():
    assert analyze("Yeah right, this is just great again!").score >= 20

