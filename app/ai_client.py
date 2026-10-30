"""Google AI Studio (Gemini API) client — one shared client for all 3 engines.

`complete_json` is the single entry point: strict schema validation, robust
JSON extraction (thought-part filtering, control-char tolerance, fence
peeling), a model fallback chain, and full telemetry. Fail-fast policy: when
every attempt fails it raises `AIClientError` with a clear message — engines
propagate it and endpoints return HTTP 503 with friendly detail (no silent
substitute output).
"""
from __future__ import annotations

import json
import re
import time
from typing import Any, Type, TypeVar

import requests
from pydantic import BaseModel

from app import config
from app.models import TelemetryRecord

T = TypeVar("T", bound=BaseModel)


class AIClientError(RuntimeError):
    """Raised when the AI call cannot produce a schema-valid answer."""


def available() -> bool:
    return bool(config.GEMINI_API_KEY)


def _answer_text(payload: dict[str, Any]) -> str:
    """Collect only real answer parts — Gemini thinking models prepend hidden
    parts flagged `"thought": true`, which would corrupt JSON extraction."""
    candidates = payload.get("candidates") or []
    if not candidates:
        raise ValueError("no candidates in Gemini response")
    parts = (candidates[0].get("content") or {}).get("parts") or []
    texts = [p.get("text", "") for p in parts if "text" in p and not p.get("thought", False)]
    return "".join(texts)


def _parse_json_obj(text: str) -> dict[str, Any]:
    """Lenient extraction: peel ```fences```, find the first `{`, tolerate
    literal control characters — free models occasionally emit rough JSON."""
    fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.S)
    candidate = fenced.group(1) if fenced else text
    start = candidate.find("{")
    if start == -1:
        raise ValueError("no JSON object found in AI answer")
    obj, _ = json.JSONDecoder(strict=False).raw_decode(candidate[start:])
    if not isinstance(obj, dict):
        raise ValueError("AI answer is not a JSON object")
    return obj


def _friendly(status: int, body: str) -> str:
    if status == 429:
        return "rate limit (429) — too many requests right now"
    if status == 503:
        return "model overloaded (503) — high demand"
    if status == 404:
        return "model not available (404)"
    return f"HTTP {status}: {body[:140]}"


def complete_json(
    engine_name: str,
    system_prompt: str,
    user_prompt: str,
    schema_cls: Type[T],
    temperature: float = 0.2,
    max_tokens: int = 700,
) -> tuple[T, TelemetryRecord]:
    """One Gemini call → one schema-valid instance + one telemetry record.

    Chain: primary model gets 2 attempts; each fallback in
    `GEMINI_FALLBACK_MODELS` gets 1 attempt. 429/503 pause briefly before the
    next try. All attempts exhausted → AIClientError (fail-fast, no mock data).
    """
    if not available():
        raise AIClientError("GEMINI_API_KEY not configured — add your Google AI Studio key to .env")

    started = time.perf_counter()
    last_error: Exception | None = None
    model_plan: list[tuple[str, int, bool]] = (
        [(config.GEMINI_MODEL, 1, False), (config.GEMINI_MODEL, 2, False)]
        + [(m, 1, True) for m in config.GEMINI_FALLBACK_MODELS]
    )

    for model, attempt, is_fallback in model_plan:
        try:
            resp = requests.post(
                f"{config.GEMINI_BASE_URL}/models/{model}:generateContent",
                params={"key": config.GEMINI_API_KEY},
                json={
                    "system_instruction": {"parts": [{"text": system_prompt}]},
                    "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
                    "generationConfig": {
                        "response_mime_type": "application/json",
                        "temperature": temperature,
                        "maxOutputTokens": max_tokens,
                    },
                },
                timeout=config.GEMINI_REQUEST_TIMEOUT,
                headers={"Content-Type": "application/json"},
            )
            if resp.status_code != 200:
                raise RuntimeError(_friendly(resp.status_code, resp.text))
            payload = resp.json()
            data = _parse_json_obj(_answer_text(payload))
            validated = schema_cls.model_validate(data)
            usage = payload.get("usageMetadata", {})
            return validated, TelemetryRecord(
                engine=engine_name,
                model=model,
                latency_ms=int((time.perf_counter() - started) * 1000),
                tokens_in=int(usage.get("promptTokenCount", 0)),
                tokens_out=int(usage.get("candidatesTokenCount", 0)),
                raw_json={
                    "schema": schema_cls.__name__,
                    "attempt": attempt,
                    "recovered_via_fallback_model": is_fallback,
                },
                source="live",
            )
        except Exception as exc:  # noqa: BLE001 — try the next attempt/model
            last_error = exc
            msg = str(exc)
            if "429" in msg or "rate limit" in msg.lower():
                time.sleep(2.5)  # breathe before the next attempt

    raise AIClientError(
        f"{schema_cls.__name__} could not be produced by Gemini after trying "
        f"{len(model_plan)} attempts: {last_error}"
    )
