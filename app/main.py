"""StayArbitrage FastAPI app — v0.3.0: Gemini-powered, fail-fast.

Serves the single-page frontend at `/` plus the JSON API (spec §5). Engine 1
parses informal intent, Engine 2 curates the 3-hotel podium, Engine 3 narrates
perk value (all via Google AI Studio Gemini). Owner-directed fail-fast policy:
unreachable APIs → HTTP 503 with a clear, friendly message — never silent
substitute data. All money math stays in `app/pricing.py`.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from app import config
from app.ai_client import AIClientError
from app.engine_intent import parse as intent_parse
from app.engine_match import pick as match_pick
from app.engine_perks import narrate as perks_narrate
from app.models import DealMatrix
from app.pricing import compute_true_cost
from app.serpapi_client import SerpApiClient, SerpApiError, breakdown_counts, grouped_amenities

STATIC_INDEX = Path(__file__).resolve().parent.parent / "static" / "index.html"

app = FastAPI(title="StayArbitrage", version="0.3.1")
serp = SerpApiClient()


class Chips(BaseModel):
    city: Optional[str] = None
    dates: Optional[str] = None
    guests: Optional[int] = None
    max_budget: Optional[int] = None
    check_in: Optional[str] = None
    check_out: Optional[str] = None


class SearchRequest(BaseModel):
    message: str = ""
    chips: Chips = Chips()


_FIELD_HINTS = {
    "city": "the destination city",
    "check_in": "a check-in date",
    "check_out": "a check-out date",
    "guests": "the number of guests",
}


def _clean_date(raw) -> Optional[str]:
    """ISO date string in, canonical ISO string out — None when unreadable/absent."""
    if not raw:
        return None
    try:
        return date.fromisoformat(str(raw).strip()).isoformat()
    except ValueError:
        return None


def _nights(check_in: str, check_out: str) -> int:
    return (date.fromisoformat(check_out) - date.fromisoformat(check_in)).days


def _booking_gate(intent, chips: dict) -> Optional[dict]:
    """Must-pass booking parameters (owner rule): city, check-in, check-out, guests.

    The app NEVER invents a stay window. Returns a 422 body listing what the
    user still needs to supply (structured `missing` so the UI can prompt with
    a form), or None when everything required is present and sane.
    """
    problems: list[str] = []
    missing: list[str] = []

    city = (intent.city or "").strip()
    city = city if city else None
    if not city:
        missing.append("city")

    guests = intent.guests
    if guests is None:
        missing.append("guests")
    elif not 1 <= int(guests) <= 16:
        problems.append("Guests must be between 1 and 16 — hotels don't quote rooms for zero or twenty.")

    chips_ci = chips.get("check_in")
    if chips_ci and not _clean_date(chips_ci):
        problems.append("That check-in date isn't readable — pick it from the date box.")

    ci = _clean_date(chips_ci) if _clean_date(chips_ci) else (
        intent.check_in.isoformat() if intent.check_in else None
    )
    chips_co = chips.get("check_out")
    if chips_co and not _clean_date(chips_co):
        problems.append("That check-out date isn't readable — pick it from the date box.")
    co = _clean_date(chips_co) if _clean_date(chips_co) else (
        intent.check_out.isoformat() if intent.check_out else None
    )

    if not ci:
        missing.append("check_in")
    if not co:
        missing.append("check_out")

    if ci and co:
        today = date.today().isoformat()
        if ci < today:
            problems.append("Check-in can't be in the past (today is " + today + ") — pick a future date.")
        if co <= ci:
            problems.append("Check-out must be after check-in.")
        elif _nights(ci, co) > 30:
            problems.append("Stays longer than 30 nights aren't searchable — pick a shorter window.")

    if not missing and not problems:
        return None

    lines = list(problems)
    if missing:
        lines.append(
            "Before I can quote real hotels I still need: "
            + ", ".join(_FIELD_HINTS[f] for f in missing) + "."
        )
    return {
        "detail": " ".join(lines),
        "missing": missing,
        "problems": problems or None,
        "partial": {"city": city, "guests": guests, "check_in": ci, "check_out": co},
    }


def _match_view(slot: str, hotel, why: str) -> dict:
    return {
        "slot": slot,
        "slot_label": {
            "best_overall_match": "Best Overall Match",
            "value_pick": "Value Pick",
            "premium_gem": "Premium Gem",
        }.get(slot, slot.replace("_", " ").title()),
        "property_token": hotel.property_token,
        "name": hotel.name,
        "city": hotel.city,
        "rate_per_night": hotel.rate_per_night,
        "total_rate": hotel.total_rate,
        "stars": hotel.stars,
        "review_score": hotel.review_score,
        "amenities": hotel.amenities,
        "nearby_places": hotel.nearby_places,
        "why_fits_you": why,
    }


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_INDEX, media_type="text/html")


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "serpapi": "ok" if config.SERPAPI_API_KEY else "missing",
        "ai": "ok" if config.GEMINI_API_KEY else "missing",
        "version": app.version,
    }


def _fail(exc: Exception) -> JSONResponse:
    """Fail-fast 503: a clear message instead of substitute data or a stack dump."""
    if isinstance(exc, SerpApiError):
        return JSONResponse(status_code=503, content={"detail": f"Live hotel data unavailable: {exc}"})
    return JSONResponse(
        status_code=503,
        content={"detail": f"AI service unavailable: {exc}"},
    )


@app.post("/api/search")
def search(req: SearchRequest):
    """Intent (Engine 1) → must-pass gate → candidate pool → podium (Engine 2).

    Missing must-pass parameters (city, dates, guests) → friendly 422 prompt;
    API failures → 503 with a clear message.
    """
    chips = req.chips.model_dump()
    try:
        intent, intent_tele = intent_parse(req.message or "", chips)
    except (SerpApiError, AIClientError) as exc:
        return _fail(exc)

    gate = _booking_gate(intent, chips)
    if gate is not None:
        return JSONResponse(status_code=422, content=gate)

    # Gate passed: every must-pass parameter is present and validated.
    check_in = _clean_date(chips.get("check_in")) or (
        intent.check_in.isoformat() if intent.check_in else None
    )
    check_out = _clean_date(chips.get("check_out")) or (
        intent.check_out.isoformat() if intent.check_out else None
    )
    guests = int(intent.guests)

    try:
        candidates, pool_tele = serp.candidate_pool(
            intent.city, guests=guests, check_in=check_in, check_out=check_out
        )

        # Budget is a hard API parameter (spec §4.1): filter BEFORE matching.
        if intent.max_budget:
            within = [c for c in candidates if (c.rate_per_night or 1 << 30) <= intent.max_budget]
            if within:
                candidates = within

        podium, match_tele = match_pick(intent, candidates)
    except (SerpApiError, AIClientError) as exc:
        return _fail(exc)

    return {
        "intent": {
            "city": intent.city,
            "dates": chips.get("dates"),
            "guests": guests,
            "max_budget": intent.max_budget,
            "check_in": check_in,
            "check_out": check_out,
            "nights": _nights(check_in, check_out),
            "semantic_filters": [f.model_dump() for f in intent.semantic_filters],
            "message_echo": req.message,
        },
        "matches": [_match_view(slot, hotel, why) for slot, hotel, why in podium],
        "telemetry": [t for t in (intent_tele, pool_tele, match_tele) if t is not None],
    }


@app.get("/api/property/{property_token}")
def property_details(property_token: str, guests: Optional[int] = None, check_in: Optional[str] = None, check_out: Optional[str] = None):
    """Details → OTA fares → deterministic True-Cost math → Engine 3 narration.

    Quotes are stay TOTALS, so the user's own dates + guests are required here
    too (the UI always passes them from the podium's search). Missing or nonsensical
    values → friendly 422 prompt; API failures → 503.
    """
    ci = _clean_date(check_in)
    co = _clean_date(check_out)
    today = date.today().isoformat()
    problems: list[str] = []
    if not ci or not co:
        problems.append("This screen quotes prices for a whole stay — pick check-in and check-out dates first (run a search).")
    if guests is None:
        problems.append("Tell me how many guests are staying.")
    elif not 1 <= guests <= 16:
        problems.append("Guests must be between 1 and 16.")
    if ci and co:
        if ci < today:
            problems.append("Check-in can't be in the past (today is " + today + ").")
        if co <= ci:
            problems.append("Check-out must be after check-in.")
        elif _nights(ci, co) > 30:
            problems.append("Stays longer than 30 nights aren't searchable.")
    if problems:
        return JSONResponse(status_code=422, content={"detail": " ".join(problems)})

    try:
        detail, source, tele = serp.property_details(
            property_token, check_in=ci, check_out=co, adults=guests
        )
        fares = serp.parse_fares(detail)
        matrix: DealMatrix = compute_true_cost(property_token, fares, guests=guests)
        notes, perk_tele = perks_narrate(fares, matrix, guests=guests)
    except SerpApiError as exc:
        return _fail(exc)
    except AIClientError as exc:
        return _fail(exc)

    # Stay window actually quoted by SerpApi — the user's own, never assumed.
    stay = {"check_in": ci, "check_out": co, "nights": _nights(ci, co)}

    price_tele_fmt = {
        "engine": "deterministic-true-cost-calculator",
        "latency_ms": 0,
        "source": source,
        "raw_json": {
            "cheapest_source": matrix.cheapest_source,
            "cheapest_price": matrix.cheapest_price,
            "highest_price": matrix.highest_price,
            "savings_inr": matrix.savings_inr,
            "savings_pct": matrix.savings_pct,
            "breakfast_adjusted_cheapest": matrix.breakfast_adjusted_cheapest,
        },
    }

    hotel_view = {
        "property_token": property_token,
        "name": detail.get("name") or property_token,
        "ratings": detail.get("ratings"),
        "reviews_breakdown": breakdown_counts(detail),
        "verified_amenities": grouped_amenities(detail),
    }

    return {
        "hotel": hotel_view,
        "fares": [f.model_dump() for f in matrix.fares],
        "savings_inr": matrix.savings_inr,
        "savings_pct": matrix.savings_pct,
        "cheapest_source": matrix.cheapest_source,
        "breakfast_adjusted_cheapest": matrix.breakfast_adjusted_cheapest,
        "perk_value_notes": notes,
        "stay": stay,
        "telemetry": [tele, price_tele_fmt, perk_tele],
    }


@app.exception_handler(Exception)
def quiet_500(request, exc):
    """Last-resort: 500s return clean JSON `{detail}` — never a bare stack dump."""
    return JSONResponse(status_code=500, content={"detail": "Something went wrong — try again."})
