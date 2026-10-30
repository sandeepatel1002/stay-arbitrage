"""Central configuration: .env loading + paths + knobs.

Secrets come from `.env` at the project root (see .env.example). Fail-fast
policy (owner-directed, v0.3.0): missing keys or unreachable APIs are NOT
silently substituted — endpoints surface a clear 503 message instead.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

SERPAPI_API_KEY: str = os.getenv("SERPAPI_API_KEY", "").strip()
SERPAPI_BASE_URL: str = os.getenv("SERPAPI_BASE_URL", "https://serpapi.com/search")
SERPAPI_TIMEOUT_SECONDS: float = float(os.getenv("SERPAPI_TIMEOUT_SECONDS", "12"))

# Google AI Studio (Gemini API) — powers all three AI engines.
GEMINI_BASE_URL: str = os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta")
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "").strip()

# Primary model + fallback chain. Default primary = gemini-3.5-flash-lite
# (verified live against the owner's key: 2.4s, pristine JSON). Chain members
# (verified live): 3.1-flash-lite 6.1s pristine JSON; 3.5-flash ~6s when up;
# 3.6-flash / 3.8-flash last resorts under capacity pressure.
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
FALLBACK_MODELS_RAW = os.getenv(
    "GEMINI_FALLBACK_MODELS",
    "gemini-3.1-flash-lite,gemini-3.5-flash,gemini-3.6-flash,gemini-3.8-flash",
)
GEMINI_FALLBACK_MODELS: list[str] = [m.strip() for m in FALLBACK_MODELS_RAW.split(",") if m.strip()]
GEMINI_REQUEST_TIMEOUT: float = float(os.getenv("GEMINI_REQUEST_TIMEOUT", "35"))

DEFAULT_CITY: str = "indore"
KNOWN_CITIES: list[str] = ["indore", "jaipur"]

# Test fixture repurposed from the retired cache (spec §3.2 → fail-fast):
SAMPLE_HOTELS_PATH: Path = PROJECT_ROOT / "data" / "sample_hotels_raw.json"

# Deterministic pricing constants (True-Cost Calculator, spec §4.4)
BREAKFAST_COST_PER_PERSON_INR: int = 450
