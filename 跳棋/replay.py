"""
跳棋 — 棋谱保存与加载
"""

import json
import os
from datetime import datetime
import config as cfg


def _save_dir(name: str) -> str:
    return os.path.join(cfg.REPLAY_DIR, name)


def save_replay(name: str, state_dict: dict, mode: str, difficulty: int,
                move_history: list):
    """保存棋谱到 replays/{name}/replay.json"""
    d = _save_dir(name)
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, "replay.json")
    data = {
        "name": name,
        "saved_at": datetime.now().isoformat(),
        "mode": mode,
        "difficulty": difficulty,
        "state": state_dict,
        "move_history": move_history,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path


def load_replay(name: str) -> dict | None:
    """加载 replays/{name}/replay.json"""
    path = os.path.join(_save_dir(name), "replay.json")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def list_replays() -> list[dict]:
    """列出所有存档棋谱的摘要。"""
    os.makedirs(cfg.REPLAY_DIR, exist_ok=True)
    replays = []
    try:
        items = sorted(os.listdir(cfg.REPLAY_DIR), reverse=True)
    except FileNotFoundError:
        return replays
    for name in items:
        subdir = os.path.join(cfg.REPLAY_DIR, name)
        if not os.path.isdir(subdir):
            continue
        rp = os.path.join(subdir, "replay.json")
        try:
            with open(rp, "r", encoding="utf-8") as f:
                d = json.load(f)
            replays.append({
                "game_id": name,
                "name": d.get("name", name),
                "saved_at": d.get("saved_at", ""),
                "mode": d.get("mode", ""),
            })
        except Exception:
            pass
    return replays
