#!/usr/bin/env python3
"""Create and rotate compressed SQLite backups."""

from __future__ import annotations

import sqlite3
import subprocess
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote

from config import Config


def backup_database(config: Config, now: datetime) -> Path:
    """Create a consistent, compressed SQLite backup and return its path."""
    config.backup_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    stamp = now.strftime("%Y%m%d-%H%M%S")
    final_path = config.backup_dir / f"opencode-{stamp}.db.zst"
    with tempfile.TemporaryDirectory(prefix="opencode-backup-", dir=config.backup_dir) as temp_dir:
        raw_path = Path(temp_dir) / "opencode.db"
        source_uri = f"file:{quote(str(config.opencode_db))}?mode=ro"
        source = sqlite3.connect(source_uri, uri=True, timeout=config.sqlite_busy_timeout_seconds)
        destination = sqlite3.connect(raw_path)
        try:
            source.execute(f"PRAGMA busy_timeout={config.sqlite_busy_timeout_seconds * 1000}")
            source.backup(destination, pages=1000, sleep=0.05)
            result = destination.execute("PRAGMA integrity_check").fetchone()
            if result != ("ok",):
                raise RuntimeError(f"backup integrity check failed: {result}")
            destination.commit()
        finally:
            destination.close()
            source.close()
        compressed = subprocess.run(
            ["zstd", "--quiet", "--force", "--rm", str(raw_path), "-o", str(final_path)],
            check=False,
            capture_output=True,
            text=True,
            timeout=config.command_timeout_seconds,
        )
        if compressed.returncode != 0 or not final_path.is_file():
            detail = compressed.stderr.strip() or "zstd did not create the backup"
            raise RuntimeError(f"backup compression failed: {detail}")
    final_path.chmod(0o600)
    rotate_backups(config, now)
    return final_path


def rotate_backups(config: Config, now: datetime) -> None:
    """Keep recent backups within configured age, count, and size limits."""
    if not config.backup_dir.is_dir():
        return
    backups = sorted(config.backup_dir.glob("opencode-*.db.zst"), key=lambda path: path.stat().st_mtime, reverse=True)
    cutoff = now - timedelta(days=config.opencode_backup_retention_days)
    retained: list[Path] = []
    for backup in backups:
        modified = datetime.fromtimestamp(backup.stat().st_mtime, tz=now.tzinfo)
        if modified < cutoff or len(retained) >= config.opencode_backup_max_count:
            backup.unlink(missing_ok=True)
            continue
        retained.append(backup)
    total = sum(path.stat().st_size for path in retained)
    for backup in reversed(retained[1:]):
        if total <= config.opencode_backup_max_size:
            break
        total -= backup.stat().st_size
        backup.unlink(missing_ok=True)
