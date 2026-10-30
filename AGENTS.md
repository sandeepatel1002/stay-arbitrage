# AGENTS.md — StayArbitrage Operating Guidelines for OpenCode

Project type: hackathon build ("StayArbitrage"). Owner is a **non-coder**; the agent owns all code, tests, and self-healing. The spec of record is `spec.md`.

## Absolute Rules

1. **Never ask the owner to write, edit, or debug code manually.** If a fix requires code changes, the agent makes them. Never paste stack traces at the owner; summarize in plain language.
2. **Autonomous verification loop:** after ANY code write/edit, immediately run shell commands
   - `python -m pytest -q` (backend), and
   - a uvicorn smoke check (`python -c "import requests;assert requests.get('http://localhost:8000/api/health').ok"` style, or TestClient) —
   and self-correct syntax/runtime/import errors, then re-run, until green, BEFORE marking a task complete in `AI_DEV_LOG.md` or `GOALS.md`.
3. **Frontend stays self-contained:** one file `static/index.html`, Tailwind via CDN, vanilla JS, no build step, no extra `.js`/`.css` files unless the user asks.
4. **Determinism boundary:** LLMs never compute prices. All rupee math lives in `app/pricing.py` and is unit-tested.
5. **Fail-fast honesty (v0.3.0, owner-directed):** there is NO cache/mock fallback for live data. When SerpApi or Gemini is missing or unreachable, raise `SerpApiError`/`AIClientError` and endpoints return HTTP 503 with a clear, friendly `detail` message. Never reintroduce substitute data or deterministic engine fallbacks.
6. **Check before changing:** if files exist outside a milestone's scope, assume they may be user work — investigate, don't overwrite.

## Environment

- Backend: FastAPI (uvicorn), Python 3.11+. Frontend: served at `/` from `static/`.
- Secrets via `.env` (see `.env.example`: `GEMINI_API_KEY`, `GEMINI_MODEL`, `GEMINI_FALLBACK_MODELS`, `SERPAPI_API_KEY`). Never hardcode keys. Never commit `.env` (add to `.gitignore`).
- AI: Google AI Studio Gemini API via plain REST (no openai SDK). Primary `gemini-3.5-flash-lite`; fallback chain `gemini-3.1-flash-lite`, `gemini-3.5-flash`, `gemini-3.6-flash`, `gemini-3.8-flash` — `gemini-2.5-flash` is 404-closed to new users, don't add it back.
- SerpApi: property details via `engine=google_hotels` + `property_token` (the old `google_hotels_property_details` engine name is unsupported).
- Tests: pytest + FastAPI TestClient; `tests/conftest.py` serves canned SerpApi payloads (from `data/sample_hotels_raw.json`, fixture-only) + canned Gemini answers — the real app must never touch the fixture file.
- Windows (PowerShell) host — prefer `python -m` invocations; quote paths with spaces.

## Communication Style for the Owner

- Plain-language status updates at the start and end of each command run.
- When tests fail: fix silently, report the fix in one sentence ("missing import — fixed, tests now green").
- Milestone completion must be recorded in `AI_DEV_LOG.md` (what was built, what was verified, judge-facing insight) and reflected in `GOALS.md` checkboxes.
