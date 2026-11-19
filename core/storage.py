"""Сохранение/загрузка партии и таблица рекордов (локальный JSON)."""
from __future__ import annotations

import json
import time
from dataclasses import asdict
from pathlib import Path

from .engine import Game
from .models import BankAccount, GameState, GameStatus, ModKind, Modifier

SAVES_DIR = Path(__file__).resolve().parent.parent / "saves"
SAVE_FILE = SAVES_DIR / "savegame.json"
SCORES_FILE = SAVES_DIR / "highscores.json"
SAVE_VERSION = 1
MAX_SCORES = 10


def state_to_dict(state: GameState) -> dict:
    d = asdict(state)
    d["status"] = state.status.value
    for m in d["modifiers"]:
        m["kind"] = m["kind"].value if hasattr(m["kind"], "value") else m["kind"]
    return {"version": SAVE_VERSION, "state": d}


def state_from_dict(data: dict) -> GameState:
    if data.get("version") != SAVE_VERSION:
        raise ValueError("Неподдерживаемая версия сохранения")
    d = dict(data["state"])
    d["status"] = GameStatus(d["status"])
    d["bank"] = BankAccount(**d["bank"])
    d["modifiers"] = [Modifier(ModKind(m["kind"]), m["target"], m["value"], m["turns_left"], m.get("label", ""))
                      for m in d["modifiers"]]
    return GameState(**d)


def save_game(game: Game, path: Path = SAVE_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state_to_dict(game.state), ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def load_game(path: Path = SAVE_FILE) -> Game:
    """Бросает FileNotFoundError / ValueError при отсутствии или повреждении файла."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return Game(state=state_from_dict(data))
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ValueError(f"Файл сохранения повреждён: {exc}") from exc


def load_scores(path: Path = SCORES_FILE) -> list[dict]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def add_score(game: Game, name: str = "Игрок", path: Path = SCORES_FILE) -> list[dict]:
    """Добавляет результат партии и возвращает обновлённый топ-10."""
    entry = {**game.score(), "name": name, "date": time.strftime("%Y-%m-%d %H:%M")}
    scores = sorted(load_scores(path) + [entry], key=lambda e: e["net_worth"], reverse=True)[:MAX_SCORES]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(scores, ensure_ascii=False, indent=1), encoding="utf-8")
    return scores
