"""Пиктограммы активов и собственности: цветные эмодзи и круглые «монеты» для криптовалют."""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPen, QPixmap

from . import theme

EMOJI_FONT = "Segoe UI Emoji"

EMOJI: dict[str, str] = {
    # сырьё
    "OIL": "🛢", "LAND": "🏞",
    # акции
    "NVDA": "🖥", "AAPL": "🍎", "MSFT": "💻", "AMZN": "📦", "GOOGL": "🔍", "META": "📱",
    "TSLA": "🔋", "JPM": "🏦", "V": "💳", "BRK": "🏛",
    # коммерческая недвижимость
    "STUDIO": "🏠", "COFFEE": "☕", "OFFICE": "🏢", "WAREHOUSE": "🏭",
    # жильё
    "housing_0": "⛺", "housing_1": "🏚", "housing_2": "🏠", "housing_3": "🏢", "housing_4": "🏙", "housing_5": "🏰",
    # транспорт
    "vehicle_0": "🚶", "vehicle_1": "🛵", "vehicle_2": "🚗", "vehicle_3": "🚘", "vehicle_4": "🚙", "vehicle_5": "🏎",
    # вкладки и прочее
    "tab_commodity": "🛢", "tab_stock": "📈", "tab_realty": "🏢", "tab_property": "🏡", "tab_bank": "🏦",
    "health": "❤", "sick": "🤒", "dead": "💀", "swan": "🦢", "cash": "💵", "calendar": "📅",
}

# (символ на монете, цвет монеты, цвет символа)
BADGES: dict[str, tuple[str, str, str]] = {
    "BTC": ("₿", "#F7931A", "#FFFFFF"),
    "ETH": ("Ξ", "#627EEA", "#FFFFFF"),
    "SOL": ("◎", "#9945FF", "#14F195"),
    "DOGE": ("Ð", "#C2A633", "#1A1A1A"),
    "tab_crypto": ("₿", "#F7931A", "#FFFFFF"),
}

_cache: dict[tuple[str, int], QPixmap] = {}


def pixmap(key: str, size: int = 20) -> QPixmap:
    """Квадратная пиктограмма (кэшируется). Требует созданного QApplication."""
    ck = (key, size)
    if ck in _cache:
        return _cache[ck]
    ratio = 2   # рисуем в двойном разрешении — чётче на масштабировании
    pm = QPixmap(size * ratio, size * ratio)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
    rect = QRectF(0, 0, size * ratio, size * ratio)
    if key in BADGES:
        glyph, bg, fg = BADGES[key]
        p.setPen(QPen(QColor(theme.BG), 1))
        p.setBrush(QColor(bg))
        p.drawEllipse(rect.adjusted(2, 2, -2, -2))
        f = QFont("Segoe UI", int(size * ratio * 0.42))
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(fg))
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, glyph)
    else:
        f = QFont(EMOJI_FONT)
        f.setPixelSize(int(size * ratio * 0.78))
        p.setFont(f)
        p.setPen(QColor(theme.TEXT))
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, EMOJI.get(key, "•"))
    p.end()
    pm.setDevicePixelRatio(ratio)
    _cache[ck] = pm
    return pm


def icon(key: str, size: int = 20) -> QIcon:
    return QIcon(pixmap(key, size))
