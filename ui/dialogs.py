"""Модальные окна: Новая игра (имя игрока), Сохранить/Загрузить, Рекорды, Итоги партии, События."""
from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
                               QHeaderView, QLabel, QLineEdit, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from core import config, storage
from core.models import GameStatus
from core.version import VERSION

from . import theme
from .widgets import fmt_money, icon_for

_STATUS_TITLE = {
    GameStatus.WON: ("ПОБЕДА!", theme.UP),
    GameStatus.LOST_BANKRUPT: ("БАНКРОТСТВО", theme.DOWN),
    GameStatus.LOST_TIMEOUT: ("ХОДЫ ЗАКОНЧИЛИСЬ", theme.AMBER),
    GameStatus.LOST_DEATH: ("ВЫ УМЕРЛИ", theme.DOWN),
}
_STATUS_RU = {"won": "победа", "lost_bankrupt": "банкрот", "lost_timeout": "время", "lost_death": "смерть",
              "playing": "—"}
MAX_NAME = 24


def _buttons(ok_text: str, cancel_text: str | None = "Отмена (Esc)") -> QDialogButtonBox:
    box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                           | (QDialogButtonBox.StandardButton.Cancel if cancel_text else QDialogButtonBox.StandardButton.NoButton))
    box.button(QDialogButtonBox.StandardButton.Ok).setText(ok_text)
    if cancel_text:
        box.button(QDialogButtonBox.StandardButton.Cancel).setText(cancel_text)
    return box


class NewGameDialog(QDialog):
    LOAD = 2   # код возврата: игрок выбрал «Загрузить сохранение»

    def __init__(self, parent: QWidget | None = None, default_name: str = "", first_start: bool = False) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Коммерсант {VERSION} — новая игра")
        self.setMinimumWidth(460)
        head = QLabel("КОММЕРСАНТ")
        head.setObjectName("big")
        head.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub = QLabel("Представьтесь: имя попадёт в таблицу рекордов и в название файла сохранения.")
        sub.setObjectName("dim")
        sub.setWordWrap(True)
        self.name = QLineEdit(default_name)
        self.name.setMaxLength(MAX_NAME)
        self.name.setPlaceholderText("ваше имя")
        self.combo = QComboBox()
        for d in config.DIFFICULTIES.values():
            self.combo.addItem(f"{d.title} — {fmt_money(d.start_cash)} → {fmt_money(d.target)}, {d.max_days} ходов", d.key)
        self.combo.setCurrentIndex(list(config.DIFFICULTIES).index(config.DEFAULT_DIFFICULTY))
        self.seed = QLineEdit()
        self.seed.setPlaceholderText("случайное")
        form = QFormLayout()
        form.addRow("Имя игрока:", self.name)
        form.addRow("Сложность:", self.combo)
        form.addRow("Seed:", self.seed)
        self.buttons = _buttons("Начать (Enter)", "Пропустить (Esc)" if first_start else "Отмена (Esc)")
        self.buttons.accepted.connect(self._accept)
        self.buttons.rejected.connect(self.reject)
        if first_start:
            load = self.buttons.addButton("Загрузить сохранение…", QDialogButtonBox.ButtonRole.ActionRole)
            load.clicked.connect(lambda: self.done(self.LOAD))
        self.warn = QLabel("")
        self.warn.setStyleSheet(f"color: {theme.DOWN};")
        lay = QVBoxLayout(self)
        lay.addWidget(head)
        lay.addWidget(sub)
        lay.addLayout(form)
        lay.addWidget(self.warn)
        lay.addWidget(self.buttons)
        self.name.setFocus()
        self.name.selectAll()

    def _accept(self) -> None:
        if not self.player_name():
            self.warn.setText("Введите имя игрока — без него результат не попадёт в таблицу рекордов.")
            self.name.setFocus()
            return
        self.accept()

    def player_name(self) -> str:
        return " ".join(self.name.text().split())

    def result_values(self) -> tuple[str, int | None, str]:
        text = self.seed.text().strip()
        return self.combo.currentData(), int(text) if text.isdigit() else None, self.player_name()


class SaveDialog(QDialog):
    """Название файла сохранения (по умолчанию — имя игрока)."""

    def __init__(self, parent: QWidget | None, default: str, existing: list[dict]) -> None:
        super().__init__(parent)
        self.setWindowTitle("Сохранить игру")
        self.setMinimumWidth(440)
        self.existing = {e["slot"].lower() for e in existing}
        self.name = QLineEdit(default)
        self.name.setMaxLength(40)
        self.name.textChanged.connect(self._check)
        self.note = QLabel("")
        self.note.setWordWrap(True)
        info = QLabel(f"Файл сохранится в папку:\n{storage.SAVES_DIR}")
        info.setObjectName("dim")
        info.setWordWrap(True)
        form = QFormLayout()
        form.addRow("Название:", self.name)
        self.buttons = _buttons("Сохранить (Enter)")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(self.note)
        lay.addWidget(info)
        lay.addWidget(self.buttons)
        self._check()
        self.name.setFocus()
        self.name.selectAll()

    def _check(self) -> None:
        clean = storage.slot_name(self.name.text())
        ok = bool(clean) and clean.lower() not in ("highscores", "settings")
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(ok)
        if not ok:
            self.note.setText("Введите название (не «highscores» и не «settings»).")
            self.note.setStyleSheet(f"color: {theme.DOWN};")
        elif clean.lower() in self.existing:
            self.note.setText(f"Сохранение «{clean}» уже есть — оно будет перезаписано.")
            self.note.setStyleSheet(f"color: {theme.AMBER};")
        else:
            self.note.setText(f"Будет создан файл «{clean}.json».")
            self.note.setStyleSheet(f"color: {theme.DIM};")

    def slot(self) -> str:
        return storage.slot_name(self.name.text())


class LoadDialog(QDialog):
    def __init__(self, parent: QWidget | None, saves: list[dict]) -> None:
        super().__init__(parent)
        self.setWindowTitle("Загрузить игру")
        self.resize(640, 340)
        self.saves = saves
        self.chosen: Path | None = None
        self.table = QTableWidget(len(saves), 5)
        t = self.table
        t.setHorizontalHeaderLabels(["Сохранение", "Игрок", "Ход", "Наличные", "Сохранено"])
        t.verticalHeader().hide()
        t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        t.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        for i, e in enumerate(saves):
            row = [e["slot"], e["player"], f'{min(e["day"], e["max_days"] or e["day"])} / {e["max_days"]}',
                   fmt_money(e["cash"]), time.strftime("%Y-%m-%d %H:%M", time.localtime(e["mtime"]))]
            for j, text in enumerate(row):
                t.setItem(i, j, QTableWidgetItem(text))
        t.cellDoubleClicked.connect(lambda *_: self._accept())
        if saves:
            t.selectRow(0)
        self.buttons = _buttons("Загрузить (Enter)", "Отмена (Esc)")
        self.buttons.accepted.connect(self._accept)
        self.buttons.rejected.connect(self.reject)
        other = self.buttons.addButton("Открыть файл…", QDialogButtonBox.ButtonRole.ActionRole)
        other.clicked.connect(self._browse)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(bool(saves))
        lay = QVBoxLayout(self)
        lay.addWidget(t)
        if not saves:
            lay.addWidget(QLabel("Сохранений пока нет. Сохраните партию: Ctrl+S."))
        lay.addWidget(self.buttons)

    def _accept(self) -> None:
        row = self.table.currentRow()
        if 0 <= row < len(self.saves):
            self.chosen = self.saves[row]["path"]
            self.accept()

    def _browse(self) -> None:
        name, _ = QFileDialog.getOpenFileName(self, "Открыть сохранение", str(storage.SAVES_DIR), "Сохранения (*.json)")
        if name:
            self.chosen = Path(name)
            self.accept()


class HighscoresDialog(QDialog):
    def __init__(self, scores: list[dict], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Рекорды")
        self.resize(900, 400)
        table = QTableWidget(len(scores), 7)
        table.setHorizontalHeaderLabels(["#", "Игрок", "Капитал", "Ходов", "Итог / сложность", "Дата", "Примечание"])
        table.verticalHeader().hide()
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        hh = table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hh.setStretchLastSection(False)
        for i, e in enumerate(scores):
            limit = e.get("max_days", 0)
            if e.get("extended"):
                note, color = "без лимита ходов (ходы продлевались)", theme.AMBER
            else:
                note, color = (f"в лимит {limit} ходов" if limit else ""), theme.DIM
            row = [str(i + 1), e.get("name", "Игрок"), fmt_money(e["net_worth"]), str(e["days"]),
                   f'{_STATUS_RU.get(e["status"], e["status"])} / {e["difficulty"]}', e.get("date", ""), note]
            for j, text in enumerate(row):
                item = QTableWidgetItem(text)
                if j == 6:
                    item.setForeground(_qcolor(color))
                table.setItem(i, j, item)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText("Закрыть (Esc)")
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(table)
        if not scores:
            lay.addWidget(QLabel("Пока пусто — сыграйте партию до конца."))
        else:
            hint = QLabel("Пометка «без лимита ходов» — игрок продлевал партию после окончания лимита, "
                          "сравнивайте такие результаты осторожно.")
            hint.setObjectName("dim")
            hint.setWordWrap(True)
            lay.addWidget(hint)
        lay.addWidget(buttons)


def _qcolor(hex_color: str):
    from PySide6.QtGui import QColor
    return QColor(hex_color)


class GameOverDialog(QDialog):
    def __init__(self, status: GameStatus, name: str, net_worth: float, days: int, extended: bool,
                 parent: QWidget | None = None, cause: str = "") -> None:
        super().__init__(parent)
        self.setWindowTitle("Итоги партии")
        self.setMinimumWidth(420)
        title, color = _STATUS_TITLE[status]
        self.setStyleSheet(f"QDialog {{ background: {theme.tone_bg(1 if status is GameStatus.WON else -1)}; }}")
        head = QLabel(title)
        head.setObjectName("big")
        head.setStyleSheet(f"color: {color}; font-size: 20pt; font-weight: bold;")
        head.setAlignment(Qt.AlignmentFlag.AlignCenter)
        text = (cause + "\n\n" if cause else "") + (f"Игрок: {name}\nИтоговый капитал: {fmt_money(net_worth)}\n"
                                                    f"Прошло ходов: {days}")
        if extended:
            text += "\n(партия продлевалась — в рекордах будет пометка «без лимита ходов»)"
        body = QLabel(text)
        body.setAlignment(Qt.AlignmentFlag.AlignCenter)
        body.setWordWrap(True)
        buttons = _buttons("В таблицу рекордов (Enter)", None)
        buttons.accepted.connect(self.accept)
        lay = QVBoxLayout(self)
        lay.addWidget(head)
        lay.addWidget(body)
        lay.addWidget(buttons)


class EventDialog(QDialog):
    """Окно события: красное — неприятность, зелёное — удача, чёрный лебедь — крупно и красным.
    В режиме реального времени время стоит, пока игрок не подтвердит."""

    def __init__(self, day_text: str, items: list[tuple[str, int]], parent: QWidget | None = None,
                 swan: bool = False, realtime: bool = True) -> None:
        super().__init__(parent)
        worst = min(t for _, t in items) if any(t < 0 for _, t in items) else max((t for _, t in items), default=0)
        color, bg = theme.tone_color(worst), theme.tone_bg(worst)
        self.setWindowTitle("Важное событие" + (" — игра на паузе" if realtime else ""))
        self.setMinimumWidth(540)
        self.setStyleSheet(f"QDialog {{ background: {bg}; border: 2px solid {color}; }}")
        title = "ЧЁРНЫЙ ЛЕБЕДЬ" if swan else "НЕПРИЯТНОСТЬ" if worst < 0 else "УДАЧА" if worst > 0 else "СОБЫТИЕ"
        head = QLabel(f"{icon_for(worst)} {title} · {day_text}")
        head.setStyleSheet(f"color: {color}; font-size: {17 if swan else 14}pt; font-weight: bold;")
        lay = QVBoxLayout(self)
        lay.addWidget(head)
        for text, tone in items:
            lbl = QLabel(text)
            lbl.setWordWrap(True)
            lbl.setStyleSheet(f"font-size: {13 if swan else 12}pt; color: {theme.tone_color(tone)};")
            lay.addWidget(lbl)
        if realtime:
            note = QLabel("Время остановлено. Игра продолжится после подтверждения.")
            note.setObjectName("dim")
            lay.addWidget(note)
        buttons = _buttons("Понятно (Enter)", None)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setObjectName("primary")
        buttons.accepted.connect(self.accept)
        lay.addWidget(buttons)
