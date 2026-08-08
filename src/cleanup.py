#!/usr/bin/env python3
"""Run one safe, resumable daily storage cleanup pass."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import shutil
import sqlite3
import subprocess
import tempfile
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Iterator

from config import ConfigurationError, Config, format_bytes, load_config
from sqlite_backup import backup_database


@contextmanager
def cleanup_lock(config: Config) -> Iterator[bool]:
    """Acquire a non-blocking process lock for the cleanup run."""
    config.state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    with config.lock_path.open("a+", encoding="utf-8") as lock_file:
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def write_json(path: Path, value: dict[str, Any]) -> None:
    """Write JSON state atomically with private permissions."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as file:
        json.dump(value, file, indent=2, sort_keys=True)
        file.write("\n")
        temporary = Path(file.name)
    temporary.chmod(0o600)
    temporary.replace(path)


def run_command(command: list[str], config: Config, cwd: Path | None = None) -> tuple[int, str, str]:
    """Run an external command with a bounded timeout."""
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=config.command_timeout_seconds,
            cwd=cwd,
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except subprocess.TimeoutExpired:
        return 124, "", f"command timed out after {config.command_timeout_seconds}s"
    except OSError as error:
        return 127, "", str(error)


def measure_path(path: Path) -> int:
    """Measure a file or directory in bytes."""
    if not path.exists():
        return 0
    du = shutil.which("du")
    if du:
        result = subprocess.run([du, "-sb", "--", str(path)], check=False, capture_output=True, text=True)
        if result.returncode == 0 and result.stdout.split():
            try:
                return int(result.stdout.split()[0])
            except ValueError:
                pass
    if path.is_file():
        return path.stat().st_size
    return sum(measure_path(child) for child in path.iterdir())


def database_size(config: Config) -> int:
    """Measure the OpenCode database and its SQLite sidecar files."""
    return sum(measure_path(Path(f"{config.opencode_db}{suffix}")) for suffix in ("", "-wal", "-shm"))


def process_is_running(names: set[str]) -> bool:
    """Check processes owned by this user without matching command arguments."""
    proc = Path("/proc")
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        status_path = entry / "status"
        cmdline_path = entry / "comm"
        try:
            status = status_path.read_text(encoding="utf-8")
            uid_line = next(line for line in status.splitlines() if line.startswith("Uid:"))
            owner_uid = int(uid_line.split()[1])
            if owner_uid != os.getuid():
                continue
            name = cmdline_path.read_text(encoding="utf-8").strip().lower()
        except (FileNotFoundError, PermissionError, StopIteration, ValueError):
            continue
        if name in names:
            return True
    return False


def process_uses_path(path: Path) -> bool:
    """Return whether a process owned by this user has a handle in a path."""
    root = path.resolve()
    proc = Path("/proc")
    if not proc.is_dir():
        return False
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            status = (entry / "status").read_text(encoding="utf-8")
            uid_line = next(line for line in status.splitlines() if line.startswith("Uid:"))
            if int(uid_line.split()[1]) != os.getuid():
                continue
            links = [entry / "cwd"]
            links.extend((entry / "fd").iterdir())
            for link in links:
                candidate = Path(os.path.realpath(link))
                try:
                    candidate.relative_to(root)
                except ValueError:
                    continue
                return True
        except (FileNotFoundError, PermissionError, OSError, StopIteration, ValueError):
            continue
    return False


def remove_temp_workspace(path: Path, config: Config) -> None:
    """Remove a workspace and keep Git worktree metadata consistent."""
    git_marker = path / ".git"
    if git_marker.is_file():
        git = shutil.which("git")
        if git is None:
            raise RuntimeError(f"Git is required to remove linked worktree: {path}")
        code, _, stderr = run_command(
            [git, "-C", str(path), "worktree", "remove", "--force", str(path)], config
        )
        if code != 0:
            raise RuntimeError(stderr or f"git worktree remove failed for {path}")
        return
    shutil.rmtree(path)


def clean_temp_workspaces(config: Config, now: datetime, dry_run: bool, warnings: list[str]) -> dict[str, int]:
    """Remove inactive, user-owned temporary workspaces after the retention period."""
    result = {
        "temp_candidates": 0,
        "temp_deleted": 0,
        "temp_deleted_bytes": 0,
        "temp_skipped_active": 0,
        "temp_skipped_recent": 0,
        "temp_skipped_unsafe": 0,
    }
    root = config.temp_root
    if not root.exists():
        return result
    if root.is_symlink() or not root.is_dir():
        warnings.append(f"temporary root is not a real directory: {root}")
        return result

    try:
        root_device = root.stat().st_dev
        entries = sorted(root.iterdir(), key=lambda item: item.name)
    except OSError as error:
        warnings.append(f"temporary root could not be inspected: {error}")
        return result

    cutoff = now - timedelta(days=config.temp_retention_days)
    for entry in entries:
        if entry.is_symlink() or not entry.is_dir():
            result["temp_skipped_unsafe"] += 1
            continue
        try:
            metadata = entry.stat()
            if metadata.st_uid != os.getuid() or metadata.st_dev != root_device:
                result["temp_skipped_unsafe"] += 1
                continue
            result["temp_candidates"] += 1
            modified = datetime.fromtimestamp(metadata.st_mtime, tz=now.tzinfo)
            if modified >= cutoff:
                result["temp_skipped_recent"] += 1
                continue
            if process_uses_path(entry):
                result["temp_skipped_active"] += 1
                continue
            size = measure_path(entry)
            if dry_run:
                result["temp_deleted"] += 1
                result["temp_deleted_bytes"] += size
                continue
            if process_uses_path(entry):
                result["temp_skipped_active"] += 1
                continue
            remove_temp_workspace(entry, config)
            result["temp_deleted"] += 1
            result["temp_deleted_bytes"] += size
        except (OSError, RuntimeError) as error:
            warnings.append(f"temporary workspace cleanup failed for {entry}: {error}")
    return result


def stale_roots(config: Config, cutoff_ms: int) -> list[dict[str, Any]]:
    """Find root session trees with no activity after the cutoff."""
    if not config.opencode_db.is_file():
        return []
    query = """
        WITH RECURSIVE tree(root_id, session_id, time_updated) AS (
            SELECT id, id, time_updated FROM session WHERE parent_id IS NULL
            UNION ALL
            SELECT tree.root_id, child.id, child.time_updated
            FROM session AS child
            JOIN tree ON child.parent_id = tree.session_id
        )
        SELECT root_id, max(time_updated) AS latest_updated, count(*) AS session_count
               , group_concat(session_id) AS session_ids
        FROM tree
        GROUP BY root_id
        HAVING max(time_updated) < ?
        ORDER BY latest_updated ASC, root_id ASC
    """
    connection = sqlite3.connect(f"file:{config.opencode_db}?mode=ro", uri=True)
    try:
        rows = connection.execute(query, (cutoff_ms,)).fetchall()
    finally:
        connection.close()
    return [
        {
            "root_id": str(row[0]),
            "latest_updated": int(row[1]),
            "session_count": int(row[2]),
            "session_ids": str(row[3]).split(",") if row[3] else [],
        }
        for row in rows
    ]


def session_exists(config: Config, session_id: str) -> bool:
    """Check whether a session remains in the database."""
    connection = sqlite3.connect(f"file:{config.opencode_db}?mode=ro", uri=True)
    try:
        return connection.execute("SELECT 1 FROM session WHERE id = ?", (session_id,)).fetchone() is not None
    finally:
        connection.close()


def clear_cache(path: Path, active_check: Callable[[], bool] | None = None) -> None:
    """Remove cache contents while preserving the cache directory."""
    if path.is_symlink():
        raise RuntimeError(f"refusing to clear symlink cache: {path}")
    path.mkdir(parents=True, exist_ok=True)
    for child in path.iterdir():
        if active_check is not None and active_check():
            raise RuntimeError("Brave started during cache cleanup")
        if child.is_symlink() or child.is_file():
            child.unlink()
        elif child.is_dir():
            shutil.rmtree(child)


def parse_journal_size(output: str) -> int | None:
    """Parse the byte value from journalctl's disk usage line."""
    units = {"B": 1, "K": 1_000, "M": 1_000_000, "G": 1_000_000_000, "T": 1_000_000_000_000}
    matches = re.findall(r"([0-9]+(?:[.,][0-9]+)?)\s*([BKMGT])", output.upper())
    for number, unit in reversed(matches):
        normalized_number = number.replace(",", ".")
        if unit in units:
            return int(float(normalized_number) * units[unit])
    return None


def journal_size(user: bool, config: Config) -> tuple[int | None, str | None]:
    """Read system or user journal usage."""
    command = ["journalctl"]
    if user:
        command.append("--user")
    command.append("--disk-usage")
    code, stdout, stderr = run_command(command, config)
    if code != 0:
        return None, stderr or "journalctl failed"
    size = parse_journal_size(stdout)
    return size, None if size is not None else "journalctl returned no size"


def vacuum_journal(user: bool, config: Config, current_size: int | None, warnings: list[str]) -> int | None:
    """Vacuum an oversized journal without prompting for credentials."""
    if current_size is None or current_size <= config.journal_warn_size:
        return current_size
    command_prefix = ["journalctl", "--user"] if user else ["sudo", "-n", "journalctl"]
    for command in (
        command_prefix + ["--rotate"],
        command_prefix + [f"--vacuum-size={config.journal_system_max_use}"],
    ):
        code, _, stderr = run_command(command, config)
        if code != 0:
            scope = "user" if user else "system"
            warnings.append(f"{scope} journal vacuum failed: {stderr or 'permission denied'}")
            return current_size
    size, error = journal_size(user, config)
    if error:
        warnings.append(error)
    return size


def opencode_version(config: Config) -> str | None:
    """Return the installed OpenCode version."""
    if not config.opencode_command.exists():
        return None
    code, stdout, _ = run_command([str(config.opencode_command), "--version"], config)
    return stdout.splitlines()[-1] if code == 0 and stdout else None


def upgrade_opencode(config: Config, warnings: list[str], dry_run: bool) -> str | None:
    """Upgrade OpenCode with its detected standalone installer."""
    before = opencode_version(config)
    if not config.opencode_upgrade_enabled or dry_run:
        return before
    if not config.opencode_command.exists():
        warnings.append("OpenCode command was not found")
        return before
    code, _, stderr = run_command(
        [str(config.opencode_command), "upgrade", "--method", config.opencode_upgrade_method], config
    )
    if code != 0:
        warnings.append(f"OpenCode upgrade failed: {stderr or 'unknown error'}")
    return opencode_version(config) or before


def prune_uv_cache(config: Config, warnings: list[str], dry_run: bool) -> int:
    """Prune unreferenced UV cache files above the configured threshold."""
    uv = shutil.which("uv")
    if uv is None:
        return 0
    size = measure_path(config.uv_cache)
    if size <= config.uv_cache_max_size or dry_run:
        return size
    code, _, stderr = run_command([uv, "cache", "prune"], config)
    if code != 0:
        warnings.append(f"UV cache prune failed: {stderr or 'unknown error'}")
    return measure_path(config.uv_cache)


def manage_brave_cache(config: Config, warnings: list[str], dry_run: bool) -> int:
    """Clear Brave cache only when Brave is stopped."""
    size = measure_path(config.brave_cache)
    if size <= config.brave_cache_max_size or dry_run:
        return size
    if process_is_running({"brave", "brave-browser", "brave-browser-stable"}):
        warnings.append(f"Brave cache exceeds {format_bytes(config.brave_cache_max_size)}; Brave is running")
        return size
    try:
        clear_cache(
            config.brave_cache,
            lambda: process_is_running({"brave", "brave-browser", "brave-browser-stable"}),
        )
    except (OSError, RuntimeError) as error:
        warnings.append(f"Brave cache cleanup failed: {error}")
    return measure_path(config.brave_cache)


def clean_logs(config: Config, now: datetime, dry_run: bool) -> int:
    """Remove old OpenCode log files."""
    if dry_run or not config.opencode_log_dir.is_dir():
        return 0
    cutoff = now - timedelta(days=config.opencode_log_retention_days)
    removed = 0
    for log_file in config.opencode_log_dir.glob("*.log"):
        if log_file.is_file() and datetime.fromtimestamp(log_file.stat().st_mtime, tz=now.tzinfo) < cutoff:
            log_file.unlink()
            removed += 1
    return removed


def clean_session_diffs(config: Config, deleted_ids: set[str], dry_run: bool) -> int:
    """Remove diff files that belong to successfully deleted sessions."""
    if dry_run or not config.session_diff_dir.is_dir():
        return 0
    removed = 0
    for session_id in deleted_ids:
        candidate = config.session_diff_dir / f"{session_id}.json"
        if candidate.is_file() and not candidate.is_symlink():
            candidate.unlink()
            removed += 1
    return removed


def checkpoint_database(config: Config, warnings: list[str]) -> None:
    """Checkpoint the WAL after session removal."""
    if not config.opencode_db.is_file():
        return
    try:
        connection = sqlite3.connect(config.opencode_db, timeout=config.sqlite_busy_timeout_seconds)
        connection.execute(f"PRAGMA busy_timeout={config.sqlite_busy_timeout_seconds * 1000}")
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        connection.close()
    except sqlite3.Error as error:
        warnings.append(f"SQLite WAL checkpoint failed: {error}")


def maybe_vacuum(config: Config, warnings: list[str], dry_run: bool) -> None:
    """Reclaim SQLite free pages only when OpenCode is not running."""
    if dry_run or not config.opencode_db.is_file() or process_is_running({"opencode"}):
        if not dry_run and process_is_running({"opencode"}):
            warnings.append("SQLite vacuum skipped because OpenCode is running")
        return
    try:
        connection = sqlite3.connect(config.opencode_db, timeout=config.sqlite_busy_timeout_seconds)
        page_size = int(connection.execute("PRAGMA page_size").fetchone()[0])
        freelist = int(connection.execute("PRAGMA freelist_count").fetchone()[0])
        if page_size * freelist < config.sqlite_vacuum_min_size:
            connection.close()
            return
        connection.execute("VACUUM")
        connection.close()
    except sqlite3.Error as error:
        warnings.append(f"SQLite VACUUM failed: {error}")


def execute(config: Config, dry_run: bool) -> dict[str, Any]:
    """Execute one cleanup pass and return its status fields."""
    now = datetime.now().astimezone()
    warnings: list[str] = []
    errors: list[str] = []
    result: dict[str, Any] = {
        "status": "success",
        "started_at": now.isoformat(timespec="seconds"),
        "attempt_date": now.date().isoformat(),
        "warnings": warnings,
        "errors": errors,
        "deleted_roots": 0,
        "deleted_sessions": 0,
        "backup_bytes": 0,
        "dry_run": dry_run,
    }
    result.update(clean_temp_workspaces(config, now, dry_run, warnings))
    result["opencode_version"] = upgrade_opencode(config, warnings, dry_run)
    result["uv_cache_bytes"] = prune_uv_cache(config, warnings, dry_run)
    result["brave_cache_bytes"] = manage_brave_cache(config, warnings, dry_run)
    result["npm_cache_bytes"] = measure_path(config.npm_cache)
    if result["npm_cache_bytes"] > config.npm_cache_warn_size:
        warnings.append(f"npm cache exceeds {format_bytes(config.npm_cache_warn_size)}")
    system_size, system_error = journal_size(False, config)
    user_size, user_error = journal_size(True, config)
    if system_error:
        warnings.append(f"system journal measurement failed: {system_error}")
    if user_error:
        warnings.append(f"user journal measurement failed: {user_error}")
    system_size = vacuum_journal(False, config, system_size, warnings)
    user_size = vacuum_journal(True, config, user_size, warnings)
    if system_size is not None:
        result["system_journal_bytes"] = system_size
        if system_size > config.journal_warn_size:
            warnings.append(f"system journal exceeds {format_bytes(config.journal_warn_size)}")
    if user_size is not None:
        result["user_journal_bytes"] = user_size
        if user_size > config.journal_warn_size:
            warnings.append(f"user journal exceeds {format_bytes(config.journal_warn_size)}")

    cutoff_ms = int((now - timedelta(days=config.session_retention_days)).timestamp() * 1000)
    try:
        candidates = stale_roots(config, cutoff_ms)
    except sqlite3.Error as error:
        candidates = []
        errors.append(f"could not inspect OpenCode sessions: {error}")
    result["candidate_roots"] = len(candidates)
    result["candidate_sessions"] = sum(int(item["session_count"]) for item in candidates)
    deleted_ids: set[str] = set()
    if candidates and not dry_run and not errors:
        try:
            backup = backup_database(config, now)
            result["backup_path"] = str(backup)
            result["backup_bytes"] = measure_path(backup)
        except (OSError, RuntimeError, sqlite3.Error, subprocess.SubprocessError) as error:
            errors.append(f"database backup failed; no sessions deleted: {error}")
    if candidates and not dry_run and not errors:
        for candidate in candidates:
            root_id = str(candidate["root_id"])
            if session_exists(config, root_id):
                code, _, stderr = run_command(
                    [str(config.opencode_command), "--pure", "session", "delete", root_id], config, config.home
                )
                if code != 0:
                    errors.append(f"session deletion failed for {root_id}: {stderr or 'unknown error'}")
                    continue
            if session_exists(config, root_id):
                errors.append(f"session deletion could not verify removal for {root_id}")
                continue
            deleted_ids.add(root_id)
            deleted_ids.update(str(session_id) for session_id in candidate["session_ids"])
            result["deleted_roots"] += 1
            result["deleted_sessions"] += int(candidate["session_count"])
    clean_session_diffs(config, deleted_ids, dry_run)
    clean_logs(config, now, dry_run)
    if deleted_ids and not dry_run:
        checkpoint_database(config, warnings)
        maybe_vacuum(config, warnings, dry_run)
    result["db_bytes"] = database_size(config)
    if result["db_bytes"] > config.opencode_db_warn_size:
        warnings.append(f"OpenCode database exceeds {format_bytes(config.opencode_db_warn_size)}")
    result["finished_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    if errors:
        result["status"] = "failed"
    elif warnings:
        result["status"] = "warning"
    return result


def parse_args() -> argparse.Namespace:
    """Parse command-line options."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="inspect state without mutating files or sessions")
    parser.add_argument("--force", action="store_true", help="run again even when today already ran")
    return parser.parse_args()


def main() -> int:
    """Run the daily gate and cleanup."""
    args = parse_args()
    config = load_config()
    now = datetime.now().astimezone()
    with cleanup_lock(config) as acquired:
        if not acquired:
            return 0
        previous: dict[str, Any] = {}
        try:
            previous = json.loads(config.status_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            previous = {}
        today = now.date().isoformat()
        if (
            not args.force
            and previous.get("attempt_date") == today
            and previous.get("status") in {"success", "warning"}
        ):
            return 0
        if not args.dry_run:
            write_json(
                config.status_path,
                {"status": "running", "attempt_date": today, "started_at": now.isoformat(timespec="seconds")},
            )
        try:
            result = execute(config, args.dry_run)
        except (ConfigurationError, OSError, RuntimeError, sqlite3.Error) as error:
            result = {
                "status": "failed",
                "attempt_date": today,
                "started_at": now.isoformat(timespec="seconds"),
                "finished_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                "warnings": [],
                "errors": [str(error)],
            }
        if args.dry_run:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            write_json(config.status_path, result)
        return 0 if result["status"] != "failed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
