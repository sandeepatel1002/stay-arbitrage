"""Engine 3 — Perk & Policy Value Equivalence (spec §4.3).

Evaluates OTA fares (free-cancellation dates, breakfast inclusion) into "real
net value" notes. A deterministic rule helper pre-computes all money facts;
the LLM ONLY narrates those pre-supplied numbers (LLMs never do arithmetic —
spec Golden Rule). Fail-fast: an AI failure raises AIClientError → HTTP 503
(owner-directed, no template substitute).
"""
from __future__ import annotations

from typing import Any

from app.ai_client import AIClientError, complete_json
from app.ai_schemas import PerkValueSchema
from app.config import BREAKFAST_COST_PER_PERSON_INR
from app.models import DealMatrix, OtaFare, TelemetryRecord

_SYSTEM = (
    "You are the perk & policy value analyzer of an Indian hotel-booking app. You receive "
    "one hotel's OTA fare list with PRE-COMPUTED facts (prices, savings vs cheapest, "
    "refundability dates, breakfast status). Write one short note per platform explaining "
    "its real net value: e.g. '₹12,670 total, fully refundable till Nov 5 — effectively "
    "risk-free' or '₹200 cheaper but breakfast ₹450/person NOT included'. Only use the "
    "numbers provided — never compute new arithmetic. Return STRICT JSON: "
    '{"notes": [{"source": <exact source name>, "net_value_note": "...", '
    '"verdict": "best_flexibility"|"best_value"|"premium_feel"|null}]} '
    "Notes ≤ 160 characters, spoken-style, one per platform."
)


def perk_facts(fares: list[OtaFare], matrix: DealMatrix, guests: int) -> list[dict[str, Any]]:
    """Deterministic money facts fed to the prompt (no arithmetic by the LLM)."""
    facts: list[dict[str, Any]] = []
    cheapest = matrix.cheapest_price
    for f in fares:
        if f.total_price is None:
            facts.append({"source": f.source, "total_price": None})
            continue
        delta = f.total_price - cheapest if cheapest is not None else None
        breakfast_addon = None
        if guests >= 2 and f.breakfast is not True:
            breakfast_addon = BREAKFAST_COST_PER_PERSON_INR * guests
        facts.append(
            {
                "source": f.source,
                "total_price": f.total_price,
                "cheaper_than_max_by_inr": (matrix.highest_price - f.total_price) if matrix.highest_price else 0,
                "costlier_than_cheapest_inr": delta if delta is not None else 0,
                "free_cancellation": f.free_cancellation,
                "breakfast_included": f.breakfast,
                "if_add_breakfast_total_inr": (f.total_price + breakfast_addon) if breakfast_addon and f.total_price else None,
                "link": f.link,
            }
        )
    return facts


def _fact_block(facts: list[dict[str, Any]]) -> str:
    lines = []
    for f in facts:
        parts = [f"- source={f['source']}"]
        if f.get("total_price") is not None:
            parts.append(f"total_price=₹{f['total_price']}")
            if f.get("costlier_than_cheapest_inr"):
                parts.append(f"costlier_than_cheapest=₹{f['costlier_than_cheapest_inr']}")
            if f.get("cheaper_than_max_by_inr"):
                parts.append(f"cheaper_than_max=₹{f['cheaper_than_max_by_inr']}")
            if f["free_cancellation"]:
                parts.append(f"free_cancellation='{f['free_cancellation']}'")
            parts.append(f"breakfast_included={str(bool(f.get('breakfast_included'))).lower()}")
            if f.get("if_add_breakfast_total_inr"):
                parts.append(f"if_add_breakfast_total=₹{f['if_add_breakfast_total_inr']}")
        lines.append(" ".join(parts))
    return "\n".join(lines)


def narrate(fares: list[OtaFare], matrix: DealMatrix, guests: int = 2) -> tuple[dict[str, dict[str, Any]], TelemetryRecord]:
    """→ {source: {"net_value_note": str, "verdict": str|None}, ...} + telemetry."""
    facts = perk_facts(fares, matrix, guests)
    if not facts:
        raise AIClientError("No priced platforms to narrate — fare list is empty.")

    schema, tele = complete_json(
        "engine3:perk-value",
        _SYSTEM,
        f"Cheapest total = ₹{matrix.cheapest_price}; highest total = ₹{matrix.highest_price} "
        f"(savings ₹{matrix.savings_inr} / {matrix.savings_pct}%). Guests={guests}. "
        f"Facts:\n{_fact_block(facts)}",
        PerkValueSchema,
    )

    fact_by_source = {f["source"].strip().lower(): f for f in facts}
    notes_by_source: dict[str, dict[str, Any]] = {}
    for note in schema.notes:
        fact = fact_by_source.get(note.source.strip().lower())
        if fact is None:
            continue  # hallucinated platform → dropped, never shown
        notes_by_source[fact["source"]] = {
            "net_value_note": note.net_value_note,
            "verdict": note.verdict,
        }

    if not notes_by_source:
        raise AIClientError("Perk analyzer returned notes for none of the quoted platforms.")
    return notes_by_source, tele
