"""Versioned USD rate card for every paid provider/model/unit."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from app.domain.enums import CostUnitType
from app.domain.errors import GuardrailViolation
from app.domain.money import with_margin


@dataclass(frozen=True, slots=True)
class Rate:
    provider: str
    model: str
    unit_type: CostUnitType
    micro_usd_per_unit: int


DEFAULT_RATES: tuple[Rate, ...] = (
    Rate("openai", "whisper-1", CostUnitType.MINUTES, 10_000),
    Rate("jev", "jev-decisions-pinned", CostUnitType.REQUESTS, 5_000),
    Rate("openrouter", "planning", CostUnitType.CHARACTERS, 100),
    Rate("openrouter", "copy", CostUnitType.CHARACTERS, 80),
    Rate("openrouter", "translation", CostUnitType.CHARACTERS, 120),
    # Curated model overrides are priced by provider unless a model-specific entry exists.
    Rate("openrouter", "*", CostUnitType.CHARACTERS, 100),
    Rate("elevenlabs", "eleven_multilingual_v2", CostUnitType.CHARACTERS, 300),
    Rate("synclabs", "lipsync-2", CostUnitType.SECONDS, 5_000),
)


@dataclass(slots=True)
class RateCard:
    """Resolves provider/model rates and applies the safety margin.

    A missing rate fails closed: callers never make a paid call with an unknown price.
    """

    version: str = "2026-10-01"
    margin: float = 0.20
    rates: dict[tuple[str, str], Rate] = field(default_factory=dict)

    @classmethod
    def default(cls, *, version: str = "2026-10-01", margin: float = 0.20) -> RateCard:
        card = cls(version=version, margin=margin)
        for rate in DEFAULT_RATES:
            card.rates[(rate.provider, rate.model)] = rate
        return card

    @classmethod
    def from_file(cls, path: Path, *, version: str, margin: float = 0.20) -> RateCard:
        payload = json.loads(path.read_text(encoding="utf-8"))
        card = cls(version=version, margin=margin)
        for item in payload.get("rates", []):
            rate = Rate(
                provider=item["provider"],
                model=item["model"],
                unit_type=CostUnitType(item["unit_type"]),
                micro_usd_per_unit=int(item["micro_usd_per_unit"]),
            )
            card.rates[(rate.provider, rate.model)] = rate
        return card

    def resolve(self, provider: str, model: str) -> Rate:
        rate = self.rates.get((provider, model)) or self.rates.get((provider, "*"))
        if rate is None:
            raise GuardrailViolation(
                "rate_missing",
                f"No rate-card entry for {provider}/{model}; refusing the paid call",
            )
        return rate

    def estimate(
        self,
        provider: str,
        model: str,
        units: float,
        *,
        unit_type: CostUnitType | None = None,
    ) -> int:
        rate = self.resolve(provider, model)
        if unit_type is not None and rate.unit_type is not unit_type:
            raise GuardrailViolation(
                "rate_unit_mismatch",
                f"Rate for {provider}/{model} is per {rate.unit_type.value}, "
                f"not {unit_type.value}",
            )
        return with_margin(rate.micro_usd_per_unit, units, self.margin)

    def rate_for(self, provider: str, model: str) -> int:
        return self.resolve(provider, model).micro_usd_per_unit
