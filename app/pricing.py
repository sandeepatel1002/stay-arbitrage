"""Deterministic True-Cost Calculator (spec §4.4).

PURE PYTHON — no LLM ever touches money (spec Golden Rule). Unit-tested to the
rupee in tests/test_pricing.py.
"""
from __future__ import annotations

from app.config import BREAKFAST_COST_PER_PERSON_INR
from app.models import DealMatrix, OtaFare


def _price_list(fares: list[OtaFare]) -> list[int]:
    return [f.total_price for f in fares if f.total_price is not None]


def compute_true_cost(
    property_token: str,
    fares: list[OtaFare],
    guests: int = 2,
) -> DealMatrix:
    """Compute exact price differences and rupee savings for one hotel.

    - cheapest/highest are the *total* prices actually shown to the user.
    - breakfast_adjusted_cheapest adds a deterministic assumed breakfast cost
      when the cheapest OTA does NOT include breakfast (breakfast ≈ ₹450/person,
      spec constant). This is the "real net value" arithmetic Engine 3 narrates.
    """
    prices = _price_list(fares)
    if not prices:
        return DealMatrix(property_token=property_token, fares=fares)

    cheapest_price = min(prices)
    highest_price = max(prices)
    cheapest_idx = prices.index(cheapest_price)
    cheapest_fare = fares[cheapest_idx]

    breakfast_adjusted = None
    if guests >= 2 and cheapest_fare.breakfast is not True and cheapest_price is not None:
        breakfast_adjusted = cheapest_price + BREAKFAST_COST_PER_PERSON_INR * guests

    savings_inr = highest_price - cheapest_price
    savings_pct = round(savings_inr / highest_price * 100, 1) if highest_price > 0 else 0.0

    return DealMatrix(
        property_token=property_token,
        fares=fares,
        cheapest_source=cheapest_fare.source,
        cheapest_price=cheapest_price,
        highest_price=highest_price,
        savings_inr=savings_inr,
        savings_pct=savings_pct,
        breakfast_adjusted_cheapest=breakfast_adjusted,
    )


def cheapest_fare(fares: list[OtaFare]) -> OtaFare | None:
    """Return the fare with the lowest total price (None if nothing priced)."""
    priced = [f for f in fares if f.total_price is not None]
    return min(priced, key=lambda f: f.total_price) if priced else None


def fare_flexibility(fare: OtaFare) -> bool:
    """True when the fare looks refundable (free_cancellation text present)."""
    return bool(fare.free_cancellation)
