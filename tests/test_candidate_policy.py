from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[1] / "src"),
)

from candidate_policy import GIB, evaluate_candidate


class CandidatePolicyTests(unittest.TestCase):

    def test_good_hevc_candidate(self):
        result = evaluate_candidate(
            current_size_bytes=25 * GIB,
            candidate_size_bytes=8 * GIB,
            resolution=1080,
            codec="HEVC",
            release_title="Movie 1080p x265",
        )

        self.assertTrue(result.accepted)
        self.assertTrue(result.preferred_codec)

    def test_720p_is_rejected(self):
        result = evaluate_candidate(
            current_size_bytes=25 * GIB,
            candidate_size_bytes=5 * GIB,
            resolution=720,
            codec="HEVC",
            release_title="Movie 720p x265",
        )

        self.assertFalse(result.accepted)

    def test_larger_file_is_rejected(self):
        result = evaluate_candidate(
            current_size_bytes=10 * GIB,
            candidate_size_bytes=12 * GIB,
            resolution=2160,
            codec="HEVC",
            release_title="Movie 2160p x265",
        )

        self.assertFalse(result.accepted)

    def test_remux_is_rejected(self):
        result = evaluate_candidate(
            current_size_bytes=50 * GIB,
            candidate_size_bytes=25 * GIB,
            resolution=2160,
            codec="HEVC",
            release_title="Movie 2160p REMUX",
        )

        self.assertFalse(result.accepted)

    def test_cam_is_rejected(self):
        result = evaluate_candidate(
            current_size_bytes=20 * GIB,
            candidate_size_bytes=3 * GIB,
            resolution=1080,
            codec="x265",
            release_title="Movie 1080p CAM x265",
        )

        self.assertFalse(result.accepted)

    def test_absolute_savings_threshold(self):
        result = evaluate_candidate(
            current_size_bytes=20 * GIB,
            candidate_size_bytes=14 * GIB,
            resolution=1080,
            codec="x265",
            release_title="Movie 1080p x265",
        )

        self.assertTrue(result.accepted)

    def test_percentage_savings_threshold(self):
        result = evaluate_candidate(
            current_size_bytes=8 * GIB,
            candidate_size_bytes=4 * GIB,
            resolution=1080,
            codec="x265",
            release_title="Movie 1080p x265",
        )

        self.assertTrue(result.accepted)

    def test_small_savings_rejected(self):
        result = evaluate_candidate(
            current_size_bytes=20 * GIB,
            candidate_size_bytes=17 * GIB,
            resolution=1080,
            codec="x265",
            release_title="Movie 1080p x265",
        )

        self.assertFalse(result.accepted)

    def test_avc_can_pass_but_is_not_preferred(self):
        result = evaluate_candidate(
            current_size_bytes=25 * GIB,
            candidate_size_bytes=8 * GIB,
            resolution=1080,
            codec="H264",
            release_title="Movie 1080p AVC",
        )

        self.assertTrue(result.accepted)
        self.assertFalse(result.preferred_codec)


if __name__ == "__main__":
    unittest.main()
