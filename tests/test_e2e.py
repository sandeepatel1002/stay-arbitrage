"""E2E suite (v0.3.0): full 3-screen data path + fail-fast error surfaces.

Every failure mode now surfaces a clear message instead of substitute data —
these tests pin the owner-directed fail-fast policy into the API contract.
"""
import pytest
from fastapi.testclient import TestClient

from app import config
from app.main import app
from app.serpapi_client import SerpApiError
from tests.conftest import TEST_CHECK_IN, TEST_CHECK_OUT

TEST_STAY = {"guests": 2, "check_in": TEST_CHECK_IN, "check_out": TEST_CHECK_OUT}


@pytest.fixture()
def http(monkeypatch):
    """Full happy-path rig: fixture-backed SerpApi + canned Gemini answers."""
    from tests.conftest import fake_gemini, fake_serp

    monkeypatch.setattr(config, "SERPAPI_API_KEY", "test-serp-key")
    monkeypatch.setattr(config, "GEMINI_API_KEY", "test-gemini-key")
    fake_serp(monkeypatch)
    fake_gemini(monkeypatch)
    return TestClient(app)


def _search(client, message="peaceful place in indore near 56 dukan, elderly parents, under 8000", chips=None):
    if chips is None:
        chips = dict(TEST_STAY)
    return client.post("/api/search", json={"message": message, "chips": chips})


# ---------------------------------------------------------------- happy path
def test_full_happy_path_indore(http):
    r = _search(http)
    assert r.status_code == 200
    body = r.json()
    matches = body["matches"]
    assert len(matches) == 3
    assert len({m["property_token"] for m in matches}) == 3
    assert all(len(m["why_fits_you"].splitlines()) == 2 for m in matches)

    token = matches[0]["property_token"]
    p = http.get(f"/api/property/{token}", params=dict(TEST_STAY))
    assert p.status_code == 200
    m = p.json()
    assert len(m["fares"]) >= 2
    prices = [f["total_price"] for f in m["fares"]]
    assert m["savings_inr"] == max(prices) - min(prices)  # rupee-exact
    priced_sources = {f["source"] for f in m["fares"] if f["total_price"] is not None}
    assert set(m["perk_value_notes"]) >= priced_sources
    assert len(m["telemetry"]) >= 2


def test_full_happy_path_jaipur(http):
    r = _search(
        http,
        "heritage stay in jaipur family of 4 under 9000",
        chips={"check_in": TEST_CHECK_IN, "check_out": TEST_CHECK_OUT},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["intent"]["city"] == "jaipur"
    assert body["intent"]["guests"] == 4
    assert len(body["matches"]) == 3


def test_booking_links_always_present(http):
    r = _search(http)
    token = r.json()["matches"][0]["property_token"]
    p = http.get(f"/api/property/{token}", params=dict(TEST_STAY)).json()
    for fare in p["fares"]:
        if fare["total_price"]:
            assert fare["link"].startswith("https://"), f"{fare['source']} lacks a booking link"


# --------------------------------------------------- fail-fast error surfaces
def test_serpapi_unreachable_is_friendly_503(http, monkeypatch):
    """Wi-Fi dies mid-demo → 503 with a clear message, NO substitute data."""
    import app.main as main_mod

    def dead_network(*a, **k):
        raise SerpApiError("Could not reach SerpApi — check your internet connection.")
    monkeypatch.setattr(main_mod.serp, "search", dead_network)

    r = _search(http)
    assert r.status_code == 503
    detail = r.json()["detail"].lower()
    assert "reach serpapi" in detail or "connection" in detail
    # no matches key anywhere on the error body
    assert "matches" not in r.json()


def test_gemini_unreachable_is_friendly_503(monkeypatch):
    """AI outage (no keys possible to fake deeper) → 503, clear AI message."""
    from tests.conftest import fake_serp

    monkeypatch.setattr(config, "SERPAPI_API_KEY", "test-serp-key")
    monkeypatch.setattr(config, "GEMINI_API_KEY", "")  # unconfigured → fail-fast
    fake_serp(monkeypatch)
    client = TestClient(app)

    r = _search(client)
    assert r.status_code == 503
    assert "GEMINI_API_KEY" in r.json()["detail"]
    assert "AI service unavailable" in r.json()["detail"]


def test_serps_dead_after_intent_also_503(http, monkeypatch):
    """Even when the intent parsed fine, dead SerpApi → 503 (never mock data)."""
    import app.main as main_mod

    def dead_pool(*a, **k):
        raise SerpApiError("SerpApi rate limited (429)")
    monkeypatch.setattr(main_mod.serp, "candidate_pool", dead_pool)

    r = _search(http)
    assert r.status_code == 503
    assert "429" in r.json()["detail"]


def test_unknown_city_ask_is_422(http):
    r = _search(http, message="somewhere peaceful under 6000", chips=dict(TEST_STAY))
    assert r.status_code == 422
    assert "city" in r.json()["detail"].lower()


def test_unexpected_exception_returns_clean_json(monkeypatch):
    """Anything unexpected → clean JSON 500, never a stack dump."""
    import app.main as main_mod
    from tests.conftest import fake_gemini, fake_serp

    fake_serp(monkeypatch)
    fake_gemini(monkeypatch)

    def boom(*a, **k):
        raise ValueError("internal oops")
    monkeypatch.setattr(main_mod.serp, "candidate_pool", boom)

    http = TestClient(app, raise_server_exceptions=False)
    r = _search(http)
    assert r.status_code == 500
    assert r.json() == {"detail": "Something went wrong — try again."}


def test_property_endpoint_503_and_500_paths(monkeypatch):
    import app.main as main_mod
    from tests.conftest import fake_gemini, fake_serp

    fake_serp(monkeypatch)
    fake_gemini(monkeypatch)

    def dead_details(*a, **k):
        raise SerpApiError("SerpApi timed out")
    monkeypatch.setattr(main_mod.serp, "property_details", dead_details)
    http = TestClient(app)
    r = http.get("/api/property/indore-1-effotel-sayaji", params=dict(TEST_STAY))
    assert r.status_code == 503 and "timed out" in r.json()["detail"]

    def boom(*a, **k):
        raise RuntimeError("weird internal state")
    monkeypatch.setattr(main_mod.serp, "property_details", boom)
    http500 = TestClient(app, raise_server_exceptions=False)
    r = http500.get("/api/property/indore-1-effotel-sayaji", params=dict(TEST_STAY))
    assert r.status_code == 500 and r.json() == {"detail": "Something went wrong — try again."}


def test_bad_body_is_422(http):
    r = http.post("/api/search", json={"chips": {"guests": "not-a-number"}})
    assert r.status_code == 422  # pydantic rejects, never a 500
