"""Главное окно: шапка, вкладки 1–5, торговля, лента новостей, горячие клавиши."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QColor, QKeySequence
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QFrame, QGridLayout, QHBoxLayout, QHeaderView,
                               QLabel, QMainWindow, QMessageBox, QProgressBar, QPushButton, QTableWidget,
                               QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget)

from core import config, market, storage
from core.engine import Game, TradeError
from core.models import AssetClass, GameStatus, ModKind

from . import theme
from .dialogs import GameOverDialog, HighscoresDialog, NewGameDialog
from .widgets import NewsLog, QtyEdit, Sparkline, fmt_money, fmt_pct, fmt_price, fmt_qty, pct_color

WIN_W, WIN_H = 860, 580

TAB_TITLES = {
    AssetClass.COMMODITY: "[1] Сырьё",
    AssetClass.STOCK: "[2] Акции",
    AssetClass.CRYPTO: "[3] Крипта",
    AssetClass.REALTY: "[4] Недвижимость",
}
BANK_TAB = 4

# Латинская клавиша + её позиция на русской раскладке (ЙЦУКЕН) — шорткаты работают в обеих раскладках.
RU = {"B": "И", "S": "Ы", "N": "Т", "Q": "Й", "Z": "Я", "X": "Ч", "C": "С", "D": "В", "W": "Ц", "L": "Д", "R": "К"}


def _label(text: str = "", name: str = "") -> QLabel:
    lbl = QLabel(text)
    if name:
        lbl.setObjectName(name)
    return lbl


def _btn(text: str, name: str = "", slot=None, tip: str = "") -> QPushButton:
    b = QPushButton(text)
    b.setFocusPolicy(Qt.FocusPolicy.TabFocus)
    if name:
        b.setObjectName(name)
    if slot:
        b.clicked.connect(slot)
    if tip:
        b.setToolTip(tip)
    return b


def _qty_buttons(owner: "MainWindow", side: str) -> list[QPushButton]:
    pre = "" if side == "buy" else "⇧"
    names = (("25%", 0.25, "Z"), ("50%", 0.5, "X"), ("Макс", 1.0, "C"))
    return [_btn(f"{t} [{pre}{k}]", "buy" if side == "buy" else "sell",
                 lambda _=False, p=p: owner.trade_pct(side, p)) for t, p, k in names]


class MarketPage(QWidget):
    """Вкладка рынка: таблица активов слева, детали + график + кнопки сделок справа."""

    HEADERS = ["Тикер", "Название", "Цена", "Δ ход", "На руках", "Стоимость"]

    def __init__(self, win: "MainWindow", cls: AssetClass) -> None:
        super().__init__()
        self.win, self.cls, self.assets = win, cls, config.assets_of(cls)
        self.table = QTableWidget(len(self.assets), len(self.HEADERS))
        t = self.table
        t.setHorizontalHeaderLabels(self.HEADERS)
        t.verticalHeader().hide()
        t.verticalHeader().setDefaultSectionSize(22)
        t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        t.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        t.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        t.setShowGrid(False)
        hh = t.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        for i, w in enumerate((82, 76, 68, 56, 70, 80)):
            t.setColumnWidth(i, w)
        t.setFixedWidth(sum((82, 76, 68, 56, 70, 80)) + 8)
        t.setCurrentCell(0, 0)
        t.currentCellChanged.connect(lambda *_: self.update_detail())

        # --- правая панель ---
        self.title = _label("", "big")
        self.price = _label()
        self.held = _label()
        self.extra = _label("", "cyan")
        for lbl in (self.price, self.held):
            lbl.setTextFormat(Qt.TextFormat.RichText)
        for lbl in (self.held, self.extra):
            lbl.setWordWrap(True)
        self.spark = Sparkline()
        self.qty = QtyEdit("1")
        self.qty.setFixedWidth(70)
        self.qty.returnPressed.connect(lambda: win.trade("buy"))
        row1 = QHBoxLayout()
        row1.addWidget(_label("Кол-во:", "dim"))
        row1.addWidget(self.qty)
        row1.addWidget(_btn("[B] Купить", "buy", lambda: win.trade("buy")))
        row1.addWidget(_btn("[S] Продать", "sell", lambda: win.trade("sell")))
        row1.addStretch()
        row2 = QHBoxLayout()
        row2.addWidget(_label("Купить:", "dim"))
        for b in _qty_buttons(win, "buy"):
            row2.addWidget(b)
        row3 = QHBoxLayout()
        row3.addWidget(_label("Продать:", "dim"))
        for b in _qty_buttons(win, "sell"):
            row3.addWidget(b)

        right = QVBoxLayout()
        right.setSpacing(3)
        for w in (self.title, self.price, self.spark, self.held, self.extra):
            right.addWidget(w)
        right.addLayout(row1)
        right.addLayout(row2)
        right.addLayout(row3)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.addWidget(self.table)
        lay.addLayout(right, 1)

    # ------------------------------------------------------------------
    def selected(self) -> str:
        return self.assets[max(self.table.currentRow(), 0)].symbol

    def move(self, delta: int) -> None:
        row = min(max(self.table.currentRow() + delta, 0), len(self.assets) - 1)
        self.table.setCurrentCell(row, 0)

    def refresh(self) -> None:
        g = self.win.game
        self.table.blockSignals(True)
        for r, a in enumerate(self.assets):
            chg = market.change_pct(g.state, a.symbol)
            held = g.qty(a.symbol)
            cells = [a.symbol, a.name, fmt_price(g.price(a.symbol)), fmt_pct(chg),
                     fmt_qty(held) if held else "·", fmt_money(held * g.price(a.symbol)) if held else "·"]
            for c, text in enumerate(cells):
                it = QTableWidgetItem(text)
                it.setTextAlignment((Qt.AlignmentFlag.AlignLeft if c < 2 else Qt.AlignmentFlag.AlignRight)
                                    | Qt.AlignmentFlag.AlignVCenter)
                if c == 3:
                    it.setForeground(QColor(pct_color(chg)))
                elif c == 0:
                    it.setForeground(QColor(theme.AMBER if held else theme.CYAN))
                self.table.setItem(r, c, it)
        self.table.blockSignals(False)
        self.update_detail()

    def update_detail(self) -> None:
        g = self.win.game
        a = config.ASSET_BY_SYMBOL[self.selected()]
        chg = market.change_pct(g.state, a.symbol)
        held = g.qty(a.symbol)
        self.title.setText(f"{a.symbol} · {a.name}")
        self.price.setText(f"<b>{fmt_price(g.price(a.symbol))} $</b> "
                           f"<span style='color:{pct_color(chg)}'>{fmt_pct(chg)}</span>"
                           f" <span style='color:{theme.DIM}'>· куп {fmt_price(g.ask(a.symbol))} / прод {fmt_price(g.bid(a.symbol))}</span>")
        self.spark.set_values(g.state.history[a.symbol])
        self.held.setText(f"На руках: <b>{fmt_qty(held)} {a.unit}</b> ≈ {fmt_money(held * g.price(a.symbol))}"
                          f"  ·  можно купить: {fmt_qty(g.max_buy(a.symbol))}")
        if a.cls is AssetClass.REALTY:
            self.extra.setText(f"Аренда {fmt_money(a.rent * g.rent_multiplier())}/ход (×{g.rent_multiplier():.2f}), "
                               f"всего {fmt_money(g.rent_income())}/ход")
        else:
            self.extra.setText("")
        self.extra.setVisible(a.cls is AssetClass.REALTY)


class BankPage(QWidget):
    def __init__(self, win: "MainWindow") -> None:
        super().__init__()
        self.win = win
        self.info = _label()
        self.info.setTextFormat(Qt.TextFormat.RichText)
        self.hint = _label("Пустое поле — вся доступная сумма. Кредит: срок ограничен, при просрочке — дефолт и штраф.", "dim")
        self.hint.setWordWrap(True)
        self.amount = QtyEdit("")
        self.amount.setPlaceholderText("сумма, $")
        self.amount.setFixedWidth(130)
        self.amount.returnPressed.connect(lambda: win.bank_do("deposit"))

        fill = QHBoxLayout()
        fill.addWidget(_label("Сумма:", "dim"))
        fill.addWidget(self.amount)
        for t, p, k in (("25%", 0.25, "Z"), ("50%", 0.5, "X"), ("Все нал.", 1.0, "C")):
            fill.addWidget(_btn(f"{t} [{k}]", "", lambda _=False, p=p: win.fill_pct(p)))
        fill.addStretch()
        acts = QHBoxLayout()
        acts.addWidget(_btn("[D] Положить на вклад", "buy", lambda: win.bank_do("deposit")))
        acts.addWidget(_btn("[W] Снять", "", lambda: win.bank_do("withdraw")))
        acts.addWidget(_btn("[L] Взять кредит", "sell", lambda: win.bank_do("loan")))
        acts.addWidget(_btn("[R] Погасить", "buy", lambda: win.bank_do("repay")))
        acts.addStretch()

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.addWidget(_label("БАНК", "big"))
        lay.addWidget(self.info)
        lay.addSpacing(6)
        lay.addLayout(fill)
        lay.addLayout(acts)
        lay.addWidget(self.hint)
        lay.addStretch()

    def refresh(self) -> None:
        g, b = self.win.game, self.win.game.state.bank
        self.info.setText(
            f"Наличные: <b>{fmt_money(g.state.cash)}</b><br>"
            f"Вклад: <b style='color:{theme.UP}'>{fmt_money(b.deposit)}</b> "
            f"— ставка {g.deposit_rate() * 100:.2f}% за ход<br>"
            f"Кредит: <b style='color:{theme.DOWN}'>{fmt_money(b.loan)}</b> "
            f"— ставка {g.loan_rate() * 100:.2f}% за ход"
            + (f", до дефолта {b.loan_turns_left} х." if b.loan > 0 else "")
            + f"<br>Доступный лимит кредита: <b>{fmt_money(g.max_loan())}</b>")


class MainWindow(QMainWindow):
    def __init__(self, game: Game | None = None) -> None:
        super().__init__()
        self.game = game or Game()
        self.setWindowTitle("Коммерсант — Retro Edition")
        self.setFixedSize(WIN_W, WIN_H)

        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        v = QVBoxLayout(root)
        v.setContentsMargins(8, 8, 8, 8)
        v.setSpacing(6)

        v.addWidget(self._build_header())

        self.tabs = QTabWidget()
        self.tabs.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.pages: list[MarketPage] = []
        for cls in config.TAB_ORDER:
            page = MarketPage(self, cls)
            self.pages.append(page)
            self.tabs.addTab(page, TAB_TITLES[cls])
        self.bank_page = BankPage(self)
        self.tabs.addTab(self.bank_page, "[5] Банк")
        self.tabs.currentChanged.connect(lambda _: self.refresh())
        v.addWidget(self.tabs, 1)

        self.event_lbl = _label("", "event")
        self.event_lbl.setWordWrap(True)
        v.addWidget(self.event_lbl)
        self.news = NewsLog()
        self.news.setFixedHeight(92)
        v.addWidget(self.news)

        status = QHBoxLayout()
        self.msg = _label("", "msg")
        self.factors = _label("", "dim")
        self.factors.setAlignment(Qt.AlignmentFlag.AlignRight)
        status.addWidget(self.msg, 1)
        status.addWidget(self.factors, 1)
        v.addLayout(status)

        v.addLayout(self._build_buttons())
        self._build_shortcuts()
        self.refresh()

    # ----------------------------- построение -----------------------------
    def _build_header(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("panel")
        grid = QGridLayout(frame)
        grid.setContentsMargins(10, 4, 10, 4)
        grid.setVerticalSpacing(0)
        self.h: dict[str, QLabel] = {}
        for col, (key, title) in enumerate((("day", "ХОД"), ("cash", "НАЛИЧНЫЕ"), ("port", "ПОРТФЕЛЬ"),
                                            ("nw", "КАПИТАЛ"), ("goal", "ЦЕЛЬ"))):
            grid.addWidget(_label(title, "dim"), 0, col)
            self.h[key] = _label("", "value")
            grid.addWidget(self.h[key], 1, col)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        grid.addWidget(self.progress, 2, 0, 1, 5)
        return frame

    def _build_buttons(self) -> QHBoxLayout:
        row = QHBoxLayout()
        self.next_btn = _btn("[N] Следующий ход", "primary", self.next_turn, "N / Т / Ctrl+Enter")
        row.addWidget(self.next_btn, 2)
        row.addWidget(_btn("[Ctrl+S] Сохранить", "", self.save))
        row.addWidget(_btn("[Ctrl+L] Загрузить", "", self.load))
        row.addWidget(_btn("[Ctrl+N] Новая игра", "", self.new_game))
        row.addWidget(_btn("[Ctrl+R] Рекорды", "", self.show_scores))
        return row

    def _action(self, keys: list[str], slot) -> None:
        act = QAction(self)
        act.setShortcuts([QKeySequence(k) for k in keys])
        act.triggered.connect(lambda _=False: slot())
        self.addAction(act)

    def _bi(self, key: str, shift: bool = False) -> list[str]:
        """Латинская + русская клавиши (с опциональным Shift)."""
        pre = "Shift+" if shift else ""
        return [pre + key, pre + RU[key]]

    def _build_shortcuts(self) -> None:
        for i in range(5):
            self._action([str(i + 1)], lambda i=i: self.tabs.setCurrentIndex(i))
        self._action(["Up"], lambda: self._move(-1))
        self._action(["Down"], lambda: self._move(1))
        self._action(["Escape"], self._clear_focus)
        self._action(self._bi("Q"), self.focus_qty)
        self._action(self._bi("N") + ["Ctrl+Return", "Ctrl+Enter"], self.next_turn)
        self._action(self._bi("B"), lambda: self.trade("buy"))
        self._action(self._bi("S"), lambda: self.trade("sell"))
        for key, p in (("Z", 0.25), ("X", 0.5), ("C", 1.0)):
            self._action(self._bi(key), lambda p=p: self.fill_pct(p) if self._on_bank() else self.trade_pct("buy", p))
            self._action(self._bi(key, True), lambda p=p: self.trade_pct("sell", p))
        for key, kind in (("D", "deposit"), ("W", "withdraw"), ("L", "loan"), ("R", "repay")):
            self._action(self._bi(key), lambda kind=kind: self._on_bank() and self.bank_do(kind))
        self._action(["Ctrl+S"], self.save)
        self._action(["Ctrl+L"], self.load)
        self._action(["Ctrl+N"], self.new_game)
        self._action(["Ctrl+R"], self.show_scores)

    # ------------------------------ состояние ------------------------------
    def _on_bank(self) -> bool:
        return self.tabs.currentIndex() == BANK_TAB

    def _page(self) -> MarketPage | None:
        i = self.tabs.currentIndex()
        return self.pages[i] if i < len(self.pages) else None

    def _move(self, delta: int) -> None:
        if (p := self._page()):
            p.move(delta)

    def _clear_focus(self) -> None:
        if (w := QApplication.focusWidget()):
            w.clearFocus()

    def focus_qty(self) -> None:
        field = self.bank_page.amount if self._on_bank() else self._page().qty
        field.setFocus()
        field.selectAll()

    def say(self, text: str, ok: bool = True) -> None:
        self.msg.setStyleSheet(f"color: {theme.UP if ok else theme.DOWN};")
        self.msg.setText(text)

    def refresh(self) -> None:
        g, s = self.game, self.game.state
        nw = g.net_worth()
        self.h["day"].setText(f"{min(s.day, s.max_days)} / {s.max_days}")
        self.h["cash"].setText(fmt_money(s.cash))
        self.h["port"].setText(fmt_money(g.portfolio_value()))
        self.h["nw"].setText(fmt_money(nw))
        self.h["nw"].setStyleSheet(f"color: {theme.UP if nw >= s.start_cash else theme.DOWN};")
        self.h["cash"].setStyleSheet(f"color: {theme.DOWN if s.cash < 0 else theme.TEXT};")
        status = {GameStatus.PLAYING: fmt_money(s.target), GameStatus.WON: "ПОБЕДА",
                  GameStatus.LOST_BANKRUPT: "БАНКРОТ", GameStatus.LOST_TIMEOUT: "ВРЕМЯ ВЫШЛО"}[s.status]
        self.h["goal"].setText(status)
        self.progress.setValue(int(max(0.0, min(nw / s.target, 1.0)) * 100))
        self.progress.setFormat(f"{max(nw, 0) / s.target * 100:.1f}% цели")
        self.event_lbl.setText(s.current_event or "Новая игра — удачи на бирже!")
        self.news.set_lines(s.log)
        self.next_btn.setEnabled(s.status is GameStatus.PLAYING)
        mods = [f"{self._mod_label(m)} ({m.turns_left})" for m in s.modifiers]
        self.factors.setText("Факторы: " + ", ".join(mods[:3]) if mods else "")
        if (p := self._page()):
            p.refresh()
        elif self._on_bank():
            self.bank_page.refresh()

    @staticmethod
    def _mod_label(m) -> str:
        names = {"ALL": "рынок", "commodity": "сырьё", "stock": "акции", "crypto": "крипта", "realty": "недвижим."}
        kind = {ModKind.DRIFT: "", ModKind.RENT: "аренда ", ModKind.RATE: "ставки "}[m.kind]
        return f"{kind}{names.get(m.target, m.target)} {m.value * 100:+.1f}%".replace("-", "−")

    # ------------------------------- действия -------------------------------
    @staticmethod
    def _parse(text: str) -> float | None:
        text = text.strip().replace(",", ".").replace(" ", "")
        try:
            return float(text) if text else None
        except ValueError:
            return None

    def _run(self, fn, ok_text) -> None:
        try:
            self.say(ok_text(fn()))
        except TradeError as exc:
            self.say(str(exc), ok=False)
        self.refresh()

    def trade(self, side: str, qty: float | None = None) -> None:
        page = self._page()
        if page is None:
            return
        qty = self._parse(page.qty.text()) if qty is None else qty
        if not qty or qty <= 0:
            self.say("Введите количество (число больше 0).", ok=False)
            return
        sym = page.selected()
        a = config.ASSET_BY_SYMBOL[sym]
        if side == "buy":
            self._run(lambda: self.game.buy(sym, qty),
                      lambda c: f"Куплено {fmt_qty(qty)} {a.unit} {sym} за {fmt_money(c)}")
        else:
            self._run(lambda: self.game.sell(sym, qty),
                      lambda c: f"Продано {fmt_qty(qty)} {a.unit} {sym} за {fmt_money(c)}")

    def trade_pct(self, side: str, pct: float) -> None:
        page = self._page()
        if page is None:
            return
        qty = self.game.qty_for_pct(page.selected(), side, pct)
        if qty <= 0:
            self.say("Нечего покупать — не хватает денег." if side == "buy" else "Нечего продавать.", ok=False)
            return
        self.trade(side, qty)

    def fill_pct(self, pct: float) -> None:
        if self._on_bank():
            cash = max(self.game.state.cash, 0.0)
            self.bank_page.amount.setText(str(int(cash * pct)))

    def bank_do(self, kind: str) -> None:
        g, b = self.game, self.game.state.bank
        amount = self._parse(self.bank_page.amount.text())
        defaults = {"deposit": max(g.state.cash, 0.0), "withdraw": b.deposit, "loan": g.max_loan(),
                    "repay": min(b.loan, max(g.state.cash, 0.0))}
        amount = defaults[kind] if amount is None else amount
        amount = round(amount, 2)
        if amount <= 0:
            self.say("Нечего делать: сумма равна нулю.", ok=False)
            return
        ops = {
            "deposit": (lambda: g.bank_deposit(amount), f"На вклад внесено {fmt_money(amount)}"),
            "withdraw": (lambda: g.bank_withdraw(amount), f"Со вклада снято {fmt_money(amount)}"),
            "loan": (lambda: g.take_loan(amount), f"Кредит получен: {fmt_money(amount)}"),
            "repay": (lambda: g.repay_loan(amount), f"Кредит погашен на {fmt_money(amount)}"),
        }
        fn, text = ops[kind]
        self._run(fn, lambda _: text)
        self.bank_page.amount.clear()

    def next_turn(self) -> None:
        if self.game.state.status is not GameStatus.PLAYING:
            return
        report = self.game.next_turn()
        parts = []
        if report.rent:
            parts.append(f"аренда +{fmt_money(report.rent)}")
        if report.deposit_interest:
            parts.append(f"вклад +{fmt_money(report.deposit_interest)}")
        self.say(f"Ход {report.day}" + (": " + ", ".join(parts) if parts else ""))
        self.refresh()
        if report.status is not GameStatus.PLAYING:
            self._game_over()

    def _game_over(self) -> None:
        s = self.game.state
        GameOverDialog(s.status, self.game.net_worth(), min(s.day, s.max_days), self).exec()
        storage.add_score(self.game)
        self.say("Результат записан в таблицу рекордов. Ctrl+N — новая игра.")
        self.show_scores()

    def _confirm(self, text: str) -> bool:
        box = QMessageBox(QMessageBox.Icon.Question, "Подтверждение", text, parent=self)
        yes = box.addButton("Да (Enter)", QMessageBox.ButtonRole.YesRole)
        box.addButton("Нет (Esc)", QMessageBox.ButtonRole.NoRole)
        box.setDefaultButton(yes)
        box.exec()
        return box.clickedButton() is yes

    def _in_progress(self) -> bool:
        return self.game.state.status is GameStatus.PLAYING and self.game.state.day > 1

    def new_game(self) -> None:
        dlg = NewGameDialog(self)
        if dlg.exec() != dlg.DialogCode.Accepted:
            return
        if self._in_progress() and not self._confirm("Текущая партия будет потеряна. Начать новую?"):
            return
        diff, seed = dlg.result_values()
        self.game = Game(diff, seed)
        self.say("Новая игра начата.")
        self.refresh()

    def save(self) -> None:
        try:
            storage.save_game(self.game)
            self.say(f"Игра сохранена: {storage.SAVE_FILE.name}")
        except OSError as exc:
            self.say(f"Не удалось сохранить: {exc}", ok=False)

    def load(self) -> None:
        if self._in_progress() and not self._confirm("Загрузить сохранение? Текущий прогресс будет потерян."):
            return
        try:
            self.game = storage.load_game()
        except FileNotFoundError:
            self.say("Сохранение не найдено — сначала нажмите Ctrl+S.", ok=False)
            return
        except ValueError as exc:
            self.say(str(exc), ok=False)
            return
        self.say("Игра загружена.")
        self.refresh()

    def show_scores(self) -> None:
        HighscoresDialog(storage.load_scores(), self).exec()
