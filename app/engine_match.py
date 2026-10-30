"""Engine 2 — Personalized "Why This Fits You" Matchmaker (spec §4.2).

Ranks the SerpApi candidate pool into EXACTLY 3 distinct podium slots —
Best Overall Match / Value Pick / Premium Gem — each with a 2-line personalized
badge grounded in amenities and review data. Validated hard (3 distinct tokens
that exist in the pool, 2-line text). Fail-fast: anything invalid raises
AIClientError → HTTP 503 (owner-directed, no deterministic substitute).
"""
from __future__ import annotations

from typing import Optional

from app.ai_client import AIClientError, complete_json
from app.ai_schemas import IntentSchema, MatchesSchema
from app.models import HotelCandidate, TelemetryRecord

_SYSTEM = (
    "You are the matchmaker of an Indian hotel-booking app. You receive the traveler's "
    "parsed needs and a numbered candidate list of hotels (token, name, stars, review "
    "score, price/night INR, amenities, nearby places). Pick EXACTLY 3 DISTINCT hotels "
    "for these slots: best_overall_match (best fit for the stated needs), value_pick "
    "(best for the money), premium_gem (most special/upgraded). "
    "STRICT RULES: (1) copy property_token EXACTLY as given in the candidate list "
    "(e.g. 'indore-2-radisson-blu') — NEVER use the row number like '1' or '#1'; "
    "(2) why_fits_you is EXACTLY 2 lines separated by \\n — line1 = how it matches the "
    "user's stated needs (amenity or location), line2 = evidence-grounded reason citing "
    "a review strength or price value; never repeat a hotel across slots. "
    'Return STRICT JSON: {"matches": [{"slot": "best_overall_match"|"value_pick"|'
    '"premium_gem", "property_token": "...", "why_fits_you": "line1\\nline2"}]}. '
    'Example why_fits_you: "Lift and quiet rooms cover your parents\' mobility needs.\\n'
    'Rated 9.1/10 with 1,544 excellent reviews, and only 0.9 km from 56 Dukan."'
)

_TEMPLATE = "#%d • token=%s • name=%s • %s★ • score %s/10 • ₹%s/night • amenities: %s • nearby: %s"


def _candidate_lines(candidates: list[HotelCandidate]) -> str:
    lines = []
    for i, c in enumerate(candidates, 1):
        nearby = ", ".join(p.get("name", "") for p in (c.nearby_places or [])[:2])
        lines.append(
            _TEMPLATE
            % (
                i,
                c.property_token,
                c.name,
                c.stars or "?",
                c.review_score or "?",
                c.rate_per_night if c.rate_per_night is not None else "?",
                ", ".join(c.amenities[:6]).lower() or "n/a",
                nearby.lower() or "n/a",
            )
        )
    return "\n".join(lines)


def _intent_summary(intent: IntentSchema) -> str:
    parts = [f"city={intent.city}", f"guests={intent.guests or 2}"]
    if intent.max_budget:
        parts.append(f"budget=₹{intent.max_budget}/night")
    if intent.semantic_filters:
        parts += [f"{f.type}: {f.value}" for f in intent.semantic_filters]
    return "; ".join(parts)


def pick(
    intent: IntentSchema,
    candidates: list[HotelCandidate],
) -> tuple[list[tuple[str, HotelCandidate, str]], Optional[TelemetryRecord]]:
    """→ [(slot, hotel, why_fits_you), ...] exactly 3 distinct, else AIClientError.

    Guardrails kept from spec §4.2 (now fail-fast instead of fallback):
    token must exist in the pool, slots must be 3 distinct hotels.
    """
    if not candidates:
        raise AIClientError("No candidate hotels survived the search budget filter — widen the ask.")

    # Keep the prompt lean: the 6 strongest candidates bound tokens & latency.
    prompt_candidates = sorted(
        candidates,
        key=lambda c: ((c.review_score or 0), -(c.rate_per_night or 0)),
        reverse=True,
    )[:6]
    schema, tele = complete_json(
        "engine2:matchmaker",
        _SYSTEM,
        f"Traveler needs: {_intent_summary(intent)}\n\nCandidates:\n{_candidate_lines(prompt_candidates)}",
        MatchesSchema,
    )

    by_token = {c.property_token: c for c in candidates}
    results: list[tuple[str, HotelCandidate, str]] = []
    seen: set[str] = set()
    for m in schema.matches:
        hotel = by_token.get(m.property_token)
        if hotel is None or hotel.property_token in seen:
            raise AIClientError(
                f"Matchmaker returned an unknown or repeated hotel ({m.property_token!r}) — refusing to show it."
            )
        results.append((m.slot, hotel, m.why_fits_you))
        seen.add(hotel.property_token)

    if len(results) != 3:
        raise AIClientError(f"Matchmaker returned {len(results)}/3 podium slots — cannot render a partial podium.")
    return results, tele
