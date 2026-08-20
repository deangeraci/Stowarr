from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path


sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[1] / "src"),
)

from completion_confidence import CompletionEvidence
from completion_state import persist_completion_state
from state import initialize_database


class CompletionStateTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.tmp.name) / "state.db")
        initialize_database(self.db)
        self.connection = sqlite3.connect(self.db)

    def tearDown(self):
        self.connection.close()
        self.tmp.cleanup()

    def test_high_confidence_is_persisted(self):
        completed = datetime(
            2026, 8, 20, 3, 46, 25,
            tzinfo=timezone.utc,
        )

        persist_completion_state(
            self.connection,
            user_id="user1",
            item_id="avengers",
            item_type="Movie",
            item_name="The Avengers",
            played=True,
            evidence=CompletionEvidence(
                completed,
                "high",
                "credible session",
            ),
            grace_days=30,
        )

        row = self.connection.execute(
            """
            SELECT
                watched_state,
                completion_confidence,
                completion_time,
                eligible_at
            FROM media_user_state
            WHERE user_id='user1'
              AND item_id='avengers'
            """
        ).fetchone()

        self.assertEqual(row[0], "complete")
        self.assertEqual(row[1], "high")
        self.assertEqual(
            row[2],
            "2026-08-20T03:46:25+00:00",
        )
        self.assertEqual(
            row[3],
            "2026-09-19T03:46:25+00:00",
        )

    def test_partial_does_not_create_completion_time(self):
        persist_completion_state(
            self.connection,
            user_id="user1",
            item_id="episode1",
            item_type="Episode",
            item_name="Episode 1",
            played=True,
            evidence=CompletionEvidence(
                None,
                "partial",
                "insufficient evidence",
            ),
            grace_days=30,
        )

        row = self.connection.execute(
            """
            SELECT completion_time, completion_confidence
            FROM media_user_state
            """
        ).fetchone()

        self.assertIsNone(row[0])
        self.assertEqual(row[1], "partial")

    def test_partial_cannot_erase_trusted_completion(self):
        completed = datetime(
            2026, 8, 20, 3, 46, 25,
            tzinfo=timezone.utc,
        )

        persist_completion_state(
            self.connection,
            user_id="user1",
            item_id="avengers",
            item_type="Movie",
            item_name="The Avengers",
            played=True,
            evidence=CompletionEvidence(
                completed,
                "high",
                "credible session",
            ),
            grace_days=30,
        )

        persist_completion_state(
            self.connection,
            user_id="user1",
            item_id="avengers",
            item_type="Movie",
            item_name="The Avengers",
            played=True,
            evidence=CompletionEvidence(
                None,
                "partial",
                "later short replay",
            ),
            grace_days=30,
        )

        row = self.connection.execute(
            """
            SELECT
                completion_confidence,
                completion_time
            FROM media_user_state
            WHERE user_id='user1'
              AND item_id='avengers'
            """
        ).fetchone()

        self.assertEqual(row[0], "high")
        self.assertEqual(
            row[1],
            "2026-08-20T03:46:25+00:00",
        )


if __name__ == "__main__":
    unittest.main()
