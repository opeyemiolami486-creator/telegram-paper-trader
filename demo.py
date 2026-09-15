from __future__ import annotations

import random
import time
from dataclasses import dataclass

from bot.strategy import Side, choose_lowest_probability


@dataclass(frozen=True)
class MockPair:
    name: str
    up_probability: float
    down_probability: float


PAIRS = tuple(
    MockPair(f"PAIR-{i}", up_probability=0.35 + i * 0.03, down_probability=0.65 - i * 0.03)
    for i in range(1, 9)
)


def run_demo(settlement_seconds: float = 0.1) -> None:
    order = list(PAIRS)
    random.SystemRandom().shuffle(order)
    print("LOCAL MOCK SITE: paper mode only")
    print("Randomized order:", " -> ".join(p.name for p in order))
    for pair in order:
        decision = choose_lowest_probability({Side.UP: pair.up_probability, Side.DOWN: pair.down_probability})
        print(f"{pair.name}: {decision.side.value if decision.side else 'ABSTAIN'} | {decision.reason}")
        print("  waiting for settlement...")
        time.sleep(settlement_seconds)
        print("  settled (simulated)")
    print("Demo complete. No browser, Telegram account, real credits, or live trade was used.")


if __name__ == "__main__":
    run_demo()
