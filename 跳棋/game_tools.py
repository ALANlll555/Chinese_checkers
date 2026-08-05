"""Shared read-only game data and calculation tools for DeepSeek and MCP."""

from __future__ import annotations

import time
from typing import Any, Callable

from ai import evaluate_components
from board import (
    BoardState, GOAL_SETS, HOME_SETS, VALID_HOLES, NEIGHBORS,
    _DIRECTION_MAP, _hex_step,
)
import config as cfg

Move = tuple[tuple[int, int], tuple[int, int]]


FEATURE_SPECS = {
    "goal_assignment_distance": {
        "label": "全体目标距离",
        "better": "lower",
        "weight": cfg.WEIGHT_GOAL_ASSIGNMENT,
        "meaning": "六颗棋分别进入不同目标孔所需的最低总距离",
    },
    "last_piece_distance": {
        "label": "最慢棋距离",
        "better": "lower",
        "weight": cfg.WEIGHT_LAST_PIECE,
        "meaning": "当前最落后棋子距离其分配目标的距离",
    },
    "forward_jump_value": {
        "label": "向前连跳机会",
        "better": "higher",
        "weight": cfg.WEIGHT_FORWARD_JUMP,
        "meaning": "现有棋子可通过合法连跳获得的有效前进价值",
    },
    "ladder_potential": {
        "label": "梯子潜力",
        "better": "higher",
        "weight": cfg.WEIGHT_LADDER_POTENTIAL,
        "meaning": "当前占位可形成后续连续跳跃通道的潜力",
    },
    "home_delay": {
        "label": "起始区滞留",
        "better": "lower",
        "weight": cfg.WEIGHT_HOME_DELAY,
        "meaning": "棋子仍滞留起始区所形成的延迟惩罚",
    },
}


def _coach_player_id(game: dict, player_id: int | None = None) -> int:
    state: BoardState = game["state"]
    if game.get("mode") == "pve" and 0 in state.active_players:
        # User-facing coaching is locked to the human side in PVE.  An LLM may
        # not silently switch the recommendation to an opponent by supplying
        # its own player_id.  Opponent analysis must use a dedicated future UI.
        pid = 0
    elif player_id is not None:
        pid = int(player_id)
    else:
        pid = state.current_player
    if pid not in state.active_players:
        raise ValueError(f"player {pid} is not active")
    return pid


def state_token(state: BoardState) -> str:
    """Small deterministic token shared with the browser overlay guard."""
    parts = [str(len(state.move_history)), str(state.current_player)]
    for pid in sorted(state.active_players):
        positions = ";".join(f"{r},{c}" for r, c in sorted(state.get_player_pieces(pid)))
        parts.append(f"{pid}:{positions}")
    return "|".join(parts)


def _move_invariants(state: BoardState, move: Move, player_id: int) -> dict:
    source, target = move
    checks = {
        "source_valid_hole": source in VALID_HOLES,
        "target_valid_hole": target in VALID_HOLES,
        "source_owned_by_player": False,
        "target_empty": False,
        "legal_for_player": False,
    }
    if checks["source_valid_hole"]:
        checks["source_owned_by_player"] = state.get_piece(source) == player_id + 1
    if checks["target_valid_hole"]:
        checks["target_empty"] = state.get_piece(target) == 0
    if checks["source_owned_by_player"] and checks["target_empty"]:
        checks["legal_for_player"] = move in set(state.get_valid_moves(player_id))
    return {
        "valid": all(checks.values()),
        "checks": checks,
        "player_id": int(player_id),
        "source_owner": state.get_piece(source) - 1 if source in VALID_HOLES and state.get_piece(source) else None,
    }


def _feature_cards(components: dict) -> list[dict]:
    cards = []
    for key, spec in FEATURE_SPECS.items():
        cards.append({
            "key": key,
            "label": spec["label"],
            "value": round(float(components.get(key, 0.0)), 3),
            "better": spec["better"],
            "meaning": spec["meaning"],
            "weight": float(spec["weight"]),
        })
    return cards


def _feature_changes(before: dict, after: dict) -> list[dict]:
    changes = []
    for key, spec in FEATURE_SPECS.items():
        old = float(before.get(key, 0.0))
        new = float(after.get(key, 0.0))
        delta = new - old
        score_effect = delta * float(spec["weight"])
        if score_effect > 1e-7:
            impact = "positive"
        elif score_effect < -1e-7:
            impact = "negative"
        else:
            impact = "neutral"
        direction = "不变"
        if delta > 1e-7:
            direction = "上升"
        elif delta < -1e-7:
            direction = "下降"
        changes.append({
            "key": key,
            "label": spec["label"],
            "before": round(old, 3),
            "after": round(new, 3),
            "delta": round(delta, 3),
            "direction": direction,
            "score_effect": round(score_effect, 3),
            "impact": impact,
            "meaning": spec["meaning"],
        })
    return changes


def _change_sentence(change: dict) -> str:
    amount = abs(float(change["delta"]))
    amount_text = str(int(amount)) if amount.is_integer() else f"{amount:.2f}"
    if change["direction"] == "不变":
        return f"{change['label']}不变"
    result = "有利" if change["impact"] == "positive" else "代价"
    return f"{change['label']}{change['direction']}{amount_text}（{result} {abs(change['score_effect']):.1f}）"


def _candidate_payload(
    state: BoardState,
    move: Move,
    *,
    player_id: int,
    before: dict,
    rank: int,
) -> dict:
    validation = _move_invariants(state, move, player_id)
    if not validation["valid"]:
        raise ValueError(f"candidate invariant failed: {validation['checks']}")
    after = evaluate_components(state.apply_move(move), player_id)
    changes = _feature_changes(before, after)
    positives = sorted(
        (item for item in changes if item["impact"] == "positive"),
        key=lambda item: -abs(item["score_effect"]),
    )
    negatives = sorted(
        (item for item in changes if item["impact"] == "negative"),
        key=lambda item: -abs(item["score_effect"]),
    )
    reason = "；".join(_change_sentence(item) for item in positives[:2])
    if not reason:
        reason = "五项评价总体保持稳定"
    tradeoff = _change_sentence(negatives[0]) if negatives else "没有明显的五项特征代价"
    detail = _move_detail(
        state,
        move,
        player_id=player_id,
        rank=rank,
        score=after["score"],
        components=after,
    )
    return {
        "rank": int(rank),
        "move": _move_to_json(move),
        "move_detail": detail,
        "score": float(after["score"]),
        "score_delta": float(after["score"] - before["score"]),
        "components": after,
        "feature_changes": changes,
        "reason": reason,
        "tradeoff": tradeoff,
        "verified": True,
        "validation": validation,
        "evidence": [
            _change_sentence(item)
            for item in sorted(changes, key=lambda item: -abs(item["score_effect"]))
            if abs(item["score_effect"]) > 1e-7
        ][:3],
    }


def _position_phase(state: BoardState, pid: int) -> dict:
    pieces = set(state.get_player_pieces(pid))
    home_count = len(pieces & HOME_SETS[pid])
    goal_count = len(pieces & GOAL_SETS[pid])
    move_count = len(state.move_history)
    if goal_count >= max(2, cfg.PIECES_PER_PLAYER // 2):
        return {
            "key": "endgame",
            "label": "收官",
            "reason": f"已有 {goal_count} 颗棋进入目标区",
        }
    if move_count < len(state.active_players) * 5 or home_count >= cfg.PIECES_PER_PLAYER - 2:
        return {
            "key": "opening",
            "label": "开局",
            "reason": f"仍有 {home_count} 颗棋位于起始区",
        }
    return {
        "key": "midgame",
        "label": "中局",
        "reason": "主要任务是延续跳跃通道并照顾落后棋",
    }


def _diagnostics(state: BoardState, pid: int, components: dict) -> list[dict]:
    pieces = set(state.get_player_pieces(pid))
    home_count = len(pieces & HOME_SETS[pid])
    goal_count = len(pieces & GOAL_SETS[pid])
    average = components["goal_assignment_distance"] / max(1, len(pieces))
    items = []
    if components["last_piece_distance"] > average + 1.5:
        items.append({
            "level": "warning",
            "title": "最慢棋正在拖长完赛时间",
            "evidence": (
                f"最慢棋距离 {components['last_piece_distance']:.1f}，"
                f"高于单棋平均 {average:.1f}"
            ),
            "action": "优先比较能降低最慢棋距离的候选",
        })
    if home_count:
        items.append({
            "level": "warning" if home_count >= 3 else "info",
            "title": "起始区仍有棋子需要释放",
            "evidence": f"当前仍有 {home_count} 颗棋留在起始区",
            "action": "避免只推进前锋而留下尾棋",
        })
    if components["forward_jump_value"] > 0:
        items.append({
            "level": "opportunity",
            "title": "当前存在可利用的向前连跳",
            "evidence": f"向前连跳价值为 {components['forward_jump_value']:.1f}",
            "action": "查看候选路径是否能保留下一轮跳板",
        })
    if components["ladder_potential"] > 0:
        items.append({
            "level": "opportunity",
            "title": "棋盘上已有梯子结构",
            "evidence": f"梯子潜力为 {components['ladder_potential']:.1f}",
            "action": "优先选择不会破坏关键跳板的走法",
        })
    if goal_count:
        items.append({
            "level": "info",
            "title": "已有棋子完成达阵",
            "evidence": f"目标区中已有 {goal_count} 颗己方棋",
            "action": "注意不要让浅层棋堵住更深目标孔",
        })
    if not items:
        items.append({
            "level": "info",
            "title": "当前结构较均衡",
            "evidence": "五项评价中没有出现单一显著瓶颈",
            "action": "从候选对比中选择最符合计划的路线",
        })
    return items[:4]


def explain_position(
    game: dict,
    player_id: int | None = None,
    limit: int = 5,
) -> dict:
    pid = _coach_player_id(game, player_id)
    state = _state_for_player(game["state"], pid)
    limit = max(1, min(int(limit), 8))
    before = evaluate_components(state, pid)
    legal = state.get_valid_moves()
    scored = []
    for move in legal:
        components = evaluate_components(state.apply_move(move), pid)
        scored.append((components["score"], move))
    scored.sort(key=lambda item: (-item[0], item[1]))
    candidates = [
        _candidate_payload(state, move, player_id=pid, before=before, rank=index + 1)
        for index, (_, move) in enumerate(scored[:limit])
    ]

    all_players = []
    for active_pid in state.active_players:
        comp = evaluate_components(state, active_pid)
        all_players.append({
            "player_id": active_pid,
            "goal_assignment_distance": comp["goal_assignment_distance"],
            "last_piece_distance": comp["last_piece_distance"],
            "score": comp["score"],
        })
    race_order = sorted(
        all_players,
        key=lambda item: (
            item["goal_assignment_distance"],
            item["last_piece_distance"],
            -item["score"],
        ),
    )
    race_rank = next(index + 1 for index, item in enumerate(race_order) if item["player_id"] == pid)
    leader = race_order[0]
    if leader["player_id"] == pid:
        race_label = "领先" if len(race_order) > 1 else "单方分析"
    else:
        gap = before["goal_assignment_distance"] - leader["goal_assignment_distance"]
        race_label = f"落后领跑者约 {gap:.1f} 距离单位"

    confidence_value = 0.62
    confidence_basis = "首选与次选差距较小，保留多条合理路线"
    if len(candidates) == 1:
        confidence_value = 0.95
        confidence_basis = "当前只有一个可用候选"
    elif len(candidates) >= 2:
        gap = candidates[0]["score"] - candidates[1]["score"]
        spread = max(1.0, candidates[0]["score"] - candidates[-1]["score"])
        confidence_value = min(0.92, 0.55 + 0.37 * max(0.0, gap) / spread)
        confidence_basis = (
            f"首选比次选高 {gap:.2f} 分；"
            + ("优势明确" if confidence_value >= 0.75 else "多个候选接近")
        )
    confidence_label = (
        "高" if confidence_value >= 0.78 else "中" if confidence_value >= 0.62 else "低"
    )

    counterfactual = None
    if len(candidates) >= 2:
        first, second = candidates[0], candidates[1]
        second_advantages = []
        for first_change, second_change in zip(first["feature_changes"], second["feature_changes"]):
            if second_change["score_effect"] > first_change["score_effect"] + 1e-7:
                second_advantages.append(second_change["label"])
        counterfactual = {
            "alternative_rank": 2,
            "score_gap": round(first["score"] - second["score"], 3),
            "text": (
                f"若改走候选 2，综合评分少 {first['score'] - second['score']:.2f}；"
                + (
                    "但它在" + "、".join(second_advantages[:2]) + "上更有利。"
                    if second_advantages
                    else "五项特征上没有明显优于首选的部分。"
                )
            ),
        }

    top = candidates[0] if candidates else None
    headline = "当前没有合法走法"
    summary = "规则引擎未找到可执行候选。"
    if top:
        detail = top["move_detail"]
        headline = (
            f"首选：棋子（{detail['piece']['position'][0]},{detail['piece']['position'][1]}）"
            f"到（{detail['target'][0]},{detail['target'][1]}）"
        )
        summary = top["reason"] + "。"

    return {
        "report_version": "xai-coach-2",
        "kind": "position",
        "player_id": pid,
        "game_id": game.get("game_id"),
        "perspective": "human" if game.get("mode") == "pve" and pid == 0 else "current_player",
        "scope": "human-player" if game.get("mode") == "pve" else "current-player",
        "move_count": len(game["state"].move_history),
        "state_token": state_token(game["state"]),
        "phase": _position_phase(state, pid),
        "headline": headline,
        "summary": summary,
        "confidence": {
            "value": round(confidence_value, 3),
            "label": confidence_label,
            "basis": confidence_basis,
        },
        "race": {
            "rank": race_rank,
            "total_players": len(race_order),
            "label": race_label,
            "order": race_order,
        },
        "current": {
            "components": before,
            "features": _feature_cards(before),
            "legal_move_count": len(legal),
            "home_piece_count": len(set(state.get_player_pieces(pid)) & HOME_SETS[pid]),
            "goal_piece_count": len(set(state.get_player_pieces(pid)) & GOAL_SETS[pid]),
        },
        "diagnostics": _diagnostics(state, pid, before),
        "candidates": candidates,
        "counterfactual": counterfactual,
        "evidence": {
            "model": "five-feature rule evaluation",
            "feature_keys": list(FEATURE_SPECS),
            "legal_moves_examined": len(legal),
            "candidate_count": len(candidates),
            "feature_count": len(FEATURE_SPECS),
            "all_candidates_verified": all(item.get("verified") for item in candidates),
            "source_owner_checked": True,
            "target_empty_checked": True,
            "generated_at_move_count": len(state.move_history),
            "note": "这是可验证的特征证据，不是模型私有思维链。",
        },
    }


def explain_last_move(game: dict) -> dict:
    state: BoardState = game["state"]
    if not state.move_history:
        return {
            "available": False,
            "headline": "当前还没有可复盘的走法",
            "summary": "完成至少一步走棋后即可比较走棋前后的五项特征。",
        }
    fr, fc, tr, tc, pid = state.move_history[-1]
    before_state = BoardState.copy_from(state)
    before_state.undo_move()
    before = evaluate_components(before_state, pid)
    after = evaluate_components(state, pid)
    changes = _feature_changes(before, after)
    positives = sorted(
        (item for item in changes if item["impact"] == "positive"),
        key=lambda item: -abs(item["score_effect"]),
    )
    negatives = sorted(
        (item for item in changes if item["impact"] == "negative"),
        key=lambda item: -abs(item["score_effect"]),
    )
    move = ((fr, fc), (tr, tc))
    return {
        "available": True,
        "player_id": pid,
        "move": _move_to_json(move),
        "move_detail": _move_detail(before_state, move, player_id=pid),
        "before": before,
        "after": after,
        "score_delta": round(after["score"] - before["score"], 3),
        "feature_changes": changes,
        "headline": f"最近一步：棋子（{fr},{fc}）到（{tr},{tc}）",
        "summary": (
            "主要收益：" + "；".join(_change_sentence(item) for item in positives[:2])
            if positives
            else "这一步没有改善五项评价"
        ),
        "risk": _change_sentence(negatives[0]) if negatives else "没有明显的五项特征代价",
        "evidence": {
            "model": "before-after five-feature comparison",
            "note": "仅比较可验证的局面特征，不展示模型私有思维链。",
        },
    }

MCP_TOOL_NAMES = (
    "list_games",
    "get_game_metadata",
    "get_game_state",
    "get_move_history",
    "get_ai_decisions",
    "get_evaluation_snapshots",
    "get_chat_history",
    "get_tool_audit_logs",
    "list_replays",
    "get_replay",
    "get_board_geometry",
    "get_legal_moves",
    "evaluate_position",
    "evaluate_move",
    "rank_candidate_moves",
    "recommend_move",
    "simulate_moves",
    "explain_position",
    "explain_last_move",
    "get_game_statistics",
)


def _position(value: Any, name: str = "position") -> tuple[int, int]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError(f"{name} must be [row, col]")
    return int(value[0]), int(value[1])


def _move_to_json(move: Move | None):
    if move is None:
        return None
    return {"from": list(move[0]), "to": list(move[1])}


def _move_path(state: BoardState, move: Move) -> dict:
    """Return one legal landing path without mutating the state.

    The rule engine exposes a move as source/final destination.  This helper
    mirrors its jump BFS and reconstructs the intermediate landing sequence so
    UI/MCP clients can explain which piece moves and how it gets there.
    """
    source, destination = move
    if destination in NEIGHBORS[source]:
        return {
            "path": [list(source), list(destination)],
            "jumped_over": [],
            "move_type": "step",
            "segment_count": 1,
            "jump_count": 0,
        }

    visited_over = {source}
    visited_land = {source}
    queue = [source]
    parent: dict[tuple[int, int], tuple[int, int]] = {}
    jumped: dict[tuple[int, int], tuple[int, int]] = {}

    while queue:
        current = queue.pop(0)
        for middle in NEIGHBORS[current]:
            if middle in visited_over or state.board[middle[0]][middle[1]] == 0:
                continue
            direction = _DIRECTION_MAP.get((current[0], current[1], middle[0], middle[1]))
            if direction is None:
                continue
            landing = _hex_step(middle[0], middle[1], direction)
            if landing not in VALID_HOLES or landing in visited_land:
                continue
            if state.board[landing[0]][landing[1]] != 0:
                continue

            parent[landing] = current
            jumped[landing] = middle
            visited_over.add(middle)
            visited_land.add(landing)
            queue.append(landing)
            if landing == destination:
                queue.clear()
                break

    if destination not in parent:
        return {
            "path": [list(source), list(destination)],
            "jumped_over": [],
            "move_type": "unknown",
            "segment_count": 1,
            "jump_count": 0,
        }

    landings = [destination]
    middles = []
    cursor = destination
    while cursor != source:
        middles.append(jumped[cursor])
        cursor = parent[cursor]
        landings.append(cursor)
    landings.reverse()
    middles.reverse()
    return {
        "path": [list(position) for position in landings],
        "jumped_over": [list(position) for position in middles],
        "move_type": "jump",
        "segment_count": len(landings) - 1,
        "jump_count": len(landings) - 1,
    }


def _move_detail(
    state: BoardState,
    move: Move | None,
    *,
    player_id: int,
    rank: int | None = None,
    score: float | None = None,
    components: dict | None = None,
) -> dict | None:
    if move is None:
        return None
    detail = {
        "move": _move_to_json(move),
        "piece": {"player_id": player_id, "position": list(move[0])},
        "target": list(move[1]),
        **_move_path(state, move),
    }
    detail["path_text"] = " → ".join(
        f"({row},{col})" for row, col in detail["path"]
    )
    if rank is not None:
        detail["rank"] = int(rank)
    if score is not None:
        detail["score"] = float(score)
    if components is not None:
        detail["components"] = components
    return detail


def _state_for_player(state: BoardState, player_id: int | None) -> BoardState:
    if player_id is None or player_id == state.current_player:
        return state
    if player_id not in state.active_players:
        raise ValueError(f"player {player_id} is not active")
    copied = BoardState.copy_from(state)
    copied.current_player = int(player_id)
    return copied


def validate_candidate_move(
    game: dict,
    from_position,
    to_position,
    player_id: int | None = None,
) -> dict:
    """Validate and canonicalize a user-facing recommendation.

    This is the final trust boundary for DeepSeek, MCP, SQL history and the
    browser overlay.  Untrusted paths and player ids are ignored.
    """
    pid = _coach_player_id(game, player_id)
    original: BoardState = game["state"]
    state = _state_for_player(original, pid)
    move = (_position(from_position, "from_position"), _position(to_position, "to_position"))
    invariants = _move_invariants(state, move, pid)
    result = {
        **invariants,
        "game_id": game.get("game_id"),
        "move_count": len(original.move_history),
        "state_token": state_token(original),
        "move": _move_to_json(move),
        "move_detail": None,
    }
    if not invariants["valid"]:
        return result
    detail = _move_detail(state, move, player_id=pid)
    detail["verified"] = True
    detail["validation"] = invariants
    result["move_detail"] = detail
    return result


def get_game_metadata(game: dict) -> dict:
    state: BoardState = game["state"]
    return {
        "game_id": game.get("game_id"),
        "mode": game.get("mode"),
        "difficulty": game.get("difficulty"),
        "num_players": len(state.active_players),
        "save_name": game.get("save_name", ""),
        "current_player": state.current_player,
        "winner": state.get_winner(),
        "is_terminal": state.is_terminal(),
        "move_count": len(state.move_history),
    }


def get_game_state(game: dict) -> dict:
    return game["state"].to_dict()


def get_move_history(game: dict, limit: int = 100) -> dict:
    state: BoardState = game["state"]
    history = state.to_dict()["move_history"]
    limit = max(1, min(int(limit), 500))
    start = max(0, len(history) - limit)
    return {"total": len(history), "moves": history[start:]}


def get_board_geometry() -> dict:
    return {
        "rows": cfg.BOARD_ROWS,
        "cols": cfg.BOARD_COLS,
        "valid_holes": [list(pos) for pos in sorted(VALID_HOLES)],
        "home_zones": {str(pid): [list(pos) for pos in sorted(zone)] for pid, zone in HOME_SETS.items()},
        "goal_zones": {str(pid): [list(pos) for pos in sorted(zone)] for pid, zone in GOAL_SETS.items()},
        "pieces_per_player": cfg.PIECES_PER_PLAYER,
        "coordinate_system": {
            "format": "[row, col]",
            "screen_orientation": "row 0 is displayed at the bottom; row 16 at the top",
            "column_direction": "column values increase from left to right",
            "odd_row_offset": "odd rows are shifted half a cell to the right",
            "note_zh": "前端坐标显示采用（行,列）；坐标层仅用于解释，不改变棋局。",
        },
    }


def get_legal_moves(
    game: dict,
    player_id: int | None = None,
    from_position: list[int] | tuple[int, int] | None = None,
) -> dict:
    state = _state_for_player(game["state"], player_id)
    moves = state.get_valid_moves()
    source = _position(from_position, "from_position") if from_position is not None else None
    if source is not None:
        moves = [move for move in moves if move[0] == source]
    return {
        "player_id": state.current_player,
        "from_position": list(source) if source else None,
        "count": len(moves),
        "moves": [_move_to_json(move) for move in sorted(moves)],
    }


def evaluate_position(game: dict, player_id: int | None = None) -> dict:
    state: BoardState = game["state"]
    pid = state.current_player if player_id is None else int(player_id)
    if pid not in state.active_players:
        raise ValueError(f"player {pid} is not active")
    return {"player_id": pid, "components": evaluate_components(state, pid)}


def evaluate_move(
    game: dict,
    from_position,
    to_position,
    player_id: int | None = None,
) -> dict:
    state = _state_for_player(game["state"], player_id)
    pid = state.current_player
    move = (_position(from_position, "from_position"), _position(to_position, "to_position"))
    legal = set(state.get_valid_moves())
    if move not in legal:
        raise ValueError("move is not legal for the selected player")
    before = evaluate_components(state, pid)
    after_state = state.apply_move(move)
    after = evaluate_components(after_state, pid)
    return {
        "player_id": pid,
        "move": _move_to_json(move),
        "move_detail": _move_detail(state, move, player_id=pid),
        "before": before,
        "after": after,
        "score_delta": after["score"] - before["score"],
        "resulting_state": after_state.to_dict(),
    }


def rank_candidate_moves(
    game: dict,
    player_id: int | None = None,
    limit: int = 10,
) -> dict:
    pid = _coach_player_id(game, player_id)
    state = _state_for_player(game["state"], pid)
    limit = max(1, min(int(limit), 50))
    before = evaluate_components(state, pid)
    scored = []
    for move in state.get_valid_moves():
        components = evaluate_components(state.apply_move(move), pid)
        scored.append((components["score"], move))
    scored.sort(key=lambda item: (-item[0], item[1]))
    candidates = [
        _candidate_payload(state, move, player_id=pid, before=before, rank=index + 1)
        for index, (_, move) in enumerate(scored[:limit])
    ]
    return {
        "player_id": pid,
        "count": len(candidates),
        "before": before,
        "candidates": candidates,
    }


def recommend_move(
    game: dict,
    difficulty: int | None = None,
    player_id: int | None = None,
) -> dict:
    """Deterministic, auditable Coach recommendation.

    The actual game AI keeps its bounded randomness.  The Coach uses a stable
    ranking so the prose, board overlay and evidence cards cannot disagree.
    """
    pid = _coach_player_id(game, player_id)
    selected_difficulty = int(difficulty or game.get("difficulty", 3))
    selected_difficulty = max(1, min(selected_difficulty, 3))
    started = time.perf_counter()
    ranked = rank_candidate_moves(
        game,
        player_id=pid,
        limit=max(5, cfg.LLM_BOARD_OVERLAY_LIMIT),
    )
    payloads = ranked["candidates"]
    elapsed_ms = (time.perf_counter() - started) * 1000
    details = []
    for payload in payloads:
        detail = dict(payload["move_detail"])
        detail.update({
            "score": payload["score"],
            "score_delta": payload["score_delta"],
            "feature_changes": payload["feature_changes"],
            "reason": payload["reason"],
            "tradeoff": payload["tradeoff"],
            "evidence": payload["evidence"],
            "verified": True,
            "validation": payload["validation"],
        })
        details.append(detail)
    first_move = payloads[0]["move"] if payloads else None
    result = {
        "player_id": pid,
        "difficulty": selected_difficulty,
        "move": first_move,
        "move_detail": details[0] if details else None,
        "local_candidates": [item["move"] for item in payloads],
        "candidate_details": details,
        "elapsed_ms": elapsed_ms,
        "selection_policy": "deterministic-explainable-ranking",
        "game_id": game.get("game_id"),
        "move_count": len(game["state"].move_history),
        "state_token": state_token(game["state"]),
        "explanation_note": (
            "游戏 AI 仍使用受控随机；AI Coach 为保证可解释性，"
            "对同一局面采用稳定排序，并逐条通过规则校验。"
        ),
    }
    if first_move is not None:
        result["evaluation"] = evaluate_move(
            game, first_move["from"], first_move["to"], pid
        )
    return result


def simulate_moves(game: dict, moves: list[dict], max_steps: int = 16) -> dict:
    state = BoardState.copy_from(game["state"])
    max_steps = max(1, min(int(max_steps), 32))
    trace = []
    for index, raw in enumerate(moves[:max_steps], start=1):
        move = (_position(raw.get("from"), "from"), _position(raw.get("to"), "to"))
        pid = state.current_player
        if move not in set(state.get_valid_moves()):
            return {
                "ok": False,
                "failed_at": index,
                "reason": "illegal move",
                "move": _move_to_json(move),
                "trace": trace,
                "state": state.to_dict(),
            }
        before = evaluate_components(state, pid)
        move_detail = _move_detail(state, move, player_id=pid, rank=index)
        state = state.apply_move(move)
        after = evaluate_components(state, pid)
        trace.append({
            "step": index,
            "player_id": pid,
            "move": _move_to_json(move),
            "move_detail": move_detail,
            "score_delta": after["score"] - before["score"],
        })
        if state.is_terminal():
            break
    return {"ok": True, "trace": trace, "state": state.to_dict()}


def get_game_statistics(game: dict) -> dict:
    state: BoardState = game["state"]
    move_counts = {pid: 0 for pid in state.active_players}
    for item in state.move_history:
        move_counts[item[4]] = move_counts.get(item[4], 0) + 1
    evaluations = {
        str(pid): evaluate_components(state, pid)
        for pid in state.active_players
    }
    return {
        "game_id": game.get("game_id"),
        "move_count": len(state.move_history),
        "current_player": state.current_player,
        "winner": state.get_winner(),
        "scores": {str(pid): state.scores.get(pid, 0) for pid in state.active_players},
        "moves_by_player": {str(pid): count for pid, count in move_counts.items()},
        "evaluations": evaluations,
    }


CHAT_TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "get_board_geometry",
            "description": "读取棋盘全部有效孔位与前端坐标方向。回答坐标含义时必须先调用。",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_game_state",
            "description": "读取当前跳棋对局的完整状态、棋子位置、进度和当前玩家。",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_legal_moves",
            "description": "查询当前或指定玩家的合法走法，可限定某一颗棋。",
            "parameters": {
                "type": "object",
                "properties": {
                    "player_id": {"type": "integer", "minimum": 0, "maximum": 5},
                    "from_position": {
                        "type": "array", "items": {"type": "integer"}, "minItems": 2, "maxItems": 2
                    },
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "evaluate_position",
            "description": "用五项规则驱动评价分析当前局面。",
            "parameters": {
                "type": "object",
                "properties": {"player_id": {"type": "integer", "minimum": 0, "maximum": 5}},
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "evaluate_move",
            "description": "验证并评价一条具体走法，返回来源棋子、完整单步/连跳路径、走棋前后分解和分差。",
            "parameters": {
                "type": "object",
                "properties": {
                    "from_position": {"type": "array", "items": {"type": "integer"}, "minItems": 2, "maxItems": 2},
                    "to_position": {"type": "array", "items": {"type": "integer"}, "minItems": 2, "maxItems": 2},
                    "player_id": {"type": "integer", "minimum": 0, "maximum": 5},
                },
                "required": ["from_position", "to_position"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "rank_candidate_moves",
            "description": "按评价分列出当前局面的最佳候选走法，并返回每个候选使用的棋子、目标和完整路径。",
            "parameters": {
                "type": "object",
                "properties": {
                    "player_id": {"type": "integer", "minimum": 0, "maximum": 5},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 20},
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "recommend_move",
            "description": "调用游戏现有三档 AI 推荐下一步，并返回最多五个候选的来源棋子、目标、完整路径和评价。",
            "parameters": {
                "type": "object",
                "properties": {
                    "difficulty": {"type": "integer", "minimum": 1, "maximum": 3},
                    "player_id": {"type": "integer", "minimum": 0, "maximum": 5},
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_move_history",
            "description": "读取当前对局最近的走棋历史。",
            "parameters": {
                "type": "object",
                "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 100}},
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "explain_position",
            "description": "生成完整可解释局面报告：人类视角、阶段、五项特征、诊断、候选对比、风险、反事实和置信度。",
            "parameters": {
                "type": "object",
                "properties": {
                    "player_id": {"type": "integer", "minimum": 0, "maximum": 5},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 8}
                },
                "additionalProperties": False
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "explain_last_move",
            "description": "复盘最近一步，比较走棋前后五项特征、收益、代价与完整路径。",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_game_statistics",
            "description": "读取当前对局的进度、各玩家走棋数和评价统计。",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
]


_CHAT_TOOLS: dict[str, Callable[..., dict]] = {
    "get_board_geometry": lambda game: get_board_geometry(),
    "get_game_state": get_game_state,
    "get_legal_moves": get_legal_moves,
    "evaluate_position": evaluate_position,
    "evaluate_move": evaluate_move,
    "rank_candidate_moves": rank_candidate_moves,
    "recommend_move": recommend_move,
    "get_move_history": get_move_history,
    "explain_position": explain_position,
    "explain_last_move": lambda game: explain_last_move(game),
    "get_game_statistics": get_game_statistics,
}


def execute_chat_tool(name: str, arguments: dict, game: dict) -> dict:
    tool = _CHAT_TOOLS.get(name)
    if tool is None:
        raise KeyError(f"unknown tool: {name}")
    args = dict(arguments or {})
    human_default_tools = {
        "get_legal_moves", "evaluate_position", "evaluate_move",
        "rank_candidate_moves", "recommend_move", "explain_position",
    }
    if name in human_default_tools and "player_id" not in args:
        args["player_id"] = _coach_player_id(game)
    return tool(game, **args)
