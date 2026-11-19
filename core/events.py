"""Пулы случайных и кросс-рыночных событий и их применение к состоянию."""
from __future__ import annotations

import math
import random
from dataclasses import dataclass
from enum import Enum

from . import config
from .models import Asset, AssetClass, GameState, ModKind, Modifier


class EffectKind(str, Enum):
    PRICE = "price"            # разовое изменение цены, lo..hi в долях
    CASH = "cash"              # абсолютное изменение наличных
    CASH_PCT = "cash_pct"      # изменение наличных в долях
    HOLDING_PCT = "holding"    # изменение количества актива на руках, в долях
    DRIFT = "drift"            # временная добавка к тренду цены
    RENT = "rent"              # временный множитель аренды (1 + value)
    RATE = "rate"              # временная добавка к ставкам банка
    REPAIR = "repair"          # списание за каждый объект недвижимости на руках


@dataclass(frozen=True)
class Effect:
    kind: EffectKind
    target: str = "ALL"        # символ / класс / ALL / "@random:<класс>"
    lo: float = 0.0
    hi: float = 0.0
    turns: int = 0


@dataclass(frozen=True)
class EventDef:
    id: str
    scope: str                 # commodity|stock|crypto|realty|bank|cross
    text: str                  # короткий текст (допускает {name})
    effects: tuple[Effect, ...]
    weight: float = 1.0
    tone: int = 0              # +1 удачное, -1 негативное, 0 нейтральное


@dataclass
class EventResult:
    event_id: str
    text: str                  # итоговая строка для ленты новостей
    tone: int


def _e(kind: EffectKind, target: str = "ALL", lo: float = 0.0, hi: float | None = None, turns: int = 0) -> Effect:
    return Effect(kind, target, lo, lo if hi is None else hi, turns)


P, CASH, CPCT, HOLD, DR, RENT, RATE, REP = (
    EffectKind.PRICE, EffectKind.CASH, EffectKind.CASH_PCT, EffectKind.HOLDING_PCT,
    EffectKind.DRIFT, EffectKind.RENT, EffectKind.RATE, EffectKind.REPAIR,
)

EVENTS: tuple[EventDef, ...] = (
    # ---------- Сырьё ----------
    EventDef("oil_opec_cut", "commodity", "ОПЕК урезала добычу — нефть дорожает.", (_e(P, "OIL", 0.08, 0.18),), 1.0, +1),
    EventDef("oil_glut", "commodity", "Перепроизводство нефти: склады переполнены.", (_e(P, "OIL", -0.18, -0.08),), 1.0, -1),
    EventDef("oil_pipeline", "commodity", "Авария на трубопроводе: часть нефти потеряна.", (_e(HOLD, "OIL", -0.15, -0.05), _e(P, "OIL", 0.03, 0.08)), 0.6, -1),
    EventDef("oil_war", "commodity", "Конфликт на Ближнем Востоке: нефть растёт несколько ходов.", (_e(DR, "OIL", 0.02, 0.04, 3),), 0.7, +1),
    EventDef("land_boom", "commodity", "Рядом построят автобан — земля дорожает.", (_e(P, "LAND", 0.08, 0.20),), 1.0, +1),
    EventDef("land_tax", "commodity", "Новый земельный налог: цены на землю падают.", (_e(P, "LAND", -0.15, -0.06),), 0.8, -1),
    EventDef("land_squat", "commodity", "Самозахват участков: потеряна часть земли.", (_e(HOLD, "LAND", -0.12, -0.04),), 0.4, -1),
    # ---------- Акции ----------
    EventDef("stock_beat", "stock", "{name}: отчёт лучше ожиданий.", (_e(P, "@random:stock", 0.06, 0.15),), 1.5, +1),
    EventDef("stock_miss", "stock", "{name}: отчёт провален, акции летят вниз.", (_e(P, "@random:stock", -0.16, -0.06),), 1.5, -1),
    EventDef("stock_rally", "stock", "Рынок акций на подъёме: «быки» у руля.", (_e(DR, "stock", 0.01, 0.02, 4),), 1.0, +1),
    EventDef("stock_dividend", "stock", "Выплата дивидендов: бонус инвесторам.", (_e(CASH, "ALL", 500, 2500),), 0.8, +1),
    EventDef("stock_ai", "stock", "Бум ИИ: техногиганты в плюсе.", (_e(P, "NVDA", 0.08, 0.16), _e(P, "MSFT", 0.03, 0.07)), 0.7, +1),
    EventDef("stock_antitrust", "stock", "Антимонопольный иск против {name}.", (_e(P, "@random:stock", -0.12, -0.05),), 0.8, -1),
    # ---------- Крипта ----------
    EventDef("crypto_etf", "crypto", "Одобрен крипто-ETF — монеты взлетают.", (_e(P, "crypto", 0.08, 0.20),), 0.9, +1),
    EventDef("crypto_ban", "crypto", "Регулятор запретил крипту в крупной стране.", (_e(P, "crypto", -0.22, -0.10),), 0.9, -1),
    EventDef("crypto_meme", "crypto", "Мем-ажиотаж: DOGE улетает вверх.", (_e(P, "DOGE", 0.20, 0.50),), 0.6, +1),
    EventDef("crypto_whale", "crypto", "Кит слил {name} — цена обваливается.", (_e(P, "@random:crypto", -0.25, -0.10),), 0.8, -1),
    EventDef("crypto_wallet", "crypto", "Фишинг: часть вашей крипты украдена.", (_e(HOLD, "crypto", -0.12, -0.04),), 0.5, -1),
    # ---------- Недвижимость ----------
    EventDef("realty_rent_boom", "realty", "Бум аренды: арендаторы платят больше.", (_e(RENT, "realty", 0.30, 0.60, 4),), 1.0, +1),
    EventDef("realty_flood", "realty", "Авария: прорвало трубы, нужен ремонт.", (_e(REP, "realty", 800, 3000),), 1.0, -1),
    EventDef("realty_vacancy", "realty", "Арендаторы съехали — аренда просела.", (_e(RENT, "realty", -0.50, -0.30, 3),), 0.8, -1),
    EventDef("realty_metro", "realty", "Рядом открыли метро — объекты дорожают.", (_e(P, "realty", 0.05, 0.12),), 0.7, +1),
    EventDef("realty_crash", "realty", "Рынок недвижимости остывает.", (_e(P, "realty", -0.10, -0.04),), 0.8, -1),
    # ---------- Банк ----------
    EventDef("bank_bonus", "bank", "Банк-партнёр дарит кэшбэк за активность.", (_e(CASH, "ALL", 300, 1500),), 0.7, +1),
    EventDef("bank_fee", "bank", "Банк ввёл комиссию за обслуживание.", (_e(CASH, "ALL", -1200, -300),), 0.7, -1),
    EventDef("bank_promo", "bank", "Акция банка: повышенная ставка по вкладам.", (_e(RATE, "ALL", 0.001, 0.002, 3),), 0.6, +1),
    # ---------- Кросс-рыночные ----------
    EventDef("x_rate_hike", "cross", "ЦБ повысил ставку: акции и недвижимость под давлением.",
             (_e(DR, "stock", -0.012, -0.006, 3), _e(DR, "realty", -0.006, -0.003, 3), _e(RATE, "ALL", 0.001, 0.002, 4)), 1.0, -1),
    EventDef("x_rate_cut", "cross", "ЦБ снизил ставку: рынки оживают.",
             (_e(DR, "stock", 0.006, 0.012, 3), _e(DR, "realty", 0.003, 0.006, 3), _e(RATE, "ALL", -0.0015, -0.0005, 4)), 1.0, +1),
    EventDef("x_panic", "cross", "Глобальная паника: все бегут из активов!",
             (_e(P, "stock", -0.14, -0.06), _e(P, "crypto", -0.25, -0.10), _e(P, "commodity", -0.08, -0.03)), 0.8, -1),
    EventDef("x_hack", "cross", "Взлом биржи: крипта падает, часть наличных пропала.",
             (_e(P, "crypto", -0.20, -0.08), _e(CPCT, "ALL", -0.04, -0.01)), 0.6, -1),
    EventDef("x_inflation", "cross", "Инфляция разгоняется: сырьё дорожает.",
             (_e(P, "commodity", 0.04, 0.10), _e(RATE, "ALL", 0.0005, 0.0015, 3)), 0.8, 0),
    EventDef("x_tax_refund", "cross", "Налоговый вычет: вам вернули деньги.", (_e(CASH, "ALL", 1000, 4000),), 0.7, +1),
    EventDef("x_theft", "cross", "Карманная кража: пропала часть наличных.", (_e(CPCT, "ALL", -0.06, -0.02),), 0.6, -1),
    EventDef("x_inheritance", "cross", "Неожиданное наследство от дальнего родственника!", (_e(CASH, "ALL", 3000, 9000),), 0.3, +1),
    EventDef("x_bull", "cross", "Мировой оптимизм: растёт всё, что можно.", (_e(DR, "ALL", 0.005, 0.01, 3),), 0.6, +1),
)


# --------------------------- выбор и применение ---------------------------

def pick_event(rng: random.Random, difficulty: config.Difficulty) -> EventDef:
    weights = [e.weight * (difficulty.bad_event_bias if e.tone < 0 else 1.0) for e in EVENTS]
    return rng.choices(EVENTS, weights=weights, k=1)[0]


def roll_event(state: GameState, rng: random.Random, difficulty: config.Difficulty) -> EventResult | None:
    """С вероятностью event_chance выбирает и применяет событие."""
    if rng.random() > difficulty.event_chance:
        return None
    return apply_event(state, pick_event(rng, difficulty), rng)


def _targets(target: str, rng: random.Random, picked: dict[str, Asset]) -> list[Asset]:
    if target == "ALL":
        return list(config.ASSETS)
    if target.startswith("@random:"):
        if target not in picked:
            picked[target] = rng.choice(config.assets_of(AssetClass(target.split(":", 1)[1])))
        return [picked[target]]
    if target in config.ASSET_BY_SYMBOL:
        return [config.ASSET_BY_SYMBOL[target]]
    return list(config.assets_of(AssetClass(target)))


def _fmt_pct(x: float) -> str:
    return f"{x * 100:+.0f}%".replace("-", "−")


def _fmt_money(x: float) -> str:
    return f"{x:+,.0f}".replace(",", " ").replace("-", "−") + " $"


def _class_label(target: str) -> str:
    return {
        "ALL": "все рынки", "commodity": "сырьё", "stock": "акции",
        "crypto": "крипта", "realty": "недвижимость",
    }.get(target, target)


def _floor_step(qty: float, step: float) -> float:
    return round(math.floor(qty / step + 1e-9) * step, 6)


def apply_event(state: GameState, ev: EventDef, rng: random.Random) -> EventResult:
    picked: dict[str, Asset] = {}
    details: list[str] = []
    for eff in ev.effects:
        value = rng.uniform(eff.lo, eff.hi)
        targets = _targets(eff.target, rng, picked)
        label = ", ".join(a.symbol for a in targets) if len(targets) <= 2 else _class_label(eff.target)

        if eff.kind is EffectKind.PRICE:
            for a in targets:
                new = max(state.prices[a.symbol] * (1.0 + value), a.base_price * config.PRICE_FLOOR_RATIO)
                state.prices[a.symbol] = round(new, 4 if new < 1 else 2)
                state.history[a.symbol][-1] = state.prices[a.symbol]  # событие входит в тот же ход
            details.append(f"{label} {_fmt_pct(value)}")
        elif eff.kind is EffectKind.CASH:
            delta = float(round(value, -1)) if abs(value) >= 100 else float(round(value))
            state.cash = round(state.cash + delta, 2)
            details.append(_fmt_money(delta))
        elif eff.kind is EffectKind.CASH_PCT:
            delta = round(state.cash * value, 2) if state.cash > 0 else 0.0
            state.cash = round(state.cash + delta, 2)
            details.append(_fmt_money(delta))
        elif eff.kind is EffectKind.HOLDING_PCT:
            changes = []
            for a in targets:
                have = state.holdings.get(a.symbol, 0.0)
                if have <= 0:
                    continue
                new = _floor_step(have * (1.0 + value), a.step)
                state.holdings[a.symbol] = new
                changes.append(f"{a.symbol} {new - have:+g}".replace("-", "−"))
            details.append(", ".join(changes) if changes else "у вас этого нет — обошлось")
        elif eff.kind in (EffectKind.DRIFT, EffectKind.RENT, EffectKind.RATE):
            kind = {EffectKind.DRIFT: ModKind.DRIFT, EffectKind.RENT: ModKind.RENT, EffectKind.RATE: ModKind.RATE}[eff.kind]
            target = targets[0].symbol if eff.target.startswith("@") else eff.target
            state.modifiers.append(Modifier(kind, target, value, eff.turns, ev.id))
            details.append(f"{_class_label(eff.target)}: {eff.turns} х.")
        elif eff.kind is EffectKind.REPAIR:
            owned = int(sum(state.holdings.get(a.symbol, 0.0) for a in config.assets_of(AssetClass.REALTY)))
            cost = float(round(value, -1)) * owned
            state.cash = round(state.cash - cost, 2)
            details.append(_fmt_money(-cost) if owned else "объектов нет — обошлось")

    name = next(iter(picked.values())).name if picked else ""
    return EventResult(ev.id, f"{ev.text.format(name=name)} [{'; '.join(details)}]", ev.tone)


def tick_modifiers(state: GameState) -> None:
    for m in state.modifiers:
        m.turns_left -= 1
    state.modifiers = [m for m in state.modifiers if m.turns_left > 0]
