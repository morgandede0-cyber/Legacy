"""Shared PC/mobile display preference for Altherya.

Kept independent from main.py so feature modules can avoid expensive renders on mobile
without importing the bot entrypoint (and creating circular imports).
"""
from __future__ import annotations
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
FILE = BASE / "data" / "display_modes.json"
_modes: dict[str, str] = {}
_loaded_mtime: float | None = None


def _reload(force: bool = False) -> None:
    global _modes, _loaded_mtime
    try:
        mtime = FILE.stat().st_mtime if FILE.exists() else None
        if not force and mtime == _loaded_mtime:
            return
        raw = json.loads(FILE.read_text(encoding="utf-8")) if FILE.exists() else {}
        _modes = {str(k): ("mobile" if str(v) == "mobile" else "pc") for k, v in raw.items()}
        _loaded_mtime = mtime
    except (OSError, ValueError, TypeError):
        _modes = {}


def get(user_id: int) -> str:
    _reload()
    return _modes.get(str(int(user_id)), "pc")


def is_mobile(user_id: int) -> bool:
    return get(user_id) == "mobile"


def set_mode(user_id: int, mode: str) -> str:
    global _loaded_mtime
    _reload()
    mode = "mobile" if mode == "mobile" else "pc"
    _modes[str(int(user_id))] = mode
    FILE.parent.mkdir(parents=True, exist_ok=True)
    FILE.write_text(json.dumps(_modes, indent=2), encoding="utf-8")
    try:
        _loaded_mtime = FILE.stat().st_mtime
    except OSError:
        _loaded_mtime = None
    return mode
