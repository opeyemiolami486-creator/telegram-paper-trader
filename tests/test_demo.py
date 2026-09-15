from demo import PAIRS
from bot.strategy import Side, choose_lowest_probability


def test_demo_has_eight_pairs():
    assert len(PAIRS) == 8
    assert len({pair.name for pair in PAIRS}) == 8


def test_demo_chooses_lower_side():
    pair = PAIRS[0]
    result = choose_lowest_probability({Side.UP: pair.up_probability, Side.DOWN: pair.down_probability})
    assert result.side is Side.UP
