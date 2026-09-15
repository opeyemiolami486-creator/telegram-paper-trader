from bot.strategy import Side, choose_lowest_probability


def test_abstains_without_probabilities():
    result = choose_lowest_probability(None)
    assert result.side is None


def test_selects_lower_probability():
    result = choose_lowest_probability({Side.UP: 0.4, Side.DOWN: 0.6})
    assert result.side is Side.UP


def test_tie_abstains():
    result = choose_lowest_probability({Side.UP: 0.5, Side.DOWN: 0.5})
    assert result.side is None


def test_invalid_probability_abstains():
    result = choose_lowest_probability({Side.UP: 1.2, Side.DOWN: 0.2})
    assert result.side is None
