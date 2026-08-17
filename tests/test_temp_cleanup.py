#!/usr/bin/env python3
"""Black-box checks for temporary workspace cleanup."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from cleanup import clean_temp_workspaces
from config import SERVICE_NAME, load_config


class TemporaryCleanupTest(unittest.TestCase):
    def test_deletes_old_workspace_and_preserves_recent_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_home = Path(temp_dir) / "config"
            temp_root = Path(temp_dir) / "opencode"
            config_dir = config_home / SERVICE_NAME
            config_dir.mkdir(parents=True)
            (config_dir / "environment").write_text(
                f"TEMP_ROOT={temp_root}\nTEMP_RETENTION_DAYS=7\n",
                encoding="utf-8",
            )
            old_workspace = temp_root / "old"
            recent_workspace = temp_root / "recent"
            old_workspace.mkdir(parents=True)
            recent_workspace.mkdir(parents=True)
            (old_workspace / "result.txt").write_text("old", encoding="utf-8")
            now = datetime.now().astimezone()
            old_time = (now - timedelta(days=8)).timestamp()
            os.utime(old_workspace, (old_time, old_time))
            os.environ["XDG_CONFIG_HOME"] = str(config_home)
            try:
                config = load_config()
                result = clean_temp_workspaces(config, now, False, [], [])
            finally:
                os.environ.pop("XDG_CONFIG_HOME", None)
            self.assertEqual(result["temp_deleted"], 1)
            self.assertFalse(old_workspace.exists())
            self.assertTrue(recent_workspace.exists())


if __name__ == "__main__":
    unittest.main()
