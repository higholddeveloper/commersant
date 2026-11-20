"""Тесты версии 1.3: тишина на рынке, наследства, лотереи, гранты, призы владельцам, налог с продажи недвижимости."""
import random

import pytest

from core import config, events, windfalls
from core import property as prop
from core.engine import Game
from core.models import GameStatus


@pytest.fixture
def g() -> Game:
    game = Game(seed=11)
    game.state.target = 10**12
    return game


def test_start_cash_and_loan_terms():
    assert config.DIFFICULTIES["normal"].start_cash == 200_000
    assert all(d.loan_term == 30 for d in config.DIFFICULTIES.values())
    assert config.DIFFICULTIES["normal"].loan_rate == 0.005       # вдвое ниже прежних 1%


def test_losses_are_halved(g):
    rng = random.Random(1)
    # потери от происшествий вдвое меньше прежних максимумов (кража: до 10% наличных на уровне 1 -> до 5%)
    m = prop.MISHAP_BY_ID["h_squatters"]
    for _ in range(200):
        out = prop.resolve(m, 1, 100_000, rng)
        assert -5_000 <= out.cash_delta <= 0
    assert prop.MISHAP_SCALE == 0.5 and prop.ILLNESS_CHANCE < 0.45


def test_oil_fire_and_land_cataclysm_need_holdings(g):
    rng = random.Random(3)
    s = g.state
    ids = {events.pick_event(rng, g.diff, s).id for _ in range(3000)}
    assert "oil_fire" not in ids and "land_quake" not in ids      # нет ни нефти, ни земли — не выпадают
    s.holdings["OIL"], s.holdings["LAND"] = 1000, 100
    ids = {events.pick_event(rng, g.diff, s).id for _ in range(6000)}
    assert "oil_fire" in ids and "land_quake" in ids


def test_oil_fire_destroys_five_percent(g):
    g.state.holdings["OIL"] = 1000
    ev = next(e for e in events.EVENTS if e.id == "oil_fire")
    events.apply_event(g.state, ev, random.Random(1))
    assert g.state.holdings["OIL"] == 950


def test_land_cataclysm_five_to_ten_percent(g):
    ev = next(e for e in events.EVENTS if e.id == "land_quake")
    for seed in range(20):
        g.state.holdings["LAND"] = 1000
        events.apply_event(g.state, ev, random.Random(seed))
        assert 900 <= g.state.holdings["LAND"] <= 950


def test_calm_market_moves_less():
    quiet, loud = [], []
    for seed in range(30):
        for calm, bucket in ((True, quiet), (False, loud)):
            game = Game(seed=seed)
            game.state.calm = calm
            from core import market
            before = game.state.prices["NVDA"]
            market.step_prices(game.state, random.Random(seed))
            bucket.append(abs(game.state.prices["NVDA"] / before - 1))
    assert sum(quiet) < sum(loud) * 0.6


def test_calm_turns_happen_often_and_suppress_swans(g):
    g.state.cash, g.state.housing, g.state.vehicle = 10**9, 5, 5
    calm_turns = 0
    for _ in range(200):
        rep = g.next_turn()
        if g.state.calm:
            calm_turns += 1
            assert not any(e.kind == "swan" for e in rep.extra)
    assert 0.15 < calm_turns / 200 < 0.55


def test_realty_sale_tax_only_on_profit(g):
    g.buy("STUDIO", 1)
    g.state.prices["STUDIO"] *= 1.5               # прибыль
    cash = g.state.cash
    gross = g.bid("STUDIO")
    proceeds = g.sell("STUDIO", 1)
    assert g.last_tax > 0
    assert proceeds == pytest.approx(gross - g.last_tax, rel=1e-3)
    assert g.state.cash == pytest.approx(cash + proceeds)
    g.buy("COFFEE", 1)
    g.state.prices["COFFEE"] *= 0.8               # убыток — налога нет
    g.sell("COFFEE", 1)
    assert g.last_tax == 0
    g.buy("OIL", 10)
    g.state.prices["OIL"] *= 2
    g.sell("OIL", 10)                             # налог только на недвижимость
    assert g.last_tax == 0


def test_welfare_for_the_poor_with_cheapest_housing(g):
    s = g.state
    s.housing = 1
    got = [windfalls.roll(s, random.Random(i), 50_000) for i in range(400)]
    welfare = [e for evs in got for e in evs if e.event_id == "welfare"]
    assert welfare and all(e.tone > 0 and e.kind == "luck" for e in welfare)
    s.housing = 3
    assert not any(e.event_id == "welfare" for i in range(400) for e in windfalls.roll(s, random.Random(i), 50_000))
    s.housing = 1
    assert not any(e.event_id == "welfare" for i in range(400) for e in windfalls.roll(s, random.Random(i), 2_000_000))


@pytest.mark.parametrize("symbol,event_id", [("STUDIO", "prize_studio"), ("COFFEE", "prize_coffee"),
                                              ("OFFICE", "prize_office"), ("WAREHOUSE", "prize_warehouse")])
def test_owner_prizes_need_the_asset(g, monkeypatch, symbol, event_id):
    monkeypatch.setattr(windfalls, "INHERIT_CHANCE", 0.0)   # наследство тоже может подарить объект
    s = g.state
    s.housing = 3
    ids = {e.event_id for i in range(1500) for e in windfalls.roll(s, random.Random(i), 10**7)}
    assert event_id not in ids
    s.holdings[symbol] = 1
    ids = {e.event_id for i in range(1500) for e in windfalls.roll(s, random.Random(i), 10**7)}
    assert event_id in ids


def test_more_objects_means_more_prizes(g):
    g.state.housing = 3

    def count(n: int) -> int:
        g.state.holdings["STUDIO"] = n
        return sum(e.event_id == "prize_studio" for i in range(4000) for e in windfalls.roll(g.state, random.Random(i), 10**7))

    assert count(5) > count(1) * 1.3


def test_office_gives_crypto_and_warehouse_gives_land(g):
    s = g.state
    s.housing = 3
    s.holdings["OFFICE"] = s.holdings["WAREHOUSE"] = 3
    before = sum(s.holdings.get(c, 0) for c in ("BTC", "ETH", "SOL", "DOGE")), s.holdings.get("LAND", 0)
    for i in range(300):
        windfalls.roll(s, random.Random(i), 10**7)
    after = sum(s.holdings.get(c, 0) for c in ("BTC", "ETH", "SOL", "DOGE")), s.holdings.get("LAND", 0)
    assert after[0] > before[0] and after[1] > before[1]
    assert s.cost_basis["LAND"] > 0


def test_inheritance_variants(g):
    s = g.state
    seen = set()
    for i in range(3000):
        for e in windfalls.roll(s, random.Random(i), 10**7):
            if e.event_id.startswith("inherit"):
                seen.add(e.event_id)
                assert "Умер" in e.text
    assert {"inherit_cash", "inherit_realty", "inherit_assets", "inherit_housing", "inherit_vehicle"} <= seen
    assert s.housing >= 1 and s.vehicle >= 1


def test_lottery_and_grants_happen(g):
    ids = {e.event_id for i in range(2000) for e in windfalls.roll(g.state, random.Random(i), 10**7)}
    assert {"lottery", "grant"} <= ids


def test_windfalls_appear_in_turn_reports(g):
    g.state.cash, g.state.housing, g.state.vehicle = 500_000, 3, 3
    kinds = set()
    for _ in range(120):
        rep = g.next_turn()
        kinds |= {e.kind for e in rep.extra}
        if g.state.status is not GameStatus.PLAYING:
            break
    assert "luck" in kinds
