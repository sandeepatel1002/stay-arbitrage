"""Engine 1 — Smart Intent Parser & Natural Filter (spec §4.1).

Informal text → hard params (city, budget, guests, dates) + semantic filters
(e.g. "near 56 Dukan", "peaceful", "elderly parents / elevator needed").
Chips always override the message. Fail-fast: an AI failure raises
AIClientError which the endpoint surfaces as HTTP 503 (owner-directed).
"""
from __future__ import annotations

from app.ai_client import complete_json
from app.ai_schemas import IntentSchema
from app.models import TelemetryRecord

_SYSTEM = (
    "You are the intent parser of an Indian hotel-booking app. "
    "Extract booking intent from the traveler's informal message. "
    "Return STRICT JSON with keys: city (string), check_in (YYYY-MM-DD or null), "
    "check_out (YYYY-MM-DD or null), guests (integer or null), "
    "max_budget (integer INR or null), search_query_expansion (string), "
    'semantic_filters: array of {"type": "proximity"|"needs"|"vibe", "value": string}. '
    'Examples: "near 56 Dukan" -> proximity("56 Dukan"); "peaceful" -> vibe("quiet/peaceful"); '
    '"elderly parents coming, lift needed" -> needs("elevator, step-free access"). '
    "Never invent values that are not stated. Budget is per night, INR."
)


def parse(message: str, chips: dict) -> tuple[IntentSchema, TelemetryRecord | None]:
    """LLM parse (fail-fast); chips fields always win (spec §4.1)."""
    user_text = (message or "").strip()
    tele: TelemetryRecord | None = None
    if not user_text:
        # No message → chips (or defaults) carry the whole request.
        city = str(chips.get("city") or "").strip().lower()
        intent = IntentSchema(city=city)
    else:
        user_prompt = f"Traveler message: {user_text}\nChips already provided (these win on conflict): " + (
            ", ".join(f"{k}={v}" for k, v in chips.items() if v is not None) or "none"
        )
        intent, tele = complete_json("engine1:intent-parser", _SYSTEM, user_prompt, IntentSchema)

    # Chips override everything the message said.
    if chips.get("city"):
        intent.city = str(chips["city"]).strip().lower()
    if chips.get("guests"):
        intent.guests = int(chips["guests"])
    if chips.get("max_budget"):
        intent.max_budget = int(chips["max_budget"])
    if not intent.city:
        intent.city = ""  # empty → endpoint asks the user for a city

    return intent, tele
