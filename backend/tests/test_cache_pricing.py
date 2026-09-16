"""Cost engine cache/reasoning pricing (F29): no fabricated rates, no negatives."""
from __future__ import annotations

from aiobs_backend.cost import compute_llm_cost
from aiobs_backend.models import Pricing


def _pricing(**overrides) -> Pricing:
    values = dict(
        provider="acme",
        model="m",
        input_price_per_1m=1.0,
        output_price_per_1m=2.0,
    )
    values.update(overrides)
    return Pricing(**values)


def test_cache_read_tokens_use_their_own_price():
    pricing = _pricing(cache_read_price_per_1m=0.5)
    cost = compute_llm_cost(pricing, 1000, 1000, cache_read_tokens=400)
    assert cost == (600 * 1.0 + 400 * 0.5 + 1000 * 2.0) / 1_000_000.0


def test_missing_cache_write_price_marks_the_call_unpriced():
    pricing = _pricing(cache_read_price_per_1m=0.5, cache_write_price_per_1m=None)
    assert compute_llm_cost(pricing, 1000, 1000, cache_write_tokens=100) is None


def test_fresh_input_is_clamped_at_zero():
    """Providers whose input count excludes cache tokens must not go negative."""
    pricing = _pricing(cache_read_price_per_1m=0.5)
    cost = compute_llm_cost(pricing, 100, 0, cache_read_tokens=200)
    assert cost == (200 * 0.5) / 1_000_000.0


def test_reasoning_tokens_fall_back_to_the_output_rate():
    pricing = _pricing()
    cost = compute_llm_cost(pricing, 0, 1000, reasoning_tokens=400)
    assert cost == (1000 * 2.0) / 1_000_000.0


def test_missing_pricing_row_is_unpriced():
    assert compute_llm_cost(None, 10, 10) is None
