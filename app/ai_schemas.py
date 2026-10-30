"""The three AI-engine response contracts (spec §4) — strict Pydantic schemas.

Every LLM answer must validate against one of these; anything malformed is
retried once and then replaced by a deterministic fallback (never trusted).
"""
from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

FilterType = Literal["proximity", "needs", "vibe"]
SlotName = Literal["best_overall_match", "value_pick", "premium_gem"]
VerdictName = Literal["best_flexibility", "best_value", "premium_feel"]


class SemanticFilter(BaseModel):
    type: FilterType
    value: str = Field(min_length=2)


class IntentSchema(BaseModel):
    """Engine 1 — Smart Intent Parser output (spec §4.1)."""

    city: str = ""
    check_in: Optional[date] = None
    check_out: Optional[date] = None
    guests: Optional[int] = Field(default=None, ge=1, le=12)
    max_budget: Optional[int] = Field(default=None, ge=0)
    semantic_filters: list[SemanticFilter] = []
    search_query_expansion: str = ""

    @field_validator("city")
    @classmethod
    def _clean_city(cls, v: str) -> str:
        return (v or "").strip().lower()

    @field_validator("check_in", "check_out", mode="before")
    @classmethod
    def _tolerate_bad_dates(cls, v):
        """Bad/absent dates must never kill the whole parse (fail-soft rule)."""
        if v in (None, "", "null"):
            return None
        if isinstance(v, date):
            return v
        try:
            return date.fromisoformat(str(v)[:10])
        except Exception:
            return None


class MatchSlot(BaseModel):
    """One podium entry from Engine 2 (spec §4.2)."""

    slot: SlotName
    property_token: str = Field(min_length=3)
    why_fits_you: str  # exactly 2 lines, enforced below

    @field_validator("why_fits_you")
    @classmethod
    def _two_lines(cls, v: str) -> str:
        lines = [ln.strip() for ln in v.strip().splitlines() if ln.strip()]
        if len(lines) != 2:
            raise ValueError("why_fits_you must be exactly 2 lines")
        return "\n".join(lines)


class MatchesSchema(BaseModel):
    """Engine 2 full answer: exactly 3 distinct hotels (spec §4.2)."""

    matches: list[MatchSlot] = Field(min_length=3, max_length=3)

    @model_validator(mode="after")
    def _distinct_tokens_and_slots(self):
        tokens = [m.property_token for m in self.matches]
        slots = [m.slot for m in self.matches]
        if len(set(tokens)) != 3:
            raise ValueError("podium slots must reference 3 distinct hotels")
        if len(set(slots)) != 3:
            raise ValueError("podium slots must be the 3 unique slot names")
        return self


class PerkNote(BaseModel):
    """Engine 3 note for a single OTA platform (spec §4.3)."""

    source: str = Field(min_length=2)
    net_value_note: str = Field(min_length=8)
    verdict: Optional[VerdictName] = None


class PerkValueSchema(BaseModel):
    """Engine 3 full answer, one note per platform (spec §4.3)."""

    notes: list[PerkNote] = Field(min_length=1)

    @model_validator(mode="after")
    def _distinct_sources(self):
        sources = [n.source.strip().lower() for n in self.notes]
        if len(set(sources)) != len(sources):
            raise ValueError("one note per platform source")
        return self
