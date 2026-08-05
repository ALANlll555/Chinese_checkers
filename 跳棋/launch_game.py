"""Start the game reliably and launch the optional local MCP endpoint."""

from __future__ import annotations

import atexit
import importlib.util
from pathlib import Path
import os
import socket
import subprocess
import sys
import threading
import time
import traceback
import webbrowser

import config as cfg


ROOT = Path(__file__).resolve().parent
LOG_DIR = ROOT / "logs"
LAUNCHER_LOG = LOG_DIR / "launcher.log"
MCP_LOG = LOG_DIR / "mcp.log"

_mcp_process: subprocess.Popen | None = None
_mcp_log_handle = None


def _port_is_open(host: str, port: int, timeout: float = 0.25) -> bool:
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except OSError:
        return False


def _wait_for_port(
    host: str,
    port: int,
    *,
    timeout: float,
    process: subprocess.Popen | None = None,
) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _port_is_open(host, port):
            return True
        if process is not None and process.poll() is not None:
            return False
        time.sleep(0.15)
    return False


def _log(message: str) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with LAUNCHER_LOG.open("a", encoding="utf-8") as handle:
        handle.write(f"[{stamp}] {message}\n")


def _tail(path: Path, max_lines: int = 30) -> str:
    if not path.exists():
        return ""
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(lines[-max_lines:])


def _mcp_dependencies_available() -> bool:
    return (
        importlib.util.find_spec("mcp") is not None
        and importlib.util.find_spec("uvicorn") is not None
    )


def _start_mcp_best_effort() -> str:
    global _mcp_process, _mcp_log_handle

    if _port_is_open(cfg.MCP_HOST, cfg.MCP_PORT):
        _log(f"MCP port {cfg.MCP_PORT} already open; using existing service")
        return "existing"

    if not _mcp_dependencies_available():
        _log("MCP skipped because optional dependencies are unavailable")
        return "unavailable"

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    _mcp_log_handle = MCP_LOG.open("a", encoding="utf-8", buffering=1)
    environment = os.environ.copy()
    environment.update(
        {
            "MCP_HOST": cfg.MCP_HOST,
            "MCP_PORT": str(cfg.MCP_PORT),
            "MCP_TRANSPORT": "streamable-http",
            "PYTHONUNBUFFERED": "1",
        }
    )

    creation_flags = 0
    if os.name == "nt":
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    process = subprocess.Popen(
        [
            sys.executable,
            str(ROOT / "mcp_server.py"),
            "--transport",
            "streamable-http",
        ],
        cwd=ROOT,
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=_mcp_log_handle,
        stderr=subprocess.STDOUT,
        creationflags=creation_flags,
    )

    if _wait_for_port(
        cfg.MCP_HOST,
        cfg.MCP_PORT,
        timeout=cfg.RELEASE_SERVICE_START_TIMEOUT,
        process=process,
    ):
        _mcp_process = process
        _log(f"MCP started pid={process.pid}")
        return "started"

    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2)

    details = _tail(MCP_LOG)
    _log("MCP startup failed; game will continue\n" + details)
    return "failed"


def _stop_mcp() -> None:
    global _mcp_process, _mcp_log_handle
    process = _mcp_process
    _mcp_process = None
    if process is not None and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=4)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2)
    if _mcp_log_handle is not None:
        _mcp_log_handle.close()
        _mcp_log_handle = None


def _open_browser_when_ready() -> None:
    if _wait_for_port(
        cfg.APP_HOST,
        cfg.APP_PORT,
        timeout=cfg.RELEASE_SERVICE_START_TIMEOUT,
    ):
        try:
            webbrowser.open(cfg.APP_URL, new=1, autoraise=True)
        except Exception as exc:
            _log(f"browser open failed: {exc}")


def main() -> int:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    _log("release launcher starting")

    if _port_is_open(cfg.APP_HOST, cfg.APP_PORT):
        print(
            f"Game server is already running at {cfg.APP_URL}. Opening the browser.",
            flush=True,
        )
        webbrowser.open(cfg.APP_URL, new=1, autoraise=True)
        return 0

    mcp_status = _start_mcp_best_effort()
    atexit.register(_stop_mcp)

    if mcp_status in {"started", "existing"}:
        print(f"MCP: {cfg.MCP_URL}", flush=True)
    elif mcp_status == "unavailable":
        print(
            "[Warning] MCP packages are unavailable. "
            "The game and DeepSeek assistant remain available.",
            flush=True,
        )
    else:
        print(
            f"[Warning] MCP did not start. The game will continue. "
            f"See {MCP_LOG}.",
            flush=True,
        )

    browser_thread = threading.Thread(
        target=_open_browser_when_ready,
        name="browser-opener",
        daemon=True,
    )
    browser_thread.start()

    from app import app

    print(f"Game: {cfg.APP_URL}", flush=True)
    print("Press Ctrl+C to stop.", flush=True)

    try:
        app.run(
            host=cfg.APP_HOST,
            port=cfg.APP_PORT,
            debug=False,
            use_reloader=False,
            threaded=True,
        )
    finally:
        _stop_mcp()
        _log("release launcher stopped")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        _stop_mcp()
        raise SystemExit(0)
    except Exception as exc:
        _stop_mcp()
        _log(f"fatal error: {exc}\n{traceback.format_exc()}")
        print(f"[STARTUP ERROR] {exc}", file=sys.stderr, flush=True)
        print(f"See log: {LAUNCHER_LOG}", file=sys.stderr, flush=True)
        raise SystemExit(1)
