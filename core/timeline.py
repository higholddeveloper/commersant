"""Игровой календарь: один ход = одна неделя. Дата, прошедшее время, смена месяца."""
from __future__ import annotations

from datetime import date, timedelta

START_DATE = date(2025, 1, 6)
TURNS_PER_YEAR = 52
_MONTHS = ("янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек")


def date_of(day: int) -> date:
    return START_DATE + timedelta(weeks=max(day, 1) - 1)


def fmt_date(day: int) -> str:
    d = date_of(day)
    return f"{d.day} {_MONTHS[d.month - 1]} {d.year}"


def elapsed_text(day: int) -> str:
    """Сколько игрового времени прошло с начала партии: «3 нед.», «1 г. 2 мес. 1 нед.»."""
    years, rest = divmod(max(day - 1, 0), TURNS_PER_YEAR)
    months = int(rest / 4.345)
    weeks = max(int(round(rest - months * 4.345)), 0)
    parts = []
    if years:
        parts.append(f"{years} г.")
    if months:
        parts.append(f"{months} мес.")
    if weeks or not parts:
        parts.append(f"{weeks} нед.")
    return " ".join(parts)


def month_changed(day: int) -> bool:
    """Наступил ли новый календарный месяц по сравнению с предыдущим ходом (дата платежей ЖКХ)."""
    return day > 1 and date_of(day).month != date_of(day - 1).month


def turns_to_next_month(day: int) -> int:
    """Через сколько ходов ближайший ежемесячный платёж."""
    n = 1
    while not month_changed(day + n):
        n += 1
    return n
