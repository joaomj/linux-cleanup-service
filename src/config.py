#!/usr/bin/env python3
"""Validated configuration for the daily storage maintenance service."""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path


SIZE_UNITS: dict[str, int] = {
    "B": 1,
    "KB": 1_000,
    "KIB": 1_024,
    "MB": 1_000_000,
    "MIB": 1_048_576,
    "GB": 1_000_000_000,
    "GIB": 1_073_741_824,
    "TB": 1_000_000_000_000,
    "TIB": 1_099_511_627_776,
}
SIZE_PATTERN = re.compile(r"^([0-9]+(?:\.[0-9]+)?)\s*([A-Za-z]+)$")
ENV_NAME_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*$")
TRUE_VALUES = {"1", "true", "yes", "on"}
FALSE_VALUES = {"0", "false", "no", "off"}


class ConfigurationError(ValueError):
    """Raised when a service setting has an invalid value."""


def parse_size(value: str, name: str) -> int:
    """Parse a positive byte size such as ``2GiB``."""
    match = SIZE_PATTERN.fullmatch(value.strip())
    if match is None:
        raise ConfigurationError(f"{name} must be a size such as 500MiB or 2GiB")
    number = float(match.group(1))
    unit = match.group(2).upper()
    multiplier = SIZE_UNITS.get(unit)
    if multiplier is None:
        raise ConfigurationError(f"{name} uses an unknown size unit: {unit}")
    result = int(number * multiplier)
    if result <= 0:
        raise ConfigurationError(f"{name} must be greater than zero")
    return result


def parse_positive_int(value: str, name: str) -> int:
    """Parse a positive integer setting."""
    try:
        result = int(value)
    except ValueError as error:
        raise ConfigurationError(f"{name} must be an integer") from error
    if result <= 0:
        raise ConfigurationError(f"{name} must be greater than zero")
    return result


def parse_bool(value: str, name: str) -> bool:
    """Parse a boolean setting."""
    normalized = value.strip().lower()
    if normalized in TRUE_VALUES:
        return True
    if normalized in FALSE_VALUES:
        return False
    raise ConfigurationError(f"{name} must be true or false")


def format_bytes(value: int) -> str:
    """Format bytes with a compact binary unit."""
    if value < 1_024:
        return f"{value}B"
    units = ("KiB", "MiB", "GiB", "TiB")
    amount = float(value)
    for unit in units:
        amount /= 1_024
        if amount < 1_024 or unit == units[-1]:
            return f"{amount:.1f}{unit}"
    return f"{value}B"


def read_environment(path: Path) -> dict[str, str]:
    """Read simple KEY=VALUE settings without shell evaluation."""
    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ConfigurationError(f"{path}:{line_number} must contain KEY=VALUE")
        key, value = line.split("=", 1)
        key = key.strip()
        if ENV_NAME_PATTERN.fullmatch(key) is None:
            raise ConfigurationError(f"{path}:{line_number} has an invalid variable name")
        values[key] = value.strip()
    return values


def _value(values: dict[str, str], name: str, default: str) -> str:
    return values.get(name, default)


@dataclass(frozen=True)
class Config:
    """Validated service configuration."""

    home: Path
    state_dir: Path
    backup_dir: Path
    status_path: Path
    lock_path: Path
    opencode_command: Path
    opencode_db: Path
    opencode_log_dir: Path
    session_diff_dir: Path
    uv_cache: Path
    brave_cache: Path
    npm_cache: Path
    session_retention_days: int
    opencode_db_warn_size: int
    opencode_backup_max_size: int
    opencode_backup_max_count: int
    opencode_backup_retention_days: int
    opencode_log_retention_days: int
    uv_cache_max_size: int
    brave_cache_max_size: int
    npm_cache_warn_size: int
    journal_warn_size: int
    journal_system_max_use: str
    journal_system_max_file_size: str
    journal_runtime_max_use: str
    journal_runtime_max_file_size: str
    sqlite_vacuum_min_size: int
    sqlite_busy_timeout_seconds: int
    command_timeout_seconds: int
    opencode_upgrade_enabled: bool
    opencode_upgrade_method: str


def load_config() -> Config:
    """Load defaults, the user environment file, and process overrides."""
    home = Path.home()
    config_dir = Path(os.environ.get("XDG_CONFIG_HOME", home / ".config")) / "linux-cleanup-service"
    file_values = read_environment(config_dir / "environment")
    values = {**file_values, **os.environ}

    def size(name: str, default: str) -> int:
        return parse_size(_value(values, name, default), name)

    def integer(name: str, default: str) -> int:
        return parse_positive_int(_value(values, name, default), name)

    journal_method = _value(values, "OPENCODE_UPGRADE_METHOD", "curl").strip().lower()
    if journal_method not in {"curl", "npm", "pnpm", "bun", "brew", "choco", "scoop"}:
        raise ConfigurationError("OPENCODE_UPGRADE_METHOD is not supported")

    state_dir = Path(os.environ.get("XDG_STATE_HOME", home / ".local" / "state")) / "linux-cleanup-service"
    data_dir = Path(os.environ.get("XDG_DATA_HOME", home / ".local" / "share")) / "opencode"
    cache_dir = Path(os.environ.get("XDG_CACHE_HOME", home / ".cache"))
    return Config(
        home=home,
        state_dir=state_dir,
        backup_dir=state_dir / "backups",
        status_path=state_dir / "status.json",
        lock_path=state_dir / "cleanup.lock",
        opencode_command=Path(_value(values, "OPENCODE_COMMAND", str(home / ".opencode" / "bin" / "opencode"))),
        opencode_db=Path(_value(values, "OPENCODE_DB_PATH", str(data_dir / "opencode.db"))),
        opencode_log_dir=Path(_value(values, "OPENCODE_LOG_DIR", str(data_dir / "log"))),
        session_diff_dir=Path(_value(values, "OPENCODE_SESSION_DIFF_DIR", str(data_dir / "storage" / "session_diff"))),
        uv_cache=Path(_value(values, "UV_CACHE_PATH", str(cache_dir / "uv"))),
        brave_cache=Path(
            _value(values, "BRAVE_CACHE_PATH", str(cache_dir / "BraveSoftware" / "Brave-Browser"))
        ),
        npm_cache=Path(_value(values, "NPM_CACHE_PATH", str(home / ".npm"))),
        session_retention_days=integer("SESSION_RETENTION_DAYS", "7"),
        opencode_db_warn_size=size("OPENCODE_DB_WARN_SIZE", "2GiB"),
        opencode_backup_max_size=size("OPENCODE_BACKUP_MAX_SIZE", "4GiB"),
        opencode_backup_max_count=integer("OPENCODE_BACKUP_MAX_COUNT", "2"),
        opencode_backup_retention_days=integer("OPENCODE_BACKUP_RETENTION_DAYS", "14"),
        opencode_log_retention_days=integer("OPENCODE_LOG_RETENTION_DAYS", "14"),
        uv_cache_max_size=size("UV_CACHE_MAX_SIZE", "1GiB"),
        brave_cache_max_size=size("BRAVE_CACHE_MAX_SIZE", "2GiB"),
        npm_cache_warn_size=size("NPM_CACHE_WARN_SIZE", "1GiB"),
        journal_warn_size=size("JOURNAL_WARN_SIZE", "100MiB"),
        journal_system_max_use=_value(values, "JOURNAL_SYSTEM_MAX_USE", "80M"),
        journal_system_max_file_size=_value(values, "JOURNAL_SYSTEM_MAX_FILE_SIZE", "8M"),
        journal_runtime_max_use=_value(values, "JOURNAL_RUNTIME_MAX_USE", "16M"),
        journal_runtime_max_file_size=_value(values, "JOURNAL_RUNTIME_MAX_FILE_SIZE", "8M"),
        sqlite_vacuum_min_size=size("SQLITE_VACUUM_MIN_SIZE", "128MiB"),
        sqlite_busy_timeout_seconds=integer("SQLITE_BUSY_TIMEOUT_SECONDS", "30"),
        command_timeout_seconds=integer("COMMAND_TIMEOUT_SECONDS", "900"),
        opencode_upgrade_enabled=parse_bool(
            _value(values, "OPENCODE_UPGRADE_ENABLED", "true"), "OPENCODE_UPGRADE_ENABLED"
        ),
        opencode_upgrade_method=journal_method,
    )


def print_journal_config() -> None:
    """Print the root journald drop-in from the active configuration."""
    config = load_config()
    print("[Journal]")
    print("Compress=yes")
    print(f"SystemMaxUse={config.journal_system_max_use}")
    print(f"SystemMaxFileSize={config.journal_system_max_file_size}")
    print(f"RuntimeMaxUse={config.journal_runtime_max_use}")
    print(f"RuntimeMaxFileSize={config.journal_runtime_max_file_size}")


def print_journal_vacuum_size() -> None:
    """Print the persistent journal vacuum target."""
    print(load_config().journal_system_max_use)


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "journal-config":
        print_journal_config()
    elif len(sys.argv) == 2 and sys.argv[1] == "journal-vacuum-size":
        print_journal_vacuum_size()
    else:
        print(format_bytes(load_config().opencode_db_warn_size))
