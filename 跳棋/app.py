"""Chinese Checkers Flask web service with AI chat, MCP tooling, and SQL persistence."""

from __future__ import annotations

import importlib.util
import json
import os
import queue
import threading
import time
import uuid

import requests

from flask import (
    Flask, Response, jsonify, render_template, request, session,
    stream_with_context,
)

from ai import evaluate, evaluate_components, get_ai_move, get_local_candidates
from board import BoardState
import config as cfg
from database import get_database
from deepseek_chat import DeepSeekChatService
from game_tools import MCP_TOOL_NAMES
from llm_comment import get_comment
from replay import list_replays, load_replay, save_replay
from state_codec import state_from_dict

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "chinese_checkers_neon_2024")
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0

# In-memory states keep gameplay fast; every state-changing action is mirrored to SQL.
GAMES: dict[str, dict] = {}
DB = get_database()
CHAT = DeepSeekChatService(DB)


def _get_game() -> dict | None:
    """Return the active game, hydrating it from SQL after a server restart."""
    game_id = session.get("game_id")
    if not game_id:
        return None
    if game_id in GAMES:
        return GAMES[game_id]

    record = DB.get_game(game_id)
    if record is None:
        return None
    state = state_from_dict(record["state"])
    game = {
        "game_id": game_id,
        "state": state,
        "mode": record["mode"],
        "difficulty": record["difficulty"],
        "num_players": record["num_players"],
        "human_first": bool(record["human_first"]),
        "save_name": record["save_name"],
        "api_key": "",
        "deepseek_settings": _normalize_deepseek_settings({}),
        "move_history": [
            {"from": [fr, fc], "to": [tr, tc], "player": pid}
            for fr, fc, tr, tc, pid in state.move_history
        ],
    }
    GAMES[game_id] = game
    return game


def _safe_bool(value, default: bool) -> bool:
    if value is None:
        return bool(default)
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "yes", "on", "enabled"}


def _normalize_deepseek_settings(raw: dict | None, api_key: str = "") -> dict:
    source = raw if isinstance(raw, dict) else {}
    effort = str(
        source.get("reasoning_effort") or cfg.LLM_REASONING_EFFORT
    ).strip().lower()
    if effort not in {"low", "high", "xhigh", "max"}:
        effort = cfg.LLM_REASONING_EFFORT
    try:
        max_tokens = int(source.get("max_tokens") or cfg.LLM_CHAT_MAX_TOKENS)
    except (TypeError, ValueError):
        max_tokens = cfg.LLM_CHAT_MAX_TOKENS
    return {
        "api_key": str(source.get("api_key") or api_key or "").strip(),
        "base_url": str(
            source.get("base_url") or cfg.LLM_API_BASE
        ).strip().rstrip("/"),
        "model": str(source.get("model") or cfg.LLM_MODEL).strip(),
        "thinking": _safe_bool(source.get("thinking"), cfg.LLM_THINKING),
        "show_reasoning": _safe_bool(
            source.get("show_reasoning"), cfg.LLM_SHOW_REASONING_DEFAULT
        ),
        "context_1m": _safe_bool(
            source.get("context_1m"), cfg.LLM_CONTEXT_1M_DEFAULT
        ),
        "strict_tools": _safe_bool(
            source.get("strict_tools"), cfg.LLM_STRICT_TOOLS
        ),
        "reasoning_effort": effort,
        "max_tokens": max(256, min(32768, max_tokens)),
    }


def _public_deepseek_settings(settings: dict | None) -> dict:
    normalized = _normalize_deepseek_settings(settings)
    normalized.pop("api_key", None)
    return normalized

def _auto_save(game: dict) -> None:
    """Keep the existing file replay behavior without blocking a move response."""
    def _save():
        try:
            name = game.get("save_name", "")
            if not name:
                return
            save_replay(
                name,
                game["state"].to_dict(),
                game["mode"],
                game["difficulty"],
                game["move_history"],
            )
        except Exception:
            pass

    threading.Thread(target=_save, daemon=True).start()


@app.route("/")
def index():
    response = app.make_response(render_template("index.html"))
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@app.route("/api/new_game", methods=["POST"])
def api_new_game():
    data = request.get_json() or {}
    num_players = int(data.get("num_players", 2))
    mode = data.get("mode", "pvp")
    difficulty = int(data.get("difficulty", 2))
    human_first = bool(data.get("human_first", True))
    save_name = data.get("save_name", "").strip()
    api_key = data.get("api_key", "").strip()
    deepseek_settings = _normalize_deepseek_settings(
        data.get("deepseek_settings"), api_key=api_key
    )
    api_key = deepseek_settings.pop("api_key", api_key)

    state = BoardState.new_game(num_players)
    if mode == "pve" and not human_first:
        ai_players = [pid for pid in state.active_players if pid != 0]
        if ai_players:
            state.current_player = ai_players[0]

    game_id = str(uuid.uuid4())[:8]
    game = {
        "game_id": game_id,
        "state": state,
        "mode": mode,
        "difficulty": difficulty,
        "num_players": num_players,
        "human_first": human_first,
        "move_history": [],
        "save_name": save_name,
        # API keys are intentionally memory-only and never written to SQL or replay files.
        "api_key": api_key,
        "deepseek_settings": deepseek_settings,
    }
    GAMES[game_id] = game
    session["game_id"] = game_id
    DB.create_game(
        game_id=game_id,
        state=state.to_dict(),
        mode=mode,
        difficulty=difficulty,
        num_players=num_players,
        human_first=human_first,
        save_name=save_name,
    )

    return jsonify({
        "game_id": game_id,
        "mode": mode,
        "difficulty": difficulty,
        "chat_enabled": True,
        "deepseek_configured": bool(api_key or cfg.LLM_API_KEY),
        "deepseek_thinking_default": cfg.LLM_THINKING,
        "deepseek_show_reasoning_default": cfg.LLM_SHOW_REASONING_DEFAULT,
        "deepseek_context_1m_default": cfg.LLM_CONTEXT_1M_DEFAULT,
        "deepseek_settings": _public_deepseek_settings(deepseek_settings),
        "local_coach_enabled": True,
        **state.to_dict(),
    })


@app.route("/api/move", methods=["POST"])
def api_move():
    game = _get_game()
    if not game:
        return jsonify({"error": "无活跃对局"}), 400

    state: BoardState = game["state"]
    data = request.get_json() or {}
    try:
        move = (tuple(data["from"]), tuple(data["to"]))
    except (KeyError, TypeError):
        return jsonify({"error": "走法参数不完整"}), 400

    if move not in state.get_valid_moves():
        return jsonify({"error": "非法走法"}), 400

    player_id = state.current_player
    state_before = state.to_dict()
    state = state.apply_move(move)
    state_after = state.to_dict()
    game["state"] = state
    game["move_history"].append({
        "from": list(move[0]), "to": list(move[1]), "player": player_id,
    })
    DB.record_move(
        game_id=game["game_id"],
        move_index=len(state.move_history),
        player_id=player_id,
        actor="human",
        move=move,
        state_before=state_before,
        state_after=state_after,
    )
    _auto_save(game)

    return jsonify({
        **state_after,
        "need_ai": game["mode"] == "pve" and not state.is_terminal(),
    })


@app.route("/api/ai_move", methods=["POST"])
def api_ai_move():
    """Calculate and apply one AI move, then persist the full decision record."""
    game = _get_game()
    if not game:
        return jsonify({"error": "无活跃对局"}), 400

    state: BoardState = game["state"]
    if state.is_terminal():
        return jsonify(state.to_dict())

    player_id = state.current_player
    state_before = state.to_dict()
    eval_before_components = evaluate_components(state, player_id)
    candidates = get_local_candidates(state, game["difficulty"])
    started = time.perf_counter()
    ai_move = get_ai_move(state, game["difficulty"])
    elapsed_ms = (time.perf_counter() - started) * 1000
    if not ai_move:
        return jsonify(state.to_dict())

    state = state.apply_move(ai_move)
    state_after = state.to_dict()
    game["state"] = state
    game["move_history"].append({
        "from": list(ai_move[0]), "to": list(ai_move[1]), "player": player_id,
    })
    eval_after_components = evaluate_components(state, player_id)
    move_index = len(state.move_history)

    DB.record_move(
        game_id=game["game_id"],
        move_index=move_index,
        player_id=player_id,
        actor="ai",
        move=ai_move,
        state_before=state_before,
        state_after=state_after,
        eval_before=eval_before_components["score"],
        eval_after=eval_after_components["score"],
    )
    DB.record_ai_decision(
        game_id=game["game_id"],
        move_index=move_index,
        player_id=player_id,
        difficulty=game["difficulty"],
        selected_move={"from": list(ai_move[0]), "to": list(ai_move[1])},
        candidates=[{"from": list(move[0]), "to": list(move[1])} for move in candidates],
        elapsed_ms=elapsed_ms,
    )
    DB.record_evaluation(
        game["game_id"], move_index, player_id, "before_ai_move", eval_before_components
    )
    DB.record_evaluation(
        game["game_id"], move_index, player_id, "after_ai_move", eval_after_components
    )
    _auto_save(game)

    game["_last_comment_ctx"] = {
        "state_dict": state_after,
        "move": ai_move,
        "eval_before": eval_before_components["score"],
        "eval_after": eval_after_components["score"],
        "player_pid": player_id,
    }

    return jsonify({
        **state_after,
        "ai_move": {
            "from": list(ai_move[0]),
            "to": list(ai_move[1]),
            "player": player_id,
        },
    })


@app.route("/api/undo", methods=["POST"])
def api_undo():
    game = _get_game()
    if not game:
        return jsonify({"error": "无活跃对局"}), 400

    state: BoardState = game["state"]
    requested = 2 if game["mode"] == "pve" else 1
    removed = 0
    for _ in range(requested):
        if state.undo_move():
            removed += 1
    if removed:
        game["move_history"] = game["move_history"][:-removed]
    game.pop("_last_comment_ctx", None)
    state_dict = state.to_dict()
    DB.undo_moves(game["game_id"], len(state.move_history), state_dict)
    _auto_save(game)
    return jsonify(state_dict)


@app.route("/api/hint", methods=["POST"])
def api_hint():
    game = _get_game()
    if not game:
        return jsonify({"error": "无活跃对局"}), 400
    move = get_ai_move(game["state"], 3)
    if move:
        return jsonify({"from": list(move[0]), "to": list(move[1])})
    return jsonify({"error": "无可用走法"}), 400


@app.route("/api/comment", methods=["GET"])
def api_comment():
    game = _get_game()
    if not game:
        return jsonify({"error": "无活跃对局"}), 400
    context = game.get("_last_comment_ctx")
    if not context:
        return jsonify({"comment": ""})
    try:
        comment = get_comment(
            context["state_dict"],
            context["move"],
            context["eval_before"],
            context["eval_after"],
            context["player_pid"],
            api_key=game.get("api_key"),
        )
        return jsonify({"comment": comment})
    except Exception:
        return jsonify({"comment": ""})


@app.route("/api/deepseek/test", methods=["POST"])
def api_deepseek_test():
    payload = request.get_json() or {}
    settings = _normalize_deepseek_settings(payload)
    api_key = settings.pop("api_key", "")
    if not api_key:
        return jsonify({"error": "请先填写 DeepSeek API Key"}), 400

    base = settings["base_url"].rstrip("/")
    if base.endswith("/v1"):
        base = base[:-3]
    if base.endswith("/beta"):
        base = base[:-5]
    endpoint = (
        f"{base}/beta/chat/completions"
        if settings["strict_tools"]
        else f"{base}/chat/completions"
    )
    request_payload = {
        "model": settings["model"],
        "messages": [{"role": "user", "content": "只回复 OK"}],
        "max_tokens": 16,
        "thinking": {"type": "disabled"},
    }
    started = time.perf_counter()
    try:
        response = requests.post(
            endpoint,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=request_payload,
            timeout=min(cfg.LLM_TIMEOUT_SECONDS, 20),
        )
        response.raise_for_status()
        data = response.json()
        if not (data.get("choices") or []):
            raise RuntimeError("模型未返回 choices")
        return jsonify({
            "ok": True,
            "model": settings["model"],
            "elapsed_seconds": round(time.perf_counter() - started, 3),
        })
    except Exception as exc:
        return jsonify({
            "error": f"DeepSeek 配置测试失败：{str(exc)[:240]}",
            "elapsed_seconds": round(time.perf_counter() - started, 3),
        }), 502

@app.route("/api/chat", methods=["POST"])
def api_chat():
    game = _get_game()
    if not game:
        return jsonify({"error": "请先开始一局游戏"}), 400
    payload = request.get_json() or {}
    message = payload.get("message", "")
    options = {
        "thinking": payload.get("thinking"),
        "show_reasoning": payload.get("show_reasoning"),
        "context_1m": payload.get("context_1m"),
    }
    try:
        return jsonify(CHAT.reply(game, message, options=options))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

@app.route("/api/chat/stream", methods=["POST"])
def api_chat_stream():
    """Stream reasoning/tool lifecycle events without changing Coach logic."""
    game = _get_game()
    if not game:
        return jsonify({"error": "请先开始一局游戏"}), 400

    payload = request.get_json() or {}
    message = payload.get("message", "")
    options = {
        "thinking": payload.get("thinking"),
        "show_reasoning": payload.get("show_reasoning"),
        "context_1m": payload.get("context_1m"),
    }

    events: queue.Queue = queue.Queue()
    finished = object()
    stream_state = {
        "label": "正在准备分析",
        "started": time.perf_counter(),
    }

    def publish(event: dict) -> None:
        event_type = event.get("type")
        if event_type == "phase" and event.get("label"):
            stream_state["label"] = event["label"]
        elif event_type == "tool_start":
            stream_state["label"] = (
                f"MCP 正在调用：{event.get('label') or event.get('name') or '工具'}"
            )
        elif event_type == "tool_end":
            stream_state["label"] = "MCP 调用完成，正在综合工具结果"
        elif event_type == "reasoning":
            stream_state["label"] = "DeepSeek 推理内容已更新"
        events.put(event)

    def worker() -> None:
        try:
            CHAT.reply(
                game,
                message,
                options=options,
                event_callback=publish,
            )
        except ValueError as exc:
            publish({"type": "error", "message": str(exc)})
        except Exception as exc:
            publish({
                "type": "error",
                "message": f"AI 助手处理失败：{str(exc)[:240]}",
            })
        finally:
            events.put(finished)

    thread = threading.Thread(
        target=worker,
        name=f"deepseek-stream-{game['game_id'][:8]}",
        daemon=True,
    )
    thread.start()

    @stream_with_context
    def generate():
        # Flush proxy/browser buffers before the first model event.
        yield ": connected\n\n"
        while True:
            try:
                event = events.get(timeout=1.0)
            except queue.Empty:
                heartbeat = {
                    "type": "heartbeat",
                    "label": stream_state["label"],
                    "elapsed_seconds": round(
                        time.perf_counter() - stream_state["started"], 1
                    ),
                }
                payload_text = json.dumps(
                    heartbeat,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                yield f"data: {payload_text}\n\n"
                continue

            if event is finished:
                break

            payload_text = json.dumps(
                event,
                ensure_ascii=False,
                separators=(",", ":"),
                default=str,
            )
            yield f"data: {payload_text}\n\n"

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )

@app.route("/api/chat/history", methods=["GET"])
def api_chat_history():
    game = _get_game()
    if not game:
        return jsonify({"messages": []})
    return jsonify({"messages": DB.get_chat_history(game["game_id"], 100)})


@app.route("/api/chat/clear", methods=["POST"])
def api_chat_clear():
    game = _get_game()
    if not game:
        return jsonify({"error": "无活跃对局"}), 400
    DB.clear_chat(game["game_id"])
    return jsonify({"ok": True})


@app.route("/api/system/status", methods=["GET"])
def api_system_status():
    game = _get_game()
    return jsonify({
        "game_active": bool(game),
        "game_id": game.get("game_id") if game else None,
        "deepseek_configured": bool((game or {}).get("api_key") or cfg.LLM_API_KEY),
        "deepseek_model": cfg.LLM_MODEL,
        "deepseek_base_url": cfg.LLM_API_BASE,
        "deepseek_max_tokens": cfg.LLM_CHAT_MAX_TOKENS,
        "deepseek_strict_tools_default": cfg.LLM_STRICT_TOOLS,
        "deepseek_context_window_tokens": cfg.LLM_CONTEXT_WINDOW_TOKENS,
        "deepseek_input_budget_tokens": cfg.LLM_INPUT_BUDGET_TOKENS,
        "deepseek_standard_context_window_tokens": cfg.LLM_STANDARD_CONTEXT_WINDOW_TOKENS,
        "deepseek_standard_input_budget_tokens": cfg.LLM_STANDARD_INPUT_BUDGET_TOKENS,
        "deepseek_thinking_default": cfg.LLM_THINKING,
        "deepseek_show_reasoning_default": cfg.LLM_SHOW_REASONING_DEFAULT,
        "deepseek_context_1m_default": cfg.LLM_CONTEXT_1M_DEFAULT,
        "deepseek_reasoning_effort": cfg.LLM_REASONING_EFFORT,
        "local_coach_enabled": True,
        "database": "sqlite",
        "mcp_installed": importlib.util.find_spec("mcp") is not None,
        "mcp_transport": cfg.MCP_TRANSPORT,
    })


@app.route("/api/mcp/manifest", methods=["GET"])
def api_mcp_manifest():
    return jsonify({
        "server": cfg.MCP_SERVER_NAME,
        "entrypoint": "python mcp_server.py --transport stdio",
        "transports": ["stdio", "streamable-http"],
        "read_only": True,
        "tools": list(MCP_TOOL_NAMES),
        "resources": [
            "game://{game_id}/state",
            "game://{game_id}/moves",
            "game://{game_id}/chat",
            "game://{game_id}/ai-decisions",
            "game://{game_id}/evaluations",
        ],
    })


@app.route("/api/state", methods=["GET"])
def api_state():
    game = _get_game()
    if not game:
        return jsonify({"error": "无活跃对局"}), 400
    return jsonify(game["state"].to_dict())


@app.route("/api/legal_moves", methods=["GET"])
def api_legal_moves():
    game = _get_game()
    if not game:
        return jsonify({"error": "无活跃对局"}), 400
    row = request.args.get("r", type=int)
    col = request.args.get("c", type=int)
    if row is None or col is None:
        return jsonify({"error": "缺少 r/c 参数"}), 400
    moves = game["state"].get_valid_moves()
    targets = [list(to) for source, to in moves if source == (row, col)]
    return jsonify({"from": [row, col], "targets": targets})


@app.route("/api/replays", methods=["GET"])
def api_replays():
    return jsonify(list_replays())


@app.route("/api/load_replay/<game_id>", methods=["GET"])
def api_load_replay(game_id):
    data = load_replay(game_id)
    if not data:
        return jsonify({"error": "棋谱不存在"}), 404
    return jsonify(data)


@app.route("/api/archive/<name>", methods=["DELETE"])
def api_delete_archive(name):
    import shutil
    directory = os.path.join(cfg.REPLAY_DIR, name)
    if os.path.isdir(directory):
        shutil.rmtree(directory)
    DB.clear_save_name(name)
    return jsonify({"ok": True})


@app.route("/api/archive/<name>", methods=["PUT"])
def api_rename_archive(name):
    import json
    new_name = (request.get_json() or {}).get("name", "").strip()
    if not new_name:
        return jsonify({"error": "名称不能为空"}), 400
    old = os.path.join(cfg.REPLAY_DIR, name)
    new = os.path.join(cfg.REPLAY_DIR, new_name)
    if os.path.exists(new):
        return jsonify({"error": "名称已存在"}), 409
    if not os.path.isdir(old):
        return jsonify({"error": "原存档不存在"}), 404
    os.rename(old, new)
    replay_path = os.path.join(new, "replay.json")
    if os.path.exists(replay_path):
        with open(replay_path, "r+", encoding="utf-8") as file:
            data = json.load(file)
            data["name"] = new_name
            file.seek(0)
            json.dump(data, file, ensure_ascii=False, indent=2)
            file.truncate()
    DB.rename_save_name(name, new_name)
    for game in GAMES.values():
        if game.get("save_name") == name:
            game["save_name"] = new_name
    return jsonify({"ok": True, "name": new_name})


@app.route("/api/archive/check/<name>", methods=["GET"])
def api_check_archive(name):
    return jsonify({"exists": os.path.isdir(os.path.join(cfg.REPLAY_DIR, name))})


if __name__ == "__main__":
    app.run(
        debug=False,
        use_reloader=False,
        host=cfg.APP_HOST,
        port=cfg.APP_PORT,
        threaded=True,
    )
