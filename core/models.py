"""Dataclasses и перечисления игрового состояния."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class AssetClass(str, Enum):
    COMMODITY = "commodity"  # Сырьё
    STOCK = "stock"          # Акции
    CRYPTO = "crypto"        # Крипта
    REALTY = "realty"        # Недвижимость


class GameStatus(str, Enum):
    PLAYING = "playing"
    WON = "won"
    LOST_BANKRUPT = "lost_bankrupt"
    LOST_TIMEOUT = "lost_timeout"
    LOST_DEATH = "lost_death"


class ModKind(str, Enum):
    DRIFT = "drift"  # добавка к дневной доходности цены (target: символ / класс / ALL)
    RENT = "rent"    # добавка к множителю аренды (1.0 + value)
    RATE = "rate"    # добавка к ставкам банка за ход (value: +0.001 = +0.1%)


@dataclass(frozen=True)
class Asset:
    """Статическое описание торгуемого актива (не меняется в ходе игры)."""
    symbol: str
    name: str
    cls: AssetClass
    base_price: float
    volatility: float          # σ дневной доходности
    drift: float = 0.0         # средний тренд за ход
    spread: float = 0.005      # покупка = цена*(1+spread), продажа = цена*(1-spread)
    step: float = 1.0          # минимальный шаг количества
    unit: str = "шт."


@dataclass
class Modifier:
    """Временный рыночный фактор от события."""
    kind: ModKind
    target: str
    value: float
    turns_left: int
    label: str = ""


@dataclass
class BankAccount:
    deposit: float = 0.0
    loan: float = 0.0
    loan_turns_left: int = 0   # сколько ходов осталось до срока погашения


@dataclass
class PatternRun:
    """Активная торговая фигура актива."""
    key: str
    step: int = 0
    amp: float = 0.1           # амплитуда фигуры (доля цены)


@dataclass
class GameState:
    day: int = 1
    max_days: int = 250
    cash: float = 0.0
    start_cash: float = 0.0
    target: float = 0.0
    prices: dict[str, float] = field(default_factory=dict)
    history: dict[str, list[float]] = field(default_factory=dict)
    holdings: dict[str, float] = field(default_factory=dict)
    cost_basis: dict[str, float] = field(default_factory=dict)  # суммарные затраты на текущую позицию
    bank: BankAccount = field(default_factory=BankAccount)
    modifiers: list[Modifier] = field(default_factory=list)
    log: list[str] = field(default_factory=list)
    current_event: str = ""
    status: GameStatus = GameStatus.PLAYING
    difficulty: str = "normal"
    seed: int = 0
    # --- игрок и собственность ---
    player: str = "Игрок"
    extended: bool = False         # игрок продлевал лимит ходов (отметка в таблице рекордов)
    housing: int = 1               # 0 = бездомный, 1..5
    vehicle: int = 1               # 0 = пешком, 1..5
    homeless_turns: int = 0
    illnesses: int = 0
    overdue_turns: int = 0         # подряд ходов с отрицательными наличными
    # --- торговые фигуры ---
    regime: str = "flat"
    regime_left: int = 0
    patterns: dict[str, PatternRun] = field(default_factory=dict)
    pattern_idle: dict[str, int] = field(default_factory=dict)
    # --- журнал ---
    log_tone: list[int] = field(default_factory=list)   # тон каждой записи лога: +1 хорошо, -1 плохо
    current_tone: int = 0
    calm: bool = False             # на рынке тишина: тренды слабые, событий почти нет
    calm_left: int = 0
    slot: str = ""                 # имя последнего слота сохранения
