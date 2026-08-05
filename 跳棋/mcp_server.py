"""Standalone MCP server exposing persisted Chinese Checkers data and calculations."""

from __future__ import annotations

import argparse
import json
import time
from typing import Any

import config as cfg
from database import get_database
from game_tools import (
    evaluate_move as tool_evaluate_move,
    evaluate_position as tool_evaluate_position,
    get_board_geometry as tool_get_board_geometry,
    get_game_metadata as tool_get_game_metadata,
    get_game_state as tool_get_game_state,
    get_game_statistics as tool_get_game_statistics,
    get_legal_moves as tool_get_legal_moves,
    get_move_history as tool_get_move_history,
    rank_candidate_moves as tool_rank_candidate_moves,
    recommend_move as tool_recommend_move,
    simulate_moves as tool_simulate_moves,
)
from replay import list_replays as replay_list, load_replay
from state_codec import state_from_dict

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:  # Allows the rest of the game to run without the optional MCP dependency.
    FastMCP = None

DB = get_database()
if FastMCP is not None:
    try:
        mcp = FastMCP(
            cfg.MCP_SERVER_NAME,
            stateless_http=True,
            json_response=True,
        )
    except TypeError:
        mcp = FastMCP(cfg.MCP_SERVER_NAME)
else:
    mcp = None


def _load_game(game_id: str) -> dict:
    record = DB.get_game(game_id)
    if record is None:
        raise ValueError(f"game not found: {game_id}")
    return {
        "game_id": game_id,
        "state": state_from_dict(record["state"]),
        "mode": record["mode"],
        "difficulty": record["difficulty"],
        "save_name": record["save_name"],
    }


def _audit(game_id: str | None, operation: str, arguments: dict, fn):
    started = time.perf_counter()
    success = True
    error = None
    result: Any = None
    try:
        result = fn()
        return result
    except Exception as exc:
        success = False
        error = str(exc)
        raise
    finally:
        DB.log_tool_call(
            game_id=game_id,
            source="mcp",
            operation=operation,
            arguments=arguments,
            result=result,
            success=success,
            error=error,
            duration_ms=(time.perf_counter() - started) * 1000,
        )


if mcp is not None:
    @mcp.tool()
    def list_games(limit: int = 20) -> dict:
        """List persisted games ordered by most recent activity."""
        return _audit(None, "list_games", {"limit": limit}, lambda: {"games": DB.list_games(limit)})

    @mcp.tool()
    def get_game_metadata(game_id: str) -> dict:
        """Read mode, difficulty, status, current player, and move count for a game."""
        return _audit(game_id, "get_game_metadata", {}, lambda: tool_get_game_metadata(_load_game(game_id)))

    @mcp.tool()
    def get_game_state(game_id: str) -> dict:
        """Read the complete persisted board state for a game."""
        return _audit(game_id, "get_game_state", {}, lambda: tool_get_game_state(_load_game(game_id)))

    @mcp.tool()
    def get_move_history(game_id: str, limit: int = 100) -> dict:
        """Read recent moves from a persisted game."""
        return _audit(game_id, "get_move_history", {"limit": limit}, lambda: tool_get_move_history(_load_game(game_id), limit))

    @mcp.tool()
    def get_ai_decisions(game_id: str) -> dict:
        """Read persisted AI selections, local candidates, difficulty, and timing."""
        return _audit(game_id, "get_ai_decisions", {}, lambda: {"decisions": DB.get_ai_decisions(game_id)})

    @mcp.tool()
    def get_evaluation_snapshots(game_id: str) -> dict:
        """Read persisted five-component evaluation snapshots."""
        return _audit(game_id, "get_evaluation_snapshots", {}, lambda: {"evaluations": DB.get_evaluation_snapshots(game_id)})

    @mcp.tool()
    def get_chat_history(game_id: str, limit: int = 50) -> dict:
        """Read SQL-backed user and assistant messages for a game."""
        return _audit(game_id, "get_chat_history", {"limit": limit}, lambda: {"messages": DB.get_chat_history(game_id, limit)})

    @mcp.tool()
    def get_tool_audit_logs(game_id: str, limit: int = 100) -> dict:
        """Read MCP and DeepSeek tool-call audit records for a game."""
        return _audit(game_id, "get_tool_audit_logs", {"limit": limit}, lambda: {"logs": DB.get_tool_logs(game_id, limit)})

    @mcp.tool()
    def list_replays() -> dict:
        """List file-based replay archives."""
        return _audit(None, "list_replays", {}, lambda: {"replays": replay_list()})

    @mcp.tool()
    def get_replay(name: str) -> dict:
        """Read one replay archive by name."""
        def run():
            replay = load_replay(name)
            if replay is None:
                raise ValueError(f"replay not found: {name}")
            return replay
        return _audit(None, "get_replay", {"name": name}, run)

    @mcp.tool()
    def get_board_geometry() -> dict:
        """Read board holes, home zones, goal zones, and piece count."""
        return _audit(None, "get_board_geometry", {}, tool_get_board_geometry)

    @mcp.tool()
    def get_legal_moves(game_id: str, player_id: int | None = None, from_row: int | None = None, from_col: int | None = None) -> dict:
        """Calculate legal single-step and multi-jump moves."""
        source = None if from_row is None or from_col is None else [from_row, from_col]
        args = {"player_id": player_id, "from_position": source}
        return _audit(game_id, "get_legal_moves", args, lambda: tool_get_legal_moves(_load_game(game_id), player_id, source))

    @mcp.tool()
    def evaluate_position(game_id: str, player_id: int | None = None) -> dict:
        """Calculate the five-component rule-driven position evaluation."""
        return _audit(game_id, "evaluate_position", {"player_id": player_id}, lambda: tool_evaluate_position(_load_game(game_id), player_id))

    @mcp.tool()
    def evaluate_move(game_id: str, from_row: int, from_col: int, to_row: int, to_col: int, player_id: int | None = None) -> dict:
        """Validate and evaluate one move, including before/after components."""
        args = {"from": [from_row, from_col], "to": [to_row, to_col], "player_id": player_id}
        return _audit(game_id, "evaluate_move", args, lambda: tool_evaluate_move(_load_game(game_id), args["from"], args["to"], player_id))

    @mcp.tool()
    def rank_candidate_moves(game_id: str, player_id: int | None = None, limit: int = 10) -> dict:
        """Rank legal moves by the shared position evaluation."""
        args = {"player_id": player_id, "limit": limit}
        return _audit(game_id, "rank_candidate_moves", args, lambda: tool_rank_candidate_moves(_load_game(game_id), player_id, limit))

    @mcp.tool()
    def recommend_move(game_id: str, difficulty: int | None = None, player_id: int | None = None) -> dict:
        """Run the existing easy, medium, or hard AI without changing the game."""
        args = {"difficulty": difficulty, "player_id": player_id}
        return _audit(game_id, "recommend_move", args, lambda: tool_recommend_move(_load_game(game_id), difficulty, player_id))

    @mcp.tool()
    def simulate_moves(game_id: str, moves: list[dict], max_steps: int = 16) -> dict:
        """Simulate a legal line on a copy of the board without mutating persisted data."""
        args = {"moves": moves, "max_steps": max_steps}
        return _audit(game_id, "simulate_moves", args, lambda: tool_simulate_moves(_load_game(game_id), moves, max_steps))

    @mcp.tool()
    def get_game_statistics(game_id: str) -> dict:
        """Read SQL aggregate statistics and current evaluation statistics."""
        def run():
            result = DB.get_statistics(game_id)
            result["position"] = tool_get_game_statistics(_load_game(game_id))
            return result
        return _audit(game_id, "get_game_statistics", {}, run)

    @mcp.resource("game://{game_id}/state")
    def game_state_resource(game_id: str) -> str:
        return json.dumps(tool_get_game_state(_load_game(game_id)), ensure_ascii=False)

    @mcp.resource("game://{game_id}/moves")
    def game_moves_resource(game_id: str) -> str:
        return json.dumps(DB.get_moves(game_id), ensure_ascii=False)

    @mcp.resource("game://{game_id}/chat")
    def game_chat_resource(game_id: str) -> str:
        return json.dumps(DB.get_chat_history(game_id, 100), ensure_ascii=False)

    @mcp.resource("game://{game_id}/ai-decisions")
    def game_ai_decisions_resource(game_id: str) -> str:
        return json.dumps(DB.get_ai_decisions(game_id), ensure_ascii=False)

    @mcp.resource("game://{game_id}/evaluations")
    def game_evaluations_resource(game_id: str) -> str:
        return json.dumps(DB.get_evaluation_snapshots(game_id), ensure_ascii=False)

    @mcp.prompt()
    def analyze_chinese_checkers_position(game_id: str, question: str = "分析当前局面") -> str:
        """Prompt template for a tool-grounded Chinese Checkers analysis."""
        return (
            "请先调用 get_game_state、evaluate_position 和 rank_candidate_moves，"
            f"再回答：{question}。game_id={game_id}。不得编造非法走法。"
        )


def main() -> None:
    if mcp is None:
        raise SystemExit("MCP dependency is not installed. Run: pip install -r requirements.txt")
    parser = argparse.ArgumentParser(description="Chinese Checkers MCP server")
    parser.add_argument(
        "--transport",
        choices=("stdio", "streamable-http"),
        default=cfg.MCP_TRANSPORT,
    )
    args = parser.parse_args()

    if args.transport == "stdio":
        mcp.run(transport="stdio")
        return

    import uvicorn

    app = mcp.streamable_http_app()
    uvicorn.run(
        app,
        host=cfg.MCP_HOST,
        port=cfg.MCP_PORT,
        log_level="info",
        access_log=True,
    )


if __name__ == "__main__":
    main()
