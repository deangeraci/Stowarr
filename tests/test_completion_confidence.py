from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[1] / "src"),
)

from completion_confidence import assess_completion


class CompletionConfidenceTests(unittest.TestCase):

    def test_unplayed_item_is_not_complete(self):
        result = assess_completion(
            played=False,
            runtime_seconds=7200,
            session_started_at="2026-08-19T00:00:00Z",
            session_duration_seconds=7000,
            jellyfin_last_played_at="2026-08-19T00:00:00Z",
        )

        self.assertEqual(result.confidence, "none")
        self.assertIsNone(result.completion_time)

    def test_missing_session_is_partial(self):
        result = assess_completion(
            played=True,
            runtime_seconds=7200,
            session_started_at=None,
            session_duration_seconds=None,
            jellyfin_last_played_at="2026-08-19T02:00:00Z",
        )

        self.assertEqual(result.confidence, "partial")
        self.assertIsNone(result.completion_time)

    def test_short_session_is_partial(self):
        result = assess_completion(
            played=True,
            runtime_seconds=7200,
            session_started_at="2026-08-19T00:00:00Z",
            session_duration_seconds=1200,
            jellyfin_last_played_at="2026-08-19T00:00:00Z",
        )

        self.assertEqual(result.confidence, "partial")
        self.assertIsNone(result.completion_time)

    def test_full_session_is_high_confidence(self):
        result = assess_completion(
            played=True,
            runtime_seconds=7200,
            session_started_at="2026-08-19T00:00:00Z",
            session_duration_seconds=7000,
            jellyfin_last_played_at="2026-08-19T01:56:40Z",
        )

        self.assertEqual(result.confidence, "high")
        self.assertIsNotNone(result.completion_time)

    def test_large_timing_mismatch_is_partial(self):
        result = assess_completion(
            played=True,
            runtime_seconds=7200,
            session_started_at="2026-08-19T00:00:00Z",
            session_duration_seconds=7000,
            jellyfin_last_played_at="2026-08-19T05:00:00Z",
        )

        self.assertEqual(result.confidence, "partial")
        self.assertIsNone(result.completion_time)


if __name__ == "__main__":
    unittest.main()
