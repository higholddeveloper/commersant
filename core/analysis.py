"""Анализ динамики цены: в какой фазе находится актив (падение, отскок, рост, пик, боковик)."""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Trend:
    key: str      # decline | rebound | growth | peak | flat | mixed | new
    title: str
    hint: str
    tone: int     # +1 хорошо (зелёный), -1 плохо (красный), 0 нейтрально
    change: float # изменение за окно анализа, доля


def analyze(history: list[float], volatility: float, window: int = 20) -> Trend:
    """Определяет фазу по последним `window` ходам. Пороги масштабируются волатильностью актива."""
    h = history[-(window + 1):]
    n = len(h) - 1
    if n < 5:
        return Trend("new", "Мало данных", "Подождите несколько ходов — история ещё формируется.", 0, 0.0)

    k = max(volatility * math.sqrt(n), 0.01)        # типичный разброс случайного блуждания за окно
    k5 = max(volatility * math.sqrt(5), 0.01)
    w = h[-1] / h[0] - 1
    lo, hi = min(h), max(h)
    pos = (h[-1] - lo) / (hi - lo) if hi > lo else 0.5
    r5 = h[-1] / h[-6] - 1
    imin = h.index(lo)
    up_frac = sum(1 for i in range(1, len(h)) if h[i] > h[i - 1]) / n
    avg = sum(h) / len(h)

    if r5 > 1.2 * k5 and pos >= 0.9 and w > 0.8 * k:
        return Trend("peak", "Резкий рост, цена на пике",
                     "Высоко после рывка — подумайте о фиксации прибыли, докупать рискованно.", +1, w)
    pre_max = max(h[: imin + 1])
    if imin < n - 1 and 1 - lo / pre_max > 0.6 * k and h[-1] / lo - 1 > 0.4 * k:
        return Trend("rebound", "Восстановление после падения",
                     "Отскок от дна — можно наращивать позицию, но следите за повторным падением.", +1, w)
    if w < -0.8 * k and pos <= 0.35:
        return Trend("decline", "Затяжное падение",
                     "Дешевеет — можно присмотреться к покупке и усреднению, не спешите ловить дно.", -1, w)
    if w > 0.8 * k and up_frac >= 0.5 and pos >= 0.6:
        return Trend("growth", "Устойчивый рост",
                     "Тренд вверх — держите позицию, докупайте на откатах.", +1, w)
    if abs(w) < 0.5 * k and (hi - lo) / avg < 2.0 * k:
        return Trend("flat", "Боковик: торгуется на одном уровне",
                     "Без движения — можно подождать сигнала, деньги пока лучше работают в другом месте.", 0, w)
    return Trend("mixed", "Колебания без чёткого тренда",
                 "Однозначного сигнала нет — действуйте осторожно, небольшими долями.", 0, w)
