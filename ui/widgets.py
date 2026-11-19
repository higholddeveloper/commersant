"""Кастомные виджеты: мини-график, поле количества, новостная лента, форматирование."""
from __future__ import annotations

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QKeyEvent, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QLineEdit, QPlainTextEdit, QSizePolicy, QWidget

from . import theme


def fmt_money(x: float, sign: bool = False) -> str:
    s = f"{x:+,.0f}" if sign else f"{x:,.0f}"
    return s.replace(",", " ").replace("-", "−") + " $"


def fmt_price(p: float) -> str:
    if p < 1:
        return f"{p:.4f}"
    if p < 100:
        return f"{p:,.2f}".replace(",", " ")
    return f"{p:,.0f}".replace(",", " ")


def fmt_qty(q: float) -> str:
    s = f"{q:,.4f}".rstrip("0").rstrip(".")
    return (s or "0").replace(",", " ")


def fmt_pct(x: float) -> str:
    return f"{x * 100:+.1f}%".replace("-", "−")


def pct_color(x: float) -> str:
    return theme.UP if x > 0.0005 else theme.DOWN if x < -0.0005 else theme.DIM


class Sparkline(QWidget):
    """График цены за период: линия, заливка, мин/макс, изменение за период и линия средней цены покупки."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._values: list[float] = []
        self._ref: float | None = None
        self.setMinimumHeight(60)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_data(self, values: list[float], ref: float | None = None) -> None:
        self._values = list(values)
        self._ref = ref if ref and ref > 0 else None
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.fillRect(r, QColor(theme.BG))
        p.setPen(QPen(QColor(theme.BORDER), 1))
        p.drawRect(r)
        vals = self._values
        if len(vals) < 2:
            p.setPen(QColor(theme.DIM))
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, "нет данных")
            return
        lo, hi = min(vals), max(vals)
        if self._ref:
            lo, hi = min(lo, self._ref), max(hi, self._ref)
        span = (hi - lo) or max(abs(hi) * 0.01, 1e-9)
        pad_l, pad_r, pad_t, pad_b = 6.0, 6.0, 16.0, 6.0
        w, h = r.width() - pad_l - pad_r, r.height() - pad_t - pad_b

        def y_of(v: float) -> float:
            return r.top() + pad_t + h * (1 - (v - lo) / span)

        pts = [QPointF(r.left() + pad_l + w * i / (len(vals) - 1), y_of(v)) for i, v in enumerate(vals)]
        color = QColor(theme.UP if vals[-1] >= vals[0] else theme.DOWN)
        p.setPen(QPen(QColor(theme.PANEL_HI), 1, Qt.PenStyle.DotLine))
        for k in range(1, 4):
            y = r.top() + pad_t + h * k / 4
            p.drawLine(QPointF(r.left() + 1, y), QPointF(r.right() - 1, y))
        fill = QColor(color)
        fill.setAlpha(40)
        poly = QPolygonF(pts + [QPointF(pts[-1].x(), r.bottom() - pad_b), QPointF(pts[0].x(), r.bottom() - pad_b)])
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(fill)
        p.drawPolygon(poly)
        if self._ref:  # средняя цена покупки
            y = y_of(self._ref)
            p.setPen(QPen(QColor(theme.CYAN), 1, Qt.PenStyle.DashLine))
            p.drawLine(QPointF(r.left() + 1, y), QPointF(r.right() - 1, y))
        p.setPen(QPen(color, 2))
        p.drawPolyline(QPolygonF(pts))
        p.setBrush(color)
        p.drawEllipse(pts[-1], 3, 3)
        p.setPen(QColor(theme.DIM))
        p.drawText(QPointF(r.left() + 6, r.top() + 12), f"макс {fmt_price(max(vals))}  мин {fmt_price(min(vals))}")
        chg = vals[-1] / vals[0] - 1 if vals[0] else 0.0
        p.setPen(QColor(pct_color(chg)))
        label = f"{len(vals) - 1} х.  {fmt_pct(chg)}"
        p.drawText(QPointF(r.right() - 6 - p.fontMetrics().horizontalAdvance(label), r.top() + 12), label)
        if self._ref:
            p.setPen(QColor(theme.CYAN))
            p.drawText(QPointF(r.left() + 6, r.bottom() - 4), "-- ср. цена покупки")


class QtyEdit(QLineEdit):
    """Поле количества. Не перехватывает буквенные горячие клавиши — они срабатывают и во время ввода."""

    _KEEP = {Qt.Key.Key_Backspace, Qt.Key.Key_Delete, Qt.Key.Key_Left, Qt.Key.Key_Right,
             Qt.Key.Key_Home, Qt.Key.Key_End, Qt.Key.Key_Period, Qt.Key.Key_Comma}

    def event(self, e: QEvent) -> bool:
        if e.type() == QEvent.Type.ShortcutOverride and isinstance(e, QKeyEvent):
            key = e.key()
            plain = not (e.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier))
            if plain and (Qt.Key.Key_0 <= key <= Qt.Key.Key_9 or key in self._KEEP):
                e.accept()  # цифры и редактирование остаются полю
                return True
            e.ignore()      # остальное — глобальным шорткатам
            return False
        return super().event(e)


class NewsLog(QPlainTextEdit):
    """Ретро-лента новостей: только чтение, прокрутка к последнему сообщению."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setReadOnly(True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setMaximumBlockCount(200)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)

    def set_lines(self, lines: list[str]) -> None:
        self.setPlainText("\n".join(lines))
        self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())
