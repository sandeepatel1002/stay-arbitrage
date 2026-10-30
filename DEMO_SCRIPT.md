# StayArbitrage — Live Walkthrough Script (product + code)

> ~5 minutes total. `DO:` = your click/keystroke. `SAY:` = read it out loud. Anything in `[brackets]` is a stage note, don't read.
> Numbers you see live will differ from this sheet — that's the point: real data. Say "around ₹X" and keep moving.

---

## 0. Pre-flight (30 sec, before anyone's watching)

1. `DO:` `python -m uvicorn app.main:app --port 8000` → open `http://localhost:8000`.
2. `DO:` Confirm the top-right chip says **`● live · SerpApi ✓ · AI ✓`**.
3. `DO:` Open a second tab of the same URL as backup.
4. `DO:` Run one throwaway search so the first live one isn't cold.

---

# PART A — Product demo (~2.5 min)

### A1 · The problem, in one breath (~20 sec)

> **SAY:** "Priya has one sentence and 47 tabs to survive: *'somewhere peaceful in Indore, near 56 Dukan — elderly parents coming, under 8,000.'* Watch what one sentence can do."

### A2 · Show the app refuses to guess (~30 sec) ← *this is a differentiator*

`DO:` Type `peaceful place in indore near 56 dukan, elderly parents, under 8000` in the big box. Leave **Dates** and **Guests** chips empty. Click **Find my stay →**.

> **SAY:** "Notice what it did **not** do: it didn't invent dates. Every real OTA needs four facts — city, check-in, check-out, guests — so the app stops and asks. That panel with the date pickers? That's the API saying *'I still need a check-in date, a check-out date'* — a structured prompt, not an error page."

`DO:` Fill the panel: check-in `[today + ~2 weeks]`, check-out `[+3 days]`, guests `2`. Click **Complete search →**.

### A3 · Screen 2 — the 3-match podium (~40 sec)

`DO:` Point at the summary line, then the gold card.

> **SAY:** "The AI parsed the sentence into hard parameters — city, dates, guests, budget — plus semantic filters: near 56 Dukan, quiet, and an elevator for the parents. Three different hotels, three different jobs: **Best Overall Match**, **Value Pick**, **Premium Gem**. And this two-line badge is written per search — it matches *her stated needs* against verified amenities and review data."

`DO:` Point at a price: **`from ₹X /night`**.

> **SAY:** "Prices here are per-night — labeled, so nobody confuses a nightly rate with a stay total."

### A4 · Screen 3 — the arbitrage matrix (~45 sec)

`DO:` Click **Compare Live Deals & Perks** on the gold card.

> **SAY:** "Same room. Same dates. Every platform quoting it, side by side. These are **stay totals for the exact dates she picked** — and every row shows the per-night equivalent under it. The green ribbon: save ₹X over the whole stay, computed by plain Python, to the rupee. **LLMs never do our math.**"

`DO:` Point at a yellow perk note.

> **SAY:** "And the notes explain real net value — refundable here, breakfast there — so a cheap price that isn't actually cheap doesn't fool anyone."

### A5 · The honesty + proof moment (~35 sec)

`DO:` Click the bottom **AI Under the Hood** drawer.

> **SAY:** "Every AI call, unedited: model, latency, tokens, raw JSON. Three Gemini engines run this — about two seconds each, with a verified fallback chain behind them. And deliberately: **there is no mock data.** If SerpApi or Gemini is down, the app says exactly what failed instead of inventing hotels. The app never lies to the traveler."

---

# PART B — Code demo (~2 min)

`DO:` Switch to the editor. Keep it to four files — judges care about *how* it was built.

### B1 · Spec-driven development (~25 sec)

`DO:` Open `spec.md` (scroll the §4.5 must-pass section), then `GOALS.md`.

> **SAY:** "This was built spec-first: `spec.md` is the source of truth — every screen, endpoint, and failure mode is written down *before* it's coded. `GOALS.md` is the acceptance list, ticked only when a test proves it. `AI_DEV_LOG.md` is the build log with evidence."

### B2 · The determinism boundary (~25 sec)

`DO:` Open `app/pricing.py`.

> **SAY:** "The single most important design rule: **money is never computed by an LLM.** Cheapest fare, savings, breakfast-adjusted cost — pure Python functions, unit-tested to the rupee. The AI only *narrates* numbers Python already computed."

### B3 · AI engineering: model chain + schemas (~30 sec)

`DO:` Open `app/ai_client.py` (show the model chain + JSON extraction), then `app/ai_schemas.py`.

> **SAY:** "One shared Gemini client: strict Pydantic schemas, JSON-fence peeling, rate-limit backoff, and a live-verified fallback chain — primary `gemini-3.5-flash-lite`, four fallbacks behind it. Model choice is a `.env` line, not a rewrite. Every AI output is schema-validated before it touches the app."

### B4 · Fail-fast + required params (~20 sec)

`DO:` Open `app/main.py`, show `_booking_gate` and `_fail`.

> **SAY:** "Two guards here: the must-pass gate you saw in the product demo — city, dates, guests — and fail-fast: unreachable API → a friendly 503 naming what failed. No cache, no mock fallback. We deleted that on purpose."

### B5 · The proof (~20 sec)

`DO:` In the terminal: `python -m pytest -q`.

> **SAY:** "73 tests, about a second, zero network. They rehearse the happy path *and* every failure: dead Wi-Fi, Gemini outage, reversed dates, missing guests. Every claim in this demo has a test behind it. Run it yourself — that's the whole command."

---

## Closing line (10 sec)

> **SAY:** "Speak like a human, get matched like a concierge, pay like an insider. StayArbitrage — and yes, the tests are green."

---

## If something breaks (say it, don't hide it)

| What happens | What you say |
|---|---|
| 503 toast appears | "That's the design working — a real API just hiccuped and the app told us instead of inventing a hotel. One more click." → retry |
| Gemini slow (>8s) | "The AI is thinking — meanwhile look at the drawer, that's the live call in flight." |
| Matrix empty / odd | "Live availability changes per minute; let's pick another card." |
| Judge asks about model choice | "Bake-off of 7 models on our own key; `gemini-3.5-flash-lite` won on speed and clean JSON. Swap is one `.env` line." |
| Judge asks "is this real data?" | "Yes — open the drawer: latency, tokens and raw JSON for every call. Nothing cached." |

---

## 15-second version (elevator / time cut)

> "One sentence in, three AI-curated hotels out, then every booking platform's price for your exact dates side by side — with savings computed in Python, not guessed by an LLM. If a service is down it tells you instead of faking it. 73 tests. Want to run them?"
