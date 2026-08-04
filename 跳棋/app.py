"""
跳棋 — Flask Web 服务
"""

from __future__ import annotations

import uuid, os
from flask import Flask, render_template, request, jsonify, session

from board import BoardState
from ai import get_ai_move, evaluate
from replay import save_replay, load_replay, list_replays
from llm_comment import get_comment
import config as cfg

app = Flask(__name__)
app.secret_key = "chinese_checkers_neon_2024"
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0  # 禁用静态文件缓存

# 服务端用 session 存储每个用户的对局状态
GAMES: dict[str, dict] = {}


def _get_game() -> dict | None:
    """获取当前会话的游戏数据。"""
    gid = session.get("game_id")
    if gid and gid in GAMES:
        return GAMES[gid]
    return None


def _auto_save(game: dict):
    """每次走棋后自动保存棋谱。"""
    import threading
    def _save():
        try:
            name = game.get("save_name", "")
            if not name:
                return
            save_replay(name, game["state"].to_dict(),
                        game["mode"], game["difficulty"],
                        game["move_history"])
        except Exception:
            pass
    t = threading.Thread(target=_save, daemon=True)
    t.start()


# ═══════════════════════════════════════════════════════
# 页面
# ═══════════════════════════════════════════════════════

@app.route("/")
def index():
    response = app.make_response(render_template("index.html"))
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


# ═══════════════════════════════════════════════════════
# API
# ═══════════════════════════════════════════════════════

@app.route("/api/new_game", methods=["POST"])
def api_new_game():
    data = request.get_json() or {}
    num_players = data.get("num_players", 2)
    mode = data.get("mode", "pvp")       # pvp | pve
    difficulty = data.get("difficulty", 2)
    human_first = data.get("human_first", True)

    save_name = data.get("save_name", "").strip()

    # 前端传入的 LLM API Key
    api_key = data.get("api_key", "")
    if api_key:
        cfg.LLM_API_KEY = api_key

    state = BoardState.new_game(num_players)

    # AI 先手：切换到第一个非人类玩家
    if mode == "pve" and not human_first:
        ai_players = [p for p in state.active_players if p != 0]
        if ai_players:
            state.current_player = ai_players[0]

    gid = str(uuid.uuid4())[:8]
    GAMES[gid] = {
        "state": state,
        "mode": mode,
        "difficulty": difficulty,
        "move_history": [],
        "save_name": save_name,
    }
    session["game_id"] = gid

    return jsonify({
        "game_id": gid,
        "mode": mode,
        "difficulty": difficulty,
        **state.to_dict(),
    })


@app.route("/api/move", methods=["POST"])
def api_move():
    game = _get_game()
    if not game:
        return jsonify({"error": "无活跃对局"}), 400

    state: BoardState = game["state"]
    data = request.get_json()
    move = (tuple(data["from"]), tuple(data["to"]))

    # 验证走法合法性
    valid = state.get_valid_moves()
    if move not in valid:
        return jsonify({"error": "非法走法"}), 400

    pid_before = state.current_player

    # 只执行人类走棋，不自动触发 AI
    state = state.apply_move(move)
    game["state"] = state
    game["move_history"].append({
        "from": list(move[0]), "to": list(move[1]),
        "player": pid_before,
    })
    _auto_save(game)

    return jsonify({
        **state.to_dict(),
        "need_ai": (game["mode"] == "pve" and not state.is_terminal()),
    })


@app.route("/api/ai_move", methods=["POST"])
def api_ai_move():
    """AI 走一步棋（由前端在人落子后调用）"""
    game = _get_game()
    if not game:
        return jsonify({"error": "无活跃对局"}), 400

    state: BoardState = game["state"]
    if state.is_terminal():
        return jsonify(state.to_dict())

    ai_pid = state.current_player
    ai_move = get_ai_move(state, game["difficulty"])
    if not ai_move:
        return jsonify(state.to_dict())

    eval_before = evaluate(state, ai_pid)
    state = state.apply_move(ai_move)
    game["state"] = state
    game["move_history"].append({
        "from": list(ai_move[0]), "to": list(ai_move[1]),
        "player": ai_pid,
    })
    _auto_save(game)
    eval_after = evaluate(state, ai_pid)

    # LLM 点评上下文
    game["_last_comment_ctx"] = {
        "state_dict": state.to_dict(),
        "move": ai_move,
        "eval_before": eval_before,
        "eval_after": eval_after,
        "player_pid": ai_pid,
    }

    return jsonify({
        **state.to_dict(),
        "ai_move": {
            "from": list(ai_move[0]),
            "to": list(ai_move[1]),
            "player": ai_pid,
        },
    })


@app.route("/api/undo", methods=["POST"])
def api_undo():
    game = _get_game()
    if not game:
        return jsonify({"error": "无活跃对局"}), 400

    state = game["state"]
    # 人机模式撤销两步
    if game["mode"] == "pve":
        state.undo_move()
        state.undo_move()
    else:
        state.undo_move()

    # 清理对应的历史记录
    rm = 2 if game["mode"] == "pve" else 1
    game["move_history"] = game["move_history"][:-rm]
    _auto_save(game)

    return jsonify(state.to_dict())


@app.route("/api/hint", methods=["POST"])
def api_hint():
    """AI 推荐走法。"""
    game = _get_game()
    if not game:
        return jsonify({"error": "无活跃对局"}), 400

    state = game["state"]
    move = get_ai_move(state, 3)  # 用最高难度给提示
    if move:
        return jsonify({"from": list(move[0]), "to": list(move[1])})
    return jsonify({"error": "无可用走法"}), 400


@app.route("/api/comment", methods=["GET"])
def api_comment():
    """获取最近一步 AI 走棋的 LLM 点评。"""
    game = _get_game()
    if not game:
        return jsonify({"error": "无活跃对局"}), 400

    ctx = game.get("_last_comment_ctx")
    if not ctx:
        return jsonify({"comment": ""})

    try:
        comment = get_comment(
            ctx["state_dict"], ctx["move"], ctx["eval_before"],
            ctx["eval_after"], ctx["player_pid"]
        )
        return jsonify({"comment": comment})
    except Exception:
        return jsonify({"comment": ""})


@app.route("/api/state", methods=["GET"])
def api_state():
    game = _get_game()
    if not game:
        return jsonify({"error": "无活跃对局"}), 400
    return jsonify(game["state"].to_dict())


@app.route("/api/legal_moves", methods=["GET"])
def api_legal_moves():
    """获取指定棋子的所有合法走法（含连跳）。"""
    game = _get_game()
    if not game:
        return jsonify({"error": "无活跃对局"}), 400

    state = game["state"]
    fr = request.args.get("r", type=int)
    fc = request.args.get("c", type=int)

    if fr is None or fc is None:
        return jsonify({"error": "缺少 r/c 参数"}), 400

    all_moves = state.get_valid_moves()
    # 筛选从 (fr,fc) 出发的走法
    targets = [list(to) for src, to in all_moves if src == (fr, fc)]
    return jsonify({"from": [fr, fc], "targets": targets})


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
    d = os.path.join(cfg.REPLAY_DIR, name)
    if os.path.isdir(d):
        shutil.rmtree(d)
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
    rp = os.path.join(new, "replay.json")
    if os.path.exists(rp):
        with open(rp, "r+", encoding="utf-8") as f:
            d = json.load(f)
            d["name"] = new_name
            f.seek(0)
            json.dump(d, f, ensure_ascii=False, indent=2)
            f.truncate()
    return jsonify({"ok": True, "name": new_name})


@app.route("/api/archive/check/<name>", methods=["GET"])
def api_check_archive(name):
    exists = os.path.isdir(os.path.join(cfg.REPLAY_DIR, name))
    return jsonify({"exists": exists})


# ═══════════════════════════════════════════════════════
# 启动
# ═══════════════════════════════════════════════════════

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
