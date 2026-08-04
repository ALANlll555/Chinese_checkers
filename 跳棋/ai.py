"""
跳棋 — AI 引擎
"""

from __future__ import annotations

import random, time
from board import BoardState, NEIGHBORS, GOAL_SETS, DIST_MATRIX, POS_TO_ID
import config as cfg


def evaluate(state: BoardState, pid: int) -> float:
    pieces = state.get_player_pieces(pid)
    if not pieces:
        return -99999

    score = 0.0

    # 距离
    goal_ids = [POS_TO_ID[g] for g in GOAL_SETS[pid] if g in POS_TO_ID]
    total_dist = 0.0
    for pos in pieces:
        pi = POS_TO_ID.get(pos)
        if pi is not None:
            total_dist += min(DIST_MATRIX[pi][gid] for gid in goal_ids)
    score += cfg.WEIGHT_DISTANCE * total_dist

    # 进度
    score += cfg.WEIGHT_PROGRESS * state.scores[pid]

    # 分散度
    if len(pieces) >= 2:
        pd_sum = 0.0
        cnt = 0
        for i in range(len(pieces)):
            pi = POS_TO_ID.get(pieces[i])
            if pi is None: continue
            for j in range(i+1, len(pieces)):
                pj = POS_TO_ID.get(pieces[j])
                if pj is None: continue
                pd_sum += DIST_MATRIX[pi][pj]
                cnt += 1
        if cnt > 0:
            score += cfg.WEIGHT_SPREAD * (pd_sum / cnt)

    # 连跳
    pv = pid + 1
    bridge = 0
    for pos in pieces:
        for nbr in NEIGHBORS.get(pos, []):
            if state.get_piece(nbr) == pv:
                bridge += 1
    score += cfg.WEIGHT_BRIDGE * bridge

    return score


def ai_random(state: BoardState):
    moves = state.get_valid_moves()
    return random.choice(moves) if moves else None


def ai_greedy(state: BoardState):
    pid = state.current_player
    moves = state.get_valid_moves()
    if not moves: return None
    best = moves[0]
    best_sc = float("-inf")
    for m in moves:
        ns = state.apply_move(m)
        sc = evaluate(ns, pid)
        if sc > best_sc:
            best_sc = sc
            best = m
    return best


def ai_minimax(state: BoardState, depth=None, time_limit=None):
    if depth is None: depth = cfg.AI_SEARCH_DEPTH
    if time_limit is None: time_limit = cfg.AI_TIME_LIMIT

    pid = state.current_player
    moves = state.get_valid_moves()
    if not moves:
        return None

    scored = [(evaluate(state.apply_move(m), pid), m) for m in moves]
    scored.sort(key=lambda x: x[0], reverse=True)

    t0 = time.time()
    best = scored[0][1]
    alpha = float("-inf")

    for _, m in scored:
        ns = state.apply_move(m)
        v = _min_val(ns, depth-1, alpha, float("inf"), pid, t0, time_limit)
        if v > alpha:
            alpha = v
            best = m
        if time.time() - t0 > time_limit:
            break
    return best


def _max_val(state, depth, alpha, beta, ai_pid, t0, tl):
    if depth == 0 or state.is_terminal():
        return evaluate(state, ai_pid)
    if time.time() - t0 > tl:
        return evaluate(state, ai_pid)
    v = float("-inf")
    for m in _order(state, ai_pid):
        v = max(v, _min_val(state.apply_move(m), depth-1, alpha, beta, ai_pid, t0, tl))
        if v >= beta: return v
        alpha = max(alpha, v)
    return v


def _min_val(state, depth, alpha, beta, ai_pid, t0, tl):
    if depth == 0 or state.is_terminal():
        return evaluate(state, ai_pid)
    if time.time() - t0 > tl:
        return evaluate(state, ai_pid)
    v = float("inf")
    for m in _order(state, state.current_player):
        v = min(v, _max_val(state.apply_move(m), depth-1, alpha, beta, ai_pid, t0, tl))
        if v <= alpha: return v
        beta = min(beta, v)
    return v


def _order(state, pid):
    moves = state.get_valid_moves()
    scored = [(evaluate(state.apply_move(m), pid), m) for m in moves]
    scored.sort(key=lambda x: x[0], reverse=True)
    return [m for _, m in scored]


def get_ai_move(state: BoardState, difficulty: int = 2):
    if difficulty == 1:
        return ai_random(state)
    elif difficulty == 2:
        return ai_greedy(state)
    else:
        return ai_minimax(state)
