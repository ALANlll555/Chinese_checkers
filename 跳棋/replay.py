"""
跳棋 — 棋谱保存与加载
"""

import json
import os
from datetime import datetime
import config as cfg


def save_replay(game_id: str, state_dict: dict, mode: str, difficulty: int):
    """保存棋谱到 JSON 文件。"""
    os.makedirs(cfg.REPLAY_DIR, exist_ok=True)
    path = os.path.join(cfg.REPLAY_DIR, f"{game_id}.json")

    data = {
        "game_id": game_id,
        "saved_at": datetime.now().isoformat(),
        "mode": mode,
        "difficulty": difficulty,
        "state": state_dict,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path


def load_replay(game_id: str) -> dict | None:
    """加载棋谱。"""
    path = os.path.join(cfg.REPLAY_DIR, f"{game_id}.json")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def list_replays() -> list[dict]:
    """列出所有存档棋谱的摘要。"""
    os.makedirs(cfg.REPLAY_DIR, exist_ok=True)
    replays = []
    for fn in sorted(os.listdir(cfg.REPLAY_DIR), reverse=True):
        if fn.endswith(".json"):
            path = os.path.join(cfg.REPLAY_DIR, fn)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    d = json.load(f)
                replays.append({
                    "game_id": d.get("game_id", fn[:-5]),
                    "saved_at": d.get("saved_at", ""),
                    "mode": d.get("mode", ""),
                })
            except Exception:
                pass
    return replays
