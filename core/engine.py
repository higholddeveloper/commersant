"""Игровой движок: сделки, ход, аренда, банк, собственность, победа/поражение."""
from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field

from . import config, events, market, patterns, timeline, windfalls
from . import property as prop
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
    utilities: float = 0.0
    event: events.EventResult | None = None            # главное рыночное событие хода
    extra: list[events.EventResult] = field(default_factory=list)   # лебеди, происшествия, арест имущества
    status: GameStatus = GameStatus.PLAYING
    lines: list[str] = field(default_factory=list)

    @property
    def all_events(self) -> list[events.EventResult]:
        return ([self.event] if self.event else []) + self.extra

    @property
    def important(self) -> bool:
        """Важное событие: в режиме реального времени ставит игру на паузу."""
        return bool(self.all_events) or self.penalty > 0 or self.status is not GameStatus.PLAYING

    @property
    def critical(self) -> bool:
        """Катастрофа (чёрный лебедь, арест имущества, смерть): окно показывается всегда, даже в пошаговом режиме."""
        return any(e.kind in ("swan", "seize") for e in self.extra)


def _floor_step(qty: float, step: float) -> float:
    return round(math.floor(qty / step + 1e-9) * step, 6)


def _money(x: float) -> str:
    return f"{x:,.0f}".replace(",", " ").replace("-", "−")


class Game:
    # --- пассивный доход от коммерческой недвижимости: 10 / 15 / 20 / 25 % годовых в зависимости от рынка ---
    RENT_TIERS = (0.10, 0.15, 0.20, 0.25)
    RENT_LABELS = ("кризис аренды", "спокойный рынок", "рост спроса", "бум аренды")
    RENT_LOOKBACK = 8

    def __init__(self, difficulty: str = config.DEFAULT_DIFFICULTY, seed: int | None = None,
                 state: GameState | None = None, player: str = "Игрок") -> None:
        if state is None:
            seed = int(time.time() * 1000) % 2**31 if seed is None else seed
            diff = config.DIFFICULTIES[difficulty]
            state = GameState(max_days=diff.max_days, cash=diff.start_cash, start_cash=diff.start_cash,
                              target=diff.target, difficulty=diff.key, seed=seed, player=player.strip() or "Игрок")
            market.init_market(state)
            boot = random.Random(seed)
            state.regime = boot.choice(list(patterns.REGIMES))
            state.regime_left = boot.randint(20, 45)
            self._append_log(state, f"{state.player}, добро пожаловать на биржу! "
                                    f"Цель: {_money(diff.target)} $ за {diff.max_days} ходов.", 0)
        self.state = state
        self.last_tax = 0.0        # налог с последней продажи недвижимости
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

    def avg_cost(self, symbol: str) -> float:
        """Средняя цена покупки текущей позиции (0, если актива нет)."""
        q = self.qty(symbol)
        return round(self.state.cost_basis.get(symbol, 0.0) / q, 4) if q > 0 else 0.0

    def portfolio_value(self) -> float:
        return round(sum(self.qty(a.symbol) * self.price(a.symbol) for a in config.ASSETS), 2)

    def property_value(self) -> float:
        """Собственность (жильё и транспорт) по цене обычной продажи."""
        s = self.state
        return round(prop.sale_value("housing", s.housing) + prop.sale_value("vehicle", s.vehicle), 2)

    def net_worth(self) -> float:
        s = self.state
        return round(s.cash + self.portfolio_value() + self.property_value() + s.bank.deposit - s.bank.loan, 2)

    # --- аренда ---
    def realty_trend(self) -> float:
        """Средний рост цен коммерческой недвижимости за последние ходы."""
        vals = []
        for a in config.assets_of(AssetClass.REALTY):
            h = self.state.history.get(a.symbol, [])
            if len(h) >= 2:
                base = h[-(self.RENT_LOOKBACK + 1)] if len(h) > self.RENT_LOOKBACK else h[0]
                vals.append(h[-1] / base - 1.0)
        return sum(vals) / len(vals) if vals else 0.0

    def rent_tier(self) -> int:
        mods = sum(m.value for m in self.state.modifiers if m.kind is ModKind.RENT)
        score = self.realty_trend() + 0.5 * mods
        return 0 if score < -0.02 else 1 if score < 0.02 else 2 if score < 0.06 else 3

    def rent_yield(self) -> float:
        """Текущая доходность аренды, годовых (0.10 … 0.25)."""
        return self.RENT_TIERS[self.rent_tier()]

    def rent_label(self) -> str:
        return self.RENT_LABELS[self.rent_tier()]

    def rent_income(self) -> float:
        value = sum(self.qty(a.symbol) * self.price(a.symbol) for a in config.assets_of(AssetClass.REALTY))
        return round(value * self.rent_yield() / timeline.TURNS_PER_YEAR, 2)

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
        self.state.cost_basis[symbol] = round(self.state.cost_basis.get(symbol, 0.0) + cost, 2)
        return cost

    def sell(self, symbol: str, qty: float) -> float:
        """Продажа. Возвращает выручку."""
        self._check_playing()
        q = self._norm_qty(symbol, qty)
        if q > self.qty(symbol) + 1e-9:
            raise TradeError("Недостаточно актива на руках")
        proceeds = round(q * self.bid(symbol), 2)
        before = self.qty(symbol)
        basis = self.state.cost_basis.get(symbol, 0.0)
        self.last_tax = 0.0
        if config.ASSET_BY_SYMBOL[symbol].cls is AssetClass.REALTY:   # налог с прибыли от продажи недвижимости
            profit = proceeds - basis * q / before
            if profit > 0:
                self.last_tax = round(profit * config.REALTY_SALE_TAX, 2)
                proceeds = round(proceeds - self.last_tax, 2)
        self.state.cash = round(self.state.cash + proceeds, 2)
        self.state.holdings[symbol] = round(before - q, 6)
        self.state.cost_basis[symbol] = 0.0 if self.qty(symbol) <= 0 else round(basis * (1 - q / before), 2)
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

    # ---------------------------- собственность ----------------------------
    def level_of(self, kind: str) -> int:
        return self.state.housing if kind == "housing" else self.state.vehicle

    def change_cost(self, kind: str, level: int) -> float:
        """Доплата за переезд / смену транспорта (отрицательная — вам вернут разницу)."""
        t = prop.tier(kind, level)
        return round((t.price if t else 0.0) - prop.sale_value(kind, self.level_of(kind)), 2)

    def change_property(self, kind: str, level: int) -> float:
        """Купить / обменять (старое продаётся по обычной цене) / продать (level=0). Возвращает доплату."""
        self._check_playing()
        if kind not in prop.TIERS or not 0 <= level <= len(prop.TIERS[kind]):
            raise TradeError("Неизвестный вариант")
        if level == self.level_of(kind):
            raise TradeError("Это у вас уже есть.")
        cost = self.change_cost(kind, level)
        if cost > self.state.cash + 1e-9:
            raise TradeError(f"Не хватает денег: нужно {_money(cost)} $")
        self.state.cash = round(self.state.cash - cost, 2)
        self._set_level(kind, level)
        if kind == "housing" and level > 0:
            self.state.homeless_turns = 0
        return cost

    def _set_level(self, kind: str, level: int) -> None:
        if kind == "housing":
            self.state.housing = level
        else:
            self.state.vehicle = level

    def monthly_upkeep(self) -> float:
        s = self.state
        t1, t2 = prop.tier("housing", s.housing), prop.tier("vehicle", s.vehicle)
        return (t1.upkeep if t1 else 0.0) + (t2.upkeep if t2 else 0.0)

    def extend_turns(self) -> None:
        """Продлевает партию, когда ходы закончились. В таблице рекордов результат помечается «без лимита ходов»."""
        s = self.state
        if s.status is not GameStatus.LOST_TIMEOUT:
            raise TradeError("Продлевать нечего: ходы ещё не закончились.")
        s.max_days += config.EXTEND_TURNS
        s.extended = True
        s.status = GameStatus.PLAYING
        self._append_log(s, f"Лимит ходов продлён на {config.EXTEND_TURNS}. В рекордах будет пометка «без лимита ходов».", 0)

    # -------------------------------- ход --------------------------------
    @staticmethod
    def _append_log(state: GameState, text: str, tone: int) -> None:
        if len(state.log_tone) < len(state.log):        # старое сохранение без тонов
            state.log_tone = [0] * (len(state.log) - len(state.log_tone)) + state.log_tone
        state.log.append(text)
        state.log_tone.append(tone)
        del state.log[: -config.LOG_LEN]
        del state.log_tone[: -config.LOG_LEN]

    def _say(self, report: TurnReport, text: str, tone: int = 0) -> None:
        line = f"{timeline.fmt_date(self.state.day)}: {text}"
        report.lines.append(line)
        self._append_log(self.state, line, tone)

    def _event(self, rep: TurnReport, ev_id: str, text: str, tone: int, kind: str) -> None:
        rep.extra.append(events.EventResult(ev_id, text, tone, kind))
        self._say(rep, text, tone)

    def _pay(self, amount: float) -> bool:
        """Оплата счёта: сначала наличные, затем вклад. False — денег не хватает (ничего не списано)."""
        s = self.state
        if amount <= 0:
            return True
        if max(s.cash, 0.0) + s.bank.deposit < amount - 1e-9:
            return False
        from_cash = min(max(s.cash, 0.0), amount)
        s.cash = round(s.cash - from_cash, 2)
        s.bank.deposit = round(s.bank.deposit - (amount - from_cash), 2)
        return True

    def _utilities(self, rep: TurnReport) -> None:
        due = self.monthly_upkeep()
        if due <= 0:
            return
        rep.utilities = due
        if not self._pay(due):   # денег не хватает — уходим в минус; банк потом опишет имущество
            self.state.cash = round(self.state.cash - due, 2)
        self._say(rep, f"коммунальные платежи и содержание авто −{_money(due)} $", 0)

    def _life(self, rep: TurnReport) -> None:
        """Происшествия с жильём и транспортом, бездомность, болезни, смерть."""
        s = self.state
        for kind in ("housing", "vehicle"):
            level = self.level_of(kind)
            out = prop.roll_mishap(kind, level, s.cash, self.rng, self.diff.bad_event_bias)
            if out is None:
                continue
            s.cash = round(s.cash + out.cash_delta, 2)
            if out.destroyed:
                self._set_level(kind, 0)
            self._event(rep, out.mishap.id, out.text, out.tone, "life")
        if s.housing > 0:
            s.homeless_turns = 0
            s.illnesses = 0
            return
        s.homeless_turns += 1
        n = s.homeless_turns
        if n == 1:
            self._event(rep, "homeless_start", f"Вы остались без жилья! Через {prop.HOMELESS_GRACE - 1} х. "
                                               "начнутся болезни — срочно купите хотя бы конуру.", -1, "life")
        elif n < prop.HOMELESS_GRACE:
            if n == prop.HOMELESS_GRACE - 2:
                self._event(rep, "homeless_cold", "Ночи холодные, вы кашляете. Крышу над головой — как можно скорее!", -1, "life")
        elif self.rng.random() < prop.ILLNESS_CHANCE:
            s.illnesses += 1
            bill = round(self.rng.uniform(1_000, 3_000), -1)
            if s.illnesses >= prop.MAX_ILLNESSES:
                self._die(rep, "Третья болезнь на улице — организм не выдержал. Вы умерли.")
            elif self._pay(bill):
                self._event(rep, "homeless_ill", f"Вы заболели на улице. Счёт за лечение −{_money(bill)} $ "
                                                 f"(болезнь {s.illnesses} из {prop.MAX_ILLNESSES - 1}).", -1, "life")
            else:
                self._die(rep, f"Вы тяжело заболели, но на лечение ({_money(bill)} $) не хватило денег. Вы умерли.")

    def _die(self, rep: TurnReport, text: str) -> None:
        self.state.status = GameStatus.LOST_DEATH
        self._event(rep, "death", text, -1, "seize")

    def _enforce(self, rep: TurnReport, immediate: bool) -> None:
        """Банк арестовывает и распродаёт имущество за долги: сразу при дефолте, иначе после двух ходов в минусе."""
        s = self.state
        if s.cash >= 0:
            s.overdue_turns = 0
            return
        s.overdue_turns += 1
        if not immediate and s.overdue_turns < 2:
            self._say(rep, f"на счёте минус {_money(-s.cash)} $ — пополните его, иначе банк опишет имущество!", -1)
            return
        for kind in ("vehicle", "housing"):
            level = self.level_of(kind)
            if level <= 0 or s.cash >= 0:
                continue
            value = prop.sale_value(kind, level, prop.SEIZE_FACTOR)
            name = prop.name_of(kind, level)
            s.cash = round(s.cash + value, 2)
            self._set_level(kind, 0)
            self._event(rep, f"seize_{kind}", f"БАНК АРЕСТОВАЛ И ПРОДАЛ «{name}» за {_money(value)} $ в счёт долга.", -1, "seize")

    def next_turn(self) -> TurnReport:
        s = self.state
        self._check_playing()
        s.day += 1
        self.rng = random.Random(s.seed + s.day * 7919)
        rep = TurnReport(day=s.day)
        defaulted = False

        # 1) пассивный доход: аренда, вклад, кредит
        rep.rent = self.rent_income()
        if rep.rent:
            s.cash = round(s.cash + rep.rent, 2)
            self._say(rep, f"аренда +{_money(rep.rent)} $ ({self.rent_yield() * 100:.0f}% годовых, {self.rent_label()})", +1)
        if s.bank.deposit > 0:
            rep.deposit_interest = round(s.bank.deposit * self.deposit_rate(), 2)
            s.bank.deposit = round(s.bank.deposit + rep.deposit_interest, 2)
            self._say(rep, f"проценты по вкладу +{_money(rep.deposit_interest)} $", +1)
        if s.bank.loan > 0:
            rep.loan_interest = round(s.bank.loan * self.loan_rate(), 2)
            s.bank.loan = round(s.bank.loan + rep.loan_interest, 2)
            s.bank.loan_turns_left -= 1
            if s.bank.loan_turns_left <= 0:
                defaulted = True
                rep.penalty = round(s.bank.loan * self.diff.default_penalty, 2)
                total = round(s.bank.loan + rep.penalty, 2)
                s.cash = round(s.cash - total, 2)  # может уйти в минус
                s.bank.loan, s.bank.loan_turns_left = 0.0, 0
                self._say(rep, f"ДЕФОЛТ по кредиту! Списано {_money(total)} $ (штраф {_money(rep.penalty)} $)", -1)
            else:
                self._say(rep, f"кредит: +{_money(rep.loan_interest)} $ процентов, срок {s.bank.loan_turns_left} х.", 0)

        # 2) ежемесячные коммунальные платежи
        if timeline.month_changed(s.day):
            self._utilities(rep)

        # 3) цены, чёрные лебеди, затем события; модификаторы «стареют» после пересчёта цен
        if s.calm_left > 0:                 # тишина на рынке: тренд слабый, событий мало
            s.calm_left -= 1
            s.calm = True
        elif self.rng.random() < config.CALM_CHANCE:
            s.calm_left = self.rng.randint(*config.CALM_TURNS) - 1
            s.calm = True
        else:
            s.calm = False
        market.step_prices(s, self.rng)
        events.tick_modifiers(s)
        swan = None if s.calm else patterns.roll_swan(s, self.rng)
        if swan:
            self._event(rep, "swan_" + swan.id, f"ЧЁРНЫЙ ЛЕБЕДЬ · {swan.title}: {swan.text}", -1, "swan")
        rep.event = events.roll_event(s, self.rng, self.diff)
        if rep.event:
            self._say(rep, rep.event.text, rep.event.tone)

        # 4) жильё и транспорт, болезни; приятные неожиданности; долги и арест имущества
        self._life(rep)
        if s.status is GameStatus.PLAYING:
            for ev in windfalls.roll(s, self.rng, self.net_worth()):
                rep.extra.append(ev)
                self._say(rep, ev.text, ev.tone)
        if s.status is GameStatus.PLAYING:
            self._enforce(rep, immediate=defaulted)

        shown = rep.all_events
        s.current_event = ("  ▪  ".join(e.text for e in shown) if shown else
                           "Рынок затих: цены почти не двигаются." if s.calm else "Тихий день на рынке.")
        s.current_tone = min(e.tone for e in shown) if any(e.tone for e in shown) else 0
        if not shown:
            self._say(rep, s.current_event)

        # 5) победа / поражение
        rep.status = self._evaluate_status()
        if rep.status is not GameStatus.PLAYING:
            self._say(rep, _STATUS_TEXT[rep.status], +1 if rep.status is GameStatus.WON else -1)
        return rep

    def _evaluate_status(self) -> GameStatus:
        s = self.state
        if s.status is GameStatus.LOST_DEATH:
            return s.status
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
        return {"name": s.player, "net_worth": self.net_worth(), "days": min(s.day, s.max_days),
                "status": s.status.value, "difficulty": s.difficulty, "extended": s.extended,
                "max_days": s.max_days, "game_date": timeline.fmt_date(s.day)}


_STATUS_TEXT = {
    GameStatus.WON: "ЦЕЛЬ ДОСТИГНУТА — вы победили!",
    GameStatus.LOST_BANKRUPT: "БАНКРОТСТВО — игра окончена.",
    GameStatus.LOST_TIMEOUT: "Ходы закончились, цель не достигнута.",
    GameStatus.LOST_DEATH: "ВЫ УМЕРЛИ — игра окончена.",
}
