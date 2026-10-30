"""SerpApi client tests (v0.3.0): live-only, fail-fast, no cache fallback.

The network is simulated with fake `requests.get` responses built from the
canned fixture; every failure mode must raise a friendly `SerpApiError`.
"""
from typing import Any

import pytest
import requests

from app import config
from app.serpapi_client import SerpApiClient, SerpApiError, _rate_number
from tests.conftest import TEST_CHECK_IN, TEST_CHECK_OUT, sample_candidates, sample_details, sample_search_payload

OK_PAYLOAD = sample_search_payload("indore")
STAY = {"check_in": TEST_CHECK_IN, "check_out": TEST_CHECK_OUT}


class FakeResponse:
    def __init__(self, payload: Any, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            resp = requests.models.Response()
            resp.status_code = self.status_code
            raise requests.HTTPError(f"{self.status_code} error", response=resp)

    def json(self):
        data = self._payload
        if isinstance(data, Exception):
            raise data
        if isinstance(data, bytes) or isinstance(data, str):
            raise ValueError("not json")
        return data


def _patch_get(monkeypatch, payload: Any):
    monkeypatch.setattr("app.serpapi_client.requests.get", lambda *a, **k: FakeResponse(payload))


@pytest.fixture(autouse=True)
def with_key(monkeypatch):
    monkeypatch.setattr(config, "SERPAPI_API_KEY", "test-serp-key")
    monkeypatch.setattr(config, "SERPAPI_TIMEOUT_SECONDS", 1.0)


def api() -> SerpApiClient:
    return SerpApiClient()


# ------------------------------------------------------------------- searches
def test_search_success_returns_live_payload(monkeypatch):
    _patch_get(monkeypatch, OK_PAYLOAD)
    payload, source, tele = api().search(q="Hotels in Indore", **STAY)
    assert source == "live" and tele.source == "live"
    assert len(payload["properties"]) >= 3


def test_live_error_payload_raises(monkeypatch):
    _patch_get(monkeypatch, {"error": "Simulated quota exhaustion"})
    with pytest.raises(SerpApiError):
        api().search(q="Hotels in Indore", **STAY)


def test_unreachable_network_raises(monkeypatch):
    def dead(*a, **k):
        raise requests.exceptions.ConnectionError("simulated: Wi-Fi cut")
    monkeypatch.setattr("app.serpapi_client.requests.get", dead)
    with pytest.raises(SerpApiError, match="reach|connection"):
        api().search(q="Hotels in Indore", **STAY)


def test_timeout_raises_friendly(monkeypatch):
    def slow(*a, **k):
        raise requests.exceptions.Timeout("simulated: slow venue Wi-Fi")
    monkeypatch.setattr("app.serpapi_client.requests.get", slow)
    with pytest.raises(SerpApiError, match="timed out"):
        api().search(q="Hotels in Indore", **STAY)


def test_http_401_names_the_key(monkeypatch):
    _patch_get(monkeypatch, [])  # json body irrelevant; status drives the error
    def bad_status(*a, **k):
        return FakeResponse([], status_code=401)
    monkeypatch.setattr("app.serpapi_client.requests.get", bad_status)
    with pytest.raises(SerpApiError, match="401|invalid"):
        api().search(q="Hotels in Indore", **STAY)


def test_no_properties_raises(monkeypatch):
    _patch_get(monkeypatch, {"properties": []})
    with pytest.raises(SerpApiError, match="no hotels"):
        api().search(q="Hotels in Indore", **STAY)


def test_property_details_roundtrip(monkeypatch):
    detail = sample_details("indore-1-effotel-sayaji")
    _patch_get(monkeypatch, detail)
    payload, source, _ = api().property_details("indore-1-effotel-sayaji", **STAY)
    assert source == "live"
    assert payload["name"] == "Effotel By Sayaji"


def test_property_details_unknown_payload_raises(monkeypatch):
    _patch_get(monkeypatch, {"search_metadata": "nothing useful"})
    with pytest.raises(SerpApiError):
        api().property_details("totally-unknown-token", **STAY)


# ------------------------------------------------------------------- parsers
def test_parse_candidates_normalizes():
    candidates = sample_candidates("indore")
    assert len(candidates) >= 3
    first = candidates[0]
    assert first.property_token and first.name
    assert isinstance(first.rate_per_night, int)


def test_parse_fares_breakfast_and_totals():
    fares = api().parse_fares(sample_details("indore-1-effotel-sayaji"))
    by_source = {f.source: f for f in fares}
    assert by_source["Booking.com"].breakfast is True
    assert by_source["Agoda"].breakfast is False
    assert all(isinstance(f.total_price, int) for f in fares)


def test_parse_fares_synthetic_link_when_omitted():
    fares = api().parse_fares(
        {
            "name": "Test Hotel",
            "prices": [
                {"source": "MysteryOTA", "total_rate": {"extracted_lowest": 15000}, "meal_plan": "Room only"},
                {"source": "AnotherOne", "rate_per_night": {"extracted_lowest": 5500}, "link": ""},
            ],
        }
    )
    assert all(f.link.startswith("https://") for f in fares)


def test_rate_number_helper():
    assert _rate_number({"lowest": "₹5,289", "extracted_lowest": 5289}) == 5289
    assert _rate_number(4500) == 4500
    assert _rate_number(None) is None
