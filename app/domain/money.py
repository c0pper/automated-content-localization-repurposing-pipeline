"""Exact money helpers.

Money is stored as integer micro-USD (1 USD = 1_000_000 micro-USD) and exchanged as
decimal strings with up to six fractional digits. Binary floating point is never used for
cost arithmetic.
"""

from __future__ import annotations

from decimal import ROUND_CEILING, Decimal, InvalidOperation

MICRO_PER_USD = 1_000_000


def parse_usd(value: str | int | Decimal | None) -> int:
    """Parse a USD decimal string (or integer micro-USD when given an int)."""
    if value is None:
        return 0
    if isinstance(value, int):
        return value
    try:
        amount = Decimal(str(value).strip())
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"Invalid USD amount: {value!r}") from exc
    if amount < 0:
        raise ValueError("USD amounts cannot be negative")
    return int((amount * MICRO_PER_USD).to_integral_value(rounding=ROUND_CEILING))


def format_usd(micro_usd: int) -> str:
    """Render integer micro-USD as a decimal string with 2-6 fractional digits."""
    if micro_usd < 0:
        raise ValueError("micro-USD cannot be negative")
    amount = Decimal(micro_usd) / MICRO_PER_USD
    text = f"{amount:.6f}".rstrip("0")
    whole, _, fraction = text.partition(".")
    if len(fraction) < 2:
        fraction = (fraction + "00")[:2]
    return f"{whole}.{fraction}"


def with_margin(base_micro_usd: int, units: float, margin: float) -> int:
    """Return ``units * base_rate * (1 + margin)`` rounded up to a whole micro-USD."""
    if units <= 0:
        return 0
    amount = Decimal(str(units)) * Decimal(base_micro_usd) * (Decimal(1) + Decimal(str(margin)))
    return int(amount.to_integral_value(rounding=ROUND_CEILING))
