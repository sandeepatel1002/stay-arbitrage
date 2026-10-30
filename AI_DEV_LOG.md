# AI_DEV_LOG.md — StayArbitrage Judge-Facing Progress Journal

> Maintained automatically by the OpenCode agent after each milestone.
> Format: date · milestone · what was built · what was verified · judge insight.

---

## Scaffolding — OpenCode SDD Setup (complete)

- **Built:** `spec.md` (full 3-screen / 3-AI-feature specification), `GOALS.md` (acceptance criteria), `AGENTS.md` (autonomous non-coder workflow rules), custom slash commands `/build-milestone`, `/verify`, `/demo-prep`, `opencode.json` (fetch MCP + permissions), `.env.example`, `.env` with owner-provided keys, `.gitignore` protecting secrets.
- **Verified:** spec-to-milestone mapping reviewed; milestones 1–4 defined with strict test-gated completion.
- **Judge insight:** the entire product is being built spec-first inside a coding agent — zero human code commits, full autonomous verify loops before any milestone is marked done.

---

## Milestone 1 complete — Infrastructure & Data Layer — Oct 24, 2026

- **Built:**
  - FastAPI backend (`app/main.py`) serving the frontend at `/`, `GET /api/health`, data-only `POST /api/search` (deterministic podium: Best Overall Match / Value Pick / Premium Gem, distinct hotels enforced) and `GET /api/property/{token}` (OTA fares + arbitration math).
  - Normalized contracts (`app/models.py`): `TelemetryRecord`, `HotelCandidate`, `OtaFare`, `DealMatrix`.
  - `app/serpapi_client.py` — live SerpApi Google Hotels calls with timeout + automatic fallback to the curated `data/sample_hotels_raw.json` cache (Indore + Jaipur); every response carries telemetry with `live`/`cache` source so judges see the mode.
  - `app/pricing.py` — deterministic True-Cost Calculator: exact cheapest/highest OTA price, rupee savings, savings %, breakfast-adjusted net cost (₹450/person assumption is a tested constant). **LLMs never do money math.**
  - Placeholder `static/index.html` (real 3-screen UI is Milestone 3).
- **Verified green:** `python -m pytest -q` → **17 passed in 1.85s** (pricing precision to the rupee, cache fallback, API happy path, chips-city-wins-over-message, podium distinctness, unknown-token graceful degradation). Live uvicorn boot on port 8000: `GET /` → 200, `GET /api/health` → 200 with both API keys detected.
- **Judge insight:** with zero network and even with zero API keys, the full search → 3 matches → price-matrix data path still returns valid results — the demo physically cannot fail on stage.
- **Next:** Milestone 2 — the three AI engines (Intent Parser, Matchmaker, Perk & Policy Value Equivalence) via OpenRouter with strict Pydantic schemas.

---

## Milestone 2 complete — The Three AI Engines (live) — Oct 24, 2026

- **Built:**
  - `app/ai_client.py` — one shared OpenRouter client (openai SDK, `base_url=https://openrouter.ai/api/v1`), strict Pydantic-schema validation, retry-once on bad JSON, full telemetry (model name, latency ms, tokens in/out).
  - `app/ai_schemas.py` — the 3 ironclad contracts: `IntentSchema` (fail-soft dates, normalized city), `MatchesSchema` (exactly 3 distinct tokens, unique slots, exactly-2-line badges), `PerkValueSchema` (one note per OTA source).
  - `app/engine_intent.py` — Engine 1: parses informal text ("near 56 Dukan" → proximity, "elderly parents" → elevator needs, "peaceful" → vibe, "under 6k" → ₹6000) into hard params + semantic filters; chips always override the message; full rule-based fallback when AI is down.
  - `app/engine_match.py` — Engine 2: ranks candidates into Best Overall Match / Value Pick / Premium Gem with 2-line "Why This Fits You" badges citing amenities + review data; Python-enforced distinctness invariant; deterministic scorer as fallback.
  - `app/engine_perks.py` — Engine 3: a rule helper pre-computes every money fact (deltas, breakfast add-on ₹450/person, refundability) and the LLM ONLY narrates those numbers — arithmetic stays in `app/pricing.py`.
  - Hardened prompts after live debugging (tokens not row numbers; 2-line badges with example; SerpApi's real `check_in_date`/`check_out_date` param names discovered via probe).
- **Verified green:** `python -m pytest -q` → **41 passed** (schema validators, mocked-LLM happy paths, invalid-JSON→fallback for all 3 engines, chips-win conflict, distinctness invariants, rupee-precise facts math). Live end-to-end on port 8000 with real keys: intent parsed from messy sentence → real SerpApi Google Hotels results (live!) → 3 distinct AI-written badges → 4-platform fare matrix with savings ₹1,430 (10.1%) and per-OTA perk notes with verdicts.
- **Judge insight — "AI Under the Hood" works as advertised:** telemetry showed `engine1:intent-parser | live | gpt-4o-mini | 3.1s | 205/135 tok` and `engine2:matchmaker | live | 5.0s | 1,939/217 tok` — and, when one earlier matchmaker answer failed the 2-line schema, the system self-healed to the deterministic podium without the user ever noticing. Invalid AI output physically cannot reach the UI.
- **Next:** Milestone 3 — the 3-screen frontend (podium cards, arbitrage matrix, telemetry drawer) wired to these live APIs.

---

---

## Milestone 3 complete — The 3-Screen Frontend — Oct 24, 2026

- **Built:** one fully self-contained `static/index.html` (Tailwind CDN + vanilla JS, no build step, no extra files):
  - **Screen 1 — Home & Intent Search:** big prompt box + one-tap example prompts + 4 structured chips (City with autocomplete, Dates, Guests, Max Budget). After search, shows the AI-parsed intent summary ("📍 Indore | 👥 2 | 💰 ₹8,000/max | 🧠 56 Dukan · quiet · elevator").
  - **Screen 2 — Curated 3-Match Podium:** exactly the 3 distinct hotels as gold/silver/bronze-styled cards (🏆 Best Overall Match / 💵 Value Pick / 💎 Premium Gem) with stars, review score, amenity chips, price/night, the personalized 2-line "Why This Fits You" badge, and the "⚖️ Compare Live Deals & Perks" action.
  - **Screen 3 — Price Arbitrage & Direct Booking Matrix:** platform rows sorted cheapest-first with OTA-branded labels, total price, breakfast/cancellation/cheapest badges, the Engine-3 perk note highlighted with its verdict chip, the savings ribbon ("You save ₹X (Y%)…"), and real outgoing "Book on [Platform]" links.
  - **"AI Under the Hood" Telemetry Drawer:** collapsible bottom drawer on every screen; lists each AI/data call with engine name, model, latency ms, tokens in/out, a live/cache/mock chip, expandable raw JSON, and a one-click "Copy raw telemetry" for judges. An amber demo-mode banner appears automatically whenever data came from the offline-safe cache.
  - Defensive UI: toasts instead of stack traces, loading states, escaped user input (`textContent`-style escaping), no undefined element references.
- **Verified green:** `python -m pytest -q` → **48 passed** (new `test_static.py` enforces the frontend contract: single self-contained file, all 3 screen markers, podium labels + CTA text, booking links, telemetry bindings, no module/bundler attributes). Live server check: `GET /` → 200 serving 20,670-byte page with ZERO missing UI identifiers; scan of all `$('id')` references against defined ids = NONE undefined (the classic zero-console-error trap); full live flow re-verified end-to-end (search → podium data → matrix with ₹1,430 / 10.1% savings).
- **Judge insight:** the "AI Under the Hood" drawer turns the demo into a trust exhibit — while the presenter is talking, judges can expand raw JSON showing `engine2:matchmaker | live | gpt-4o-mini | 5.1s | 1,939/225 tok`. Nothing is faked, nothing is hidden; if the internet dies mid-demo, an amber banner honestly announces cache mode and the pitch continues.
- **Next:** Milestone 4 — E2E test suite, network-failure simulations, final `/verify` sweep, and demo-day hardening.

---

## Model switch — FREE OpenRouter model (post-M3 update) — Oct 24, 2026

- **Built:** the app now runs 100% on a free OpenRouter model: **`poolside/laguna-s-2.1:free`**, chosen via a live bake-off against the real engine schemas (other free candidates were rate-limited 429, forbidden 403, or too slow ~2min). Added a resilience chain to `app/ai_client.py`: primary model → 2 attempts (429-backoff) → `openrouter/free` router fallback attempt → deterministic engine fallbacks. Output-token cap (700) added to stop free-model rambling; matchmaker prompt trimmed to the 6 strongest candidates (latency 41s → **7.4s** live).
- **Verified green:** 48 tests passed; full live pipeline: engine1 4.7s, serpapi live 0.3s, engine2 7.4s with *real personalized badges citing actual live hotels* (HOTEL PTC / Solaris / Blue Leaf), engine3 perk notes live.
- **Judge insight:** "our AI stack costs ₹0 per demo run" — three real AI calls per search on a free OpenRouter model, each individually rate-limit-proofed, with the offline deterministic stack beneath every layer.
- **Swap cost:** one line in `.env` (`OPENROUTER_MODEL=...`) — paid models like `openai/gpt-4o-mini` documented in `.env.example` for judges who ask.

---

## Milestone 4 complete — E2E, Error Recovery & Verification — Oct 24, 2026

- **Built:**
  - `tests/test_e2e.py` — the "demo cannot fail" proof suite: zero-keys full happy path (Indore + Jaipur), dead-network simulation (live key present, Wi-Fi cut → cache mode carries the demo), SerpApi error-payload simulation, AI outage mid-demo (rule parser + deterministic podium + template notes all verified), booking-link guarantee, unknown-token graceful degradation, no-stack-dump 500s.
  - `tests/test_js_syntax.py` — the browser JS is compiled with Node (`node --check`, esprima fallback) in CI-style tests — syntax errors physically cannot ship in the frontend.
  - **Booking-link hardening:** `parse_fares` now synthesizes a booking-search URL when a live source omits links, so "Book on [Platform]" never renders dead.
  - Telemetry completeness: Engine 1 now records an honest fallback row in the drawer when the rule parser takes over (matching Engines 2 & 3).
  - Test-suite hygiene: all tests are fully offline/deterministic (fixtures force cache + mock rather than silently consuming live quota) — **suite runtime dropped from ~4 minutes to 1.8s**.
  - `README.md` — judge quickstart: 2-command run, the 3-screen story, ₹0-AI fact, and the command map.
- **Verified green:** `python -m pytest -q` → **58 passed** (unit pricing 5, schemas 6, intent 7, matchmaker 5, perks 4, SerpApi 6, API 6, static 7, JS syntax 1, E2E 11). Live boot re-verified with current code: `GET /` → 200 (all UI markers, zero undefined element ids), `GET /api/health` → 200 with both keys detected. Final live pipeline spot-check: real SerpApi data → AI podium with fallback-proof telemetry → 4-platform matrix with ₹1,430 (10.1%) savings and per-OTA perk verdicts.
- **Judge insight:** the project now has a verifiable claim structure — every resilience promise (Wi-Fi dies, SerpApi errors, AI throttles, zero keys) is a named passing test, and the judge can run `python -m pytest -q` and watch 58 green checks in under 2 seconds. Failure isn't just tolerated in this architecture; it's actually rehearsed and covered before each milestone callout in the Dev Log.
- **Next:** `/demo-prep` for the 2-minute stage presentation, then demo day.

---


## 🎯 Demo prep — PITCH.md complete — Oct 24, 2026

- **Built:** `PITCH.md` — the timed 2-minute stage script (≈325 spoken words): cold-open hook, click-by-click 3-screen demo, ₹1,430/10.1% savings reveal, telemetry-drawer proof moment, ₹0-inference closer; plus a 3-row demo-day risk table (AI throttle → resilience chain, SerpApi outage → cache mode, surprises → toasts/backup tab), a pre-stage checklist, a claims-fairness section tied line-by-line to `GOALS.md`, and one line of rehearsal advice ("click first, narrate while it loads").
- **Verified green:** every claim in the script maps to a `[x]` gate in `GOALS.md` (10/10) or a documented live verification in this log; no vaporware — the AI is on the free model (`poolside/laguna-s-2.1:free`), ₹0 per run, exactly as the log records it.
- **Status:** all four milestones complete, PITCH ready — project is stage-ready. 🎤

---

## v0.3.0 — Gemini switch + fail-fast re-architecture — Oct 25, 2026 (owner-directed)

- **Built:**
  - **AI provider swap:** OpenRouter → **Google AI Studio (Gemini API)** on the owner's own key. New `app/ai_client.py`: plain-REST `generateContent` with `response_mime_type: application/json`, hidden **thought-part filtering** (thinking models corrupt naive text extraction), fence peeling + lenient JSON extraction (`raw_decode`, control-char tolerant), 429/503 backoff, and Gemini `usageMetadata` token counts in telemetry.
  - **Model chain picked from live probes of 7 models on the owner's key:** primary **`gemini-3.5-flash-lite` (2.4s, pristine JSON)**; fallbacks `gemini-3.1-flash-lite` (6.1s, pristine), `gemini-3.5-flash` (~6s when up), `gemini-3.6-flash` / `gemini-3.8-flash` (last resort under capacity). Excluded with evidence: `gemini-2.5-flash` (404 — closed to new users), `gemini-3-flash-preview` (mangled JSON), `gemini-flash-latest` (timeout).
  - **Offline fallbacks removed everywhere (fail-fast policy):** SerpApi cache fallback, the 3 engines' deterministic fallbacks, the amber cache banner — all deleted. Failures now surface as HTTP 503 with a friendly `detail` naming the cause (`SerpApiError` / `AIClientError` → `_fail()` in `app/main.py`); missing city → friendly 422. `data/sample_hotels_raw.json` is now a pytest-only fixture; the running app never reads it.
  - **SerpApi contract fix:** property details now go through `engine=google_hotels` + `property_token` (the old `_property_details` engine name returns 400 on current keys) with dates/`currency=INR`; `free_cancellation` parser normalizes both bool and date-string payloads.
  - Frontend: real error toasts reading the backend `detail`; health chip renamed to `serpapi`/`ai` (amber when a key is missing); `openai` dropped from requirements.
- **Verified green:** `python -m pytest -q` → **68 passed in ~1s** (rewritten: canned Gemini fixtures + fixture-backed SerpApi; fail-fast 503/422/500 surfaces pinned). **Live smoke on real APIs: health ok → search 200 (Gemini 1.6–2.0s per engine call, SerpApi 0.7s) → 3-hotel podium with 2-line AI badges → 6-platform arbitrage matrix with rupee-exact ₹3,586 (52%) savings + per-OTA perk verdicts → unknown hotel = clean 503.**
- **Judge insight:** v0.3.0 trades "never fails on stage" for something stronger: **the app never lies.** Every number is real Gemini-narrated, SerpApi-sourced data; when a service dies the UI states exactly what happened instead of quietly showing stale hotels — and every one of those honesty paths is a named, passing test.
- **Key cost note:** the OpenRouter free-tier ride is over; the AI now runs on the owner's Google AI Studio key at its normal billing (test suite still costs nothing — it mocks everything).

---


## Oct 25, 2026 (later) — Price-Unit Labeling Fix (podium /night vs matrix totals)

- **What owner flagged:** podium showed ₹2,117 but clicking the hotel showed ~₹7,207 — looked like a mismatch.
- **Root cause:** not bad data, unlabeled units. Podium shows the search-stage *per-night* snapshot; the matrix shows the *stay TOTAL* (3 nights, live re-quoted). Verified live: Solaris on Agoda = ₹2,349/night × 3 = ₹7,047 total — exact match.
- **Fix (labeling, everywhere):** `/api/property` now returns a `stay` block (check-in/out + nights = 3). Podium cards say "**from** ₹2,117 **/night**"; matrix subtitle: "Prices below are TOTALS — per-night shown under each"; every row shows "₹7,047 total · 3 nights" + "≈ ₹2,349/night"; savings ribbon framed "**over the whole 3-night stay**".
- **Verified green:** pytest 68 passed; served-HTML markers confirmed live (TOTALS / stay?.nights / from / /night all present); health {serpapi: ok, ai: ok, v0.3.0}. Live diag re-run: podium ₹2,349/night ↔ matrix ₹7,047 total ↔ ₹2,349/night — units reconcile to the rupee.
- **Judge insight:** the two prices were never wrong — they measure different things (nightly snapshot vs live stay total). Now the UI *names the unit on every number*, which is exactly what a real bookings product must do. Residual nuance (real dynamic pricing): the search-snapshot nightly can drift from the detail-stage nightly minutes later — noted, not a bug.
- Scope note: price comparison across OTAs is done for the demo's fixed 3-night window; a user-supplied date picker on the podium screen is a future feature (spec'd, not owed).

## Oct 26, 2026 — v0.3.1: Must-Pass Booking Parameters (no more assumed dates)

- **What owner flagged:** the app was silently assuming a 3-night stay two weeks out when the traveler never mentioned dates; and a real booking needs check-in, check-out and guest count before any price is meaningful. If the user forgets them, the app should *ask*.
- **Fix:** new must-pass gate (§4.5). `city`, `check_in`, `check_out`, `guests` are required; `demo_window()` and every silent default were deleted. Missing/invalid → HTTP 422 with `{detail, missing[], problems[], partial{}}`. Validation: ISO dates, check-in not in the past, check-out strictly after check-in, stay ≤ 30 nights, guests 1–16.
- **Frontend:** a 422 with `missing` opens an inline "Almost there — hotels need these to quote real prices" panel (City / Guests / Check-in / Check-out; missing fields highlighted red, date inputs bounded to future dates), then "Complete search →" re-runs. The intent summary now shows the real stay window ("Indore · 2026-11-09 → 2026-11-12 · 3 nights · 2 guests"). `openDetails` passes the user's dates to the matrix; the matrix subtitle repeats them and each row shows the stay total + per-night equivalent.
- **Verified green:** pytest **73 passed in ~1.2s** (5 new gate tests: missing dates prompt, missing guests prompt, reversed dates, past check-in, chips-win; property-without-dates 422). Live smoke on real APIs: no-dates search → 422 `missing: [guests, check_in, check_out]`; full search → 200 echoing the user's own dates; property without dates → 422; property with dates → totals for exactly that window (FabHotels ₹3,780 / Booking ₹3,450, ₹445 savings); reversed dates → 422. Health → 0.3.1.
- **Judge insight:** price honesty now starts *before* the numbers: a bookings product that guesses your dates is a product that lies. The app refuses to quote until it has the four facts every real OTA requires — and the refusal itself is a friendly, structured prompt the UI turns into a form, not an error page.
