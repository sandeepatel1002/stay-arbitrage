# StayArbitrage

**AI Hotel Matchmaker & Multi-OTA Price Arbitrage Engine** — built 100% inside OpenCode by an AI coding agent under a Spec-Driven Development workflow. The human operator wrote zero lines of code.

> One messy sentence → the perfect hotel podium → the same room across every platform, priced to the rupee.

---

## The 3-Screen Flow

1. **Home & Intent Search** — type like a human: *"peaceful place in Indore near 56 Dukan, elderly parents coming, under 8000"*. Engine 1 (Smart Intent Parser, Gemini) turns it into hard search parameters + semantic filters (proximity, mobility needs, vibe). Structured chips (City / Dates / Guests / Max Budget) override anything ambiguous.
2. **Curated 3-Match Podium** — Engine 2 (Personalized Matchmaker) picks exactly 3 distinct hotels: 🏆 **Best Overall Match**, 💵 **Value Pick**, 💎 **Premium Gem** — each with a personalized 2-line "Why This Fits You" badge grounded in real amenities and review data.
3. **Price Arbitrage & Direct Booking Matrix** — the same room across Agoda, Booking.com, Priceline, MakeMyTrip, official sites etc. Engine 3 narrates the *real net value* of each fare's perks (free-cancellation dates, breakfast), while a **deterministic Python True-Cost Calculator** computes exact rupee savings (LLMs never do money math). One tap → "Book on [Platform]".

**"AI Under the Hood" telemetry drawer** — bottom of every screen: model name, latency (ms), tokens in/out, and the raw JSON of every AI call. Nothing is faked, nothing is hidden.

## Judge Facts

- **Powered by Google AI Studio (Gemini API)** on the owner's own key — primary `gemini-3.5-flash-lite` (≈2s live) with a live-verified fallback chain: `gemini-3.1-flash-lite` → `gemini-3.5-flash` → `gemini-3.6-flash` → `gemini-3.8-flash`.
- **Fail-fast by design (v0.3.0):** if the network or an API dies, the app tells you exactly what broke — a friendly HTTP 503 message, no substitute data, no silent mock hotels.
- **Everything is verified:** `python -m pytest` — unit (rupee-exact pricing), engine (canned Gemini fixtures), schema contract, static frontend contract, JavaScript compiler parse, and E2E via in-process HTTP tests including fail-fast 503 surfaces.
- **Spec-driven:** `spec.md` is the single source of truth; `AI_DEV_LOG.md` records what was built and verified per milestone; `GOALS.md` is the acceptance checklist.
- **Demo walkthrough:** `DEMO_SCRIPT.md` — a ~5-minute product + code demo script with timings, exact lines to say, and fallbacks.

## Quickstart (2 commands)

```powershell
pip install -r requirements.txt
python -m uvicorn app.main:app --port 8000
```

Open **http://localhost:8000**. Add keys in `.env` (copy from `.env.example`) for live SerpApi + Gemini.

| Key | Get it |
|---|---|
| `SERPAPI_API_KEY` | https://serpapi.com/manage-api-key |
| `GEMINI_API_KEY` | https://aistudio.google.com/apikey |

## Tech Stack

Python 3.11+ · FastAPI · Google AI Studio (Gemini API, REST) · SerpApi google_hotels engines · single-file HTML/Tailwind/Vanilla-JS frontend · pytest.

## OpenCode Commands

| Command | Does |
|---|---|
| `/build-milestone 1–4` | Builds + verifies a milestone end-to-end, updates the judge log |
| `/verify` | Full automated health check (tests + serving + happy path) |
| `/demo-prep` | Generates the 2-minute stage presentation in `PITCH.md` |
