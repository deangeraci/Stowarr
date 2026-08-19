from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[1] / "src"),
)

from audit import record_event
from state import (
    CURRENT_SCHEMA_VERSION,
    identity_key,
    initialize_database,
)


class StateTests(unittest.TestCase):

    def test_movie_identity(self):
        self.assertEqual(
            identity_key("movie", "radarr:5"),
            "movie:radarr:5",
        )

    def test_season_identity(self):
        self.assertEqual(
            identity_key(
                "season",
                "tvdb:123",
                1,
            ),
            "season:tvdb:123:season:1",
        )

    def test_existing_season_suffix_not_duplicated(self):
        self.assertEqual(
            identity_key(
                "season",
                "Mr. Robot:season:1",
                1,
            ),
            "season:Mr. Robot:season:1",
        )

    def test_schema_and_audit(self):
        with tempfile.TemporaryDirectory() as temp:
            db = str(
                Path(temp) / "test.db"
            )

            initialize_database(db)

            con = sqlite3.connect(db)

            version = con.execute(
                """
                SELECT value
                FROM schema_metadata
                WHERE key='schema_version'
                """
            ).fetchone()[0]

            self.assertEqual(
                int(version),
                CURRENT_SCHEMA_VERSION,
            )

            record_event(
                con,
                event_type="test_event",
                identity_key="movie:test",
                details={"safe": True},
            )

            con.commit()

            count = con.execute(
                """
                SELECT COUNT(*)
                FROM audit_log
                """
            ).fetchone()[0]

            self.assertEqual(count, 1)

            con.close()


if __name__ == "__main__":
    unittest.main()
