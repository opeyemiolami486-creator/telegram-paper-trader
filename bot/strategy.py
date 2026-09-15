from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping


class Side(str, Enum):
    UP = "UP"
    DOWN = "DOWN"


@dataclass(frozen=True)
class Decision:
    side: Side | None
    reason: str


def choose_lowest_probability(probabilities: Mapping[Side, float] | None) -> Decision:
    """Return the lower supplied probability, or abstain when data is unsafe/missing.

    This is intentionally not a prediction engine. It never scrapes a page to invent
    probabilities and abstains on ties, invalid values, or incomplete input.
    """
    if not probabilities or set(probabilities) != {Side.UP, Side.DOWN}:
        return Decision(None, "No trusted UP/DOWN probabilities supplied; abstaining")
    up, down = probabilities[Side.UP], probabilities[Side.DOWN]
    if not (0.0 <= up <= 1.0 and 0.0 <= down <= 1.0):
        return Decision(None, "Probability outside [0, 1]; abstaining")
    if up == down:
        return Decision(None, "Probabilities tie; abstaining")
    side = Side.UP if up < down else Side.DOWN
    return Decision(side, f"Selected lower supplied probability ({side.value})")
