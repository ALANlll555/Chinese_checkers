"""Reliable release bootstrap invoked by the single Windows BAT."""

from __future__ import annotations

from pathlib import Path
import os
import subprocess
import sys
import time
import traceback
import venv


ROOT = Path(__file__).resolve().parent
PROJECT = ROOT / "跳棋"
LOG_PATH = ROOT / "startup.log"
VENV_DIR = ROOT / ".venv"


def log(message: str) -> None:
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(f"[{stamp}] {message}\n")


def venv_python() -> Path:
    if os.name == "nt":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def run(command: list[str]) -> int:
    log("RUN " + " ".join(command))
    completed = subprocess.run(command, cwd=ROOT)
    log(f"EXIT {completed.returncode}")
    return completed.returncode


def main() -> int:
    LOG_PATH.write_text("", encoding="utf-8")
    log(f"bootstrap python={sys.executable}")
    log(f"python version={sys.version}")
    log(f"root={ROOT}")

    if sys.version_info < (3, 10):
        raise RuntimeError("Python 3.10 or newer is required.")

    required = [
        PROJECT / "app.py",
        PROJECT / "bootstrap.py",
        PROJECT / "launch_game.py",
        PROJECT / "release_selftest.py",
        PROJECT / "requirements.txt",
    ]
    missing = [str(path.relative_to(ROOT)) for path in required if not path.exists()]
    if missing:
        raise RuntimeError(
            "The ZIP package was not fully extracted. Missing: " + ", ".join(missing)
        )

    python = venv_python()
    if not python.exists():
        print("[First launch] Creating the local Python environment...", flush=True)
        log("creating venv with system_site_packages=True")
        builder = venv.EnvBuilder(
            with_pip=True,
            clear=False,
            symlinks=False,
            upgrade=False,
            system_site_packages=True,
        )
        builder.create(VENV_DIR)

    if not python.exists():
        raise RuntimeError(f"Virtual environment Python was not created: {python}")

    print(
        "[1/3] Checking dependencies (downloads only when missing/outdated)...",
        flush=True,
    )
    code = run([str(python), str(PROJECT / "bootstrap.py")])
    if code != 0:
        raise RuntimeError(
            "Dependency check failed. See startup.log for the executed command."
        )

    print("[2/3] Verifying buttons and backend flows...", flush=True)
    code = run([str(python), str(PROJECT / "release_selftest.py")])
    if code != 0:
        raise RuntimeError(
            "Release self-test failed. See startup.log for details."
        )

    print("[3/3] Starting the game...", flush=True)
    return run([str(python), str(PROJECT / "launch_game.py")])


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(0)
    except Exception as exc:
        log(f"FATAL {exc}\n{traceback.format_exc()}")
        print(f"\n[STARTUP ERROR] {exc}", file=sys.stderr, flush=True)
        print(f"Detailed log: {LOG_PATH}", file=sys.stderr, flush=True)
        raise SystemExit(1)
