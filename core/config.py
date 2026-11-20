"""Стартовые параметры, списки активов, настройки сложности."""
from __future__ import annotations

from dataclasses import dataclass

from .models import Asset, AssetClass

C, S, K, R = AssetClass.COMMODITY, AssetClass.STOCK, AssetClass.CRYPTO, AssetClass.REALTY

ASSETS: tuple[Asset, ...] = (
    # --- Сырьё ---
    Asset("OIL", "Нефть", C, 70.0, 0.060, 0.001, 0.010, 1, "барр."),
    Asset("LAND", "Земля", C, 1000.0, 0.030, 0.003, 0.030, 1, "сот."),
    # --- Акции S&P 500 ---
    Asset("NVDA", "NVIDIA", S, 180.0, 0.070, 0.004, 0.004, 1, "шт."),
    Asset("AAPL", "Apple", S, 230.0, 0.030, 0.003, 0.004, 1, "шт."),
    Asset("MSFT", "Microsoft", S, 420.0, 0.030, 0.003, 0.004, 1, "шт."),
    Asset("AMZN", "Amazon", S, 200.0, 0.040, 0.003, 0.004, 1, "шт."),
    Asset("GOOGL", "Alphabet", S, 170.0, 0.035, 0.003, 0.004, 1, "шт."),
    Asset("META", "Meta", S, 560.0, 0.050, 0.003, 0.004, 1, "шт."),
    Asset("TSLA", "Tesla", S, 250.0, 0.080, 0.002, 0.004, 1, "шт."),
    Asset("JPM", "JPMorgan", S, 220.0, 0.025, 0.002, 0.004, 1, "шт."),
    Asset("V", "Visa", S, 280.0, 0.020, 0.002, 0.004, 1, "шт."),
    Asset("BRK", "Berkshire", S, 470.0, 0.015, 0.002, 0.004, 1, "шт."),
    # --- Крипта ---
    Asset("BTC", "Bitcoin", K, 90000.0, 0.090, 0.002, 0.010, 0.001, "BTC"),
    Asset("ETH", "Ethereum", K, 3000.0, 0.110, 0.002, 0.010, 0.01, "ETH"),
    Asset("SOL", "Solana", K, 150.0, 0.140, 0.002, 0.012, 0.1, "SOL"),
    Asset("DOGE", "Dogecoin", K, 0.25, 0.180, 0.000, 0.015, 10.0, "DOGE"),
    # --- Недвижимость (поштучно, пассивный доход в % годовых от текущей цены) ---
    Asset("STUDIO", "Студия", R, 60_000.0, 0.010, 0.002, 0.030, 1, "шт."),
    Asset("COFFEE", "Кофейня", R, 120_000.0, 0.012, 0.002, 0.030, 1, "шт."),
    Asset("OFFICE", "Офис", R, 250_000.0, 0.015, 0.002, 0.030, 1, "шт."),
    Asset("WAREHOUSE", "Склад", R, 180_000.0, 0.012, 0.002, 0.030, 1, "шт."),
)

ASSET_BY_SYMBOL: dict[str, Asset] = {a.symbol: a for a in ASSETS}

# Порядок вкладок: [1] Сырьё [2] Акции [3] Крипта [4] Недвижимость ([5] Банк — без активов)
TAB_ORDER: tuple[AssetClass, ...] = (C, S, K, R)


def assets_of(cls: AssetClass) -> tuple[Asset, ...]:
    return tuple(a for a in ASSETS if a.cls == cls)


@dataclass(frozen=True)
class Difficulty:
    key: str
    title: str
    start_cash: float
    target: float
    max_days: int
    event_chance: float        # вероятность события за ход
    bad_event_bias: float      # множитель веса негативных событий
    deposit_rate: float        # ставка вклада за ход
    loan_rate: float           # ставка кредита за ход
    loan_term: int             # срок кредита, ходов
    loan_limit_ratio: float    # макс. кредит как доля от чистого капитала (без долга)
    default_penalty: float     # штраф за просрочку, доля от долга
    bankruptcy_floor: float    # капитал <= этого значения => банкротство


DIFFICULTIES: dict[str, Difficulty] = {
    "easy": Difficulty("easy", "Лёгкая", 100_000, 500_000, 250, 0.70, 0.8, 0.004, 0.008, 12, 0.6, 0.10, 0.0),
    "normal": Difficulty("normal", "Нормальная", 100_000, 1_000_000, 250, 0.75, 1.0, 0.003, 0.010, 10, 0.5, 0.15, 0.0),
    "hard": Difficulty("hard", "Сложная", 50_000, 1_000_000, 250, 0.85, 1.3, 0.002, 0.012, 8, 0.4, 0.20, 0.0),
}
DEFAULT_DIFFICULTY = "normal"

HISTORY_LEN = 400      # точек истории котировок (хватает на всю партию с продлением)
LOG_LEN = 50           # записей в логе
PRICE_FLOOR_RATIO = 0.05   # цена не падает ниже 5% от базовой
MAX_TURN_RETURN = (-0.40, 0.60)  # ограничение доходности за ход
MEAN_REVERSION = 0.03  # сила возврата к «справедливой» цене

EXTEND_TURNS = 100     # на сколько ходов игрок может продлить партию по окончании лимита
