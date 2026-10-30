"""Unit tests for the deterministic True-Cost Calculator (spec §4.4)."""
from app.models import OtaFare
from app.pricing import cheapest_fare, compute_true_cost, fare_flexibility


def _fare(source, total, cancel=None, breakfast=False):
    return OtaFare(source=source, base_price=total // 3, total_price=total, free_cancellation=cancel, breakfast=breakfast, link="https://example.com")


def test_savings_exact_rupees():
    fares = [_fare("Agoda", 12670), _fare("Booking.com", 12900), _fare("MakeMyTrip", 13350), _fare("Official Site", 14100)]
    m = compute_true_cost("tok-1", fares)
    assert m.cheapest_price == 12670
    assert m.cheapest_source == "Agoda"
    assert m.highest_price == 14100
    assert m.savings_inr == 14100 - 12670
    assert m.savings_pct == round((m.savings_inr / 14100) * 100, 1)


def test_breakfast_adjusted_cost():
    # Cheapest OTA has NO breakfast, 2 guests → +450*2
    fares = [_fare("Agoda", 10000), _fare("Booking.com", 10500, breakfast=True)]
    m = compute_true_cost("tok-2", fares, guests=2)
    assert m.breakfast_adjusted_cheapest == 10000 + 2 * 450


def test_no_breakfast_adjustment_when_included():
    fares = [_fare("Agoda", 10000, breakfast=True), _fare("Booking.com", 10500)]
    m = compute_true_cost("tok-3", fares, guests=2)
    assert m.breakfast_adjusted_cheapest is None


def test_empty_fares_zero_matrix():
    m = compute_true_cost("tok-4", [])
    assert m.savings_inr == 0
    assert m.cheapest_source is None


def test_cheapest_fare_and_flexibility():
    fares = [_fare("Agoda", 9000), _fare("Priceline", 8000, cancel="Free cancellation before 2026-11-05")]
    assert cheapest_fare(fares).source == "Priceline"
    assert fare_flexibility(fares[1]) is True
    assert fare_flexibility(fares[0]) is False
