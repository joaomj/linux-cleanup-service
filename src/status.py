#!/usr/bin/env python3
"""Render the last daily cleanup result for an interactive shell."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from config import Config, format_bytes, load_config


def read_status(config: Config) -> dict[str, Any] | None:
    """Read the atomically written status record."""
    try:
        return json.loads(config.status_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except json.JSONDecodeError:
        return {"status": "failed", "errors": ["status file is invalid"]}


def service_is_active() -> bool:
    """Return whether the user service is active."""
    try:
        result = subprocess.run(
            ["systemctl", "--user", "is-active", "linux-cleanup.service"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0 and result.stdout.strip() in {"active", "activating"}


def format_value(status: dict[str, Any], key: str) -> str:
    """Format a byte field from a status record."""
    value = status.get(key)
    return format_bytes(int(value)) if isinstance(value, int) else "?"


def render_shell(config: Config) -> str:
    """Render one concise shell status line."""
    status = read_status(config)
    if status is None:
        return "[linux-cleanup] running | first daily cleanup has started"
    state = str(status.get("status", "unknown"))
    if state == "running" and not service_is_active():
        state = "failed"
        status.setdefault("errors", []).append("cleanup stopped before it wrote a final result")
    parts = [f"[linux-cleanup] {state}"]
    if status.get("finished_at"):
        parts.append(str(status["finished_at"]))
    if isinstance(status.get("deleted_roots"), int):
        parts.append(f"deleted {status['deleted_roots']} roots/{status.get('deleted_sessions', '?')} sessions")
    if isinstance(status.get("opencode_version"), str):
        parts.append(f"OpenCode {status['opencode_version']}")
    for key, label in (
        ("db_bytes", "DB"),
        ("backup_bytes", "backup"),
        ("brave_cache_bytes", "Brave"),
        ("uv_cache_bytes", "UV"),
        ("npm_cache_bytes", "npm"),
        ("system_journal_bytes", "system journal"),
        ("user_journal_bytes", "user journal"),
    ):
        if key in status:
            parts.append(f"{label} {format_value(status, key)}")
    warnings = status.get("warnings", [])
    errors = status.get("errors", [])
    if warnings:
        parts.append("warning: " + "; ".join(str(item) for item in warnings[:2]))
    if errors:
        parts.append("error: " + "; ".join(str(item) for item in errors[:2]))
    return " | ".join(parts)


def main() -> int:
    """Print shell status or JSON status."""
    config = load_config()
    if len(sys.argv) > 1 and sys.argv[1] == "--json":
        status = read_status(config)
        print(json.dumps(status or {}, indent=2, sort_keys=True))
    else:
        print(render_shell(config))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
