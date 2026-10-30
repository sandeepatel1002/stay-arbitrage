"""Engine 3 tests (v0.3.0): facts math, narration mapping, fail-fast on outage."""
import pytest

import app.engine_perks as eng
from app.ai_client import AIClientError
from app.ai_schemas import PerkNote, PerkValueSchema
from app.engine_perks import narrate, perk_facts
from app.models import OtaFare
from app.pricing import compute_true_cost
from tests.conftest import ai_down, sample_details
from app.serpapi_client import SerpApiClient

_api = SerpApiClient()


def _setup(token="indore-1-effotel-sayaji"):
    fares = _api.parse_fares(sample_details(token))
    matrix = compute_true_cost(token, fares, guests=2)
    return fares, matrix


def _fake_ai(schema):
    def fake(engine_name, system_prompt, user_prompt, schema_cls, temperature=0.2, max_tokens=700):
        assert schema_cls is PerkValueSchema
        assert "costlier_than_cheapest" in user_prompt or "total_price" in user_prompt
        return schema, None
    return fake


def test_perk_facts_money_math():
    fares, matrix = _setup()
    facts = {f["source"]: f for f in perk_facts(fares, matrix, guests=2)}
    by_price = {f.source: f.total_price for f in fares}
    agoda = facts["Agoda"]
    assert agoda["total_price"] == by_price["Agoda"]
    assert agoda["costlier_than_cheapest_inr"] == by_price["Agoda"] - matrix.cheapest_price
    # Agoda room-only, 2 guests → breakfast add-on fact present.
    assert agoda["if_add_breakfast_total_inr"] == by_price["Agoda"] + 2 * 450


def test_narrate_with_mocked_ai(monkeypatch):
    fares, matrix = _setup()
    sources = [f.source for f in fares if f.total_price is not None]
    schema = PerkValueSchema(
        notes=[PerkNote(source=s, net_value_note=f"AI note for {s} with ₹1,234 fact", verdict=None) for s in sources]
    )
    monkeypatch.setattr(eng, "complete_json", _fake_ai(schema))
    notes, _ = narrate(fares, matrix, guests=2)
    assert set(notes) >= set(sources)
    assert any("AI note" in n["net_value_note"] for n in notes.values())


def test_hallucinated_source_dropped_but_real_kept(monkeypatch):
    fares, matrix = _setup()
    real = [f.source for f in fares if f.total_price is not None]
    schema = PerkValueSchema(
        notes=[PerkNote(source="GhostOTA", net_value_note="hallucinated platform note 99")]
        + [PerkNote(source=s, net_value_note=f"real note for {s}, ₹valid", verdict=None) for s in real]
    )
    monkeypatch.setattr(eng, "complete_json", _fake_ai(schema))
    notes, _ = narrate(fares, matrix, guests=2)
    assert "GhostOTA" not in notes
    assert set(notes) == set(real)


def test_zero_matching_notes_fails_fast(monkeypatch):
    fares, matrix = _setup()
    schema = PerkValueSchema(
        notes=[PerkNote(source="GhostOTA", net_value_note="hallucinated platform note 99")]
    )
    monkeypatch.setattr(eng, "complete_json", _fake_ai(schema))
    with pytest.raises(AIClientError, match="none of the quoted platforms"):
        narrate(fares, matrix, guests=2)


def test_ai_down_fails_fast(monkeypatch):
    ai_down(monkeypatch)
    fares, matrix = _setup()
    with pytest.raises(AIClientError):
        narrate(fares, matrix, guests=2)


def test_unpriced_fare_kept_in_facts():
    fares = [OtaFare(source="NoData OTA", total_price=None)]
    facts = perk_facts(fares, compute_true_cost("tok", fares, guests=2), 2)
    assert facts[0]["total_price"] is None
