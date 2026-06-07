from app.ml.text_model import TextInsightModel


def test_negative_delivery_complaint_is_high_priority():
    model = TextInsightModel(max_text_length=4000, max_tokens=256)
    result = model.generate(
        "Курьер опоздал на два дня, поддержка не отвечает. Срочно верните деньги!",
        creativity=0.3,
        max_tokens=160,
    )
    assert result.sentiment == "negative"
    assert result.category == "delivery"
    assert result.urgency == "high"
    assert result.metrics["confidence"] >= 0.5
    assert "опоздал" in result.metrics["explanations"]


def test_positive_support_message_is_positive():
    model = TextInsightModel(max_text_length=4000, max_tokens=256)
    result = model.generate("Спасибо, менеджер быстро помог решить вопрос с оплатой.", 0.2, 120)
    assert result.sentiment == "positive"
    assert result.urgency == "normal"
