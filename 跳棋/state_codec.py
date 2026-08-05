"""Conversion between BoardState and persisted JSON snapshots."""

from __future__ import annotations

from board import BoardState
import config as cfg


def state_from_dict(data: dict) -> BoardState:
    active = [int(pid) for pid in data.get("active_players", [0, 3])]
    state = BoardState(active)
    state.current_player = int(data.get("current_player", active[0]))
    state.board = [[0] * cfg.BOARD_COLS for _ in range(cfg.BOARD_ROWS)]
    state._pieces = {pid: set() for pid in range(6)}

    for raw_pid, positions in (data.get("pieces") or {}).items():
        pid = int(raw_pid)
        for raw_pos in positions:
            pos = (int(raw_pos[0]), int(raw_pos[1]))
            state._pieces[pid].add(pos)
            state.board[pos[0]][pos[1]] = pid + 1

    state.move_history = []
    for item in data.get("move_history", []):
        if len(item) == 3 and isinstance(item[0], (list, tuple)):
            (fr, fc), (tr, tc), pid = item
        else:
            fr, fc, tr, tc, pid = item
        state.move_history.append((int(fr), int(fc), int(tr), int(tc), int(pid)))

    state.scores = {pid: 0 for pid in range(6)}
    for raw_pid, value in (data.get("scores") or {}).items():
        state.scores[int(raw_pid)] = int(value)
    for pid in active:
        state._update_score(pid)
    return state
