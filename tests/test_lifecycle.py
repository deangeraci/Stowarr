from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path


sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[1] / "src"),
)

from lifecycle import assess_lifecycle


NOW = datetime(
    2026, 8, 19, 2, 0, 0,
    tzinfo=timezone.utc,
)


class LifecycleTests(unittest.TestCase):

    def test_incomplete_is_blocked(self):
        result = assess_lifecycle(
            watched_state="incomplete",
            completion_time=None,
            completion_confidence="unknown",
            delay_days=30,
            now=NOW,
        )
        self.assertEqual(result.status, "BLOCKED")

    def test_complete_without_timestamp_is_blocked(self):
        result = assess_lifecycle(
            watched_state="complete",
            completion_time=None,
            completion_confidence="unknown",
            delay_days=30,
            now=NOW,
        )
        self.assertEqual(result.status, "BLOCKED")

    def test_partial_confidence_is_blocked(self):
        result = assess_lifecycle(
            watched_state="complete",
            completion_time="2026-07-01T00:00:00+00:00",
            completion_confidence="partial",
            delay_days=30,
            now=NOW,
        )
        self.assertEqual(result.status, "BLOCKED")

    def test_high_confidence_waits_30_days(self):
        result = assess_lifecycle(
            watched_state="complete",
            completion_time="2026-08-01T00:00:00+00:00",
            completion_confidence="high",
            delay_days=30,
            now=NOW,
        )
        self.assertEqual(result.status, "WAIT")

    def test_high_confidence_becomes_eligible(self):
        result = assess_lifecycle(
            watched_state="complete",
            completion_time="2026-06-01T00:00:00+00:00",
            completion_confidence="high",
            delay_days=30,
            now=NOW,
        )
        self.assertEqual(result.status, "ELIGIBLE")


if __name__ == "__main__":
    unittest.main()
