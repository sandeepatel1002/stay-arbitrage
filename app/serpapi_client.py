"""SerpApi Google Hotels client — live-only with clear failures (spec §3.2).

Fail-fast policy (owner-directed, v0.3.0): no cache fallback. When SerpApi is
unreachable, erroring, or returns nothing usable, `SerpApiError` is raised and
endpoints surface a friendly 503 message instead of serving substitute data.
"""
from __future__ import annotations

import time
import urllib.parse
from typing import Any, Optional

import requests

from app import config
from app.models import HotelCandidate, OtaFare, TelemetryRecord


class SerpApiError(RuntimeError):
    """Raised when live hotel data cannot be fetched (fail-fast policy)."""


def _rate_number(obj: Any) -> Optional[int]:
    """SerpApi rates hide ints inside dicts: {"lowest": "₹5,289", "extracted_lowest": 5289}."""
    if isinstance(obj, dict):
        return obj.get("extracted_lowest") or obj.get("extracted_before_taxes_fees")
    if isinstance(obj, (int, float)):
        return int(obj)
    return None


def _flatten_amenities(groups: Any) -> list[str]:
    """verified_amenities may arrive grouped like {"general": [...], "room": [...]}. Flatten."""
    flat: list[str] = []
    if isinstance(groups, dict):
        for items in groups.values():
            for item in items or []:
                if isinstance(item, dict) and "value" in item:
                    flat.append(item["value"])
                elif isinstance(item, str):
                    flat.append(item)
    elif isinstance(groups, list):
        flat.extend(g for g in groups if isinstance(g, str))
    return flat


def _synthetic_link(hotel_name: str, source: str) -> str:
    """Deterministic booking-URL fallback so "Book on [Platform]" never goes dead."""
    if not hotel_name:
        return ""
    query = urllib.parse.quote_plus(f"{hotel_name} {source} booking")
    return f"https://www.google.com/search?q={query}"


class SerpApiClient:
    """Live SerpApi wrapper. Raises SerpApiError on any unusable response."""

    # ------------------------------------------------------------------- live
    def _live_call(self, params: dict[str, Any]) -> dict[str, Any]:
        try:
            merged = {"api_key": config.SERPAPI_API_KEY, "num": 20, **params}
            resp = requests.get(config.SERPAPI_BASE_URL, params=merged, timeout=config.SERPAPI_TIMEOUT_SECONDS)
            resp.raise_for_status()
            payload = resp.json()
        except requests.exceptions.Timeout as exc:
            raise SerpApiError("SerpApi timed out — the network or the API is too slow right now.") from exc
        except requests.exceptions.ConnectionError as exc:
            raise SerpApiError("Could not reach SerpApi — check your internet connection.") from exc
        except requests.exceptions.RequestException as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            hint = {
                401: "invalid SERPAPI_API_KEY (rejected 401)",
                403: "SerpApi rejected the key (403) — check quota/plan",
                429: "SerpApi rate limit (429) — too many requests",
            }.get(status)
            raise SerpApiError(hint or f"SerpApi request failed: {exc}") from exc
        if isinstance(payload, dict) and payload.get("error"):
            raise SerpApiError(f"SerpApi returned an error payload: {str(payload['error'])[:160]}")
        return payload

    # ----------------------------------------------------------- normalizing
    def parse_candidates(self, payload: dict[str, Any], city: str) -> list[HotelCandidate]:
        out: list[HotelCandidate] = []
        for prop in payload.get("properties", []):
            token = prop.get("property_token")
            if not token:
                continue
            out.append(
                HotelCandidate(
                    property_token=token,
                    name=prop.get("name") or "Unknown hotel",
                    city=city,
                    rate_per_night=_rate_number(prop.get("rate_per_night")),
                    total_rate=_rate_number(prop.get("total_rate")),
                    stars=prop.get("overall_class"),
                    review_score=prop.get("review_score"),
                    amenities=prop.get("amenities") or [],
                    nearby_places=prop.get("nearby_places") or [],
                )
            )
        return out

    def parse_fares(self, detail: dict[str, Any]) -> list[OtaFare]:
        fares: list[OtaFare] = []
        hotel_name = detail.get("name") or ""
        for price in detail.get("prices", []):
            source = price.get("source") or price.get("provider") or "unknown"
            meal_plan = (price.get("meal_plan") or "").lower()
            free_cancellation = price.get("free_cancellation")
            if isinstance(free_cancellation, bool):  # current engine: true/false flag
                free_cancellation = "Free cancellation" if free_cancellation else None
            elif free_cancellation is not None:
                free_cancellation = str(free_cancellation).strip() or None
            fares.append(
                OtaFare(
                    source=source,
                    base_price=_rate_number(price.get("rate_per_night")),
                    total_price=_rate_number(price.get("total_rate")) or _rate_number(price.get("rate_per_night")),
                    free_cancellation=free_cancellation,
                    breakfast="breakfast" in meal_plan,
                    link=price.get("link") or _synthetic_link(hotel_name, source),
                )
            )
        return fares

    # ----------------------------------------------------------------- public
    def search(
        self, q: str, check_in: str, check_out: str, adults: int = 2
    ) -> tuple[dict[str, Any], str, TelemetryRecord]:
        """Google Hotels search → (payload, "live", telemetry). Raises on failure.

        Dates are required (owner rule: the app never invents a stay window) —
        the endpoint layer prompts the user for anything missing before calling.
        """
        started = time.perf_counter()
        engine = "serpapi:google_hotels"
        live_params: dict[str, Any] = {
            "engine": "google_hotels",
            "q": q,
            "adults": adults,
            # SerpApi names these check_in_date / check_out_date.
            "check_in_date": check_in,
            "check_out_date": check_out,
        }

        payload = self._live_call({"currency": "INR", "gl": "in", "hl": "en", **live_params})
        if not payload.get("properties"):
            raise SerpApiError(f"SerpApi found no hotels for '{q}' on those dates — try another city or wider dates.")
        return (
            payload,
            "live",
            TelemetryRecord(engine=engine, latency_ms=int((time.perf_counter() - started) * 1000), source="live", raw_json=live_params),
        )

    def property_details(
        self, property_token: str, check_in: str, check_out: str, adults: int = 2
    ) -> tuple[dict[str, Any], str, TelemetryRecord]:
        """Property details (prices, reviews_breakdown). Raises on failure.

        SerpApi now serves property details through the plain `google_hotels`
        engine with a `property_token` parameter (the dedicated
        `google_hotels_property_details` engine name returns 400 on current
        keys) — see https://serpapi.com/google-hotels-api.
        Dates are required so the quoted totals match the user's chosen stay.
        """
        started = time.perf_counter()
        engine = "serpapi:google_hotels_property"
        params: dict[str, Any] = {
            "engine": "google_hotels",
            "property_token": property_token,
            "adults": adults,
            "check_in_date": check_in,
            "check_out_date": check_out,
            "currency": "INR",
            "gl": "in",
            "hl": "en",
        }
        payload = self._live_call(params)
        if not (payload.get("prices") or payload.get("name")):
            raise SerpApiError("SerpApi returned no usable details for that hotel.")
        return (
            payload,
            "live",
            TelemetryRecord(engine=engine, latency_ms=int((time.perf_counter() - started) * 1000), source="live", raw_json=None),
        )

    def candidate_pool(
        self, city: str, guests: int, check_in: str, check_out: str
    ) -> tuple[list[HotelCandidate], TelemetryRecord]:
        """Search + parse, wrapped for telemetry convenience."""
        payload, source, tele = self.search(q=f"Hotels in {city}", check_in=check_in, check_out=check_out, adults=guests)
        return self.parse_candidates(payload, city), tele


def breakdown_counts(detail: dict[str, Any]) -> dict[str, int]:
    """reviews_breakdown → {"excellent": 412, ...} ints only (spec §3.3)."""
    out: dict[str, int] = {}
    rb = detail.get("reviews_breakdown") or {}
    if isinstance(rb, dict):
        for key, val in rb.items():
            if isinstance(val, (int, float)):
                out[str(key)] = int(val)
            elif isinstance(val, str) and val.strip().endswith("%"):
                pass  # share, not a count — drop for LLM-grounding purposes
    return out


def grouped_amenities(detail: dict[str, Any]) -> list[str]:
    return _flatten_amenities(detail.get("verified_amenities"))
