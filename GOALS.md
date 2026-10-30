# StayArbitrage — Hackathon Acceptance Criteria (GOALS)

> Checked off by the OpenCode agent as each criterion is verified with automated tests.
> Judge-visible progress log lives in `AI_DEV_LOG.md`.

## Core Functional Goals

- [x] Intent parser extracts city and budget from conversational text. **✓ Milestone 2 (Gemini, v0.3.0)** — `gemini-3.5-flash-lite` live intent parse ≈1.6s; chips override verified; missing city → friendly 422.
- [x] Matchmaker returns exactly 3 distinct cards with personalized "Why This Fits You" chips. **✓ Milestone 2 + 3** — schema-enforced 3-distinct-tokens + 2-line badges; podium cards render them live.
- [x] Price comparison renders all available OTAs with the Perk Value Equivalence highlight. **✓ Milestone 3** — platform rows render with perk notes + verdict chips; live 4-OTA matrix verified.
- [x] Price math and savings are 100% computed via deterministic Python logic (`app/pricing.py`). **✓ Milestone 1** — rupee-exact, unit tests green; LLMs only narrate pre-computed numbers; savings ribbon shows the math.
- [x] UI runs cleanly at `http://localhost:8000` with 0 console errors. **✓ Milestone 3+4** — served page has zero undefined element ids, and the inline JS is compiler-verified (`node --check`) inside pytest.
- [x] `AI_DEV_LOG.md` tracks all milestone completions for judges. **✓** — scaffolding + M1 + M2 + M3 entries logged.

## Extended Verification Gates

- [x] **Fail-fast honesty (v0.3.0, owner-directed):** when SerpApi or Gemini is missing/unreachable, endpoints return HTTP 503 with a clear message naming what failed — no substitute data, ever. **✓ v0.3.0** — dead-network, API-outage and unconfigured-key tests all pin the clean 503/422 surfaces; unknown hotel → friendly 503 verified live.
- [x] Telemetry drawer shows model name, latency (ms), token usage, and raw JSON. **✓ Milestone 3+4** — collapsible drawer with live source chip + copy button.
- [x] All 3 "Book on [Platform]" style CTAs are real outgoing links. **✓ Milestone 4** — SerpApi links plus a deterministic synthetic-search-URL fallback; a dedicated test guarantees no fare renders a dead link.
- [x] pytest suite green (`pytest` exit code 0) covering engines, pricing, and E2E screens data paths. **✓ v0.3.1** — **73 passed in ~1s**: schemas, 3 engines (canned Gemini fixtures), rupee pricing, static + JS-compiler frontend contract, required-parameter prompts, and E2E fail-fast error surfaces (dead network, SerpApi outage, Gemini outage). Live smoke verified: real SerpApi + real Gemini, multi-OTA matrix, rupee-exact savings.
- [x] **Must-pass booking parameters (v0.3.1, owner-directed):** city, check-in, check-out and guests are required — the app never invents a stay window. Missing/invalid values → friendly 422 with a structured `missing` list that the UI turns into an inline date/guest prompt panel. **✓ v0.3.1** — gate tests (missing dates, missing guests, reversed dates, past check-in, chips-win) + live 422→panel flow verified.
