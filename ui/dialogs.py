"""Модальные окна: Новая игра, Рекорды, Итоги партии."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit,
                               QTableWidget, QTableWidgetItem, QVBoxLayout, QHeaderView, QWidget)

from core import config
from core.models import GameStatus

from .widgets import fmt_money

_STATUS_TITLE = {
    GameStatus.WON: ("ПОБЕДА!", "amber"),
    GameStatus.LOST_BANKRUPT: ("БАНКРОТСТВО", "sell"),
    GameStatus.LOST_TIMEOUT: ("ХОДЫ ЗАКОНЧИЛИСЬ", "dim"),
}
_STATUS_RU = {"won": "победа", "lost_bankrupt": "банкрот", "lost_timeout": "время", "playing": "—"}


class NewGameDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Новая игра")
        self.combo = QComboBox()
        for d in config.DIFFICULTIES.values():
            self.combo.addItem(f"{d.title} — {fmt_money(d.start_cash)} → {fmt_money(d.target)}", d.key)
        self.combo.setCurrentIndex(list(config.DIFFICULTIES).index(config.DEFAULT_DIFFICULTY))
        self.seed = QLineEdit()
        self.seed.setPlaceholderText("случайное")
        form = QFormLayout()
        form.addRow("Сложность:", self.combo)
        form.addRow("Seed:", self.seed)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Начать (Enter)")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Отмена (Esc)")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(buttons)

    def result_values(self) -> tuple[str, int | None]:
        text = self.seed.text().strip()
        return self.combo.currentData(), int(text) if text.isdigit() else None


class HighscoresDialog(QDialog):
    def __init__(self, scores: list[dict], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Рекорды")
        self.resize(560, 340)
        table = QTableWidget(len(scores), 5)
        table.setHorizontalHeaderLabels(["#", "Капитал", "Ходов", "Итог", "Дата"])
        table.verticalHeader().hide()
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        for i, e in enumerate(scores):
            row = [str(i + 1), fmt_money(e["net_worth"]), str(e["days"]),
                   f'{_STATUS_RU.get(e["status"], e["status"])} / {e["difficulty"]}', e.get("date", "")]
            for j, text in enumerate(row):
                table.setItem(i, j, QTableWidgetItem(text))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText("Закрыть (Esc)")
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(table)
        if not scores:
            lay.addWidget(QLabel("Пока пусто — сыграйте партию до конца."))
        lay.addWidget(buttons)


class GameOverDialog(QDialog):
    def __init__(self, status: GameStatus, net_worth: float, days: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Итоги партии")
        title, style = _STATUS_TITLE[status]
        head = QLabel(title)
        head.setObjectName("big")
        head.setAlignment(Qt.AlignmentFlag.AlignCenter)
        body = QLabel(f"Итоговый капитал: {fmt_money(net_worth)}\nПрошло ходов: {days}")
        body.setAlignment(Qt.AlignmentFlag.AlignCenter)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("В таблицу рекордов (Enter)")
        buttons.accepted.connect(self.accept)
        lay = QVBoxLayout(self)
        lay.addWidget(head)
        lay.addWidget(body)
        lay.addWidget(buttons)


class EventDialog(QDialog):
    """Уведомление о важном событии в режиме реального времени: время стоит, пока игрок не подтвердит."""

    def __init__(self, day: int, lines: list[str], tone: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Важное событие — игра на паузе")
        self.setMinimumWidth(520)
        color = {1: "#3DFF7A", -1: "#FF4D5E", 0: "#FFB000"}[tone]
        head = QLabel(f"СОБЫТИЕ · ход {day}")
        head.setObjectName("big")
        body = QLabel("<br><br>".join(lines))
        body.setWordWrap(True)
        body.setStyleSheet(f"font-size: 12pt; color: {color};")
        note = QLabel("Время остановлено. Игра продолжится после подтверждения.")
        note.setObjectName("dim")
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
        ok.setText("Понятно (Enter)")
        ok.setObjectName("primary")
        buttons.accepted.connect(self.accept)
        lay = QVBoxLayout(self)
        lay.addWidget(head)
        lay.addWidget(body)
        lay.addWidget(note)
        lay.addWidget(buttons)
