"""Small numeric helpers shared by analytics/alerts/overview."""
from __future__ import annotations

from math import ceil, floor


def percentile(values: list[float], pct: float) -> float:
    """Linear-interpolated percentile over an unsorted list of values."""
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    k = (len(ordered) - 1) * pct
    lo, hi = floor(k), ceil(k)
    if lo == hi:
        return ordered[lo]
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (k - lo)
