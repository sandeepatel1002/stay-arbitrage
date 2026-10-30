"""FastAPI app tests (v0.3.0): Gemini-backed endpoints with fail-fast 503s.

SerpApi is fixture-backed (`fake_serp`), Gemini is canned (`fake_gemini`) —
the full happy path is exercised without network or key spend.
"""
import pytest
from fastapi.testclient import TestClient

from app import config
from app.main import app
from tests.conftest import TEST_CHECK_IN, TEST_CHECK_OUT

TEST_STAY = {"guests": 2, "check_in": TEST_CHECK_IN, "check_out": TEST_CHECK_OUT}


@pytest.fixture()
def http(monkeypatch):
    """TestClient with fixture-backed SerpApi + canned Gemini answers."""
    from tests.conftest import fake_gemini, fake_serp

    monkeypatch.setattr(config, "SERPAPI_API_KEY", "test-serp-key")
    monkeypatch.setattr(config, "GEMINI_API_KEY", "test-gemini-key")
    fake_serp(monkeypatch)
    fake_gemini(monkeypatch)
    return TestClient(app)


def test_index_serves(http):
    r = http.get("/")
    assert r.status_code == 200
    assert "StayArbitrage" in r.text


def test_health_with_keys(http):
    r = http.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["serpapi"] == "ok"
    assert body["ai"] == "ok"


def test_health_reports_missing_keys(monkeypatch):
    monkeypatch.setattr(config, "SERPAPI_API_KEY", "")
    monkeypatch.setattr(config, "GEMINI_API_KEY", "")
    client = TestClient(app)
    body = client.get("/api/health").json()
    assert body["serpapi"] == "missing"
    assert body["ai"] == "missing"


def test_search_full_happy_path(http):
    r = http.post("/api/search", json={"message": "peaceful place in indore near 56 dukan, elderly parents, under 8000", "chips": dict(TEST_STAY)})
    assert r.status_code == 200
    body = r.json()
    assert body["intent"]["city"] == "indore"
    assert body["intent"]["check_in"] == TEST_CHECK_IN  # user's own dates echoed back
    assert body["intent"]["nights"] == 3
    matches = body["matches"]
    assert len(matches) == 3
    assert len({m["property_token"] for m in matches}) == 3  # distinct podium
    for m in matches:
        assert len(m["why_fits_you"].splitlines()) == 2  # 2-line AI badge
    # telemetry: engine1 + serpapi + engine2, all "live"
    engines = {t["engine"] for t in body["telemetry"]}
    assert {"engine1:intent-parser", "serpapi:google_hotels", "engine2:matchmaker"} <= engines
    assert all(t["source"] == "live" for t in body["telemetry"])


def test_search_jaipur_second_city(http):
    r = http.post(
        "/api/search",
        json={"message": "family of 4 peaceful jaipur under 9000", "chips": {"check_in": TEST_CHECK_IN, "check_out": TEST_CHECK_OUT}},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["intent"]["city"] == "jaipur"
    assert body["intent"]["guests"] == 4
    assert len(body["matches"]) == 3


def test_chips_city_wins_over_message(http):
    r = http.post("/api/search", json={"message": "jaipur", "chips": {"city": "indore", **TEST_STAY}})
    assert r.status_code == 200
    assert r.json()["intent"]["city"] == "indore"


def test_no_city_is_friendly_422(http):
    r = http.post("/api/search", json={"message": "somewhere peaceful under 6000", "chips": dict(TEST_STAY)})
    assert r.status_code == 422
    assert "city" in r.json()["detail"].lower()
    assert "city" in r.json()["missing"]


def test_missing_dates_prompt_instead_of_assuming(http):
    """Owner rule: no invented 3-night default — missing dates → 422 prompt."""
    r = http.post("/api/search", json={"message": "peaceful indore", "chips": {"guests": 2}})
    assert r.status_code == 422
    body = r.json()
    assert set(body["missing"]) == {"check_in", "check_out"}
    assert "check-in date" in body["detail"].lower() or "dates" in body["detail"].lower()
    assert body["partial"]["city"] == "indore"


def test_missing_guests_prompted(http):
    r = http.post("/api/search", json={"message": "peaceful indore", "chips": dict(TEST_STAY, guests=None)})
    assert r.status_code == 422
    body = r.json()
    assert "guests" in body["missing"]
    assert "check_in" not in body["missing"]


def test_checkout_before_checkin_is_422(http):
    r = http.post(
        "/api/search",
        json={"message": "indore", "chips": {"guests": 2, "check_in": TEST_CHECK_OUT, "check_out": TEST_CHECK_IN}},
    )
    assert r.status_code == 422
    assert "after check-in" in r.json()["detail"]


def test_past_checkin_is_422(http):
    from datetime import timedelta

    r = http.post(
        "/api/search",
        json={"message": "indore", "chips": {"guests": 2, "check_in": "2020-01-01", "check_out": TEST_CHECK_OUT}},
    )
    assert r.status_code == 422
    assert "past" in r.json()["detail"].lower()


def test_budget_echo_and_filter(http):
    r = http.post("/api/search", json={"message": "indore", "chips": {"max_budget": 9000, **TEST_STAY}})
    assert r.status_code == 200
    body = r.json()
    assert body["intent"]["max_budget"] == 9000  # chips win
    rates = [m["rate_per_night"] for m in body["matches"]]
    assert all(x is not None and x <= 9000 for x in rates)


def test_too_narrow_budget_is_503(http):
    """Fail-fast: a budget that leaves only 1 hotel cannot fill a 3-slot podium."""
    r = http.post("/api/search", json={"message": "indore", "chips": {"max_budget": 2500, **TEST_STAY}})
    assert r.status_code == 503
    detail = r.json()["detail"].lower()
    assert "widen" in detail or "podium" in detail


def test_property_returns_matrix_with_savings(http):
    token = "indore-1-effotel-sayaji"
    r = http.get(f"/api/property/{token}", params=dict(TEST_STAY))
    assert r.status_code == 200
    body = r.json()
    assert body["hotel"]["name"] == "Effotel By Sayaji"
    assert len(body["fares"]) >= 2
    assert isinstance(body["savings_inr"], int) and body["savings_inr"] > 0
    prices = [f["total_price"] for f in body["fares"]]
    assert body["savings_inr"] == max(prices) - min(prices)
    priced = [f["source"] for f in body["fares"] if f["total_price"] is not None]
    assert set(body["perk_value_notes"]) >= set(priced)  # AI notes cover priced platforms
    assert body["stay"] == {
        "check_in": TEST_CHECK_IN,
        "check_out": TEST_CHECK_OUT,
        "nights": 3,
    }  # the user's own stay window, labeled so totals aren't mistaken for /night
    engines = {t.get("engine") for t in body["telemetry"] if isinstance(t, dict)}
    assert {"serpapi:google_hotels_property", "deterministic-true-cost-calculator", "engine3:perk-value"} <= engines


def test_property_without_dates_is_friendly_422(http):
    """No silent 3-night default here either — the matrix must quote a real stay."""
    r = http.get("/api/property/indore-1-effotel-sayaji")
    assert r.status_code == 422
    detail = r.json()["detail"].lower()
    assert "check-in" in detail or "dates" in detail
    r2 = http.get("/api/property/indore-1-effotel-sayaji", params={"check_in": TEST_CHECK_IN, "check_out": TEST_CHECK_OUT})
    assert r2.status_code == 422
    assert "guest" in r2.json()["detail"].lower()


def test_unknown_hotel_is_503_not_crash(http):
    r = http.get("/api/property/totally-unknown-token", params=dict(TEST_STAY))
    assert r.status_code == 503
    assert "detail" in r.json()
    assert "unavailable" in r.json()["detail"].lower()
