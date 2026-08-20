from __future__ import annotations

import sys
import unittest
from datetime import datetime
from pathlib import Path


sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[1] / "src"),
)

from completion_selector import (
    PlaybackSession,
    select_completion,
)


TZ = "America/New_York"


class CompletionSelectorTests(unittest.TestCase):

    def test_full_session_wins_over_short_sessions(self):
        result = select_completion(
            played=True,
            runtime_seconds=8008,
            sessions=[
                PlaybackSession(
                    datetime.fromisoformat(
                        "2026-07-31T17:58:53.703180"
                    ),
                    189,
                ),
                PlaybackSession(
                    datetime.fromisoformat(
                        "2026-07-31T21:53:52.654300"
                    ),
                    7413,
                ),
            ],
            jellyfin_last_played_at=(
                "2026-08-16T21:20:24.629Z"
            ),
            timezone_name=TZ,
        )

        self.assertEqual(result.confidence, "high")
        self.assertEqual(
            result.completion_time.isoformat(),
            "2026-08-01T03:57:25.654300+00:00",
        )

    def test_short_only_history_remains_partial(self):
        result = select_completion(
            played=True,
            runtime_seconds=2703,
            sessions=[
                PlaybackSession(
                    datetime.fromisoformat(
                        "2026-07-24T18:20:54.608724"
                    ),
                    118,
                ),
            ],
            jellyfin_last_played_at=(
                "2026-08-16T21:20:19.202Z"
            ),
            timezone_name=TZ,
        )

        self.assertEqual(result.confidence, "partial")
        self.assertIsNone(result.completion_time)

    def test_unplayed_item_never_completes(self):
        result = select_completion(
            played=False,
            runtime_seconds=7200,
            sessions=[
                PlaybackSession(
                    datetime.fromisoformat(
                        "2026-08-19T20:00:00"
                    ),
                    7000,
                ),
            ],
            jellyfin_last_played_at=(
                "2026-08-20T00:00:00Z"
            ),
            timezone_name=TZ,
        )

        self.assertEqual(result.confidence, "none")
        self.assertIsNone(result.completion_time)


if __name__ == "__main__":
    unittest.main()
