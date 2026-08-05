"""Cached release smoke test executed after dependencies are available."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time
from urllib.parse import quote


ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent
MARKER = Path(sys.prefix) / ".chinese_checkers_release_selftest.json"

FINGERPRINT_FILES = (
    ROOT / "app.py",
    ROOT / "board.py",
    ROOT / "ai.py",
    ROOT / "game_tools.py",
    ROOT / "deepseek_chat.py",
    ROOT / "schema.sql",
    ROOT / "templates" / "index.html",
    ROOT / "static" / "js" / "game.js",
    ROOT / "static" / "js" / "chat.js",
    ROOT / "static" / "js" / "audio.js",
)


def fingerprint() -> str:
    digest = hashlib.sha256()
    for path in FINGERPRINT_FILES:
        digest.update(path.relative_to(ROOT).as_posix().encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _handler_root(handler: str) -> str:
    expression = handler.strip()
    match = re.match(r"([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)?)", expression)
    return match.group(1) if match else ""


def static_button_audit() -> dict:
    html = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
    scripts = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((ROOT / "static" / "js").glob("*.js"))
    )

    handlers = []
    for match in re.finditer(
        r"\b(?:onclick|onchange|oninput)=\"([^\"]+)\"",
        html,
        flags=re.IGNORECASE,
    ):
        handler = match.group(1)
        root = _handler_root(handler)
        if root:
            handlers.append((handler, root))

    ai_chat_exports = {"AIChat.send", "AIChat.ask", "AIChat.clear"}
    unresolved = []
    for handler, root in handlers:
        if root in ai_chat_exports:
            continue
        if "." in root:
            unresolved.append({"handler": handler, "reason": "unknown object method"})
            continue
        patterns = (
            rf"\b(?:async\s+)?function\s+{re.escape(root)}\s*\(",
            rf"\bwindow\.{re.escape(root)}\s*=",
            rf"\bconst\s+{re.escape(root)}\s*=",
            rf"\blet\s+{re.escape(root)}\s*=",
        )
        if not any(re.search(pattern, scripts) for pattern in patterns):
            unresolved.append({"handler": handler, "reason": "function not found"})

    if unresolved:
        raise AssertionError(
            "Unresolved inline controls: "
            + json.dumps(unresolved, ensure_ascii=False)
        )

    required_stream_terms = (
        "case 'phase'",
        "case 'heartbeat'",
        "case 'reasoning'",
        "case 'tool_start'",
        "case 'tool_end'",
        "chat-process-phase-list",
    )
    chat_source = (ROOT / "static" / "js" / "chat.js").read_text(encoding="utf-8")
    missing_stream_terms = [
        term for term in required_stream_terms if term not in chat_source
    ]
    if missing_stream_terms:
        raise AssertionError(
            f"Missing stream UI terms: {missing_stream_terms}"
        )

    return {
        "inline_handlers": len(handlers),
        "unique_handlers": len({root for _, root in handlers}),
    }


def _assert_status(response, expected: int | tuple[int, ...], label: str):
    allowed = (expected,) if isinstance(expected, int) else expected
    if response.status_code not in allowed:
        body = response.get_data(as_text=True)
        raise AssertionError(
            f"{label}: HTTP {response.status_code}, expected {allowed}: {body[:500]}"
        )
    return response


def backend_flow_audit() -> dict:
    with tempfile.TemporaryDirectory(prefix="cc-release-selftest-") as temp:
        temp_path = Path(temp)
        os.environ["CHINESE_CHECKERS_DB"] = str(temp_path / "selftest.sqlite3")
        os.environ["CHINESE_CHECKERS_DATA_DIR"] = str(temp_path / "data")

        import config as cfg
        cfg.REPLAY_DIR = str(temp_path / "replays")

        import app as app_module
        app_module.GAMES.clear()
        app_module.app.config.update(TESTING=True, SECRET_KEY="release-selftest")

        client = app_module.app.test_client()
        checks = []

        def checked(method: str, path: str, *, label: str, expected=200, **kwargs):
            response = getattr(client, method)(path, **kwargs)
            _assert_status(response, expected, label)
            checks.append(label)
            return response

        checked("get", "/", label="首页")
        checked("get", "/api/system/status", label="系统状态")
        manifest = checked("get", "/api/mcp/manifest", label="MCP 清单").get_json()
        if not manifest.get("tools"):
            raise AssertionError("MCP 清单未返回工具")
        checked("get", "/api/replays", label="棋谱列表")

        archive = "selftest_archive"
        new_game = checked(
            "post",
            "/api/new_game",
            label="开始 PVE 对局",
            json={
                "num_players": 2,
                "mode": "pve",
                "difficulty": 2,
                "human_first": True,
                "save_name": archive,
                "api_key": "",
                "deepseek_settings": {
                    "thinking": True,
                    "show_reasoning": True,
                    "context_1m": False,
                },
            },
        ).get_json()

        if new_game.get("current_player") != 0:
            raise AssertionError("PVE 人类先手未生效")

        checked("get", "/api/state", label="读取当前局面")

        pieces = new_game.get("pieces") or {}
        player_pieces = pieces.get("0") or pieces.get(0) or []
        legal_source = None
        legal_target = None
        for source in player_pieces:
            legal = checked(
                "get",
                f"/api/legal_moves?r={source[0]}&c={source[1]}",
                label=f"读取合法走法 {source}",
            ).get_json()
            targets = legal.get("targets") or []
            if targets:
                legal_source = source
                legal_target = targets[0]
                break
        if legal_source is None:
            raise AssertionError("初始局面未找到可操作棋子")

        checked("post", "/api/hint", label="AI 提示", json={})
        checked(
            "post",
            "/api/move",
            label="人类落子",
            json={"from": legal_source, "to": legal_target},
        )
        checked("post", "/api/ai_move", label="AI 落子", json={})
        checked("get", "/api/comment", label="LLM 智能点评")
        checked("post", "/api/undo", label="悔棋", json={})

        stream = checked(
            "post",
            "/api/chat/stream",
            label="AI Coach 事件流",
            json={
                "message": "请分析当前局面",
                "thinking": True,
                "show_reasoning": True,
                "context_1m": False,
            },
        )
        stream_text = stream.get_data(as_text=True)
        for event_type in ('"type":"start"', '"type":"phase"', '"type":"text"', '"type":"done"'):
            if event_type not in stream_text:
                raise AssertionError(
                    f"AI Coach 事件流缺少 {event_type}: {stream_text[:800]}"
                )

        checked("get", "/api/chat/history", label="聊天历史")
        checked("post", "/api/chat/clear", label="清空聊天", json={})

        # The DeepSeek test button has both validation and success paths.
        checked(
            "post",
            "/api/deepseek/test",
            label="DeepSeek 空 Key 校验",
            expected=400,
            json={},
        )

        class FakeDeepSeekResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "choices": [{"message": {"content": "OK"}}]
                }

        original_post = app_module.requests.post
        app_module.requests.post = lambda *args, **kwargs: FakeDeepSeekResponse()
        try:
            checked(
                "post",
                "/api/deepseek/test",
                label="DeepSeek 配置测试",
                json={
                    "api_key": "selftest-key",
                    "base_url": "https://example.invalid",
                    "model": "selftest-model",
                },
            )
        finally:
            app_module.requests.post = original_post

        # Auto-save runs in a daemon thread; allow a short bounded wait.
        replay_path = Path(cfg.REPLAY_DIR) / archive / "replay.json"
        deadline = time.monotonic() + 2.0
        while not replay_path.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        if not replay_path.exists():
            raise AssertionError("命名存档未生成 replay.json")

        checked(
            "get",
            f"/api/archive/check/{quote(archive)}",
            label="存档重名检查",
        )
        checked(
            "get",
            f"/api/load_replay/{quote(archive)}",
            label="加载存档",
        )

        renamed = "selftest_archive_renamed"
        checked(
            "put",
            f"/api/archive/{quote(archive)}",
            label="重命名存档",
            json={"name": renamed},
        )
        checked(
            "get",
            f"/api/load_replay/{quote(renamed)}",
            label="加载重命名存档",
        )
        checked(
            "delete",
            f"/api/archive/{quote(renamed)}",
            label="删除存档",
        )

        checked(
            "post",
            "/api/new_game",
            label="开始 PVP 对局",
            json={
                "num_players": 4,
                "mode": "pvp",
                "difficulty": 1,
                "human_first": True,
                "save_name": "",
            },
        )

        return {
            "backend_checks": len(checks),
            "mcp_tools": len(manifest.get("tools") or []),
        }


def read_marker() -> dict:
    if not MARKER.exists():
        return {}
    try:
        return json.loads(MARKER.read_text(encoding="utf-8"))
    except Exception:
        return {}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--static-only", action="store_true")
    args = parser.parse_args(argv)

    current_fingerprint = fingerprint()
    marker = read_marker()
    if (
        not args.force
        and not args.static_only
        and marker.get("fingerprint") == current_fingerprint
        and marker.get("passed") is True
    ):
        print("Release self-test already passed for this build; skipping.", flush=True)
        return 0

    started = time.perf_counter()
    static_result = static_button_audit()
    backend_result = {} if args.static_only else backend_flow_audit()
    result = {
        "passed": True,
        "fingerprint": current_fingerprint,
        "static": static_result,
        "backend": backend_result,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "updated_at": time.time(),
    }

    if not args.static_only:
        MARKER.write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    print(
        "Release self-test passed: "
        + json.dumps(result, ensure_ascii=False),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
