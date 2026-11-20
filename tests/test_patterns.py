import random

import pytest

from core import config, patterns
from core.engine import Game
from core.models import GameState, PatternRun


def fresh() -> GameState:
    return Game(seed=1).state


def test_all_patterns_start_flat_and_have_shape():
    for p in patterns.PATTERNS.values():
        assert p.points[0] == 0 and len(p.points) >= 4 and p.length >= 10
        assert patterns.target(p, 0) == 0
        assert patterns.target(p, p.length) == pytest.approx(p.points[-1])


def test_pattern_follows_its_trajectory():
    """Без шума накопленная доходность по шагам совпадает с заготовленной формой фигуры."""
    s = fresh()
    a = config.ASSET_BY_SYMBOL["AAPL"]
    patterns.force_pattern(s, a, "double_bottom")
    run = s.patterns["AAPL"]
    p = patterns.PATTERNS["double_bottom"]
    total = 0.0
    rng = random.Random(1)
    lows = []
    for _ in range(p.length):
        delta, vol_mult, _ = patterns.step_asset(s, a, rng)
        total += delta
        lows.append(total)
    assert total == pytest.approx(p.points[-1] * run.amp)
    # двойное дно: два минимума примерно на одном уровне, затем выход выше начала
    assert min(lows) == pytest.approx(-1.0 * run.amp, abs=0.2 * run.amp)
    assert lows[-1] > 0
    assert "AAPL" not in s.patterns and s.pattern_idle["AAPL"] >= 2   # фигура закончилась, пауза до следующей


@pytest.mark.parametrize("key,sign", [("head_shoulders", -1), ("inverse_hs", +1), ("rising_wedge", -1),
                                      ("falling_wedge", +1), ("double_top", -1), ("bull", +1), ("bear", -1)])
def test_pattern_net_direction_matches_bias(key, sign):
    p = patterns.PATTERNS[key]
    assert p.bias == sign
    assert patterns.target(p, p.length) * sign > 0


def test_flat_pattern_is_range_bound():
    p = patterns.PATTERNS["flat"]
    assert max(abs(x) for x in p.points) <= 0.25 and p.bias == 0


def test_prices_actually_form_patterns_and_regime_changes():
    g = Game(seed=3)
    g.state.cash, g.state.housing, g.state.vehicle, g.state.target = 10**9, 5, 5, 10**15
    seen_regimes = set()
    starts = 0
    for _ in range(200):
        before = set(g.state.patterns)
        g.next_turn()
        seen_regimes.add(g.state.regime)
        starts += len(set(g.state.patterns) - before)
    assert starts > 20
    assert len(seen_regimes) >= 2


def test_regime_biases_pattern_choice():
    def sample(regime):
        s = fresh()
        s.regime = regime
        bull = 0
        for i in range(400):
            s.patterns.clear()
            s.pattern_idle["OIL"] = 0
            patterns.step_asset(s, config.ASSET_BY_SYMBOL["OIL"], random.Random(i))
            if s.patterns.get("OIL") and s.patterns["OIL"].key in patterns.BULLISH:
                bull += 1
        return bull
    assert sample("bull") > sample("bear") * 2


def test_hint_only_when_pattern_mostly_formed():
    s = fresh()
    s.patterns["OIL"] = PatternRun("double_top", 5, 0.2)
    assert patterns.hint(s, "OIL") is None
    s.patterns["OIL"] = PatternRun("double_top", 14, 0.2)
    p, progress = patterns.hint(s, "OIL")
    assert p.key == "double_top" and progress > 0.5
    s.patterns["OIL"] = PatternRun("swan_crash", 10, 0.2)
    assert patterns.hint(s, "OIL") is None      # сценарии лебедей не подсказываем


def test_black_swan_hits_prices_immediately_and_recovers():
    s = fresh()
    swan = next(x for x in patterns.SWANS if x.id == "pandemic")
    before = dict(s.prices)
    patterns.apply_swan(s, swan, random.Random(1))
    assert all(s.prices[a.symbol] < before[a.symbol] for a in config.assets_of(config.AssetClass.STOCK))
    assert s.prices["OIL"] < before["OIL"] * 0.95
    assert s.history["OIL"][-1] == s.prices["OIL"]
    assert all(s.patterns[a.symbol].key == "swan_crash" for a in config.assets_of(config.AssetClass.STOCK))


def test_gulf_war_pushes_oil_up_but_stocks_down():
    s = fresh()
    swan = next(x for x in patterns.SWANS if x.id == "gulf_war")
    before = dict(s.prices)
    patterns.apply_swan(s, swan, random.Random(2))
    assert s.prices["OIL"] > before["OIL"] and s.prices["AAPL"] < before["AAPL"]


def test_swans_appear_in_game_as_critical_reports():
    found = 0
    for seed in range(40):
        g = Game(seed=seed)
        g.state.cash, g.state.housing, g.state.vehicle, g.state.target = 10**9, 5, 5, 10**15
        for _ in range(120):
            rep = g.next_turn()
            if any(e.kind == "swan" for e in rep.extra):
                found += 1
                assert rep.critical and rep.important
                assert "ЧЁРНЫЙ ЛЕБЕДЬ" in g.state.log[-1] or any("ЧЁРНЫЙ ЛЕБЕДЬ" in line for line in rep.lines)
    assert 40 * 120 * patterns.SWAN_CHANCE * 0.3 < found < 40 * 120 * patterns.SWAN_CHANCE * 1.8


def test_prices_stay_sane_with_patterns():
    g = Game(seed=11)
    g.state.cash, g.state.housing, g.state.vehicle, g.state.target = 10**9, 5, 5, 10**15
    for _ in range(249):
        g.next_turn()
    for a in config.ASSETS:
        assert a.base_price * config.PRICE_FLOOR_RATIO <= g.price(a.symbol) < a.base_price * 30
