"""Приятные неожиданности: наследство, лотереи, гранты, пособие и призы владельцам коммерческой недвижимости."""
from __future__ import annotations

import math
import random
from dataclasses import dataclass

from . import config
from . import property as prop
from .events import EventResult
from .models import AssetClass, GameState

LOTTERY_CHANCE = 0.035
GRANT_CHANCE = 0.03
INHERIT_CHANCE = 0.012
WELFARE_CHANCE = 0.08
WELFARE_RANGE = (5_000, 10_000)
WELFARE_NET_CAP = 300_000     # пособие положено только малоимущим
OWNER_BONUS = 0.20            # +20% к шансу приза за каждый следующий объект
OWNER_CAP = 0.5

RELATIVES = ("Умер дальний родственник из Канады", "Умер двоюродный дед", "Умерла тётя из Саратова",
             "Умерла бабушка по отцовской линии", "Умер троюродный брат", "Умер дядя-коллекционер")


@dataclass(frozen=True)
class OwnerPrize:
    symbol: str
    chance: float
    text: str
    kind: str                  # cash | crypto | land
    lo: float
    hi: float


OWNER_PRIZES: tuple[OwnerPrize, ...] = (
    OwnerPrize("STUDIO", 0.04, "Премия за участие в фотовыставке в вашей студии", "cash", 3_000, 9_000),
    OwnerPrize("COFFEE", 0.04, "Денежный приз за победу вашей кофейни в конкурсе пирожных", "cash", 3_000, 10_000),
    OwnerPrize("OFFICE", 0.08, "Партнёры по офису подарили вам", "crypto", 2_000, 8_000),
    OwnerPrize("WAREHOUSE", 0.04, "Администрация передала вам под развитие земельные участки:", "land", 2_000, 6_000),
)


def _money(x: float) -> str:
    return f"{x:,.0f}".replace(",", " ") + " $"


def _floor_step(qty: float, step: float) -> float:
    return round(math.floor(qty / step + 1e-9) * step, 6)


def give_asset(state: GameState, symbol: str, value: float) -> tuple[float, float]:
    """Дарит актив примерно на сумму value (не меньше минимального шага). Возвращает (количество, стоимость)."""
    a = config.ASSET_BY_SYMBOL[symbol]
    price = state.prices[symbol]
    qty = max(_floor_step(value / price, a.step), a.step)
    cost = round(qty * price, 2)
    state.holdings[symbol] = round(state.holdings.get(symbol, 0.0) + qty, 6)
    state.cost_basis[symbol] = round(state.cost_basis.get(symbol, 0.0) + cost, 2)
    return qty, cost


def _ev(out: list[EventResult], ev_id: str, text: str) -> None:
    out.append(EventResult(ev_id, text, +1, "luck"))


def _inherit(state: GameState, rng: random.Random, out: list[EventResult]) -> None:
    head = rng.choice(RELATIVES)
    kinds = ["cash", "cash", "realty", "securities", "securities"]
    if state.housing < 4:
        kinds.append("housing")
    if state.vehicle < 4:
        kinds.append("vehicle")
    kind = rng.choice(kinds)
    if kind == "cash":
        amount = float(round(rng.uniform(15_000, 70_000), -3))
        state.cash = round(state.cash + amount, 2)
        _ev(out, "inherit_cash", f"{head}: по завещанию вам достались деньги +{_money(amount)}.")
    elif kind == "realty":
        sym = rng.choice(("STUDIO", "STUDIO", "COFFEE"))
        give_asset(state, sym, 1.0)
        _ev(out, "inherit_realty", f"{head}: по завещанию вам перешла недвижимость — {config.ASSET_BY_SYMBOL[sym].name} (1 шт.).")
    elif kind == "securities":
        sym = rng.choice(["LAND", "NVDA", "AAPL", "MSFT", "AMZN", "GOOGL", "META", "JPM", "V", "BRK", "BTC", "ETH", "SOL"])
        qty, cost = give_asset(state, sym, rng.uniform(10_000, 45_000))
        a = config.ASSET_BY_SYMBOL[sym]
        _ev(out, "inherit_assets", f"{head}: вам перешли активы — {qty:g} {a.unit} {a.symbol} (≈{_money(cost)}).")
    else:
        key = kind
        lvl = max(getattr(state, key) + 1, 2)
        setattr(state, key, lvl)
        if key == "housing":
            state.homeless_turns = 0
        _ev(out, f"inherit_{key}", f"{head}: вам переписали {'жильё' if key == 'housing' else 'транспорт'} — "
                                   f"«{prop.name_of(key, lvl)}»!")


def roll(state: GameState, rng: random.Random, net_worth: float) -> list[EventResult]:
    """Все приятные неожиданности хода: пустой список, если ничего не выпало."""
    out: list[EventResult] = []

    if rng.random() < INHERIT_CHANCE:
        _inherit(state, rng, out)

    if rng.random() < LOTTERY_CHANCE:
        r = rng.random()
        prize = (float(round(rng.uniform(80_000, 150_000), -3)) if r < 0.01 else
                 float(round(rng.uniform(15_000, 40_000), -3)) if r < 0.15 else
                 float(round(rng.uniform(2_000, 8_000), -2)))
        state.cash = round(state.cash + prize, 2)
        what = "ДЖЕКПОТ! " if prize >= 80_000 else ""
        _ev(out, "lottery", f"{what}Вы выиграли в лотерею +{_money(prize)}.")

    if rng.random() < GRANT_CHANCE:
        if state.holdings.get("LAND", 0.0) > 0 and rng.random() < 0.5:
            amount = float(round(rng.uniform(4_000, 12_000), -2))
            text = f"Грант фермерам и землевладельцам: +{_money(amount)}."
        else:
            amount = float(round(rng.uniform(3_000, 10_000), -2))
            text = f"Вы получили грант на развитие малого бизнеса: +{_money(amount)}."
        state.cash = round(state.cash + amount, 2)
        _ev(out, "grant", text)

    if state.housing == 1 and net_worth < WELFARE_NET_CAP and rng.random() < WELFARE_CHANCE:
        amount = float(round(rng.uniform(*WELFARE_RANGE), -2))
        state.cash = round(state.cash + amount, 2)
        _ev(out, "welfare", f"Государство выплатило пособие малоимущим: +{_money(amount)} «на поддержание штанов».")

    for p in OWNER_PRIZES:
        n = int(state.holdings.get(p.symbol, 0.0))
        if n <= 0:
            continue
        if rng.random() >= min(p.chance * (1 + OWNER_BONUS * (n - 1)), OWNER_CAP):
            continue
        value = float(round(rng.uniform(p.lo, p.hi), -2))
        if p.kind == "cash":
            state.cash = round(state.cash + value, 2)
            _ev(out, "prize_" + p.symbol.lower(), f"{p.text}: +{_money(value)}.")
        elif p.kind == "crypto":
            sym = rng.choice([a.symbol for a in config.assets_of(AssetClass.CRYPTO)])
            qty, cost = give_asset(state, sym, value)
            _ev(out, "prize_office", f"{p.text} {qty:g} {sym} (≈{_money(cost)}).")
        else:
            qty, cost = give_asset(state, "LAND", value)
            _ev(out, "prize_warehouse", f"{p.text} {qty:g} сот. (≈{_money(cost)}).")
    return out
