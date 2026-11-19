"""Игровой движок: сделки, ход, аренда, банк, победа/поражение."""
from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field

from . import config, events, market
from .models import AssetClass, GameState, GameStatus, ModKind


class TradeError(ValueError):
    """Недопустимая операция (не хватает денег/актива, неверное количество и т.п.)."""


@dataclass
class TurnReport:
    day: int
    rent: float = 0.0
    deposit_interest: float = 0.0
    loan_interest: float = 0.0
    penalty: float = 0.0
    event: events.EventResult | None = None
    status: GameStatus = GameStatus.PLAYING
    lines: list[str] = field(default_factory=list)


def _floor_step(qty: float, step: float) -> float:
    return round(math.floor(qty / step + 1e-9) * step, 6)


def _money(x: float) -> str:
    return f"{x:,.0f}".replace(",", " ").replace("-", "−")


class Game:
    def __init__(self, difficulty: str = config.DEFAULT_DIFFICULTY, seed: int | None = None,
                 state: GameState | None = None) -> None:
        if state is None:
            seed = int(time.time() * 1000) % 2**31 if seed is None else seed
            diff = config.DIFFICULTIES[difficulty]
            state = GameState(max_days=diff.max_days, cash=diff.start_cash, start_cash=diff.start_cash,
                              target=diff.target, difficulty=diff.key, seed=seed)
            market.init_market(state)
            state.log.append("Добро пожаловать на биржу! Цель: "
                             f"{_money(diff.target)} $ за {diff.max_days} ходов.")
        self.state = state
        self.diff = config.DIFFICULTIES[state.difficulty]
        self.rng = random.Random(state.seed + state.day * 7919)

    # ------------------------------ оценки ------------------------------
    def price(self, symbol: str) -> float:
        return self.state.prices[symbol]

    def ask(self, symbol: str) -> float:
        """Цена покупки (с учётом спреда)."""
        return round(self.price(symbol) * (1 + config.ASSET_BY_SYMBOL[symbol].spread), 4)

    def bid(self, symbol: str) -> float:
        """Цена продажи (с учётом спреда)."""
        return round(self.price(symbol) * (1 - config.ASSET_BY_SYMBOL[symbol].spread), 4)

    def qty(self, symbol: str) -> float:
        return self.state.holdings.get(symbol, 0.0)

    def portfolio_value(self) -> float:
        return round(sum(self.qty(a.symbol) * self.price(a.symbol) for a in config.ASSETS), 2)

    def net_worth(self) -> float:
        s = self.state
        return round(s.cash + self.portfolio_value() + s.bank.deposit - s.bank.loan, 2)

    def rent_multiplier(self) -> float:
        return max(0.0, 1.0 + sum(m.value for m in self.state.modifiers if m.kind is ModKind.RENT))

    def rent_income(self) -> float:
        base = sum(self.qty(a.symbol) * a.rent for a in config.assets_of(AssetClass.REALTY))
        return round(base * self.rent_multiplier(), 2)

    def deposit_rate(self) -> float:
        d = sum(m.value for m in self.state.modifiers if m.kind is ModKind.RATE)
        return max(0.0, self.diff.deposit_rate + d)

    def loan_rate(self) -> float:
        d = sum(m.value for m in self.state.modifiers if m.kind is ModKind.RATE)
        return max(0.001, self.diff.loan_rate + d)

    # ------------------------------ сделки ------------------------------
    def _check_playing(self) -> None:
        if self.state.status is not GameStatus.PLAYING:
            raise TradeError("Игра окончена. Начните новую партию.")

    def _norm_qty(self, symbol: str, qty: float) -> float:
        a = config.ASSET_BY_SYMBOL[symbol]
        q = _floor_step(qty, a.step)
        if q < a.step:
            raise TradeError(f"Минимальное количество: {a.step:g} {a.unit}")
        return q

    def max_buy(self, symbol: str) -> float:
        a = config.ASSET_BY_SYMBOL[symbol]
        if self.state.cash <= 0:
            return 0.0
        return _floor_step(self.state.cash / self.ask(symbol), a.step)

    def qty_for_pct(self, symbol: str, side: str, pct: float) -> float:
        """Количество для кнопок 25% / 50% / Макс. side: 'buy' | 'sell'."""
        a = config.ASSET_BY_SYMBOL[symbol]
        base = self.max_buy(symbol) if side == "buy" else self.qty(symbol)
        return base if pct >= 1.0 else _floor_step(base * pct, a.step)

    def buy(self, symbol: str, qty: float) -> float:
        """Покупка. Возвращает потраченную сумму."""
        self._check_playing()
        q = self._norm_qty(symbol, qty)
        cost = round(q * self.ask(symbol), 2)
        if cost > self.state.cash + 1e-9:
            raise TradeError(f"Не хватает денег: нужно {_money(cost)} $")
        self.state.cash = round(self.state.cash - cost, 2)
        self.state.holdings[symbol] = round(self.qty(symbol) + q, 6)
        return cost

    def sell(self, symbol: str, qty: float) -> float:
        """Продажа. Возвращает выручку."""
        self._check_playing()
        q = self._norm_qty(symbol, qty)
        if q > self.qty(symbol) + 1e-9:
            raise TradeError("Недостаточно актива на руках")
        proceeds = round(q * self.bid(symbol), 2)
        self.state.cash = round(self.state.cash + proceeds, 2)
        self.state.holdings[symbol] = round(self.qty(symbol) - q, 6)
        return proceeds

    # ------------------------------- банк -------------------------------
    def bank_deposit(self, amount: float) -> None:
        self._check_playing()
        if amount <= 0 or amount > self.state.cash + 1e-9:
            raise TradeError("Недостаточно наличных для вклада")
        self.state.cash = round(self.state.cash - amount, 2)
        self.state.bank.deposit = round(self.state.bank.deposit + amount, 2)

    def bank_withdraw(self, amount: float) -> None:
        self._check_playing()
        if amount <= 0 or amount > self.state.bank.deposit + 1e-9:
            raise TradeError("На вкладе нет такой суммы")
        self.state.bank.deposit = round(self.state.bank.deposit - amount, 2)
        self.state.cash = round(self.state.cash + amount, 2)

    def max_loan(self) -> float:
        """Доступный кредитный лимит: доля от капитала без учёта долга минус текущий долг."""
        equity = self.net_worth() + self.state.bank.loan
        return max(0.0, round(self.diff.loan_limit_ratio * equity - self.state.bank.loan, 2))

    def take_loan(self, amount: float) -> None:
        self._check_playing()
        if amount <= 0 or amount > self.max_loan() + 1e-9:
            raise TradeError(f"Лимит кредита: {_money(self.max_loan())} $")
        bank = self.state.bank
        if bank.loan <= 0:
            bank.loan_turns_left = self.diff.loan_term
        bank.loan = round(bank.loan + amount, 2)
        self.state.cash = round(self.state.cash + amount, 2)

    def repay_loan(self, amount: float) -> float:
        """Погашает долг; возвращает фактически погашенную сумму."""
        self._check_playing()
        bank = self.state.bank
        paid = round(min(amount, bank.loan, max(self.state.cash, 0.0)), 2)
        if paid <= 0:
            raise TradeError("Нечем или нечего погашать")
        bank.loan = round(bank.loan - paid, 2)
        self.state.cash = round(self.state.cash - paid, 2)
        if bank.loan <= 0:
            bank.loan, bank.loan_turns_left = 0.0, 0
        return paid

    # -------------------------------- ход --------------------------------
    def _say(self, report: TurnReport, text: str) -> None:
        line = f"Д{self.state.day}: {text}"
        report.lines.append(line)
        self.state.log.append(line)
        del self.state.log[: -config.LOG_LEN]

    def next_turn(self) -> TurnReport:
        s = self.state
        self._check_playing()
        s.day += 1
        self.rng = random.Random(s.seed + s.day * 7919)
        rep = TurnReport(day=s.day)

        # 1) пассивный доход: аренда, вклад, кредит
        rep.rent = self.rent_income()
        if rep.rent:
            s.cash = round(s.cash + rep.rent, 2)
            self._say(rep, f"аренда +{_money(rep.rent)} $")
        if s.bank.deposit > 0:
            rep.deposit_interest = round(s.bank.deposit * self.deposit_rate(), 2)
            s.bank.deposit = round(s.bank.deposit + rep.deposit_interest, 2)
            self._say(rep, f"проценты по вкладу +{_money(rep.deposit_interest)} $")
        if s.bank.loan > 0:
            rep.loan_interest = round(s.bank.loan * self.loan_rate(), 2)
            s.bank.loan = round(s.bank.loan + rep.loan_interest, 2)
            s.bank.loan_turns_left -= 1
            if s.bank.loan_turns_left <= 0:
                rep.penalty = round(s.bank.loan * self.diff.default_penalty, 2)
                total = round(s.bank.loan + rep.penalty, 2)
                s.cash = round(s.cash - total, 2)  # может уйти в минус
                s.bank.loan, s.bank.loan_turns_left = 0.0, 0
                self._say(rep, f"ДЕФОЛТ по кредиту! Списано {_money(total)} $ (штраф {_money(rep.penalty)} $)")
            else:
                self._say(rep, f"кредит: +{_money(rep.loan_interest)} $ процентов, "
                               f"срок {s.bank.loan_turns_left} х.")

        # 2) цены, затем события; модификаторы «стареют» после пересчёта цен
        market.step_prices(s, self.rng)
        events.tick_modifiers(s)
        rep.event = events.roll_event(s, self.rng, self.diff)
        s.current_event = rep.event.text if rep.event else "Тихий день на рынке."
        self._say(rep, s.current_event)

        # 3) победа / поражение
        rep.status = self._evaluate_status()
        if rep.status is not GameStatus.PLAYING:
            self._say(rep, _STATUS_TEXT[rep.status])
        return rep

    def _evaluate_status(self) -> GameStatus:
        s = self.state
        nw = self.net_worth()
        if nw >= s.target:
            s.status = GameStatus.WON
        elif nw <= self.diff.bankruptcy_floor:
            s.status = GameStatus.LOST_BANKRUPT
        elif s.day > s.max_days:
            s.status = GameStatus.LOST_TIMEOUT
        return s.status

    def score(self) -> dict:
        """Данные для таблицы рекордов."""
        s = self.state
        return {"net_worth": self.net_worth(), "days": min(s.day, s.max_days), "status": s.status.value,
                "difficulty": s.difficulty}


_STATUS_TEXT = {
    GameStatus.WON: "ЦЕЛЬ ДОСТИГНУТА — вы победили!",
    GameStatus.LOST_BANKRUPT: "БАНКРОТСТВО — игра окончена.",
    GameStatus.LOST_TIMEOUT: "Ходы закончились, цель не достигнута.",
}
