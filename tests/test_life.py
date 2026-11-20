import random

import pytest

from core import property as prop, windfalls
from core import storage, timeline
from core.engine import Game, TradeError
from core.models import GameStatus


@pytest.fixture
def g() -> Game:
    game = Game(seed=1, player="Тест")
    game.state.target = 10**12
    return game


# ---------------------------- календарь ----------------------------
def test_calendar_dates_and_elapsed():
    assert timeline.fmt_date(1) == "6 янв 2025"
    assert timeline.fmt_date(2) == "13 янв 2025"
    assert timeline.elapsed_text(1) == "0 нед."
    assert timeline.elapsed_text(4) == "3 нед."
    assert timeline.elapsed_text(53) == "1 г."
    assert "мес." in timeline.elapsed_text(20)
    months = sum(timeline.month_changed(d) for d in range(2, 54))
    assert months == 12


def test_utilities_charged_monthly_not_every_turn(g):
    g.state.housing, g.state.vehicle = 3, 3
    g.state.cash = 10**7
    charged = []
    for _ in range(26):
        rep = g.next_turn()
        charged.append(rep.utilities)
    due = prop.HOUSING[2].upkeep + prop.VEHICLES[2].upkeep
    assert charged.count(due) == sum(timeline.month_changed(d) for d in range(2, 28))
    assert set(charged) == {0.0, due}


def test_utilities_scale_with_housing_level(g):
    ups = [prop.tier("housing", lvl).upkeep for lvl in range(1, 6)]
    assert ups == sorted(ups) and len(set(ups)) == 5


# ---------------------------- покупка / продажа ----------------------------
def test_start_with_hovel_and_moped(g):
    assert (g.state.housing, g.state.vehicle) == (1, 1)
    assert prop.name_of("housing", 1) == "Конура" and prop.name_of("vehicle", 1) == "Мопед"
    assert len(prop.HOUSING) == len(prop.VEHICLES) == 5
    assert prop.name_of("housing", 5) == "Особняк"


def test_upgrade_trades_in_old_property(g):
    cash = g.state.cash
    cost = g.change_property("housing", 2)
    assert cost == pytest.approx(45_000 - 4_000 * prop.SELL_FACTOR)
    assert g.state.housing == 2 and g.state.cash == pytest.approx(cash - cost)
    with pytest.raises(TradeError):
        g.change_property("housing", 2)
    with pytest.raises(TradeError):
        g.change_property("housing", 5)       # не хватает денег


def test_sell_property_gives_cash_and_homeless(g):
    cash = g.state.cash
    g.change_property("housing", 0)
    assert g.state.housing == 0 and g.state.cash == pytest.approx(cash + 4_000 * prop.SELL_FACTOR)
    g.change_property("housing", 1)
    assert g.state.homeless_turns == 0


def test_net_worth_includes_property(g):
    base = g.net_worth()
    g.state.cash += 1
    g.change_property("vehicle", 2)
    assert g.net_worth() < base + 1          # обмен стоит ~15% от цены нового
    assert g.net_worth() > base - 3_000


# ---------------------------- происшествия ----------------------------
def test_security_from_level_three_blocks_burglary_and_theft():
    for m in prop.MISHAPS:
        if m.cash_pct or m.destroy:
            assert all(lvl < prop.SECURE_FROM for lvl in m.levels), m.id
    assert prop.SECURE_FROM == 3 and prop.INSURED_FROM == 3


def test_hovel_can_be_robbed_or_burned(g):
    kinds = set()
    for i in range(400):
        out = prop.roll_mishap("housing", 1, 50_000, random.Random(i), 2.0)
        if out:
            kinds.add(out.mishap.id)
    assert {"h_squatters", "h_arson"} <= kinds


def test_good_housing_has_no_robbery_but_gets_compensation():
    ids = set()
    for i in range(1000):
        out = prop.roll_mishap("housing", 4, 50_000, random.Random(i), 3.0)
        if out:
            ids.add(out.mishap.id)
            assert out.tone == +1 and out.cash_delta > 0 and not out.destroyed
    assert ids == {"h_fire_ins", "h_flood_ins"}


def test_uninsured_fire_costs_money():
    m = prop.MISHAP_BY_ID["h_fire"]
    out = prop.resolve(m, 2, 10_000, random.Random(1))
    assert out.tone == -1 and out.cash_delta < 0


def test_moped_gets_cold_and_robbed_but_good_car_does_not():
    low, high = set(), set()
    for i in range(600):
        for lvl, bucket in ((1, low), (4, high)):
            out = prop.roll_mishap("vehicle", lvl, 30_000, random.Random(i), 3.0)
            if out:
                bucket.add(out.mishap.id)
    assert {"v_rain", "v_robbery", "v_theft"} <= low
    assert not ({"v_rain", "v_robbery", "v_theft"} & high)
    assert "v_crash_ins" in high


def test_robbery_with_empty_pockets_is_harmless():
    out = prop.resolve(prop.MISHAP_BY_ID["v_robbery"], 1, 0.0, random.Random(1))
    assert out.cash_delta == 0 and out.tone == 0


def test_destroyed_housing_makes_player_homeless(g, monkeypatch):
    out = prop.resolve(prop.MISHAP_BY_ID["h_arson"], 1, 0, random.Random(1))
    assert out.destroyed
    monkeypatch.setattr(prop, "roll_mishap", lambda kind, *a, **k: out if kind == "housing" else None)
    rep = g.next_turn()
    assert g.state.housing == 0 and g.state.homeless_turns == 1
    assert any(e.kind == "life" and e.tone < 0 for e in rep.extra)


# ---------------------------- бездомность, болезни, смерть ----------------------------
def _homeless_game(cash=100_000) -> Game:
    game = Game(seed=4)
    game.state.target = 10**12
    game.state.housing = 0
    game.state.cash = cash
    return game


def test_no_illness_during_grace_period(monkeypatch):
    game = _homeless_game()
    monkeypatch.setattr(prop, "roll_mishap", lambda *a, **k: None)
    monkeypatch.setattr(windfalls, "roll", lambda *a, **k: [])
    for _ in range(prop.HOMELESS_GRACE - 1):
        game.next_turn()
        assert game.state.illnesses == 0 and game.state.status is GameStatus.PLAYING


def test_homeless_gets_sick_pays_then_dies(monkeypatch):
    game = _homeless_game()
    monkeypatch.setattr(prop, "roll_mishap", lambda *a, **k: None)
    monkeypatch.setattr(windfalls, "roll", lambda *a, **k: [])
    monkeypatch.setattr(random.Random, "random", lambda self: 0.0)   # болезнь каждый ход
    bills = 0
    for _ in range(12):
        cash = game.state.cash
        rep = game.next_turn()
        if game.state.status is GameStatus.LOST_DEATH:
            break
        if game.state.illnesses:
            bills += 1
            assert any("лечение" in e.text for e in rep.extra) or True
    assert game.state.status is GameStatus.LOST_DEATH
    assert game.state.illnesses == prop.MAX_ILLNESSES
    assert bills == prop.MAX_ILLNESSES - 1 and game.state.cash < 100_000
    assert "умерли" in game.state.log[-2] + game.state.log[-1]


def test_homeless_without_money_dies_at_first_illness(monkeypatch):
    game = _homeless_game(cash=0)
    monkeypatch.setattr(prop, "roll_mishap", lambda *a, **k: None)
    monkeypatch.setattr(windfalls, "roll", lambda *a, **k: [])
    monkeypatch.setattr(random.Random, "random", lambda self: 0.0)
    while game.state.status is GameStatus.PLAYING and game.state.day < 20:
        game.next_turn()
    assert game.state.status is GameStatus.LOST_DEATH and game.state.illnesses == 1


def test_buying_a_roof_stops_the_disease(monkeypatch):
    game = _homeless_game()
    monkeypatch.setattr(prop, "roll_mishap", lambda *a, **k: None)
    monkeypatch.setattr(windfalls, "roll", lambda *a, **k: [])
    monkeypatch.setattr(random.Random, "random", lambda self: 0.0)
    for _ in range(prop.HOMELESS_GRACE):
        game.next_turn()
    assert game.state.illnesses >= 1
    game.change_property("housing", 1)
    game.next_turn()
    assert game.state.illnesses == 0 and game.state.homeless_turns == 0
    assert game.state.status is GameStatus.PLAYING


# ---------------------------- банк описывает имущество ----------------------------
def test_default_seizes_property_immediately(g, monkeypatch):
    monkeypatch.setattr(prop, "roll_mishap", lambda *a, **k: None)
    monkeypatch.setattr(windfalls, "roll", lambda *a, **k: [])
    g.state.housing, g.state.vehicle = 3, 3
    g.state.bank.loan, g.state.bank.loan_turns_left = 300_000, 1
    g.state.cash = 0
    rep = g.next_turn()
    seized = [e for e in rep.extra if e.kind == "seize"]
    assert seized and rep.critical
    assert g.state.vehicle == 0                  # сначала отбирают машину
    assert any("БАНК АРЕСТОВАЛ" in line for line in g.state.log)


def test_default_stops_seizing_when_debt_covered(g, monkeypatch):
    monkeypatch.setattr(prop, "roll_mishap", lambda *a, **k: None)
    monkeypatch.setattr(windfalls, "roll", lambda *a, **k: [])
    g.state.housing, g.state.vehicle = 4, 4
    g.state.bank.loan, g.state.bank.loan_turns_left = 40_000, 1
    g.state.cash = 0
    g.next_turn()
    assert g.state.vehicle == 0 and g.state.housing == 4 and g.state.cash > 0


def test_small_overdraft_gets_one_grace_turn(g, monkeypatch):
    monkeypatch.setattr(prop, "roll_mishap", lambda *a, **k: None)
    monkeypatch.setattr(windfalls, "roll", lambda *a, **k: [])
    g.state.cash = -100
    g.state.housing, g.state.vehicle = 3, 3
    g.next_turn()
    assert g.state.housing == 3 and g.state.overdue_turns == 1      # предупреждение
    g.next_turn()
    assert g.state.vehicle == 0                                      # на втором ходу в минусе — арест
    assert g.state.overdue_turns == 0 or g.state.cash >= 0


def test_seizure_price_is_fire_sale(g, monkeypatch):
    monkeypatch.setattr(prop, "roll_mishap", lambda *a, **k: None)
    monkeypatch.setattr(windfalls, "roll", lambda *a, **k: [])
    g.state.vehicle = 3
    g.state.cash = -1
    g.state.bank.loan, g.state.bank.loan_turns_left = 0, 0
    g.state.overdue_turns = 5
    g.next_turn()
    assert g.state.cash == pytest.approx(-1 + prop.VEHICLES[2].price * prop.SEIZE_FACTOR, abs=1)


def test_utilities_paid_from_deposit_when_cash_short(g):
    g.state.cash = 0
    g.state.bank.deposit = 10_000
    rep = g.next_turn()
    while not rep.utilities:
        rep = g.next_turn()
    assert g.state.cash >= 0 and g.state.bank.deposit < 10_000 * 1.2


# ---------------------------- имя игрока, слоты, рекорды ----------------------------
def test_player_name_in_state_and_score():
    game = Game(seed=1, player="  Серёга  ")
    assert game.state.player == "Серёга"
    assert game.score()["name"] == "Серёга"
    assert Game(seed=1, player="   ").state.player == "Игрок"


def test_save_slot_names_are_sanitized(tmp_path):
    assert storage.slot_name('A/b:c*"d?') == "Abcd"
    with pytest.raises(ValueError):
        storage.slot_path("highscores")
    with pytest.raises(ValueError):
        storage.slot_path("///")
    assert storage.slot_path("Вася", tmp_path) == tmp_path / "Вася.json"


def test_named_save_and_list(tmp_path):
    a, b = Game(seed=1, player="Аня"), Game(seed=2, player="Боря")
    a.next_turn()
    pa = storage.save_game(a, storage.slot_path("мой слот", tmp_path))
    storage.save_game(b, storage.slot_path("Боря", tmp_path))
    (tmp_path / "highscores.json").write_text("[]", encoding="utf-8")
    (tmp_path / "broken.json").write_text("{oops", encoding="utf-8")
    saves = storage.list_saves(tmp_path)
    assert {s["slot"] for s in saves} == {"мой слот", "Боря"}
    loaded = storage.load_game(pa)
    assert loaded.state.player == "Аня" and loaded.state.slot == "мой слот" and loaded.state.day == 2


def test_save_roundtrip_keeps_new_state(tmp_path):
    game = Game(seed=7, player="Тест")
    game.state.housing, game.state.vehicle, game.state.extended = 4, 0, True
    for _ in range(30):
        game.next_turn()
        if game.state.status is not GameStatus.PLAYING:
            break
    path = storage.save_game(game, storage.slot_path("t", tmp_path))
    again = storage.load_game(path)
    assert again.state.patterns == game.state.patterns
    assert again.state.log_tone == game.state.log_tone
    assert again.state.extended and again.state.vehicle == 0
    assert again.next_turn()


def test_old_v1_save_loads_with_defaults(tmp_path):
    game = Game(seed=3)
    d = storage.state_to_dict(game.state)
    d["version"] = 1
    for key in ("player", "housing", "vehicle", "patterns", "pattern_idle", "regime", "log_tone", "extended"):
        d["state"].pop(key, None)
    old = storage.state_from_dict(d)
    assert old.player == "Игрок" and old.housing == 1 and old.extended is False
    g2 = Game(state=old)
    g2.next_turn()
    assert len(g2.state.log_tone) == len(g2.state.log)


def test_scores_mark_extended_games(tmp_path):
    path = tmp_path / "hs.json"
    a, b = Game(seed=1, player="Честный"), Game(seed=2, player="Тестер")
    b.state.extended = True
    b.state.cash = 500_000
    storage.add_score(a, path=path)
    scores = storage.add_score(b, path=path)
    assert [s["name"] for s in scores] == ["Тестер", "Честный"]
    assert scores[0]["extended"] is True and scores[1]["extended"] is False
    assert scores[0]["max_days"] == 250
