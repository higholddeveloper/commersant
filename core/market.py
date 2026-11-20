"""Генерация цен: тренд + торговые фигуры + волатильность + модификаторы событий + мягкий возврат к среднему."""
from __future__ import annotations

import math
import random

from . import config, patterns
from .models import Asset, GameState, ModKind


def modifier_drift(state: GameState, asset: Asset) -> float:
    total = 0.0
    for m in state.modifiers:
        if m.kind is ModKind.DRIFT and m.target in (asset.symbol, asset.cls.value, "ALL"):
            total += m.value
    return total


def fair_price(asset: Asset, day: int) -> float:
    return asset.base_price * (1.0 + asset.drift) ** max(day - 1, 0)


def init_market(state: GameState) -> None:
    for a in config.ASSETS:
        state.prices[a.symbol] = a.base_price
        state.history[a.symbol] = [a.base_price]
        state.holdings.setdefault(a.symbol, 0.0)


def step_prices(state: GameState, rng: random.Random) -> None:
    """Один шаг рынка: пересчитывает цены и дописывает историю."""
    lo, hi = config.MAX_TURN_RETURN
    patterns.update_regime(state, rng)
    for a in config.ASSETS:
        price = state.prices[a.symbol]
        shape, vol_mult, rev_mult = patterns.step_asset(state, a, rng)
        reversion = config.MEAN_REVERSION * rev_mult * math.log(fair_price(a, state.day) / price)
        if state.calm:   # тишина: упавшее падает чуть-чуть, выросшее чуть-чуть растёт
            shape *= config.CALM_SHAPE
            vol_mult *= config.CALM_SHAPE
        ret = a.drift + shape + rng.gauss(0.0, a.volatility * vol_mult) + modifier_drift(state, a) + reversion
        ret = min(max(ret, lo), hi)
        new_price = max(price * (1.0 + ret), a.base_price * config.PRICE_FLOOR_RATIO)
        state.prices[a.symbol] = _round_price(new_price)
        record_history(state, a.symbol)


def record_history(state: GameState, symbol: str) -> None:
    hist = state.history.setdefault(symbol, [])
    hist.append(state.prices[symbol])
    del hist[: -config.HISTORY_LEN]


def change_pct(state: GameState, symbol: str) -> float:
    """Изменение цены за последний ход, в долях (0.05 = +5%)."""
    h = state.history.get(symbol, [])
    if len(h) < 2 or h[-2] == 0:
        return 0.0
    return h[-1] / h[-2] - 1.0


def _round_price(p: float) -> float:
    return round(p, 4) if p < 1 else round(p, 2)
