#!/usr/bin/env python3
"""Black-box checks for configuration parsing and root drop-in output."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from config import SERVICE_NAME, ConfigurationError, format_bytes, load_config, parse_size
from cleanup import journal_size, parse_journal_size


class ConfigurationTest(unittest.TestCase):
    def test_size_parser_accepts_binary_units(self) -> None:
        self.assertEqual(parse_size("1GiB", "TEST"), 1_073_741_824)
        self.assertEqual(parse_size("500MiB", "TEST"), 524_288_000)

    def test_size_parser_rejects_unknown_units(self) -> None:
        with self.assertRaises(ConfigurationError):
            parse_size("4bananas", "TEST")

    def test_temp_root_must_be_absolute(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            env = os.environ.copy()
            env["XDG_CONFIG_HOME"] = temp_dir
            config_dir = Path(temp_dir) / SERVICE_NAME
            config_dir.mkdir()
            (config_dir / "environment").write_text("TEMP_ROOT=relative\n", encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(SRC / "config.py")],
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )
            self.assertNotEqual(result.returncode, 0)

    def test_format_bytes_is_compact(self) -> None:
        self.assertEqual(format_bytes(1_048_576), "1.0MiB")

    def test_journal_size_parser_reads_decimal_unit(self) -> None:
        self.assertEqual(parse_journal_size("Archived and active journals take up 990.2M"), 990_200_000)

    @unittest.skipUnless(sys.platform == "linux", "journalctl permission behavior is Linux-only")
    def test_permission_limited_journal_is_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_home = root / "config"
            config_dir = config_home / SERVICE_NAME
            command_dir = root / "bin"
            config_dir.mkdir(parents=True)
            command_dir.mkdir()
            (config_dir / "environment").write_text("COMMAND_TIMEOUT_SECONDS=5\n", encoding="utf-8")
            journalctl = command_dir / "journalctl"
            journalctl.write_text(
                "#!/bin/sh\nprintf 'No journal files were opened due to insufficient permissions.\\n' >&2\nexit 1\n",
                encoding="utf-8",
            )
            journalctl.chmod(0o755)
            original = {key: os.environ.get(key) for key in ("PATH", "XDG_CONFIG_HOME")}
            try:
                os.environ["PATH"] = f"{command_dir}:{os.environ['PATH']}"
                os.environ["XDG_CONFIG_HOME"] = str(config_home)
                skipped: list[str] = []
                size, error = journal_size(False, load_config(), skipped)
            finally:
                for key, value in original.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value
            self.assertIsNone(size)
            self.assertIsNone(error)
            self.assertEqual(skipped, ["system journal measurement"])

    @unittest.skipUnless(sys.platform == "linux", "journalctl permission behavior is Linux-only")
    def test_journal_size_accepts_size_with_permission_hint(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_home = root / "config"
            config_dir = config_home / SERVICE_NAME
            command_dir = root / "bin"
            config_dir.mkdir(parents=True)
            command_dir.mkdir()
            journalctl = command_dir / "journalctl"
            journalctl.write_text(
                "#!/bin/sh\nprintf 'Archived and active journals take up 8M in the file system.\\n'\nprintf 'Hint: insufficient permissions for other users.\\n' >&2\n",
                encoding="utf-8",
            )
            journalctl.chmod(0o755)
            original = {key: os.environ.get(key) for key in ("PATH", "XDG_CONFIG_HOME")}
            try:
                os.environ["PATH"] = f"{command_dir}:{os.environ['PATH']}"
                os.environ["XDG_CONFIG_HOME"] = str(config_home)
                skipped: list[str] = []
                size, error = journal_size(False, load_config(), skipped)
            finally:
                for key, value in original.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value
            self.assertEqual(size, 8_000_000)
            self.assertIsNone(error)
            self.assertEqual(skipped, [])

    def test_journal_config_uses_environment_override(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            env = os.environ.copy()
            env["XDG_CONFIG_HOME"] = temp_dir
            config_dir = Path(temp_dir) / SERVICE_NAME
            config_dir.mkdir()
            (config_dir / "environment").write_text(
                "JOURNAL_SYSTEM_MAX_USE=70M\nJOURNAL_RUNTIME_MAX_USE=12M\n", encoding="utf-8"
            )
            result = subprocess.run(
                [sys.executable, str(SRC / "config.py"), "journal-config"],
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )
            self.assertEqual(result.returncode, 0)
            self.assertIn("SystemMaxUse=70M", result.stdout)
            self.assertIn("RuntimeMaxUse=12M", result.stdout)

    def test_sudoers_config_lists_exact_service_commands(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            env = os.environ.copy()
            env["XDG_CONFIG_HOME"] = temp_dir
            config_dir = Path(temp_dir) / SERVICE_NAME
            config_dir.mkdir()
            (config_dir / "environment").write_text(
                "JOURNAL_SYSTEM_MAX_USE=70M\n", encoding="utf-8"
            )
            result = subprocess.run(
                [sys.executable, str(SRC / "config.py"), "sudoers-config"],
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )
            self.assertEqual(result.returncode, 0)
            self.assertIn("ALL=(root) NOPASSWD:", result.stdout)
            self.assertIn("/usr/bin/apt-get update", result.stdout)
            self.assertIn("/usr/bin/apt-get upgrade -y", result.stdout)
            self.assertIn("/usr/bin/snap refresh", result.stdout)
            self.assertIn("/usr/bin/journalctl --rotate", result.stdout)
            self.assertIn("/usr/bin/journalctl --vacuum-size=70M", result.stdout)


if __name__ == "__main__":
    unittest.main()
