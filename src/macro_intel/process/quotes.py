"""Quote change semantics: bp for yields and spreads, % for prices, points for indices like VIX."""

from __future__ import annotations

from macro_intel.models import MarketSpec


def compute_change(spec: MarketSpec, value: float | None, prev: float | None) -> float | None:
    if value is None or prev is None:
        return None
    if spec.change_units == "bp":
        return round((value - prev) * (1 if spec.units == "bp" else 100), 2)
    if spec.change_units == "pts":
        return round(value - prev, 4)
    return round((value / prev - 1.0) * 100.0, 4) if prev else None
