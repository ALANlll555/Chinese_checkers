"""
跳棋 — 棋盘状态与规则引擎
"""

from __future__ import annotations

from copy import deepcopy
from collections import deque

import config as cfg


def _build_hole_set():
    holes = set()
    for r, (s, e) in enumerate(cfg.ROW_HOLE_RANGES):
        for c in range(s, e + 1):
            holes.add((r, c))
    return holes


def _build_neighbors():
    EVEN = [(-1,-1), (-1,0), (0,-1), (0,1), (1,-1), (1,0)]
    ODD  = [(-1,0), (-1,1), (0,-1), (0,1), (1,0),  (1,1)]
    holes = _build_hole_set()
    nb = {}
    for r, c in holes:
        dirs = EVEN if r % 2 == 0 else ODD
        nb[(r,c)] = []
        for dr, dc in dirs:
            nr, nc = r+dr, c+dc
            if (nr, nc) in holes:
                nb[(r,c)].append((nr, nc))
    return nb


def _build_dist_matrix():
    holes = _build_hole_set()
    pl = sorted(holes)
    p2i = {p:i for i,p in enumerate(pl)}
    n = len(pl)
    nb = _build_neighbors()
    dist = [[-1]*n for _ in range(n)]
    for i, s in enumerate(pl):
        q = deque([s])
        dist[i][i] = 0
        while q:
            cur = q.popleft()
            d = dist[i][p2i[cur]]
            for nxt in nb[cur]:
                j = p2i[nxt]
                if dist[i][j] == -1:
                    dist[i][j] = d+1
                    q.append(nxt)
    return dist


VALID_HOLES = _build_hole_set()
NEIGHBORS = _build_neighbors()
POS_LIST = sorted(VALID_HOLES)
POS_TO_ID = {p:i for i,p in enumerate(POS_LIST)}
DIST_MATRIX = _build_dist_matrix()

HOME_SETS = {pid: set(cfg.PLAYER_HOME_ZONES.get(pid, [])) for pid in range(6)}
GOAL_SETS = {0: HOME_SETS[3], 1: HOME_SETS[4], 2: HOME_SETS[5],
             3: HOME_SETS[0], 4: HOME_SETS[1], 5: HOME_SETS[2]}


# ── 六边形方向工具 ───────────────────────────────────
# 6 个方向索引：0=右, 1=右上, 2=左上, 3=左, 4=左下, 5=右下
# 偏移量因行奇偶而异（odd-row offset hex grid）
_EVEN_OFFSETS = [(0,1), (-1,0), (-1,-1), (0,-1), (1,-1), (1,0)]
_ODD_OFFSETS  = [(0,1), (-1,1), (-1,0),  (0,-1), (1,0),  (1,1)]


def _hex_step(r: int, c: int, direction: int):
    """按六边形方向走一步，返回 (nr, nc)。"""
    dr, dc = (_EVEN_OFFSETS if r % 2 == 0 else _ODD_OFFSETS)[direction]
    return (r + dr, c + dc)


# 方向查找表：{ (r,c, nr,nc): direction_index }
_DIRECTION_MAP: dict[tuple, int] = {}
for (r, c) in VALID_HOLES:
    offsets = _EVEN_OFFSETS if r % 2 == 0 else _ODD_OFFSETS
    for di, (dr, dc) in enumerate(offsets):
        nr, nc = r + dr, c + dc
        if (nr, nc) in VALID_HOLES:
            _DIRECTION_MAP[(r, c, nr, nc)] = di


class BoardState:
    __slots__ = ("board", "current_player", "active_players",
                 "move_history", "scores")

    def __init__(self, active=None):
        self.board = [[0]*cfg.BOARD_COLS for _ in range(cfg.BOARD_ROWS)]
        self.current_player = 0
        self.active_players = active or [0, 3]
        self.move_history = []
        self.scores = {p: 0 for p in range(6)}

    @classmethod
    def new_game(cls, num_players=2):
        mapping = {2: [0,3], 3: [0,2,4], 4: [0,1,3,4], 6: list(range(6))}
        active = mapping.get(num_players, [0,3])
        s = cls(active)
        for pid in active:
            for r, c in HOME_SETS[pid]:
                s.board[r][c] = pid + 1
        s.current_player = active[0]
        for pid in active:
            s._update_score(pid)
        return s

    @classmethod
    def copy_from(cls, other):
        s = cls(list(other.active_players))
        s.board = deepcopy(other.board)
        s.current_player = other.current_player
        s.move_history = list(other.move_history)
        s.scores = dict(other.scores)
        return s

    def get_piece(self, pos):
        r, c = pos
        return self.board[r][c]

    def get_player_pieces(self, pid):
        pv = pid + 1
        return [(r,c) for r,c in VALID_HOLES if self.board[r][c] == pv]

    def get_valid_moves(self, pid=None):
        if pid is None:
            pid = self.current_player
        moves = []
        for src in self.get_player_pieces(pid):
            for nbr in NEIGHBORS[src]:
                if self.board[nbr[0]][nbr[1]] == 0:
                    moves.append((src, nbr))
            self._collect_jumps(src, moves)
        return moves

    def _collect_jumps(self, src, moves):
        """
        BFS 收集从 src 出发的所有连跳终点。
        关键在于：起跳点 → 跳板 → 落点必须三点共线（同一六边形方向）。
        """
        visited_over = {src}              # 已作为跳板的棋子
        q = deque([src])

        while q:
            cur = q.popleft()
            for nbr in NEIGHBORS[cur]:
                # 跳板必须有棋子，且未被本回合使用过
                if nbr in visited_over or self.board[nbr[0]][nbr[1]] == 0:
                    continue

                # 确定跳的方向（0-5）
                key = (cur[0], cur[1], nbr[0], nbr[1])
                direction = _DIRECTION_MAP.get(key)
                if direction is None:
                    continue

                # 沿同一方向再走一步 = 落点
                land = _hex_step(nbr[0], nbr[1], direction)

                # 落点必须有效、为空、未被访问
                if land not in VALID_HOLES or land in visited_over:
                    continue
                if self.board[land[0]][land[1]] != 0:
                    continue

                # 有效跳跃！
                moves.append((src, land))
                visited_over.add(nbr)
                q.append(land)

    def apply_move(self, move):
        ns = BoardState.copy_from(self)
        (fr, fc), (tr, tc) = move
        pv = ns.board[fr][fc]
        ns.board[fr][fc] = 0
        ns.board[tr][tc] = pv
        pid = pv - 1
        ns.move_history.append((fr, fc, tr, tc, pid))
        ns._update_score(pid)
        ns._next_turn()
        return ns

    def _update_score(self, pid):
        pv = pid + 1
        self.scores[pid] = sum(
            1 for pos in GOAL_SETS[pid]
            if self.board[pos[0]][pos[1]] == pv
        )

    def _next_turn(self):
        idx = self.active_players.index(self.current_player)
        self.current_player = self.active_players[
            (idx + 1) % len(self.active_players)
        ]

    def undo_move(self):
        if not self.move_history:
            return False
        fr, fc, tr, tc, pid = self.move_history.pop()
        pv = pid + 1
        self.board[tr][tc] = 0
        self.board[fr][fc] = pv
        self.current_player = pid
        self._update_score(pid)
        return True

    def is_goal_reached(self, pid=None):
        if pid is None:
            pid = self.current_player
        return self.scores[pid] >= cfg.PIECES_PER_PLAYER

    def get_winner(self):
        for pid in self.active_players:
            if self.is_goal_reached(pid):
                return pid
        return None

    def is_terminal(self):
        return self.get_winner() is not None

    def to_dict(self):
        """序列化为前端可用的 JSON。"""
        pieces = {}
        for pid in self.active_players:
            pieces[str(pid)] = self.get_player_pieces(pid)
        return {
            "current_player": self.current_player,
            "active_players": self.active_players,
            "pieces": pieces,
            "scores": {str(k): v for k, v in self.scores.items()},
            "move_count": len(self.move_history),
            "winner": self.get_winner(),
            "is_terminal": self.is_terminal(),
        }
