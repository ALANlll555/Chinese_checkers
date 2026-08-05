"""Check release dependencies and install only what is actually missing."""

from __future__ import annotations

import argparse
import hashlib
from importlib import metadata
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parent
REQUIREMENTS = ROOT / "requirements.txt"
VENV_ROOT = Path(sys.prefix)
MARKER = VENV_ROOT / ".chinese_checkers_requirements.json"

MODULE_NAMES = {
    "flask": "flask",
    "requests": "requests",
    "mcp": "mcp",
    "uvicorn": "uvicorn",
}
CORE_DISTRIBUTIONS = {"flask", "requests"}
OPTIONAL_DISTRIBUTIONS = {"mcp", "uvicorn"}


def digest() -> str:
    return hashlib.sha256(REQUIREMENTS.read_bytes()).hexdigest()


def normalize_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def version_key(value: str) -> tuple[int, ...]:
    numbers = re.findall(r"\d+", str(value))
    return tuple(int(number) for number in numbers[:6]) or (0,)


def compare_versions(left: str, right: str) -> int:
    a = list(version_key(left))
    b = list(version_key(right))
    length = max(len(a), len(b))
    a.extend([0] * (length - len(a)))
    b.extend([0] * (length - len(b)))
    return (a > b) - (a < b)


def satisfies_specifier(installed: str, specifier: str) -> bool:
    for raw_clause in filter(None, (item.strip() for item in specifier.split(","))):
        match = re.fullmatch(r"(>=|<=|==|!=|>|<)\s*([0-9][0-9A-Za-z_.+-]*)", raw_clause)
        if not match:
            return False
        operator, expected = match.groups()
        comparison = compare_versions(installed, expected)
        if operator == ">=" and comparison < 0:
            return False
        if operator == ">" and comparison <= 0:
            return False
        if operator == "<=" and comparison > 0:
            return False
        if operator == "<" and comparison >= 0:
            return False
        if operator == "==" and comparison != 0:
            return False
        if operator == "!=" and comparison == 0:
            return False
    return True


def parse_requirements() -> list[dict]:
    parsed = []
    for raw_line in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        match = re.fullmatch(r"([A-Za-z0-9_.-]+)\s*(.*)", line)
        if not match:
            raise RuntimeError(f"Unsupported requirement syntax: {line}")
        distribution, specifier = match.groups()
        normalized = normalize_name(distribution)
        parsed.append({
            "distribution": distribution,
            "normalized": normalized,
            "specifier": specifier.strip(),
            "requirement": line,
            "module": MODULE_NAMES.get(normalized, normalized.replace("-", "_")),
            "optional": normalized in OPTIONAL_DISTRIBUTIONS,
        })
    return parsed


def requirement_status() -> list[dict]:
    statuses = []
    for requirement in parse_requirements():
        installed_version = None
        try:
            installed_version = metadata.version(requirement["distribution"])
        except metadata.PackageNotFoundError:
            installed_version = None

        module_ready = importlib.util.find_spec(requirement["module"]) is not None
        version_ready = (
            installed_version is not None
            and satisfies_specifier(installed_version, requirement["specifier"])
        )
        statuses.append({
            **requirement,
            "installed_version": installed_version,
            "module_ready": module_ready,
            "satisfied": bool(module_ready and version_ready),
        })
    return statuses


def pip_install(requirements: list[str]) -> int:
    if not requirements:
        return 0
    command = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "--prefer-binary",
        "--no-warn-script-location",
        *requirements,
    ]
    print("Installing only missing/outdated dependencies:", flush=True)
    print(" ".join(command), flush=True)
    return subprocess.run(command, cwd=ROOT).returncode


def read_marker() -> dict:
    if not MARKER.exists():
        return {}
    try:
        return json.loads(MARKER.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_marker(statuses: list[dict], *, attempted: bool) -> None:
    MARKER.write_text(
        json.dumps(
            {
                "requirements_sha256": digest(),
                "all_ready": all(item["satisfied"] for item in statuses),
                "optional_failures": [
                    item["requirement"]
                    for item in statuses
                    if item["optional"] and not item["satisfied"]
                ],
                "install_attempted": bool(attempted),
                "packages": {
                    item["distribution"]: {
                        "version": item["installed_version"],
                        "satisfied": item["satisfied"],
                    }
                    for item in statuses
                },
                "updated_at": time.time(),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def describe_problem(item: dict) -> str:
    if item["installed_version"] is None:
        return f"{item['distribution']}（未安装）"
    if not item["module_ready"]:
        return f"{item['distribution']} {item['installed_version']}（无法导入）"
    return (
        f"{item['distribution']} {item['installed_version']}"
        f"（要求 {item['specifier']}）"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--repair", action="store_true")
    args, _ = parser.parse_known_args(argv)

    marker = read_marker()
    statuses = requirement_status()
    unsatisfied = [item for item in statuses if not item["satisfied"]]

    if not unsatisfied:
        print(
            "All installed dependency versions satisfy requirements; "
            "skipping pip download.",
            flush=True,
        )
        write_marker(statuses, attempted=False)
        return 0

    core_missing = [
        item for item in unsatisfied
        if item["normalized"] in CORE_DISTRIBUTIONS
    ]
    optional_missing = [
        item for item in unsatisfied
        if item["normalized"] in OPTIONAL_DISTRIBUTIONS
    ]

    previous_optional_failure = (
        not args.repair
        and not core_missing
        and marker.get("requirements_sha256") == digest()
        and bool(marker.get("optional_failures"))
        and bool(marker.get("install_attempted"))
    )

    if previous_optional_failure:
        print(
            "Core dependencies are ready. Optional MCP dependencies failed "
            "previously, so this launch will not download them again.",
            flush=True,
        )
        print(
            'Run "python bootstrap.py --repair" to retry optional dependencies.',
            flush=True,
        )
        write_marker(statuses, attempted=True)
        return 0

    print("Dependency check found:", flush=True)
    for item in unsatisfied:
        print(f"  - {describe_problem(item)}", flush=True)

    install_targets = [item["requirement"] for item in unsatisfied]
    pip_result = pip_install(install_targets)
    statuses = requirement_status()

    remaining_core = [
        item for item in statuses
        if item["normalized"] in CORE_DISTRIBUTIONS and not item["satisfied"]
    ]
    remaining_optional = [
        item for item in statuses
        if item["normalized"] in OPTIONAL_DISTRIBUTIONS and not item["satisfied"]
    ]

    write_marker(statuses, attempted=True)

    if remaining_core:
        print(
            "\nCore dependencies are still unavailable:",
            file=sys.stderr,
            flush=True,
        )
        for item in remaining_core:
            print(f"  - {describe_problem(item)}", file=sys.stderr, flush=True)
        print(
            "Check the network, proxy, certificate, or pip configuration.",
            file=sys.stderr,
            flush=True,
        )
        return 1

    if remaining_optional:
        print(
            "\n[Warning] Optional MCP HTTP dependencies remain unavailable. "
            "The game and local Explainable AI Coach can still start.",
            flush=True,
        )
        for item in remaining_optional:
            print(f"  - {describe_problem(item)}", flush=True)
        return 0

    if pip_result != 0:
        print(
            "[Warning] pip returned a non-zero code, but all required "
            "versions are now importable.",
            flush=True,
        )

    print("Dependency check completed.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
