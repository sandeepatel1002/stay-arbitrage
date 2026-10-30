"""Engine 1 tests (v0.3.0): mocked Gemini, chips override, fail-fast on AI outage."""
import pytest

import app.engine_intent as eng
from app.ai_client import AIClientError
from app.ai_schemas import IntentSchema
from app.engine_intent import parse
from tests.conftest import ai_down, fake_gemini


def _fake_intent(city="indore", guests=2, max_budget=None, filters=()):
    def fake(engine_name, system_prompt, user_prompt, schema_cls, temperature=0.2, max_tokens=700):
        assert schema_cls is IntentSchema
        assert "Traveler message" in user_prompt  # prompt contract respected
        return (
            IntentSchema(city=city, guests=guests, max_budget=max_budget, semantic_filters=list(filters)),
            None,
        )
    return fake


def test_llm_parse_extracts_intent(monkeypatch):
    monkeypatch.setattr(eng, "complete_json", _fake_intent(city="jaipur", max_budget=8500))
    intent, tele = parse("sunny haveli in jaipur under 8500", {})
    assert intent.city == "jaipur"
    assert intent.max_budget == 8500


def test_semantic_filters_flow_through(monkeypatch):
    from app.ai_schemas import SemanticFilter

    monkeypatch.setattr(eng, "complete_json", _fake_intent(city="indore", filters=[SemanticFilter(type="proximity", value="56 Dukan")]))
    intent, _ = parse("indore near 56 Dukan", {})
    assert any(f.type == "proximity" and f.value == "56 Dukan" for f in intent.semantic_filters)


def test_chips_win_over_message(monkeypatch):
    monkeypatch.setattr(eng, "complete_json", _fake_intent(city="jaipur", max_budget=5000))
    intent, _ = parse("jaipur under 5000", {"city": "indore", "max_budget": 6000})
    assert intent.city == "indore"
    assert intent.max_budget == 6000


def test_empty_message_with_chips_skips_ai(monkeypatch):
    called = {"n": 0}

    def spy(*a, **k):
        called["n"] += 1
        raise AssertionError("LLM must not be called for an empty message")

    monkeypatch.setattr(eng, "complete_json", spy)
    intent, tele = parse("", {"city": "Jaipur"})
    assert intent.city == "jaipur"
    assert tele is None
    assert called["n"] == 0


def test_ai_down_fails_fast(monkeypatch):
    ai_down(monkeypatch)
    with pytest.raises(AIClientError):
        parse("peaceful indore", {})


def test_full_gemini_style_happy_path(monkeypatch):
    """The conftest canned parser: message → city/budget/filters like the probe showed."""
    fake_gemini(monkeypatch)
    intent, tele = parse("peaceful place in indore near 56 Dukan, elderly parents coming, under 8000", {})
    assert intent.city == "indore"
    assert intent.max_budget == 8000
    ftypes = {f.type for f in intent.semantic_filters}
    assert {"vibe", "needs", "proximity"} <= ftypes
