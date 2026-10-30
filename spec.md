# StayArbitrage — System Specification (SDD Source of Truth)

> **Project:** AI Hotel Matchmaker & Multi-OTA Price Arbitrage Engine
> **Context:** AI-first hackathon build, developed 100% inside OpenCode under a Spec-Driven Development workflow.
> **Golden Rule of this spec:** All code, tests, and self-healing are performed by the OpenCode agent. The human operator is a non-coder and is NEVER asked to write or edit code.

---

## 1. Product Vision

A traveler signs on with one line of informal text ("somewhere peaceful in Indore near 56 Dukan, elderly parents coming, under 6k"). StayArbitrage:

1. Parses that sentence into **structured search intent** (AI Feature 1).
2. Curates a **podium of exactly 3 distinct hotels** with personalized "Why This Fits You" badges (AI Feature 2).
3. Exposes the **multi-OTA price arbitrage matrix** — Agoda vs Booking.com vs Priceline vs MakeMyTrip vs Official Site — with AI-evaluated perks plus a **deterministic Python true-cost calculator** producing exact rupee savings (AI Feature 3 + deterministic core).

**Fail-fast policy (v0.3.0, owner-directed):** there is NO offline substitute data. When an external API (SerpApi or Gemini) is missing or unreachable, endpoints return HTTP 503 with a clear, friendly message naming what failed — the UI shows the truth instead of made-up hotels.

---

## 2. Tech Stack (locked)

| Layer | Choice | Notes |
|---|---|---|
| Backend | Python 3.11+ / FastAPI | Single app, serves API + static frontend |
| Frontend | Single-page HTML + TailwindCSS (CDN) + Vanilla JS | Self-contained `static/index.html` |
| LLM access | Google AI Studio — Gemini API (`generateContent`, REST) | Primary `gemini-3.5-flash-lite` + verified fallback chain; strict Pydantic response schemas |
| Hotel data | SerpApi Google Hotels engine (`google_hotels`; property details via the same engine with `property_token` — the old `google_hotels_property_details` engine name now returns 400) | `property_token` used for detail/pricing fetch |
| Tests | `pytest` + FastAPI `TestClient` | All milestones gated by tests |
| Config | `.env` via `python-dotenv` | `GEMINI_API_KEY`, `GEMINI_MODEL`, `GEMINI_FALLBACK_MODELS`, `SERPAPI_API_KEY` |

**OpenCode native config:** `opencode.json` wires the `fetch` MCP tool and permissions. `.env.example` documents required secrets.

---

## 3. Data Sources & Contracts

### 3.1 SerpApicandidate pipeline
- **Search stage:** `engine=google_hotels` params `q`, `check_in`, `check_out`, `adults`, `currency=INR`, `gl=in`, `hl=en`. Primary parse targets: `properties[]` → `name`, `property_token`, `rate_per_night.extracted_lowest`, `total_rate.extracted_lowest`, `overall_class`, `amenities[]`, `nearby_places[]`.
- **Detail stage:** the SAME `engine=google_hotels` call with `property_token` plus dates/adults/`currency=INR` (SerpApi's current contract; the standalone `google_hotels_property_details` engine name is unsupported on current keys). Primary parse targets: `reviews_breakdown`, `prices[]` (per OTA: `source`, `rate_per_night`, `total_rate`, `free_cancellation` — may be a bool flag or a date string; the parser normalizes both, `payment`), `featured_prices[]`, `ratings`, `verified_amenities` → `amenities[]` grouped.

### 3.2 Canned test fixture — `data/sample_hotels_raw.json`
- Formerly the demo "cache"; retained (v0.3.0) **only as a pytest fixture**: hand-curated realistic payloads for **Indore and Jaipur** matching the schemas above (3.1).
- Shape: `{ "_note": ..., "indore": {"search": {...}, "details": { "<token>": {...} }}, "jaipur": {...} }`
- Tests simulate SerpApi responses and canned Gemini answers from it (`tests/conftest.py`) — the suite is offline, deterministic, and free.
- The running app NEVER reads this file; live calls only, fail-fast on failure (§1 policy).

### 3.3 Normalized internal models (`app/models.py`, explicit)
- `HotelCandidate`: `property_token`, `name`, `city`, `rate_per_night`, `total_rate`, `stars`, `amenities: list[str]`, `reviews_breakdown: dict[str,int]`, `nearby_places`.
- `OtaFare`: `source`, `base_price`, `total_price`, `free_cancellation: str | None`, `breakfast: bool`, `link`.
- `DealMatrix`: `property_token`, list[OtaFare], computed savings (Python only).

---

## 4. The Three AI Engines (Milestone 2)

All engines call the Gemini API via one shared client (`app/ai_client.py`, plain REST `generateContent` with `response_mime_type: application/json`) and return **Pydantic-validated JSON**. Robustness: hidden thought-part filtering, fence peeling, lenient JSON extraction (`raw_decode`, control-char tolerant), 429/503 backoff, and a verified model fallback chain (primary `gemini-3.5-flash-lite` → `gemini-3.1-flash-lite` → `gemini-3.5-flash` → `gemini-3.6-flash` → `gemini-3.8-flash`). When every attempt fails, the client raises `AIClientError` — engines propagate it and endpoints return HTTP 503 with a clear message (v0.3.0 fail-fast policy: no deterministic substitute output). Each engine emits a **TelemetryRecord** with Gemini `usageMetadata` token counts.

### 4.1 Engine 1 — Smart Intent Parser & Natural Filter
- **In:** free text + optional chip values (City, Dates, Guests, Max Budget over-rides).
- **Out (Pydantic `IntentSchema`):**
  - `city: str` (e.g. "indore"), `check_in/check_out: date|None`, `guests: int|null`, `max_budget: int|null`  → mapped to hard SerpApi params (`q`, `check_in`, `adults`).
  - `semantic_filters: [{type: "proximity"|"needs"|"vibe", value: str}]` — e.g. "near 56 Dukan" → proximity("56 Dukan"), "elderly parents / elevator" → needs("elevator,step-free access"), "peaceful" → vibe.
  - `search_query_expansion: str` — extra query terms for Google Hotels `q`.
- Fails fast: AI-unreachable → `AIClientError` → HTTP 503; missing must-pass booking parameters → friendly HTTP 422 **with a structured `missing` list** (see §4.5).
- Tests: scripted utterances via canned Gemini fixtures, chip-vs-text conflict (chips win), required-parameter prompts.

### 4.2 Engine 2 — Personalized "Why This Fits You" Matchmaker
- **In:** user intent schema + candidate pool (from search stage, richer details when available).
- **Logic:** LLM scores/ranks candidates and MUST pick **3 distinct hotels** for slots: `best_overall_match`, `value_pick`, `premium_gem`. Guardrails (Python-enforced, fail-fast): distinctness (no duplicate tokens) and token-membership in the candidate pool — any violation raises `AIClientError` → HTTP 503, never a rules-based substitute podium.
- **Out (Pydantic `MatchesSchema`):** per slot: `slot`, `property_token`, `why_fits_you` = **exactly 2 lines** (line 1 = need-match, line 2 = value/review-grounded reason citing amenity or `reviews_breakdown` category).
- Tests: distinctness invariant; 2-line constraint; invented tokens rejected; AI-outage → 503.

### 4.3 Engine 3 — Perk & Policy Value Equivalence
- **In:** one hotel's OTA fares (`OtaFare[]`) incl. `free_cancellation` dates + breakfast flags.
- **Out (Pydantic `PerkValueSchema`):** per OTA: `net_value_note` (e.g. "₹X, fully refundable till 18 Jun — effectively risk-free", "₹200 cheaper but breakfast ₹450/person"), and `verdict: "best_flexibility"|"best_value"|"premium_feel"|None`. LLM narrates ONLY; a numeric rule helper pre-computes deltas that feed the prompt.
- Tests: schema validation, no raw arithmetic performed in narrative beyond pref-supplied numbers.

### 4.4 Deterministic True-Cost Calculator (`app/pricing.py`, pure Python, no LLM)
- Inputs list[OtaFare]; outputs: cheapest OTA, premium delta vs cheapest, breakfast-adjusted cost (×2 guests when 2 guests & breakfast≈₹450 not included), flexibility flag.
- Emits `savings_inr` = max_price_seen − cheapest_price, `savings_pct`.
- **Unit-tested to the rupee. LLMs never compute money.**

### 4.5 Must-Pass Booking Parameters (v0.3.1, owner-directed)
The app **never invents a stay window**. Four parameters are required before any live quote:

| Parameter | Source | Validation |
|---|---|---|
| `city` | message text or City chip | must be non-empty |
| `check_in` | message text ("Nov 6–9") or structured date chips | ISO date, not in the past |
| `check_out` | same | ISO date, strictly after `check_in`, stay ≤ 30 nights |
| `guests` | message text or Guests chip | integer 1–16 |

- Missing/invalid → `HTTP 422` with a structured body:
  `{detail: friendly sentence, missing: ["check_in","check_out"], problems: [validation msgs], partial: {city, guests, check_in, check_out}}`.
- The frontend turns that into an inline **"Almost there"** panel (date pickers + guest count, missing fields highlighted in red) — the user is *asked*, never defaulted.
- `GET /api/property` requires `?guests=&check_in=&check_out=` for the same reason: its prices are stay totals for the user's own dates.
- Tests: missing dates → 422 prompt (no silent 3-night default); missing guests → 422; reversed dates → 422; past check-in → 422; structured chips win over text; property without dates → 422.

---

## 5. API Endpoints (Milestone 1–2 schema, locked)

FastAPI served from the repo root; static files at `/` (serves `static/index.html`).

| Method | Path | Purpose |
|---|---|---|
| `GET /` | serves single-page UI | Must return 200 |
| `POST /api/search` | body `{message, chips{city,dates,guests,max_budget,check_in,check_out}}` → Engine 1 → must-pass gate (§4.5) → candidate pool → Engine 2 → returns `{intent, matches[3], telemetry}` |
| `GET /api/property/{property_token}` | `?guests&check_in&check_out` (required) → fetch details via SerpApi → Engine 3 → DealMatrix → returns `{hotel, fares, savings_inr, savings_pct, stay{check_in,check_out,nights}, telemetry}` |
| `POST /api/search` errors | 422 `{detail, missing[], problems[], partial{}}` for missing/invalid must-pass params; 503 JSON `{detail}` when SerpApi/Gemini unreachable (fail-fast); 500 JSON `{detail}` for anything unexpected |
| `GET /api/property` errors | 422 `{detail}` when dates/guests are missing or nonsensical; 503/500 as above |
| `GET /api/health` | `{status, serpapi:"ok|missing", ai:"ok|missing", version}` |

- **Telemetry:** Every AI/data operation appends `TelemetryRecord(engine, model, latency_ms, tokens_in, tokens_out, raw_json|None, source:"live")`. `/api/search` response embeds `telemetry[]` for the UI drawer.

---

## 6. Frontend — Three Screens (Milestone 3, single `static/index.html`)

Tailwind via CDN, vanilla JS (no frameworks, no build step). State object `S{screen, lastSearch, lastMatrix}`.

- **Screen 1 — Home & Intent Search:** big prompt box + chips row (City ✱, Dates ✱, Guests ✱, Max Budget optional). "Find my stay →" button. Renders intent-formalized summary line back ("Indore · 2026-11-09 → 2026-11-12 · 3 nights · 2 guests · ₹6000 max · + elevator/quiet"). If must-pass parameters are missing (§4.5), an inline **"Almost there — hotels need these to quote real prices"** panel appears with City / Guests / Check-in / Check-out inputs (missing ones highlighted) and a "Complete search →" button.
- **Screen 2 — Curated 3-Match Podium:** exactly 3 cards, gold/silver/bronze badges labeled `Best Overall Match | Value Pick | Premium Gem`. Each card: photo/colors, name, stars, price/night, amenity chips, and the 2-line "Why This Fits You" badge. Button: **"Compare Live Deals & Perks"** → Screen 3.
- **Screen 3 — Price Arbitrage & Direct Booking Matrix:** per-OTA rows (Agoda, Booking.com, Priceline, MakeMyTrip, Official Site or whatever `source` returns) with total price, free-cancellation date, breakfast badge, **Perk Value Equivalence highlight** (Engine 3 note), savings ribbon ("Save ₹1,240 (17%) vs highest"), and **"Book on [Platform]"** outgoing anchor (SerpApi-provided link or generated search-URL fallback).
- **"AI Under the Hood" Telemetry Drawer:** collapsible bottom drawer; fetches telemetry from responses; shows model name, latency (ms), tokens in/out, `live` source chip, and raw JSON (pretty-printed, copy button).
- Zero console errors required (GOALS). Error paths surface the backend's friendly `detail` as a toast; a top-right health chip shows `SerpApi ✓/✗ · AI ✓/✗` (amber when a key is missing).

---

## 7. Milestones

**Milestone 1 — Infrastructure & Data Layer**
Repo skeleton (`app/`, `static/`, `data/`, `tests/`), FastAPI bootstrap serving `/` + `/api/health`, `pyproject`/`requirements.txt`, `.env` loading, `serpapi_client.py` (live calls with timeout + cache fallback), curated `sample_hotels_raw.json` (2 cities), `pricing.py` True-Cost Calculator + pytest-mathed savings, no AI yet (AI engines stubbed as 501 or data-only).

**Milestone 2 — The Three AI Engines**
`ai_client.py` (OpenRouter via openai SDK base_url override), 3 Pydantic schemas, Engine 1/2/3 modules with retry-once-on-bad-JSON and deterministic fallbacks, unit tests with mocked OpenRouter responses (+ optional live smoke test when key present), endpoints upgraded to real engines.

**Milestone 3 — The 3-Screen Frontend**
Single `static/index.html`, 3 screens + Telemetry Drawer wired to `/api/*`, mobile-friendly, zero console errors, graceful demo-mode banner when `source: cache`.

**Milestone 4 — E2E, Error Recovery & Verification**
pytest E2E suite (TestClient through live-mock paths), network-failure simulation, `/verify` green end-to-end (backend tests + frontend serving + no 5xx on happy path), final `PITCH.md` via `/demo-prep`, polish pass on telemetry and demo safety.

**v0.3.0 addendum — Gemini switch + fail-fast re-architecture (Oct 25, 2026, owner-directed)**
- AI provider: OpenRouter → **Google AI Studio Gemini API** on the owner's own key; primary `gemini-3.5-flash-lite` (verified ~2.4s, pristine JSON) with a live-verified fallback chain, excluding `gemini-2.5-flash` (404 — closed to new users).
- Offline cache fallback REMOVED: no substitute data, ever. `SerpApiError` / `AIClientError` → HTTP 503 with friendly detail; missing city → 422; deterministic engine fallbacks and the amber cache banner are gone from code and UI.
- `data/sample_hotels_raw.json` survives only as a pytest fixture; the app never reads it.
- SerpApi property details migrated to SerpApi's current contract (`engine=google_hotels` + `property_token`); `free_cancellation` tolerates both bool and date-string payloads.
- Health keys renamed: `serpapi`/`ai` with `ok|missing`; version 0.3.0.

**v0.3.1 addendum — Must-pass booking parameters + price-unit labels (Oct 26, 2026, owner-directed)**
- The 3-night "demo window" default is **gone**: city, check-in, check-out and guests are now required (§4.5). Missing values → 422 with a structured `missing` list; the UI prompts with an inline date/guest panel instead of guessing.
- `GET /api/property` now requires `?guests&check_in&check_out` and quotes totals for the user's own stay; it returns a `stay{check_in,check_out,nights}` block.
- Screen 2 labels its prices "**from ₹X /night**" (search snapshot); Screen 3 labels rows "**₹Y total · N nights**" plus "≈ ₹X/night" and frames savings "over the whole N-night stay" — resolving the podium-vs-matrix unit confusion.
- Version 0.3.1; 73 tests green.

---

## 8. Operational Rules (mirrors AGENTS.md)

- OpenCode does 100% of edits; never instruct the human to code.
- After every code change: run `pytest` (backend) and `uvicorn http 200 check` (frontend) before declaring done.
- No new dependencies without checking they're installable via pip in one command.
- LLM outputs are always schema-validated; string digits are never trusted for money math.
