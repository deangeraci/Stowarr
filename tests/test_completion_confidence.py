from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[1] / "src"),
)

from completion_confidence import assess_completion


TZ = "America/New_York"


class CompletionConfidenceTests(unittest.TestCase):

    def test_unplayed_item_is_not_complete(self):
        result = assess_completion(
            played=False,
            runtime_seconds=7200,
            session_started_at="2026-08-19T00:00:00",
            session_duration_seconds=7000,
            jellyfin_last_played_at="2026-08-19T04:00:00Z",
            timezone_name=TZ,
        )

        self.assertEqual(result.confidence, "none")
        self.assertIsNone(result.completion_time)

    def test_missing_session_is_partial(self):
        result = assess_completion(
            played=True,
            runtime_seconds=7200,
            session_started_at=None,
            session_duration_seconds=None,
            jellyfin_last_played_at="2026-08-19T04:00:00Z",
            timezone_name=TZ,
        )

        self.assertEqual(result.confidence, "partial")
        self.assertIsNone(result.completion_time)

    def test_short_session_is_partial(self):
        result = assess_completion(
            played=True,
            runtime_seconds=7200,
            session_started_at="2026-08-19T00:00:00",
            session_duration_seconds=1200,
            jellyfin_last_played_at="2026-08-19T04:00:00Z",
            timezone_name=TZ,
        )

        self.assertEqual(result.confidence, "partial")
        self.assertIsNone(result.completion_time)

    def test_later_last_played_preserves_historical_completion(self):
        result = assess_completion(
            played=True,
            runtime_seconds=7200,
            session_started_at="2026-08-19T00:00:00",
            session_duration_seconds=7000,
            jellyfin_last_played_at="2026-08-20T04:00:00Z",
            timezone_name=TZ,
        )

        self.assertEqual(result.confidence, "high")
        self.assertIsNotNone(result.completion_time)

    def test_last_played_before_session_is_partial(self):
        result = assess_completion(
            played=True,
            runtime_seconds=7200,
            session_started_at="2026-08-19T00:00:00",
            session_duration_seconds=7000,
            jellyfin_last_played_at="2026-08-18T20:00:00Z",
            timezone_name=TZ,
        )

        self.assertEqual(result.confidence, "partial")
        self.assertIsNone(result.completion_time)

    def test_spiderman3_real_world_evidence_is_high_confidence(self):
        result = assess_completion(
            played=True,
            runtime_seconds=8350,
            session_started_at="2026-08-18T22:00:47.279543",
            session_duration_seconds=8089,
            jellyfin_last_played_at="2026-08-19T02:00:27.2448696Z",
            timezone_name=TZ,
        )

        self.assertEqual(result.confidence, "high")
        self.assertIsNotNone(result.completion_time)

        self.assertEqual(
            result.completion_time.isoformat(),
            "2026-08-19T04:15:36.279543+00:00",
        )


if __name__ == "__main__":
    unittest.main()
