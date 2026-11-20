"""Собственность: жильё и транспорт (5 уровней), коммунальные платежи, происшествия, защита и страховка."""
from __future__ import annotations

import random
from dataclasses import dataclass

SELL_FACTOR = 0.85        # обычная продажа / обмен
SEIZE_FACTOR = 0.70       # распродажа имущества банком
SECURE_FROM = 3           # с этого уровня есть охрана / сигнализация — грабители не страшны
INSURED_FROM = 3          # с этого уровня имущество застраховано — вместо штрафа компенсация
HOMELESS_GRACE = 5        # столько ходов без жилья можно продержаться, затем начинаются болезни
MAX_ILLNESSES = 3         # третья болезнь на улице — смерть


@dataclass(frozen=True)
class Tier:
    level: int
    name: str
    price: float
    upkeep: float      # платёж в месяц (коммунальные / топливо и страховка)
    perks: str


HOUSING: tuple[Tier, ...] = (
    Tier(1, "Конура", 4_000, 40, "картонная будка: сыро, холодно, ни замка, ни охраны"),
    Tier(2, "Однокомнатная квартира", 45_000, 200, "своя крыша и дверь с замком, но без охраны"),
    Tier(3, "Трёхкомнатная квартира", 120_000, 450, "дом с охраной и страховкой: грабители не страшны"),
    Tier(4, "Пентхаус", 300_000, 900, "охрана, консьерж, страховка"),
    Tier(5, "Особняк", 700_000, 2_200, "своя территория, охрана, страховка по высшему разряду"),
)
VEHICLES: tuple[Tier, ...] = (
    Tier(1, "Мопед", 1_000, 20, "дёшево, но дождь, холод и грабители ближе, чем хотелось бы"),
    Tier(2, "Старый хэтчбек", 12_000, 90, "крыша над головой в пути, но без сигнализации и страховки"),
    Tier(3, "Хороший седан", 40_000, 200, "сигнализация и страховка: не угонят и не ограбят"),
    Tier(4, "Внедорожник", 100_000, 400, "надёжный, застрахованный, с охраняемой парковкой"),
    Tier(5, "Премиум-седан", 250_000, 800, "статусная машина с личным водителем и полной страховкой"),
)
TIERS = {"housing": HOUSING, "vehicle": VEHICLES}
KIND_TITLE = {"housing": "Жильё", "vehicle": "Транспорт"}
NOTHING = {"housing": "Бездомный", "vehicle": "Пешком"}


def tier(kind: str, level: int) -> Tier | None:
    return TIERS[kind][level - 1] if level > 0 else None


def name_of(kind: str, level: int) -> str:
    t = tier(kind, level)
    return t.name if t else NOTHING[kind]


def sale_value(kind: str, level: int, factor: float = SELL_FACTOR) -> float:
    t = tier(kind, level)
    return round(t.price * factor, 2) if t else 0.0


def is_secure(level: int) -> bool:
    return level >= SECURE_FROM


def is_insured(level: int) -> bool:
    return level >= INSURED_FROM


@dataclass(frozen=True)
class Mishap:
    id: str
    kind: str                                  # housing | vehicle
    levels: tuple[int, ...]                    # на каких уровнях может случиться
    chance: float                              # вероятность за ход (в сумме с остальными того же вида)
    text: str
    cash_pct: tuple[float, float] | None = None   # потеря доли наличных (кража, грабёж)
    repair_pct: tuple[float, float] | None = None  # ремонт: доля стоимости объекта
    fine: tuple[float, float] | None = None       # фиксированный штраф / счёт
    destroy: bool = False                      # объект потерян (сгорел, угнан)
    comp_pct: tuple[float, float] | None = None   # компенсация страховой (если застраховано)
    ill: bool = False                          # счёт за лечение


MISHAPS: tuple[Mishap, ...] = (
    # ---- жильё ----
    Mishap("h_squatters", "housing", (1,), 0.050, "Бомжи залезли в вашу конуру и вынесли все пожитки.", cash_pct=(0.04, 0.10)),
    Mishap("h_arson", "housing", (1,), 0.015, "Пьяные алкаши подожгли вашу конуру — жильё сгорело дотла!", destroy=True),
    Mishap("h_burglary", "housing", (2,), 0.040, "Квартиру вскрыли, пока вас не было: пропали деньги и вещи.", cash_pct=(0.05, 0.14)),
    Mishap("h_inspection", "housing", (1, 2), 0.030, "Санинспекция выписала штраф за антисанитарию.", fine=(150, 600)),
    Mishap("h_fire", "housing", (1, 2), 0.020, "Пожар из-за проводки: нужен срочный ремонт.", repair_pct=(0.15, 0.35)),
    Mishap("h_fire_ins", "housing", (3, 4, 5), 0.018, "Пожар в доме — страховая выплатила компенсацию.", comp_pct=(0.04, 0.09)),
    Mishap("h_flood", "housing", (2,), 0.030, "Соседи сверху затопили квартиру: ремонт за ваш счёт.", repair_pct=(0.04, 0.10)),
    Mishap("h_flood_ins", "housing", (3, 4, 5), 0.025, "Соседи затопили квартиру — управляющая компания выплатила компенсацию.", comp_pct=(0.02, 0.05)),
    # ---- транспорт ----
    Mishap("v_rain", "vehicle", (0, 1), 0.045, "Попали под ливень, простудились: счёт за лечение.", fine=(300, 1_200), ill=True),
    Mishap("v_robbery", "vehicle", (0, 1, 2), 0.035, "На тёмной улице вас ограбили и отобрали наличные.", cash_pct=(0.05, 0.15)),
    Mishap("v_theft", "vehicle", (1, 2), 0.010, "Транспорт угнали со двора!", destroy=True),
    Mishap("v_breakdown", "vehicle", (1, 2), 0.030, "Поломка в дороге: ремонт и эвакуатор.", repair_pct=(0.08, 0.20)),
    Mishap("v_crash", "vehicle", (1, 2), 0.020, "Авария по вашей вине: штраф и ремонт.", repair_pct=(0.15, 0.35)),
    Mishap("v_crash_ins", "vehicle", (3, 4, 5), 0.020, "Авария не по вашей вине — страховая выплатила компенсацию.", comp_pct=(0.04, 0.09)),
    Mishap("v_fine", "vehicle", (1, 2, 3, 4, 5), 0.025, "Штраф ГИБДД за превышение скорости.", fine=(150, 700)),
)
MISHAP_BY_ID = {m.id: m for m in MISHAPS}


@dataclass
class MishapOutcome:
    mishap: Mishap
    text: str
    tone: int
    cash_delta: float = 0.0
    destroyed: bool = False


def _money(x: float) -> str:
    return f"{abs(x):,.0f}".replace(",", " ") + " $"


def roll_mishap(kind: str, level: int, cash: float, rng: random.Random, bias: float = 1.0) -> MishapOutcome | None:
    """Не более одного происшествия на вид собственности за ход."""
    pool = [m for m in MISHAPS if m.kind == kind and level in m.levels]
    if not pool:
        return None
    total = min(sum(m.chance for m in pool) * bias, 0.95)
    if rng.random() >= total:
        return None
    m = rng.choices(pool, weights=[x.chance for x in pool], k=1)[0]
    return resolve(m, level, cash, rng)


def resolve(m: Mishap, level: int, cash: float, rng: random.Random) -> MishapOutcome:
    t = tier(m.kind, level)
    value = t.price if t else 0.0
    if m.comp_pct and is_insured(level):
        pay = round(value * rng.uniform(*m.comp_pct), -1)
        return MishapOutcome(m, f"{m.text} +{_money(pay)}", +1, +pay)
    if m.destroy:
        return MishapOutcome(m, f"{m.text} Вы остались без {'жилья' if m.kind == 'housing' else 'транспорта'}.",
                             -1, 0.0, True)
    if m.cash_pct:
        loss = round(max(cash, 0.0) * rng.uniform(*m.cash_pct), -1)
        if loss <= 0:
            return MishapOutcome(m, f"{m.text} Но брать было нечего — обошлось.", 0)
        return MishapOutcome(m, f"{m.text} −{_money(loss)}", -1, -loss)
    if m.repair_pct:
        cost = max(round(value * rng.uniform(*m.repair_pct), -1), 50.0)
        return MishapOutcome(m, f"{m.text} −{_money(cost)}", -1, -cost)
    if m.fine:
        cost = round(rng.uniform(*m.fine), -1)
        return MishapOutcome(m, f"{m.text} −{_money(cost)}", -1, -cost)
    return MishapOutcome(m, m.text, 0)


SHORT = {
    "h_squatters": "бомжи в доме", "h_arson": "поджог", "h_burglary": "кража со взломом",
    "h_inspection": "штрафы инспекций", "h_fire": "пожар", "h_fire_ins": "пожар",
    "h_flood": "затопление", "h_flood_ins": "затопление",
    "v_rain": "дождь и простуда", "v_robbery": "ограбление на дороге", "v_theft": "угон",
    "v_breakdown": "поломки", "v_crash": "аварии", "v_crash_ins": "авария", "v_fine": "штрафы ГИБДД",
}


def risks(kind: str, level: int) -> tuple[list[str], list[str]]:
    """(чем грозит, за что платит страховка) для данного уровня."""
    bad, covered = [], []
    for m in MISHAPS:
        if m.kind == kind and level in m.levels:
            (covered if m.comp_pct and is_insured(level) else bad).append(SHORT[m.id])
    if kind == "vehicle" and level == 0:
        bad.append("долгая дорога пешком")
    return bad, covered
