"""Торговые фигуры и режимы рынка: цены движутся не только случайно, но и по узнаваемым формациям.

Каждый актив время от времени «входит» в фигуру (бычий/медвежий тренд, флэт, клинья, двойное дно/вершина,
голова и плечи и т.д.) — это заготовленная траектория накопленной доходности, на которую накладывается шум.
Поверх идёт глобальный режим рынка (бычий / медвежий / флэт), который смещает выбор фигур.
«Чёрные лебеди» — редкие катастрофы, которые принудительно запускают фигуры-обвалы на нужных активах.
"""
from __future__ import annotations

import random
from dataclasses import dataclass

from . import config
from .models import Asset, AssetClass, GameState, PatternRun

AMP_PER_VOL = 3.2
AMP_RANGE = (0.04, 0.30)


@dataclass(frozen=True)
class PatternDef:
    key: str
    title: str
    hint: str
    bias: int                       # +1 бычья, -1 медвежья, 0 нейтральная
    length: int                     # ходов
    points: tuple[float, ...]       # ключевые точки накопленной лог-доходности в долях амплитуды
    vol_mult: float = 0.45          # во сколько раз ослаблен случайный шум
    weight: float = 1.0
    swan: bool = False


PATTERNS: dict[str, PatternDef] = {p.key: p for p in (
    PatternDef("bull", "Бычий тренд", "Тренд вверх с откатами — держите и докупайте на просадках.", +1, 20,
               (0, 0.5, 0.3, 1.0, 0.8, 1.6), 0.6, 1.4),
    PatternDef("bear", "Медвежий тренд", "Тренд вниз с отскоками — не спешите покупать, отскоки продают.", -1, 20,
               (0, -0.5, -0.3, -1.0, -0.8, -1.6), 0.6, 1.4),
    PatternDef("flat", "Флэт (боковик)", "Цена ходит в коридоре — покупка у низа, продажа у верха.", 0, 14,
               (0, 0.2, -0.2, 0.15, -0.15, 0.0), 0.7, 1.2),
    PatternDef("rising_wedge", "Восходящий клин", "Рост на затухающей силе — после пробоя вниз обычно резкое падение.",
               -1, 20, (0, 0.6, 0.3, 0.9, 0.6, 1.1, 0.9, 1.2, -0.3, -0.9), 0.4, 0.8),
    PatternDef("falling_wedge", "Нисходящий клин", "Падение выдыхается — обычно пробой вверх и рывок.",
               +1, 20, (0, -0.6, -0.3, -0.9, -0.6, -1.1, -0.9, -1.2, 0.3, 0.9), 0.4, 0.8),
    PatternDef("double_bottom", "Двойное дно", "Дважды отскочили от одного уровня — вероятен разворот вверх.",
               +1, 22, (0, -1.0, -0.4, -1.0, -0.2, 0.8), 0.4, 0.9),
    PatternDef("double_top", "Двойная вершина", "Дважды упёрлись в потолок — вероятен разворот вниз.",
               -1, 22, (0, 1.0, 0.4, 1.0, 0.2, -0.8), 0.4, 0.9),
    PatternDef("head_shoulders", "Голова и плечи", "Классический разворот вниз после трёх вершин — фиксируйте прибыль.",
               -1, 24, (0, 0.8, 0.3, 1.3, 0.3, 0.8, 0.2, -0.8), 0.4, 0.8),
    PatternDef("inverse_hs", "Перевёрнутая голова и плечи", "Три впадины, средняя глубже — разворот вверх.",
               +1, 24, (0, -0.8, -0.3, -1.3, -0.3, -0.8, -0.2, 0.8), 0.4, 0.8),
    # --- сценарии чёрных лебедей (в случайный выбор не попадают) ---
    PatternDef("swan_crash", "Обвал и восстановление", "Паника на рынке.", -1, 14,
               (0, -0.9, -1.6, -1.9, -1.6, -1.0, -0.6, -0.3), 0.6, 0.0, True),
    PatternDef("swan_spike", "Скачок на новостях", "Резкий рост на панике и дефиците.", +1, 12,
               (0, 0.9, 1.6, 1.8, 1.3, 0.9, 0.5), 0.6, 0.0, True),
)}

BULLISH = {k for k, p in PATTERNS.items() if p.bias > 0 and not p.swan}
BEARISH = {k for k, p in PATTERNS.items() if p.bias < 0 and not p.swan}

REGIMES = {"bull": "бычий", "bear": "медвежий", "flat": "боковой"}
REGIME_BIAS = {"bull": 0.0010, "bear": -0.0010, "flat": 0.0}   # лёгкий общий дрейф режима, за ход


def amplitude(asset: Asset) -> float:
    return min(max(asset.volatility * AMP_PER_VOL, AMP_RANGE[0]), AMP_RANGE[1])


def target(p: PatternDef, step: int) -> float:
    """Накопленная лог-доходность (в долях амплитуды) на шаге step от 0 до length."""
    pos = min(max(step, 0), p.length) / p.length * (len(p.points) - 1)
    i = min(int(pos), len(p.points) - 2)
    return p.points[i] + (p.points[i + 1] - p.points[i]) * (pos - i)


# ---------------------------- режим рынка ----------------------------
def update_regime(state: GameState, rng: random.Random) -> None:
    state.regime_left -= 1
    if state.regime_left > 0 and state.regime in REGIMES:
        return
    choices = [r for r in REGIMES if r != state.regime] or list(REGIMES)
    state.regime = rng.choice(choices)
    state.regime_left = rng.randint(25, 55)


def _weights(regime: str) -> list[tuple[str, float]]:
    out = []
    for key, p in PATTERNS.items():
        if p.swan:
            continue
        w = p.weight
        if regime == "bull":
            w *= 2.6 if key in BULLISH else 0.45 if key in BEARISH else 1.0
        elif regime == "bear":
            w *= 2.6 if key in BEARISH else 0.45 if key in BULLISH else 1.0
        else:
            w *= 4.0 if key == "flat" else 0.8
        out.append((key, w))
    return out


def _start_pattern(state: GameState, asset: Asset, key: str, mult: float = 1.0) -> None:
    amp = amplitude(asset) * mult
    if asset.cls is AssetClass.REALTY:
        amp *= 0.8
    state.patterns[asset.symbol] = PatternRun(key, 0, round(amp, 4))


def force_pattern(state: GameState, asset: Asset, key: str, mult: float = 1.0) -> None:
    """Принудительный запуск (чёрный лебедь)."""
    _start_pattern(state, asset, key, mult)
    state.pattern_idle.pop(asset.symbol, None)


def step_asset(state: GameState, asset: Asset, rng: random.Random) -> tuple[float, float, float]:
    """Возвращает (добавка к доходности от фигуры, множитель шума, множитель возврата к среднему)."""
    sym = asset.symbol
    run = state.patterns.get(sym)
    if run is None:
        idle = state.pattern_idle.get(sym)
        if idle is None:
            idle = state.pattern_idle[sym] = rng.randint(0, 6)
        if idle > 0:
            state.pattern_idle[sym] = idle - 1
            return REGIME_BIAS.get(state.regime, 0.0), 1.0, 1.0
        keys, ws = zip(*_weights(state.regime))
        _start_pattern(state, asset, rng.choices(keys, weights=ws, k=1)[0])
        run = state.patterns[sym]
    p = PATTERNS[run.key]
    prev = target(p, run.step)
    run.step += 1
    delta = (target(p, run.step) - prev) * run.amp
    if run.step >= p.length:
        del state.patterns[sym]
        state.pattern_idle[sym] = rng.randint(2, 8)
    return delta, p.vol_mult, 0.25


def hint(state: GameState, symbol: str) -> tuple[PatternDef, float] | None:
    """Формирующаяся фигура: подсказка появляется, когда фигура пройдена больше чем наполовину."""
    run = state.patterns.get(symbol)
    if run is None:
        return None
    p = PATTERNS[run.key]
    progress = run.step / p.length
    return (p, progress) if progress >= 0.5 and not p.swan else None


# ---------------------------- чёрные лебеди ----------------------------
@dataclass(frozen=True)
class Swan:
    id: str
    title: str
    text: str
    # (цель: символ / класс / ALL, фигура, множитель амплитуды); конкретные символы идут после классов и перекрывают их
    hits: tuple[tuple[str, str, float], ...]
    weight: float = 1.0
    cash_pct: float = 0.0   # доля наличных, потерянных сразу (заморозка счетов и т.п.)


SWANS: tuple[Swan, ...] = (
    Swan("pandemic", "ПАНДЕМИЯ", "Вспышка смертельного вируса: границы закрыты, рынки в свободном падении!",
         (("stock", "swan_crash", 1.8), ("crypto", "swan_crash", 1.4), ("commodity", "swan_crash", 1.6),
          ("realty", "swan_crash", 1.0), ("OIL", "swan_crash", 2.2)), 1.0),
    Swan("gulf_war", "ВОЙНА В ПЕРСИДСКОМ ЗАЛИВЕ", "Война в Персидском заливе: танкеры стоят, нефть взлетает, акции падают.",
         (("stock", "swan_crash", 1.1), ("crypto", "swan_crash", 0.9), ("commodity", "swan_spike", 0.8),
          ("OIL", "swan_spike", 2.4)), 1.0),
    Swan("bank_run", "БАНКОВСКИЙ КРИЗИС", "Крупные банки лопаются, вкладчики штурмуют отделения — паника на всех рынках.",
         (("stock", "swan_crash", 1.6), ("realty", "swan_crash", 1.6), ("crypto", "swan_crash", 1.1),
          ("JPM", "swan_crash", 2.4)), 0.8, 0.03),
    Swan("exchange_collapse", "КРАХ КРИПТОБИРЖИ", "Одна из крупнейших криптобирж обанкротилась: доверие к крипте разрушено.",
         (("crypto", "swan_crash", 2.6),), 0.8),
    Swan("cyber_attack", "КИБЕРАТАКА ГОДА", "Массовая хакерская атака парализовала технологические компании и платёжные системы.",
         (("crypto", "swan_crash", 1.0), ("NVDA", "swan_crash", 2.0), ("MSFT", "swan_crash", 2.0),
          ("GOOGL", "swan_crash", 1.8), ("META", "swan_crash", 1.8), ("V", "swan_crash", 2.0)), 0.7, 0.02),
    Swan("black_monday", "ЧЁРНЫЙ ПОНЕДЕЛЬНИК", "Биржи рухнули за один день — самый резкий обвал за поколение!",
         (("stock", "swan_crash", 2.4), ("crypto", "swan_crash", 1.6), ("commodity", "swan_crash", 1.0)), 0.7),
    Swan("ai_breakthrough", "ТЕХНОЛОГИЧЕСКИЙ ПРОРЫВ", "Прорыв в области ИИ: технологические гиганты взлетают.",
         (("NVDA", "swan_spike", 2.2), ("MSFT", "swan_spike", 1.6), ("GOOGL", "swan_spike", 1.5),
          ("AMZN", "swan_spike", 1.3), ("META", "swan_spike", 1.3)), 0.6),
)
SWAN_CHANCE = 0.012   # за ход (~3 за партию в 250 ходов)


def targets(spec: str) -> list[Asset]:
    if spec == "ALL":
        return list(config.ASSETS)
    if spec in config.ASSET_BY_SYMBOL:
        return [config.ASSET_BY_SYMBOL[spec]]
    return list(config.assets_of(AssetClass(spec)))


def apply_swan(state: GameState, swan: Swan, rng: random.Random) -> None:
    """Запускает сценарий и сразу делает первый шаг: новость бьёт по ценам мгновенно."""
    for spec, key, mult in swan.hits:
        for a in targets(spec):
            force_pattern(state, a, key, mult)
    for sym in list(state.patterns):
        a = config.ASSET_BY_SYMBOL[sym]
        run = state.patterns[sym]
        if PATTERNS[run.key].swan and run.step == 0:
            shape, _, _ = step_asset(state, a, rng)
            new = max(state.prices[sym] * (1.0 + shape), a.base_price * config.PRICE_FLOOR_RATIO)
            state.prices[sym] = round(new, 4 if new < 1 else 2)
            state.history[sym][-1] = state.prices[sym]
    if swan.cash_pct and state.cash > 0:
        state.cash = round(state.cash * (1 - swan.cash_pct), 2)


def roll_swan(state: GameState, rng: random.Random) -> Swan | None:
    if rng.random() >= SWAN_CHANCE:
        return None
    swan = rng.choices(SWANS, weights=[s.weight for s in SWANS], k=1)[0]
    apply_swan(state, swan, rng)
    return swan
