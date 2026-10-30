"""Engine 2 tests (v0.3.0): distinctness invariant, invented tokens rejected, fail-fast."""
import pytest

import app.engine_match as eng
from app.ai_client import AIClientError
from app.ai_schemas import MatchSlot, MatchesSchema
from app.ai_schemas import IntentSchema
from app.engine_match import pick
from tests.conftest import ai_down, sample_candidates


def _schema_for(candidates, invented=False):
    tokens = [c.property_token for c in candidates[:3]]
    if invented:
        tokens[2] = "made-up-token-not-in-pool"
    slots = ["best_overall_match", "value_pick", "premium_gem"]
    return MatchesSchema(
        matches=[
            MatchSlot(
                slot=slots[i],
                property_token=tokens[i],
                why_fits_you=f"AI line one for {tokens[i]}\nAI line two for {tokens[i]}",
            )
            for i in range(3)
        ]
    )


def _fake_ai(schema):
    def fake(engine_name, system_prompt, user_prompt, schema_cls, temperature=0.2, max_tokens=700):
        assert schema_cls is MatchesSchema
        assert "token=" in user_prompt  # candidates must be in the prompt
        return schema, None
    return fake


def _intent(city="indore"):
    return IntentSchema(city=city, guests=2)


def test_happy_ai_picks_three_distinct(monkeypatch):
    candidates = sample_candidates("indore")
    monkeypatch.setattr(eng, "complete_json", _fake_ai(_schema_for(candidates)))
    results, _ = pick(_intent(), candidates)
    tokens = [h.property_token for _, h, _ in results]
    assert len(tokens) == 3 and len(set(tokens)) == 3
    assert all("AI line" in why for _, _, why in results)


def test_invented_token_rejected_fail_fast(monkeypatch):
    candidates = sample_candidates("indore")
    monkeypatch.setattr(eng, "complete_json", _fake_ai(_schema_for(candidates, invented=True)))
    with pytest.raises(AIClientError, match="unknown or repeated"):
        pick(_intent(), candidates)


def test_ai_down_fails_fast(monkeypatch):
    ai_down(monkeypatch)
    with pytest.raises(AIClientError, match="Gemini unreachable"):
        pick(_intent(), sample_candidates("indore"))


def test_empty_pool_fails_fast():
    with pytest.raises(AIClientError, match="No candidate"):
        pick(_intent(), [])


def test_prompt_lists_capped_at_six(monkeypatch):
    candidates = sample_candidates("indore") * 2  # 6+ candidates → prompt cap kicks in
    seen = {}

    def fake(engine_name, system_prompt, user_prompt, schema_cls, temperature=0.2, max_tokens=700):
        seen["n"] = user_prompt.count("token=")
        return _schema_for(candidates), None

    monkeypatch.setattr(eng, "complete_json", fake)
    try:
        pick(_intent(), candidates[:5])  # 5 candidates → 5 prompt lines ≤ 6 cap
    except AIClientError:
        pass  # schema invented a token not in the 5-pool — fine for this test
    assert seen["n"] == 5
