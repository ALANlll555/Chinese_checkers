"""SQLite persistence for games, moves, evaluations, chat, and MCP audit logs."""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable

import config as cfg


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


class GameDatabase:
    """Small, thread-safe SQLite repository using one connection per operation."""

    def __init__(self, path: str | Path | None = None, schema_path: str | Path | None = None):
        self.path = Path(path or cfg.DATABASE_PATH)
        self.schema_path = Path(schema_path or cfg.DATABASE_SCHEMA_PATH)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_lock = threading.Lock()
        self.initialize()

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=10.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA busy_timeout = 10000")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        with self._init_lock:
            schema = self.schema_path.read_text(encoding="utf-8")
            with self.connect() as connection:
                connection.executescript(schema)
                columns = {
                    row["name"] for row in connection.execute("PRAGMA table_info(chat_messages)")
                }
                if "metadata_json" not in columns:
                    connection.execute(
                        "ALTER TABLE chat_messages ADD COLUMN metadata_json TEXT NOT NULL DEFAULT '{}'"
                    )
                connection.execute(
                    "INSERT INTO schema_meta(key, value) VALUES('schema_version','3') "
                    "ON CONFLICT(key) DO UPDATE SET value='3'"
                )

    def create_game(
        self,
        game_id: str,
        state: dict,
        mode: str,
        difficulty: int,
        num_players: int,
        human_first: bool,
        save_name: str = "",
    ) -> None:
        status = "finished" if state.get("is_terminal") else "active"
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO games (
                    game_id, mode, difficulty, num_players, human_first,
                    save_name, status, winner, current_player, state_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(game_id) DO UPDATE SET
                    mode=excluded.mode,
                    difficulty=excluded.difficulty,
                    num_players=excluded.num_players,
                    human_first=excluded.human_first,
                    save_name=excluded.save_name,
                    status=excluded.status,
                    winner=excluded.winner,
                    current_player=excluded.current_player,
                    state_json=excluded.state_json,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (
                    game_id, mode, int(difficulty), int(num_players), int(human_first),
                    save_name, status, state.get("winner"), state["current_player"], _json(state),
                ),
            )

    def update_game_state(self, game_id: str, state: dict) -> None:
        status = "finished" if state.get("is_terminal") else "active"
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE games
                SET state_json=?, current_player=?, winner=?, status=?, updated_at=CURRENT_TIMESTAMP
                WHERE game_id=?
                """,
                (_json(state), state["current_player"], state.get("winner"), status, game_id),
            )

    def rename_save_name(self, old_name: str, new_name: str) -> None:
        with self.connect() as connection:
            connection.execute(
                "UPDATE games SET save_name=?, updated_at=CURRENT_TIMESTAMP WHERE save_name=?",
                (new_name, old_name),
            )

    def clear_save_name(self, name: str) -> None:
        with self.connect() as connection:
            connection.execute(
                "UPDATE games SET save_name='', updated_at=CURRENT_TIMESTAMP WHERE save_name=?",
                (name,),
            )

    def record_move(
        self,
        game_id: str,
        move_index: int,
        player_id: int,
        actor: str,
        move,
        state_before: dict,
        state_after: dict,
        eval_before: float | None = None,
        eval_after: float | None = None,
    ) -> None:
        (fr, fc), (tr, tc) = move
        with self.connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO moves (
                    game_id, move_index, player_id, actor,
                    from_row, from_col, to_row, to_col,
                    state_before_json, state_after_json, eval_before, eval_after
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    game_id, int(move_index), int(player_id), actor,
                    int(fr), int(fc), int(tr), int(tc),
                    _json(state_before), _json(state_after), eval_before, eval_after,
                ),
            )
            connection.execute(
                """
                UPDATE games
                SET state_json=?, current_player=?, winner=?, status=?, updated_at=CURRENT_TIMESTAMP
                WHERE game_id=?
                """,
                (
                    _json(state_after), state_after["current_player"], state_after.get("winner"),
                    "finished" if state_after.get("is_terminal") else "active", game_id,
                ),
            )

    def record_ai_decision(
        self,
        game_id: str,
        move_index: int,
        player_id: int,
        difficulty: int,
        selected_move,
        candidates: Iterable | None = None,
        elapsed_ms: float | None = None,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO ai_decisions (
                    game_id, move_index, player_id, difficulty,
                    selected_move_json, candidates_json, elapsed_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    game_id, int(move_index), int(player_id), int(difficulty),
                    _json(selected_move), _json(list(candidates or [])), elapsed_ms,
                ),
            )

    def record_evaluation(
        self,
        game_id: str,
        move_index: int,
        player_id: int,
        context: str,
        components: dict,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO evaluation_snapshots (
                    game_id, move_index, player_id, context, score, components_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    game_id, int(move_index), int(player_id), context,
                    float(components.get("score", 0.0)), _json(components),
                ),
            )

    def undo_moves(self, game_id: str, keep_move_count: int, state: dict) -> None:
        with self.connect() as connection:
            connection.execute(
                "DELETE FROM evaluation_snapshots WHERE game_id=? AND move_index>?",
                (game_id, int(keep_move_count)),
            )
            connection.execute(
                "DELETE FROM ai_decisions WHERE game_id=? AND move_index>?",
                (game_id, int(keep_move_count)),
            )
            connection.execute(
                "DELETE FROM moves WHERE game_id=? AND move_index>?",
                (game_id, int(keep_move_count)),
            )
            connection.execute(
                """
                UPDATE games
                SET state_json=?, current_player=?, winner=?, status=?, updated_at=CURRENT_TIMESTAMP
                WHERE game_id=?
                """,
                (
                    _json(state), state["current_player"], state.get("winner"),
                    "finished" if state.get("is_terminal") else "active", game_id,
                ),
            )

    def append_chat_message(
        self,
        game_id: str,
        role: str,
        content: str,
        model: str | None = None,
        tool_name: str | None = None,
        tool_call_id: str | None = None,
        metadata: dict | None = None,
    ) -> int:
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO chat_messages (
                    game_id, role, content, model, tool_name, tool_call_id, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (game_id, role, content, model, tool_name, tool_call_id, _json(metadata or {})),
            )
            return int(cursor.lastrowid)

    def get_chat_history(self, game_id: str, limit: int = 50) -> list[dict]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, role, content, model, tool_name, tool_call_id,
                       metadata_json, created_at
                FROM (
                    SELECT * FROM chat_messages WHERE game_id=? ORDER BY id DESC LIMIT ?
                ) ORDER BY id ASC
                """,
                (game_id, max(1, int(limit))),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            raw_metadata = item.pop("metadata_json", "{}") or "{}"
            try:
                item["metadata"] = json.loads(raw_metadata)
            except (TypeError, json.JSONDecodeError):
                item["metadata"] = {}
            result.append(item)
        return result

    def clear_chat(self, game_id: str) -> None:
        with self.connect() as connection:
            connection.execute("DELETE FROM chat_messages WHERE game_id=?", (game_id,))

    def get_game(self, game_id: str) -> dict | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM games WHERE game_id=?", (game_id,)).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["state"] = json.loads(result.pop("state_json"))
        return result

    def list_games(self, limit: int = 20) -> list[dict]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT game_id, mode, difficulty, num_players, human_first,
                       save_name, status, winner, current_player, created_at, updated_at
                FROM games ORDER BY updated_at DESC LIMIT ?
                """,
                (max(1, min(int(limit), 200)),),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_moves(self, game_id: str) -> list[dict]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT move_index, player_id, actor, from_row, from_col,
                       to_row, to_col, eval_before, eval_after, created_at
                FROM moves WHERE game_id=? ORDER BY move_index ASC
                """,
                (game_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_ai_decisions(self, game_id: str) -> list[dict]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT move_index, player_id, difficulty, selected_move_json,
                       candidates_json, elapsed_ms, created_at
                FROM ai_decisions WHERE game_id=? ORDER BY move_index ASC
                """,
                (game_id,),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["selected_move"] = json.loads(item.pop("selected_move_json"))
            item["candidates"] = json.loads(item.pop("candidates_json"))
            result.append(item)
        return result

    def get_evaluation_snapshots(self, game_id: str) -> list[dict]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT move_index, player_id, context, score, components_json, created_at
                FROM evaluation_snapshots WHERE game_id=? ORDER BY id ASC
                """,
                (game_id,),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["components"] = json.loads(item.pop("components_json"))
            result.append(item)
        return result

    def get_tool_logs(self, game_id: str, limit: int = 100) -> list[dict]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT request_id, source, operation, arguments_json, result_json,
                       success, error, duration_ms, created_at
                FROM mcp_audit_logs WHERE game_id=? ORDER BY id DESC LIMIT ?
                """,
                (game_id, max(1, min(int(limit), 500))),
            ).fetchall()
        result = []
        for row in reversed(rows):
            item = dict(row)
            item["arguments"] = json.loads(item.pop("arguments_json"))
            raw_result = item.pop("result_json")
            item["result"] = json.loads(raw_result) if raw_result else None
            item["success"] = bool(item["success"])
            result.append(item)
        return result

    def get_statistics(self, game_id: str) -> dict:
        game = self.get_game(game_id)
        if game is None:
            raise KeyError(f"game not found: {game_id}")
        with self.connect() as connection:
            move_rows = connection.execute(
                """
                SELECT player_id, actor, COUNT(*) AS move_count,
                       AVG(CASE WHEN eval_before IS NOT NULL AND eval_after IS NOT NULL
                                THEN eval_after - eval_before END) AS avg_eval_gain
                FROM moves WHERE game_id=? GROUP BY player_id, actor
                """,
                (game_id,),
            ).fetchall()
            chat_count = connection.execute(
                "SELECT COUNT(*) FROM chat_messages WHERE game_id=?", (game_id,)
            ).fetchone()[0]
            tool_count = connection.execute(
                "SELECT COUNT(*) FROM mcp_audit_logs WHERE game_id=?", (game_id,)
            ).fetchone()[0]
        return {
            "game_id": game_id,
            "status": game["status"],
            "winner": game["winner"],
            "current_player": game["current_player"],
            "move_count": game["state"].get("move_count", 0),
            "moves_by_player": [dict(row) for row in move_rows],
            "chat_message_count": int(chat_count),
            "tool_call_count": int(tool_count),
        }

    def log_tool_call(
        self,
        game_id: str | None,
        source: str,
        operation: str,
        arguments: dict,
        result: Any,
        success: bool,
        duration_ms: float,
        error: str | None = None,
        request_id: str | None = None,
    ) -> str:
        request_id = request_id or str(uuid.uuid4())
        result_json = None if result is None else _json(result)
        if result_json is not None and len(result_json) > cfg.MCP_AUDIT_RESULT_MAX_CHARS:
            result_json = _json({
                "truncated": True,
                "original_chars": len(result_json),
                "preview": result_json[: cfg.MCP_AUDIT_RESULT_MAX_CHARS],
            })
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO mcp_audit_logs (
                    request_id, game_id, source, operation, arguments_json,
                    result_json, success, error, duration_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    request_id, game_id, source, operation, _json(arguments),
                    result_json, int(success), error, float(duration_ms),
                ),
            )
        return request_id


_DB: GameDatabase | None = None
_DB_LOCK = threading.Lock()


def get_database() -> GameDatabase:
    global _DB
    if _DB is None:
        with _DB_LOCK:
            if _DB is None:
                _DB = GameDatabase()
    return _DB
