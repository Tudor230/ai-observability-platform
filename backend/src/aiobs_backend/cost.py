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
) -> float | None:
    """Per-LLM-span USD cost, or ``None`` when the call cannot be priced.

    Missing cache prices or a missing pricing row make the call *unpriced*
    (F29): the engine never fabricates a rate or double-discounts cache tokens.
    The fresh-input count is clamped at zero so cache conventions that already
    exclude cached tokens cannot produce negative cost.
    """
    if pricing is None:
        return None
    inp = float(pricing.input_price_per_1m or 0.0)
    outp = float(pricing.output_price_per_1m or 0.0)
    if cache_read_tokens and pricing.cache_read_price_per_1m is None:
        return None
    if cache_write_tokens and pricing.cache_write_price_per_1m is None:
        return None
    cache_read = float(pricing.cache_read_price_per_1m or 0.0)
    cache_write = float(pricing.cache_write_price_per_1m or 0.0)
    # Reasoning tokens are billed at the output rate when no specific price is set.
    reasoning = (
        float(pricing.reasoning_price_per_1m)
        if pricing.reasoning_price_per_1m is not None
        else outp
    )
    fresh_input = max(0, input_tokens - cache_read_tokens - cache_write_tokens)
    fresh_output = max(0, output_tokens - reasoning_tokens)
    return (
        fresh_input * inp
        + cache_read_tokens * cache_read
        + cache_write_tokens * cache_write
        + fresh_output * outp
        + reasoning_tokens * reasoning
    ) / 1_000_000.0