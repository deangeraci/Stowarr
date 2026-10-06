import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from completion_config import configured_grace_days
from completion_confidence import local_wall_clock_to_utc, assess_completion


class CompletionConfigTests(unittest.TestCase):
    def test_nested_delay_wins(self):
        self.assertEqual(configured_grace_days({"lifecycle":{"watched_delay_days":60}, "watched_delay_days":30}), 60)

    def test_legacy_and_default_delay(self):
        self.assertEqual(configured_grace_days({"watched_delay_days":45}), 45)
        self.assertEqual(configured_grace_days({}), 30)
        self.assertEqual(configured_grace_days({"lifecycle":{"watched_delay_days":0}}), 0)

    def test_invalid_delays_fail_closed(self):
        for raw in [-1, True, 0.5, None, "-1", "invalid"]:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                configured_grace_days({"lifecycle":{"watched_delay_days":raw}})


class TimezoneMigrationTests(unittest.TestCase):
    history = dict(before="America/New_York", after="America/Chicago",
                   uncertain_from="2026-09-01", uncertain_until="2026-09-10")

    def test_before_and_after_boundary_use_correct_offsets(self):
        self.assertEqual(local_wall_clock_to_utc("2026-08-31T20:00:00", self.history).isoformat(), "2026-09-01T00:00:00+00:00")
        self.assertEqual(local_wall_clock_to_utc("2026-09-10T20:00:00", self.history).isoformat(), "2026-09-11T01:00:00+00:00")

    def test_migration_window_stays_partial(self):
        for date in ["2026-09-01T20:00:00", "2026-09-09T20:00:00"]:
            result = assess_completion(played=True, runtime_seconds=3600,
                session_started_at=date, session_duration_seconds=3600,
                jellyfin_last_played_at=None, timezone_name=self.history)
            self.assertEqual(result.confidence, "partial")
            self.assertIsNone(result.completion_time)

    def test_aware_timestamp_preserves_its_offset(self):
        self.assertEqual(local_wall_clock_to_utc("2026-09-05T20:00:00-05:00", self.history).isoformat(), "2026-09-06T01:00:00+00:00")
