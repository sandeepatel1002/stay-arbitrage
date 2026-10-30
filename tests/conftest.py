"""Shared test fixtures (v0.3.0 fail-fast world).

- `data/sample_hotels_raw.json` is now purely a canned fixture (the offline
  cache was retired) — tests simulate SerpApi responses with it.
- AI engines are served canned Gemini-shaped answers via patched
  `complete_json` in every engine module — fast, deterministic, free.
"""
from __future__ import annotations

import json
import re
from typing import Any

import pytest

from app import config
from app.ai_schemas import IntentSchema, MatchSlot, MatchesSchema, PerkNote, PerkValueSchema
from app.models import TelemetryRecord
from app.serpapi_client import SerpApiClient, SerpApiError

SAMPLE: dict[str, Any] = json.loads(config.SAMPLE_HOTELS_PATH.read_text(encoding="utf-8"))
CITIES = [c for c in SAMPLE if not c.startswith("_")]
REAL_API = SerpApiClient()

# Canonical test stay (dates are required parameters now — never assumed).
from datetime import date, timedelta

TEST_CHECK_IN = (date.today() + timedelta(days=14)).isoformat()
TEST_CHECK_OUT = (date.today() + timedelta(days=17)).isoformat()
TEST_STAY = {"check_in": TEST_CHECK_IN, "check_out": TEST_CHECK_OUT}


def sample_search_payload(city: str) -> dict[str, Any]:
    return SAMPLE[city]["search"]


def sample_candidates(city: str, n: int = 6):
    return REAL_API.parse_candidates(sample_search_payload(city), city)[:n]


def sample_details(token: str) -> dict[str, Any] | None:
    for city in CITIES:
        detail = SAMPLE[city].get("details", {}).get(token)
        if detail is not None:
            return detail
    return None


def city_from_query(q: str) -> str:
    ql = (q or "").lower()
    return next((c for c in CITIES if c in ql), CITIES[0])


class FakeSerp:
    """Deterministic stand-in for the live SerpApi client, built from the fixture."""

    def search(self, q, check_in, check_out, adults=2):
        city = city_from_query(q)
        payload = sample_search_payload(city)
        return (
            payload,
            "live",
            TelemetryRecord(engine="serpapi:google_hotels", source="live", raw_json={"fixture": city}),
        )

    def property_details(self, property_token, check_in, check_out, adults=2):
        detail = sample_details(property_token)
        if detail is None:
            raise SerpApiError(f"fixture has no details for token {property_token}")
        return (
            detail,
            "live",
            TelemetryRecord(engine="serpapi:google_hotels_property", source="live"),
        )

    def candidate_pool(self, city, guests, check_in, check_out):
        payload, _, tele = self.search(f"Hotels in {city}", check_in, check_out, adults=guests)
        return REAL_API.parse_candidates(payload, city), tele

    def parse_fares(self, detail):
        return REAL_API.parse_fares(detail)


class AiDown:
    """Simulates the Gemini API being unreachable for every engine."""

    def __init__(self, msg: str = "simulated: Gemini unreachable"):
        self.msg = msg

    def __call__(self, *args, **kwargs):
        from app.ai_client import AIClientError

        raise AIClientError(self.msg)


def _auto_matches(user_prompt: str) -> MatchesSchema:
    """Build a valid podium from the tokens listed in the matchmaker prompt."""
    tokens = re.findall(r"token=([\w\-]+)", user_prompt)[:3]
    if len(tokens) < 3:  # mirrors the real engine: cannot fill a 3-slot podium
        from app.ai_client import AIClientError

        raise AIClientError("Matchmaker: fewer than 3 hotels fit this ask — widen the ask or budget.")
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


def _auto_notes(user_prompt: str) -> PerkValueSchema:
    """Build a note per platform named in the perk prompt (multi-word sources OK)."""
    sources = re.findall(r"source=(.+?)(?= \w+=|$)", user_prompt, re.M)
    return PerkValueSchema(
        notes=[
            PerkNote(source=s, net_value_note=f"AI perk note for {s} — refundable, ₹facts supplied", verdict=None)
            for s in sources
        ]
    )


def _auto_intent(user_prompt: str) -> IntentSchema:
    """Tiny rule parser for tests: city + guests + budget from the prompt text."""
    text = user_prompt.lower()
    city = next((c for c in CITIES if c in text), "")
    guests = None
    m = re.search(r"family of (\d+)|(\d+) adults", text)
    if m:
        guests = int(m.group(1) or m.group(2))
    budget = None
    m = re.search(r"under (?:₹)?([\d,]+)", text)
    if m:
        budget = int(m.group(1).replace(",", ""))
    filters = []
    if "peaceful" in text:
        filters.append({"type": "vibe", "value": "quiet/peaceful"})
    if "elderly" in text or "parent" in text:
        filters.append({"type": "needs", "value": "elevator, step-free access"})
    if "56 dukan" in text:
        filters.append({"type": "proximity", "value": "56 Dukan"})
    return IntentSchema(
        city=city, guests=guests, max_budget=budget,
        semantic_filters=filters,
    )


def fake_gemini(monkeypatch) -> None:
    """Serve canned, schema-shaped Gemini answers to all 3 engines deterministically."""
    import app.engine_intent as ei
    import app.engine_match as em
    import app.engine_perks as ep

    def fake(engine_name, system_prompt, user_prompt, schema_cls, temperature=0.2, max_tokens=700):
        tele = TelemetryRecord(
            engine=engine_name, model="gemini-test-fake", latency_ms=5, tokens_in=40, tokens_out=90, source="live",
        )
        if schema_cls is IntentSchema:
            return _auto_intent(user_prompt), tele
        if schema_cls is MatchesSchema:
            return _auto_matches(user_prompt), tele
        if schema_cls is PerkValueSchema:
            return _auto_notes(user_prompt), tele
        raise AssertionError(f"unexpected schema {schema_cls}")

    for mod in (ei, em, ep):
        monkeypatch.setattr(mod, "complete_json", fake)


def ai_down(monkeypatch, msg: str = "simulated: Gemini unreachable") -> None:
    import app.engine_intent as ei
    import app.engine_match as em
    import app.engine_perks as ep

    down = AiDown(msg)
    for mod in (ei, em, ep):
        monkeypatch.setattr(mod, "complete_json", down)


def fake_serp(monkeypatch):
    """Swap the app's live SerpApi client for the fixture-backed one."""
    import app.main as main_mod

    monkeypatch.setattr(main_mod, "serp", FakeSerp())
