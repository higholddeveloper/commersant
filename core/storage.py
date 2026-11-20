"""Сохранение/загрузка партии (именованные слоты) и таблица рекордов (локальный JSON)."""
from __future__ import annotations

import json
import os
import re
import sys
import time
from dataclasses import asdict
from pathlib import Path

from .engine import Game
from .models import BankAccount, GameState, GameStatus, ModKind, Modifier, PatternRun


def _saves_dir() -> Path:
    """Рядом с проектом; в собранном .exe — рядом с игрой, а если там нельзя писать — в %LOCALAPPDATA%."""
    if not getattr(sys, "frozen", False):
        return Path(__file__).resolve().parent.parent / "saves"
    local = Path(sys.executable).resolve().parent / "saves"
    try:
        local.mkdir(parents=True, exist_ok=True)
        probe = local / ".w"
        probe.write_text("x")
        probe.unlink()
        return local
    except OSError:
        return Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Commersant" / "saves"


SAVES_DIR = _saves_dir()
SAVE_FILE = SAVES_DIR / "savegame.json"        # старое имя единственного слота (читается как обычный слот)
SCORES_FILE = SAVES_DIR / "highscores.json"
SETTINGS_FILE = SAVES_DIR / "settings.json"
SAVE_VERSION = 2
SUPPORTED_VERSIONS = (1, 2)
MAX_SCORES = 15
_RESERVED = {"highscores", "settings"}


# ------------------------------- слоты -------------------------------
def slot_name(text: str) -> str:
    """Безопасное имя файла сохранения из произвольного текста."""
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", text).strip().strip(".")
    return name[:40].strip()


def slot_path(name: str, directory: Path | None = None) -> Path:
    clean = slot_name(name)
    if not clean or clean.lower() in _RESERVED:
        raise ValueError("Недопустимое имя сохранения")
    return (directory or SAVES_DIR) / f"{clean}.json"


def state_to_dict(state: GameState) -> dict:
    d = asdict(state)
    d["status"] = state.status.value
    for m in d["modifiers"]:
        m["kind"] = m["kind"].value if hasattr(m["kind"], "value") else m["kind"]
    return {"version": SAVE_VERSION, "state": d}


def state_from_dict(data: dict) -> GameState:
    if data.get("version") not in SUPPORTED_VERSIONS:
        raise ValueError("Неподдерживаемая версия сохранения")
    d = dict(data["state"])
    d["status"] = GameStatus(d["status"])
    d["bank"] = BankAccount(**d["bank"])
    d["modifiers"] = [Modifier(ModKind(m["kind"]), m["target"], m["value"], m["turns_left"], m.get("label", ""))
                      for m in d["modifiers"]]
    d["patterns"] = {k: PatternRun(**v) for k, v in d.get("patterns", {}).items()}
    known = set(GameState.__dataclass_fields__)
    return GameState(**{k: v for k, v in d.items() if k in known})


def save_game(game: Game, path: Path | None = None) -> Path:
    """Сохраняет партию. Без пути — в слот с именем игрока (или последний использованный слот)."""
    if path is None:
        path = slot_path(game.state.slot or game.state.player)
    path.parent.mkdir(parents=True, exist_ok=True)
    game.state.slot = path.stem
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state_to_dict(game.state), ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)
    return path


def load_game(path: Path = SAVE_FILE) -> Game:
    """Бросает FileNotFoundError / ValueError при отсутствии или повреждении файла."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        game = Game(state=state_from_dict(data))
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ValueError(f"Файл сохранения повреждён: {exc}") from exc
    game.state.slot = path.stem
    return game


def list_saves(directory: Path | None = None) -> list[dict]:
    """Сохранения в папке: новые первыми. Повреждённые файлы пропускаются."""
    directory = directory or SAVES_DIR
    out = []
    for p in directory.glob("*.json") if directory.exists() else []:
        if p.stem.lower() in _RESERVED:
            continue
        try:
            st = json.loads(p.read_text(encoding="utf-8"))["state"]
            out.append({"path": p, "slot": p.stem, "player": st.get("player", "Игрок"), "day": st["day"],
                        "max_days": st.get("max_days", 0), "cash": st["cash"], "mtime": p.stat().st_mtime,
                        "status": st.get("status", "playing")})
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return sorted(out, key=lambda e: e["mtime"], reverse=True)


# ------------------------------- рекорды -------------------------------
def load_scores(path: Path = SCORES_FILE) -> list[dict]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def add_score(game: Game, name: str | None = None, path: Path = SCORES_FILE) -> list[dict]:
    """Добавляет результат партии и возвращает обновлённый топ."""
    entry = {**game.score(), "date": time.strftime("%Y-%m-%d %H:%M")}
    if name:
        entry["name"] = name
    scores = sorted(load_scores(path) + [entry], key=lambda e: e["net_worth"], reverse=True)[:MAX_SCORES]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(scores, ensure_ascii=False, indent=1), encoding="utf-8")
    return scores


# ------------------------------- настройки -------------------------------
DEFAULT_SETTINGS = {"realtime": False, "speed": 3.0, "period": 30, "last_name": ""}


def load_settings(path: Path = SETTINGS_FILE) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        data = {}
    return {**DEFAULT_SETTINGS, **{k: v for k, v in data.items() if k in DEFAULT_SETTINGS}}


def save_settings(settings: dict, path: Path = SETTINGS_FILE) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(settings, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass  # настройки не критичны
