#!/usr/bin/env python3
"""Black-box checks for configuration parsing and journal output."""

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

from config import ConfigurationError, format_bytes, parse_size
from cleanup import parse_journal_size


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
            config_dir = Path(temp_dir) / "linux-cleanup-service"
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

    def test_journal_config_uses_environment_override(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            env = os.environ.copy()
            env["XDG_CONFIG_HOME"] = temp_dir
            config_dir = Path(temp_dir) / "linux-cleanup-service"
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


if __name__ == "__main__":
    unittest.main()
