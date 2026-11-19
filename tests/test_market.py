import random

import pytest

from core import config, market
from core.engine import Game
from core.models import GameState, ModKind, Modifier


def fresh() -> GameState:
    return Game(seed=1).state


def test_init_prices_and_history():
    s = fresh()
    assert set(s.prices) == {a.symbol for a in config.ASSETS}
    assert all(s.prices[a.symbol] == a.base_price and s.history[a.symbol] == [a.base_price] for a in config.ASSETS)


def test_step_is_deterministic_for_seed():
    a, b = fresh(), fresh()
    market.step_prices(a, random.Random(42))
    market.step_prices(b, random.Random(42))
    assert a.prices == b.prices


def test_prices_stay_positive_and_history_bounded():
    s = fresh()
    rng = random.Random(7)
    for day in range(2, 400):
        s.day = day
        market.step_prices(s, rng)
    assert all(p > 0 for p in s.prices.values())
    assert all(len(h) <= config.HISTORY_LEN for h in s.history.values())


def test_turn_return_is_clamped():
    s = fresh()
    s.modifiers.append(Modifier(ModKind.DRIFT, "ALL", 5.0, 3))
    s.day = 2
    before = dict(s.prices)
    market.step_prices(s, random.Random(1))
    for sym, p in s.prices.items():
        assert p <= before[sym] * (1 + config.MAX_TURN_RETURN[1]) + 0.01


def test_modifier_drift_matches_target():
    s = fresh()
    s.modifiers.append(Modifier(ModKind.DRIFT, "crypto", 0.02, 2))
    s.modifiers.append(Modifier(ModKind.DRIFT, "BTC", 0.01, 2))
    assert market.modifier_drift(s, config.ASSET_BY_SYMBOL["BTC"]) == pytest.approx(0.03)
    assert market.modifier_drift(s, config.ASSET_BY_SYMBOL["OIL"]) == 0


def test_change_pct():
    s = fresh()
    s.history["OIL"] = [100.0, 110.0]
    assert market.change_pct(s, "OIL") == pytest.approx(0.10)
    s.history["OIL"] = [100.0]
    assert market.change_pct(s, "OIL") == 0.0
