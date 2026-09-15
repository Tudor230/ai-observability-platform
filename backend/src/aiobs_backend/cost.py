"""Cost engine (plans/backend.md §8): token counts × pricing, USD."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Pricing


class PricingResolver:
    """Resolve a (provider, model) to an effective pricing row."""

    def __init__(self, session: Session, at: datetime):
        self._session = session
        self._at = at
        self._cache: dict[tuple[str, str], Pricing | None] = {}

    def resolve(self, provider: str | None, model: str | None) -> Pricing | None:
        if not provider or not model:
            return None
        key = (provider.lower(), model)
        if key in self._cache:
            return self._cache[key]
        self._cache[key] = self._resolve(provider, model)
        return self._cache[key]

    def _resolve(self, provider: str, model: str) -> Pricing | None:
        rows = (
            self._session.execute(
                select(Pricing)
                .where(
                    Pricing.provider == provider.lower(),
                    Pricing.effective_from <= self._at,
                )
                .order_by(Pricing.effective_from.desc())
            )
            .scalars()
            .all()
        )
        if not rows:
            return None
        # Fallback chain: exact model → model prefix → provider default → unpriced.
        exact = next(
            (p for p in rows if p.model_match == "exact" and p.model == model), None
        )
        if exact:
            return exact
        prefix = next(
            (p for p in rows if p.model_match == "prefix" and model.startswith(p.model)),
            None,
        )
        if prefix:
            return prefix
        return next((p for p in rows if p.model_match == "default"), None)


def compute_llm_cost(
    pricing: Pricing | None,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
    reasoning_tokens: int = 0,
) -> float:
    """Per-LLM-span USD cost. 0 if no pricing applies (caller marks it unpriced)."""
    if pricing is None:
        return 0.0
    inp = float(pricing.input_price_per_1m or 0.0)
    outp = float(pricing.output_price_per_1m or 0.0)
    cache_read = float(pricing.cache_read_price_per_1m) if pricing.cache_read_price_per_1m is not None else inp
    cache_write = float(pricing.cache_write_price_per_1m) if pricing.cache_write_price_per_1m is not None else inp * 1.25
    reasoning = float(pricing.reasoning_price_per_1m) if pricing.reasoning_price_per_1m is not None else outp
    return (
        (input_tokens - cache_read_tokens - cache_write_tokens) * inp
        + cache_read_tokens * cache_read
        + cache_write_tokens * cache_write
        + (output_tokens - reasoning_tokens) * outp
        + reasoning_tokens * reasoning
    ) / 1_000_000.0