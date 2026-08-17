#!/usr/bin/env python3
"""Black-box checks for SQLite storage reclamation."""

from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from cleanup import maybe_vacuum
from config import load_config


class SQLiteVacuumTest(unittest.TestCase):
    def test_vacuum_runs_when_another_client_has_the_database_open(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database = Path(temp_dir) / "opencode.db"
            seed = sqlite3.connect(database)
            try:
                seed.execute("CREATE TABLE data (value TEXT)")
                seed.executemany("INSERT INTO data VALUES (?)", [("x" * 4096,) for _ in range(512)])
                seed.commit()
                seed.execute("DELETE FROM data")
                seed.commit()
                open_client = sqlite3.connect(database)
                try:
                    config = replace(
                        load_config(),
                        opencode_db=database,
                        sqlite_vacuum_min_size=1,
                        sqlite_busy_timeout_seconds=1,
                    )
                    warnings: list[str] = []
                    skipped: list[str] = []
                    maybe_vacuum(config, warnings, skipped, False)
                finally:
                    open_client.close()
            finally:
                seed.close()

            self.assertEqual(warnings, [])
            self.assertEqual(skipped, [])
            with sqlite3.connect(database) as connection:
                self.assertEqual(connection.execute("PRAGMA freelist_count").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
