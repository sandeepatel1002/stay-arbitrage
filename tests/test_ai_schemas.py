"""Schema contract tests (spec §4) — validators must hard-reject malformed AI output."""
import pytest
from pydantic import ValidationError

from app.ai_schemas import IntentSchema, MatchesSchema, MatchSlot, PerkValueSchema


def test_intent_bad_dates_fail_soft():
    # Bad date strings become None instead of killing the parse (fail-soft).
    i = IntentSchema(city="Indore", check_in="not-a-date", check_out="2026-11-06")
    assert i.check_in is None
    assert i.check_out is not None


def test_intent_city_normalized():
    i = IntentSchema(city="  Indore ")
    assert i.city == "indore"


def _slot(name, token):
    return MatchSlot(slot=name, property_token=token, why_fits_you="line one\nline two")


def test_match_two_line_enforcement():
    with pytest.raises(ValidationError):
        MatchSlot(slot="value_pick", property_token="tok-abc", why_fits_you="only one line")


def test_match_requires_3_distinct_tokens():
    ok = MatchesSchema(matches=[
        _slot("best_overall_match", "a-token"),
        _slot("value_pick", "b-token"),
        _slot("premium_gem", "c-token"),
    ])
    assert len(ok.matches) == 3

    with pytest.raises(ValidationError):  # duplicate hotel across slots
        MatchesSchema(matches=[
            _slot("best_overall_match", "a-token"),
            _slot("value_pick", "a-token"),
            _slot("premium_gem", "c-token"),
        ])

    with pytest.raises(ValidationError):  # duplicate slot names
        MatchesSchema(matches=[
            _slot("best_overall_match", "a-token"),
            _slot("best_overall_match", "b-token"),
            _slot("premium_gem", "c-token"),
        ])


def test_perk_requires_distinct_sources():
    PerkValueSchema(notes=[{"source": "Agoda", "net_value_note": "low total here 123"}])

    with pytest.raises(ValidationError):
        PerkValueSchema(notes=[
            {"source": "Agoda", "net_value_note": "first note for agoda"},
            {"source": "AGODA", "net_value_note": "second note agoda again"},
        ])
