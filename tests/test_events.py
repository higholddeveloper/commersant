import random
from collections import Counter

import pytest

from core import config, events
from core.engine import Game
from core.events import EVENTS, Effect, EffectKind, EventDef


def state():
    return Game(seed=1).state


def test_pool_covers_all_markets_and_cross():
    scopes = {e.scope for e in EVENTS}
    assert {"commodity", "stock", "crypto", "realty", "bank", "cross"} <= scopes
    assert len({e.id for e in EVENTS}) == len(EVENTS)


def test_every_event_applies_and_text_is_short():
    for ev in EVENTS:
        s = state()
        s.holdings.update({"OIL": 10, "STUDIO": 2, "BTC": 1})
        res = events.apply_event(s, ev, random.Random(3))
        assert res.text and "{" not in res.text
        assert len(res.text) <= 160
        assert all(p > 0 for p in s.prices.values())


def test_price_event_changes_price_and_history():
    s = state()
    ev = EventDef("t", "commodity", "t", (Effect(EffectKind.PRICE, "OIL", 0.10, 0.10),))
    events.apply_event(s, ev, random.Random(1))
    assert s.prices["OIL"] == pytest.approx(77.0)
    assert s.history["OIL"][-1] == s.prices["OIL"]


def test_cash_and_holding_effects():
    s = state()
    s.holdings["OIL"] = 100
    ev = EventDef("t", "x", "t", (Effect(EffectKind.CASH, "ALL", 1000, 1000),
                                  Effect(EffectKind.HOLDING_PCT, "OIL", -0.5, -0.5)))
    events.apply_event(s, ev, random.Random(1))
    assert s.cash == 101_000
    assert s.holdings["OIL"] == 50


def test_repair_costs_per_property():
    s = state()
    s.holdings["STUDIO"] = 3
    ev = EventDef("t", "realty", "t", (Effect(EffectKind.REPAIR, "realty", 1000, 1000),))
    events.apply_event(s, ev, random.Random(1))
    assert s.cash == 100_000 - 3000


def test_modifier_expires():
    s = state()
    ev = EventDef("t", "x", "t", (Effect(EffectKind.DRIFT, "stock", 0.01, 0.01, 2),))
    events.apply_event(s, ev, random.Random(1))
    assert len(s.modifiers) == 1
    events.tick_modifiers(s)
    assert len(s.modifiers) == 1
    events.tick_modifiers(s)
    assert s.modifiers == []


def test_random_target_names_company():
    s = state()
    ev = next(e for e in EVENTS if e.id == "stock_beat")
    res = events.apply_event(s, ev, random.Random(5))
    assert any(a.name in res.text for a in config.assets_of(config.AssetClass.STOCK))


def test_event_chance_and_bad_bias():
    diff = config.DIFFICULTIES["normal"]
    rng = random.Random(0)
    fired = sum(events.roll_event(state(), rng, diff) is not None for _ in range(1000))
    assert 680 < fired < 820  # ~75%
    rng = random.Random(0)
    hard = Counter(events.pick_event(rng, config.DIFFICULTIES["hard"]).tone for _ in range(3000))
    rng = random.Random(0)
    easy = Counter(events.pick_event(rng, config.DIFFICULTIES["easy"]).tone for _ in range(3000))
    assert hard[-1] > easy[-1]
