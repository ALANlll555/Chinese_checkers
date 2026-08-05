"""
跳棋 — AI 引擎

三档 AI 共用同一套、由规则直接支持的局面评价：
1. 全部棋子到不同目标孔的最小总距离；
2. 最落后棋子的距离；
3. 当前有效向前连跳能力；
4. 可继续利用的梯子结构；
5. 棋子在起始区的滞留程度。

随机性只发生在近似最优候选内，不会从全部合法走法中盲选。
"""

from __future__ import annotations

import math
import random
import time
from collections import OrderedDict
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from board import (
    BoardState,
    DIST_MATRIX,
    GOAL_SETS,
    HOME_SETS,
    NEIGHBORS,
    POS_TO_ID,
    VALID_HOLES,
    _DIRECTION_MAP,
    _hex_step,
)
import config as cfg

Position = Tuple[int, int]
Move = Tuple[Position, Position]
ScoredMove = Tuple[float, Move]


# 每个位置到各玩家任一目标孔的静态最短距离。
_GOAL_IDS = {
    pid: tuple(POS_TO_ID[g] for g in GOAL_SETS[pid] if g in POS_TO_ID)
    for pid in range(6)
}
_GOAL_DISTANCE = {
    pid: {
        pos: min(DIST_MATRIX[POS_TO_ID[pos]][goal_id] for goal_id in _GOAL_IDS[pid])
        for pos in VALID_HOLES
    }
    for pid in range(6)
}

# evaluate() 在搜索排序和叶节点中会反复遇到同一状态；使用有界 LRU 缓存。
_EVAL_CACHE: "OrderedDict[Tuple[object, ...], Dict[str, float]]" = OrderedDict()


def _state_key(state: BoardState, pid: int) -> Tuple[object, ...]:
    pieces = tuple(
        (player, tuple(sorted(state.get_player_pieces(player))))
        for player in state.active_players
    )
    player_turns = sum(1 for item in state.move_history if item[4] == pid)
    return pid, tuple(state.active_players), pieces, player_turns


def _cache_get(key):
    cached = _EVAL_CACHE.get(key)
    if cached is not None:
        _EVAL_CACHE.move_to_end(key)
        return dict(cached)
    return None


def _cache_put(key, value):
    _EVAL_CACHE[key] = dict(value)
    _EVAL_CACHE.move_to_end(key)
    while len(_EVAL_CACHE) > cfg.AI_EVAL_CACHE_SIZE:
        _EVAL_CACHE.popitem(last=False)


def clear_evaluation_cache() -> None:
    """测试或长时间运行时可显式清空评价缓存。"""
    _EVAL_CACHE.clear()


def _hungarian_assignment(cost: Sequence[Sequence[int]]) -> Tuple[int, int]:
    """返回方阵最小分配总成本，以及该分配中的最大单项成本。"""
    n = len(cost)
    if n == 0:
        return 0, 0

    # Hungarian algorithm，1-based 实现，O(n^3)。
    u = [0] * (n + 1)
    v = [0] * (n + 1)
    p = [0] * (n + 1)
    way = [0] * (n + 1)

    for i in range(1, n + 1):
        p[0] = i
        j0 = 0
        minv = [float("inf")] * (n + 1)
        used = [False] * (n + 1)
        while True:
            used[j0] = True
            i0 = p[j0]
            delta = float("inf")
            j1 = 0
            for j in range(1, n + 1):
                if used[j]:
                    continue
                cur = cost[i0 - 1][j - 1] - u[i0] - v[j]
                if cur < minv[j]:
                    minv[j] = cur
                    way[j] = j0
                if minv[j] < delta:
                    delta = minv[j]
                    j1 = j
            for j in range(n + 1):
                if used[j]:
                    u[p[j]] += int(delta)
                    v[j] -= int(delta)
                else:
                    minv[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while True:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1
            if j0 == 0:
                break

    assigned_goal = [-1] * n
    for j in range(1, n + 1):
        if p[j] != 0:
            assigned_goal[p[j] - 1] = j - 1

    assigned_costs = [cost[i][assigned_goal[i]] for i in range(n)]
    return sum(assigned_costs), max(assigned_costs, default=0)


def _goal_assignment_metrics(state: BoardState, pid: int) -> Tuple[int, int]:
    pieces = sorted(state.get_player_pieces(pid))
    goals = sorted(GOAL_SETS[pid])
    if not pieces:
        return 9999, 9999

    # 正常规则下棋子数和目标孔数相同；保留防御性处理。
    n = min(len(pieces), len(goals))
    pieces = pieces[:n]
    goals = goals[:n]
    cost = [
        [DIST_MATRIX[POS_TO_ID[piece]][POS_TO_ID[goal]] for goal in goals]
        for piece in pieces
    ]
    return _hungarian_assignment(cost)


def _forward_jump_value(state: BoardState, pid: int) -> float:
    """每颗棋只计入其当前最佳有效向前连跳，避免分支数量重复奖励。"""
    best_by_piece: Dict[Position, int] = {}
    for src, dst in state.get_valid_moves(pid):
        # 相邻位置是普通单步；图距离大于 1 才视为跳跃终点。
        if DIST_MATRIX[POS_TO_ID[src]][POS_TO_ID[dst]] <= 1:
            continue
        gain = _GOAL_DISTANCE[pid][src] - _GOAL_DISTANCE[pid][dst]
        if gain > best_by_piece.get(src, 0):
            best_by_piece[src] = gain
    return float(sum(best_by_piece.values()))


def _occupant_after_jump(state: BoardState, src: Position, land: Position, pid: int):
    def occupant(pos: Position) -> int:
        if pos == src:
            return 0
        if pos == land:
            return pid + 1
        return state.get_piece(pos)
    return occupant


def _direct_forward_jumps(
    state: BoardState,
    src: Position,
    pid: int,
    occupant=None,
):
    if occupant is None:
        occupant = state.get_piece

    src_dist = _GOAL_DISTANCE[pid][src]
    for middle in NEIGHBORS[src]:
        middle_piece = occupant(middle)
        if middle_piece == 0:
            continue
        direction = _DIRECTION_MAP.get((src[0], src[1], middle[0], middle[1]))
        if direction is None:
            continue
        land = _hex_step(middle[0], middle[1], direction)
        if land not in VALID_HOLES or occupant(land) != 0:
            continue
        gain = src_dist - _GOAL_DISTANCE[pid][land]
        if gain > 0:
            yield middle, land, gain, middle_piece - 1


def _ladder_potential(state: BoardState, pid: int) -> float:
    """
    评价能产生向前跳跃的跳板链接，并对可形成第二段连续跳跃的结构加分。
    己方跳板比对手跳板稳定，因此权重更高。
    """
    links: Dict[Tuple[Position, Position], float] = {}
    chains: Dict[Tuple[Position, Position, Position, Position], float] = {}

    for src in state.get_player_pieces(pid):
        for middle, land, gain, middle_owner in _direct_forward_jumps(state, src, pid):
            stability = 1.0 if middle_owner == pid else cfg.AI_OPPONENT_LADDER_STABILITY
            key = (middle, land)
            links[key] = max(links.get(key, 0.0), gain * stability)

            occupant = _occupant_after_jump(state, src, land, pid)
            for middle2, land2, gain2, middle2_owner in _direct_forward_jumps(
                state, land, pid, occupant
            ):
                stability2 = (
                    1.0 if middle2_owner == pid else cfg.AI_OPPONENT_LADDER_STABILITY
                )
                chain_key = (middle, land, middle2, land2)
                chain_value = (gain + gain2) * min(stability, stability2)
                chains[chain_key] = max(chains.get(chain_key, 0.0), chain_value)

    return sum(links.values()) + cfg.AI_LADDER_CHAIN_BONUS * sum(chains.values())


def _home_delay(state: BoardState, pid: int) -> float:
    home_count = sum(1 for pos in state.get_player_pieces(pid) if pos in HOME_SETS[pid])
    player_turns = sum(1 for item in state.move_history if item[4] == pid)
    phase = min(1.5, player_turns / max(1.0, cfg.PIECES_PER_PLAYER * 1.5))
    return home_count * (cfg.AI_HOME_BASE_DELAY + phase)


def evaluate_components(state: BoardState, pid: int) -> Dict[str, float]:
    """返回可解释的原始特征和总分。"""
    key = _state_key(state, pid)
    cached = _cache_get(key)
    if cached is not None:
        return cached

    pieces = state.get_player_pieces(pid)
    if not pieces:
        result = {
            "goal_assignment_distance": 9999.0,
            "last_piece_distance": 9999.0,
            "forward_jump_value": 0.0,
            "ladder_potential": 0.0,
            "home_delay": 0.0,
            "score": -cfg.AI_WIN_SCORE,
        }
        _cache_put(key, result)
        return result

    total_distance, last_distance = _goal_assignment_metrics(state, pid)
    jump_value = _forward_jump_value(state, pid)
    ladder_value = _ladder_potential(state, pid)
    home_delay = _home_delay(state, pid)

    score = (
        cfg.WEIGHT_GOAL_ASSIGNMENT * total_distance
        + cfg.WEIGHT_LAST_PIECE * last_distance
        + cfg.WEIGHT_FORWARD_JUMP * jump_value
        + cfg.WEIGHT_LADDER_POTENTIAL * ladder_value
        + cfg.WEIGHT_HOME_DELAY * home_delay
    )

    winner = state.get_winner()
    if winner == pid:
        score += cfg.AI_WIN_SCORE
    elif winner is not None:
        score -= cfg.AI_WIN_SCORE

    result = {
        "goal_assignment_distance": float(total_distance),
        "last_piece_distance": float(last_distance),
        "forward_jump_value": float(jump_value),
        "ladder_potential": float(ladder_value),
        "home_delay": float(home_delay),
        "score": float(score),
    }
    _cache_put(key, result)
    return result


def evaluate(state: BoardState, pid: int) -> float:
    return evaluate_components(state, pid)["score"]


def _score_moves(
    state: BoardState,
    pid: int,
    moves: Optional[Iterable[Move]] = None,
) -> List[ScoredMove]:
    if moves is None:
        moves = state.get_valid_moves()
    scored = [(evaluate(state.apply_move(move), pid), move) for move in sorted(moves)]
    scored.sort(key=lambda item: (-item[0], item[1]))
    return scored


def _difficulty_profile(difficulty: int) -> Dict[str, float]:
    if difficulty <= 1:
        return {
            "margin_ratio": cfg.AI_EASY_MARGIN_RATIO,
            "margin_min": cfg.AI_EASY_MARGIN_MIN,
            "margin_max": cfg.AI_EASY_MARGIN_MAX,
            "candidate_limit": cfg.AI_EASY_CANDIDATES,
            "temperature": cfg.AI_EASY_TEMPERATURE,
        }
    if difficulty == 2:
        return {
            "margin_ratio": cfg.AI_MEDIUM_MARGIN_RATIO,
            "margin_min": cfg.AI_MEDIUM_MARGIN_MIN,
            "margin_max": cfg.AI_MEDIUM_MARGIN_MAX,
            "candidate_limit": cfg.AI_MEDIUM_CANDIDATES,
            "temperature": cfg.AI_MEDIUM_TEMPERATURE,
        }
    return {
        "margin_ratio": cfg.AI_HARD_MARGIN_RATIO,
        "margin_min": cfg.AI_HARD_MARGIN_MIN,
        "margin_max": cfg.AI_HARD_MARGIN_MAX,
        "candidate_limit": cfg.AI_HARD_CANDIDATES,
        "temperature": cfg.AI_HARD_TEMPERATURE,
    }


def _near_optimal_shortlist(
    scored: Sequence[ScoredMove],
    difficulty: int,
) -> List[ScoredMove]:
    if not scored:
        return []

    profile = _difficulty_profile(difficulty)
    best = scored[0][0]
    reference_index = min(
        len(scored) - 1,
        max(1, int(profile["candidate_limit"]) * 2) - 1,
    )
    local_span = max(0.0, best - scored[reference_index][0])
    margin = max(
        profile["margin_min"],
        min(profile["margin_max"], local_span * profile["margin_ratio"]),
    )

    shortlist = [item for item in scored if item[0] >= best - margin]
    return shortlist[: int(profile["candidate_limit"])]


def get_local_candidates(state: BoardState, difficulty: int = 2) -> List[Move]:
    """返回参与受控随机的近似最优候选，便于测试和诊断。"""
    pid = state.current_player
    scored = _score_moves(state, pid)
    return [move for _, move in _near_optimal_shortlist(scored, difficulty)]


def _sample_scored_move(
    scored: Sequence[ScoredMove],
    difficulty: int,
    rng: Optional[random.Random] = None,
):
    shortlist = _near_optimal_shortlist(scored, difficulty)
    if not shortlist:
        return None
    if len(shortlist) == 1:
        return shortlist[0][1]

    profile = _difficulty_profile(difficulty)
    temperature = max(1e-6, profile["temperature"])
    best = shortlist[0][0]
    weights = [math.exp((score - best) / temperature) for score, _ in shortlist]
    chooser = rng if rng is not None else random
    return chooser.choices([move for _, move in shortlist], weights=weights, k=1)[0]


def ai_random(state: BoardState, rng: Optional[random.Random] = None):
    """低难度：高温度、较宽质量窗口，但只在合理候选中随机。"""
    pid = state.current_player
    moves = state.get_valid_moves()
    if not moves:
        return None
    return _sample_scored_move(_score_moves(state, pid, moves), 1, rng)


def ai_greedy(state: BoardState, rng: Optional[random.Random] = None):
    """中难度：一步评价，在更窄的近似最优集合中采样。"""
    pid = state.current_player
    moves = state.get_valid_moves()
    if not moves:
        return None
    return _sample_scored_move(_score_moves(state, pid, moves), 2, rng)


def _ordered_moves(state: BoardState, ai_pid: int) -> List[Move]:
    moves = state.get_valid_moves()
    if not moves:
        return []
    scored = _score_moves(state, ai_pid, moves)
    maximizing = state.current_player == ai_pid
    if not maximizing:
        scored.reverse()
    limit = cfg.AI_SEARCH_BRANCH_LIMIT
    if limit > 0:
        scored = scored[:limit]
    return [move for _, move in scored]


def _search(
    state: BoardState,
    depth: int,
    alpha: float,
    beta: float,
    ai_pid: int,
    started: float,
    time_limit: float,
) -> float:
    if depth <= 0 or state.is_terminal():
        return evaluate(state, ai_pid)
    if time.perf_counter() - started >= time_limit:
        return evaluate(state, ai_pid)

    moves = _ordered_moves(state, ai_pid)
    if not moves:
        return evaluate(state, ai_pid)

    if state.current_player == ai_pid:
        value = float("-inf")
        for move in moves:
            value = max(
                value,
                _search(
                    state.apply_move(move), depth - 1, alpha, beta,
                    ai_pid, started, time_limit,
                ),
            )
            alpha = max(alpha, value)
            if alpha >= beta or time.perf_counter() - started >= time_limit:
                break
        return value

    # 多人局面采用 paranoid 模型：其余玩家均视为当前 AI 的对手。
    value = float("inf")
    for move in moves:
        value = min(
            value,
            _search(
                state.apply_move(move), depth - 1, alpha, beta,
                ai_pid, started, time_limit,
            ),
        )
        beta = min(beta, value)
        if alpha >= beta or time.perf_counter() - started >= time_limit:
            break
    return value


def ai_minimax(
    state: BoardState,
    depth: Optional[int] = None,
    time_limit: Optional[float] = None,
    rng: Optional[random.Random] = None,
):
    """高难度：Alpha-Beta/Paranoid 搜索，根节点仅在近似最优值中低温采样。"""
    if depth is None:
        depth = cfg.AI_SEARCH_DEPTH
    if time_limit is None:
        time_limit = cfg.AI_TIME_LIMIT

    pid = state.current_player
    moves = state.get_valid_moves()
    if not moves:
        return None

    root_order = _score_moves(state, pid, moves)
    if cfg.AI_HARD_ROOT_LIMIT > 0:
        root_order = root_order[:cfg.AI_HARD_ROOT_LIMIT]

    started = time.perf_counter()
    searched: List[ScoredMove] = []
    alpha = float("-inf")

    for heuristic_score, move in root_order:
        if time.perf_counter() - started >= time_limit and searched:
            break
        next_state = state.apply_move(move)
        value = _search(
            next_state,
            depth - 1,
            alpha,
            float("inf"),
            pid,
            started,
            time_limit,
        )
        # 搜索超时仍保留已完成根节点；heuristic_score 仅用于稳定排序。
        searched.append((value, move))
        alpha = max(alpha, value)

    if not searched:
        searched = root_order
    searched.sort(key=lambda item: (-item[0], item[1]))
    return _sample_scored_move(searched, 3, rng)


def get_ai_move(
    state: BoardState,
    difficulty: int = 2,
    rng: Optional[random.Random] = None,
):
    if difficulty == 1:
        return ai_random(state, rng)
    if difficulty == 2:
        return ai_greedy(state, rng)
    return ai_minimax(state, rng=rng)
