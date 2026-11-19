import pytest

from core import storage
from core.engine import Game, TradeError
from core.models import GameStatus, ModKind, Modifier


@pytest.fixture
def g() -> Game:
    return Game(seed=1)


def test_start_state(g):
    assert g.state.cash == 100_000 and g.state.day == 1 and g.state.max_days == 150
    assert g.net_worth() == 100_000


def test_buy_sell_uses_spread(g):
    cost = g.buy("OIL", 100)
    assert cost == pytest.approx(100 * 70 * 1.01)
    assert g.qty("OIL") == 100
    proceeds = g.sell("OIL", 100)
    assert proceeds == pytest.approx(100 * 70 * 0.99)
    assert g.state.cash < 100_000  # спред — плата за круг


def test_buy_errors(g):
    with pytest.raises(TradeError):
        g.buy("BTC", 100)          # не хватает денег
    with pytest.raises(TradeError):
        g.sell("OIL", 1)           # нечего продавать
    with pytest.raises(TradeError):
        g.buy("BTC", 0.0001)       # меньше шага


def test_fractional_crypto_step(g):
    g.buy("BTC", 0.0155)
    assert g.qty("BTC") == pytest.approx(0.015)


def test_percent_helpers(g):
    full = g.qty_for_pct("OIL", "buy", 1.0)
    assert full == g.max_buy("OIL")
    assert g.qty_for_pct("OIL", "buy", 0.5) == pytest.approx(full / 2, abs=1)
    g.buy("OIL", 40)
    assert g.qty_for_pct("OIL", "sell", 0.5) == 20
    assert g.qty_for_pct("OIL", "sell", 1.0) == 40
    g.buy("OIL", g.qty_for_pct("OIL", "buy", 1.0))
    assert g.state.cash >= 0 and g.max_buy("OIL") == 0


def test_rent_paid_at_turn_start(g):
    g.buy("STUDIO", 1)
    rep = g.next_turn()
    assert rep.rent == 300
    assert g.state.day == 2
    assert g.rent_income() == 300


def test_rent_modifier(g):
    g.state.holdings["STUDIO"] = 2
    g.state.modifiers.append(Modifier(ModKind.RENT, "realty", 0.5, 3))
    assert g.rent_income() == pytest.approx(900)


def test_deposit_interest(g):
    g.bank_deposit(10_000)
    rep = g.next_turn()
    assert rep.deposit_interest > 0
    assert g.state.bank.deposit > 10_000
    with pytest.raises(TradeError):
        g.bank_withdraw(1_000_000)
    g.bank_withdraw(1000)


def test_loan_limit_and_repay(g):
    limit = g.max_loan()
    assert limit == pytest.approx(50_000)
    with pytest.raises(TradeError):
        g.take_loan(limit + 1)
    g.take_loan(20_000)
    assert g.state.bank.loan == 20_000 and g.state.bank.loan_turns_left == 10
    assert g.net_worth() == pytest.approx(100_000)  # долг компенсирован наличными
    assert g.repay_loan(5_000) == 5_000
    g.repay_loan(1_000_000)
    assert g.state.bank.loan == 0 and g.state.bank.loan_turns_left == 0


def test_loan_default_penalty(g):
    g.take_loan(10_000)
    rep = None
    for _ in range(g.diff.loan_term):
        rep = g.next_turn()
    assert rep.penalty > 0
    assert g.state.bank.loan == 0
    assert any("ДЕФОЛТ" in line for line in g.state.log)


def test_win_condition(g):
    g.state.cash = g.state.target
    rep = g.next_turn()
    assert rep.status is GameStatus.WON
    with pytest.raises(TradeError):
        g.buy("OIL", 1)
    with pytest.raises(TradeError):
        g.next_turn()


def test_bankruptcy(g):
    g.state.cash = -10_000
    rep = g.next_turn()
    assert rep.status is GameStatus.LOST_BANKRUPT


def test_timeout():
    g = Game(seed=2)
    status = GameStatus.PLAYING
    while status is GameStatus.PLAYING:
        status = g.next_turn().status
    assert status is GameStatus.LOST_TIMEOUT
    assert g.state.day == g.state.max_days + 1


def test_same_seed_same_game():
    a, b = Game(seed=5), Game(seed=5)
    for _ in range(20):
        a.next_turn()
        b.next_turn()
    assert a.state.prices == b.state.prices and a.state.log == b.state.log


def test_save_load_roundtrip(tmp_path):
    g = Game(seed=9)
    g.buy("OIL", 10)
    g.take_loan(5000)
    for _ in range(8):
        g.next_turn()
    path = tmp_path / "s.json"
    storage.save_game(g, path)
    g2 = storage.load_game(path)
    assert g2.state == g.state
    assert g2.net_worth() == g.net_worth()
    g2.next_turn()  # загруженная партия играбельна


def test_load_corrupted(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{oops", encoding="utf-8")
    with pytest.raises(ValueError):
        storage.load_game(p)
    with pytest.raises(FileNotFoundError):
        storage.load_game(tmp_path / "none.json")


def test_highscores_sorted_and_capped(tmp_path):
    path = tmp_path / "hs.json"
    for i in range(12):
        g = Game(seed=i)
        g.state.cash = 1000 * i
        storage.add_score(g, path=path)
    scores = storage.load_scores(path)
    assert len(scores) == storage.MAX_SCORES
    assert scores == sorted(scores, key=lambda e: e["net_worth"], reverse=True)
