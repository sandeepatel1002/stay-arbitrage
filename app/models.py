"""Internal data contracts (spec §3.3) — normalized models shared by every layer."""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class TelemetryRecord(BaseModel):
    """One observation of an AI or data operation, surfaced in the UI drawer."""

    engine: str
    model: str = "deterministic-python"
    latency_ms: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    raw_json: Optional[dict[str, Any]] = None
    source: str = Field(pattern="^(live|cache|mock)$")


class HotelCandidate(BaseModel):
    """One hotel from a SerpApi search response (spec §3.1 search targets)."""

    property_token: str
    name: str
    city: str
    rate_per_night: Optional[int] = None
    total_rate: Optional[int] = None
    stars: Optional[int] = None
    review_score: Optional[float] = None
    amenities: list[str] = []
    nearby_places: list[dict[str, Any]] = []


class OtaFare(BaseModel):
    """One platform's deal for one hotel (spec §3.1 detail targets)."""

    source: str
    base_price: Optional[int] = None
    total_price: Optional[int] = None
    free_cancellation: Optional[str] = None
    breakfast: bool = False
    link: str = ""


class DealMatrix(BaseModel):
    """Arbitrage math for one hotel — computed ONLY by deterministic Python."""

    property_token: str
    fares: list[OtaFare]
    cheapest_source: Optional[str] = None
    cheapest_price: Optional[int] = None
    highest_price: Optional[int] = None
    savings_inr: int = 0
    savings_pct: float = 0.0
    breakfast_adjusted_cheapest: Optional[int] = None
