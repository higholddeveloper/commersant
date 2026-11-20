"""Ретро-палитра терминала 90-х и QSS-тема."""
from __future__ import annotations

BG = "#0B1020"
PANEL = "#111A33"
PANEL_HI = "#1A2750"
BORDER = "#2F4A8A"
TEXT = "#C8D3F5"
DIM = "#6F7FB0"
UP = "#3DFF7A"
DOWN = "#FF4D5E"
AMBER = "#FFB000"
CYAN = "#4DD0FF"
SELECT_BG = "#4A3A00"   # подсветка выбранной строки
BAD_BG = "#2B0C16"      # фон сообщений о неприятностях
GOOD_BG = "#0A2B16"     # фон приятных сообщений


def tone_color(tone: int) -> str:
    return UP if tone > 0 else DOWN if tone < 0 else AMBER


def tone_bg(tone: int) -> str:
    return GOOD_BG if tone > 0 else BAD_BG if tone < 0 else PANEL

FONT_FAMILY = "Consolas"
FONT_SIZE = 10

QSS = f"""
* {{ font-family: "{FONT_FAMILY}", "Courier New", monospace; font-size: {FONT_SIZE}pt; color: {TEXT}; }}
QMainWindow, QDialog, QWidget#root {{ background: {BG}; }}
QFrame#panel {{ background: {PANEL}; border: 1px solid {BORDER}; }}
QLabel {{ background: transparent; }}
QLabel#dim {{ color: {DIM}; }}
QLabel#amber {{ color: {AMBER}; }}
QLabel#cyan {{ color: {CYAN}; }}
QLabel#big {{ font-size: 14pt; font-weight: bold; color: {AMBER}; }}
QLabel#value {{ font-size: 12pt; font-weight: bold; }}
QLabel#event {{ color: {AMBER}; background: {PANEL}; border: 1px solid {AMBER}; padding: 3px 6px; }}
QLabel#msg {{ color: {CYAN}; }}

QTabWidget::pane {{ border: 1px solid {BORDER}; background: {PANEL}; top: -1px; }}
QTabBar::tab {{ background: {BG}; color: {DIM}; border: 1px solid {BORDER}; padding: 5px 7px; margin-right: 2px; }}
QTabBar::tab:selected {{ background: {PANEL_HI}; color: {AMBER}; border-bottom-color: {PANEL_HI}; }}
QTabBar::tab:hover:!selected {{ color: {TEXT}; }}

QPushButton {{ background: {PANEL_HI}; border: 1px solid {BORDER}; padding: 4px 8px; color: {TEXT}; }}
QPushButton:hover {{ border-color: {AMBER}; color: {AMBER}; }}
QPushButton:pressed {{ background: {BORDER}; }}
QPushButton:disabled {{ color: {DIM}; border-color: {PANEL_HI}; }}
QPushButton#buy {{ color: {UP}; border-color: {UP}; }}
QPushButton#sell {{ color: {DOWN}; border-color: {DOWN}; }}
QPushButton#period {{ padding: 3px 8px; }}
QPushButton#small {{ padding: 2px 6px; }}
QPushButton#period:checked {{ background: {AMBER}; color: {BG}; border-color: {AMBER}; font-weight: bold; }}
QPushButton#primary {{ color: {AMBER}; border: 2px solid {AMBER}; font-weight: bold; }}
QPushButton#primary:hover {{ background: {AMBER}; color: {BG}; }}
QPushButton#buy:hover {{ background: {UP}; color: {BG}; }}
QPushButton#sell:hover {{ background: {DOWN}; color: {BG}; }}

QLineEdit, QComboBox {{ background: {BG}; border: 1px solid {BORDER}; padding: 4px; selection-background-color: {AMBER}; selection-color: {BG}; }}
QLineEdit:focus, QComboBox:focus {{ border-color: {AMBER}; }}
QComboBox QAbstractItemView {{ background: {BG}; border: 1px solid {BORDER}; selection-background-color: {PANEL_HI}; }}

QTableWidget {{ background: {BG}; gridline-color: {PANEL_HI}; border: 1px solid {BORDER};
               selection-background-color: {PANEL_HI}; selection-color: {AMBER}; outline: 0; }}
QHeaderView::section {{ background: {PANEL}; color: {DIM}; border: none; border-bottom: 1px solid {BORDER}; padding: 3px; }}
QPlainTextEdit, QTextEdit {{ background: {BG}; border: 1px solid {BORDER}; }}
QProgressBar {{ background: {BG}; border: 1px solid {BORDER}; text-align: center; height: 12px; color: {TEXT}; }}
QProgressBar::chunk {{ background: {AMBER}; }}
QScrollBar:vertical {{ background: {BG}; width: 10px; }}
QScrollBar::handle:vertical {{ background: {BORDER}; min-height: 20px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QMessageBox {{ background: {BG}; }}
"""
