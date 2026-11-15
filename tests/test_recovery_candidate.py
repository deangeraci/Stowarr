import json
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from movie_staging_executor import fresh_recovery_snapshot


class FreshRecoveryCandidateTests(unittest.TestCase):
    def test_recovery_reads_live_movie_and_current_candidates(self):
        radarr = Mock()
        movie = {"id": 15, "title": "Movie", "year": 2020}
        candidate = {"identity_key": "movie:radarr:15", "title": "Movie (2020)",
                     "source_file_id": "2", "source_size_bytes": 20,
                     "release_id": "b" * 40, "release_title": "Fresh",
                     "release_size_bytes": 10, "indexer_id": "1"}
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.side_effect = [movie, [{"title": "Fresh"}]]
        radarr.request.return_value = response
        clients = {"radarr": radarr, "jellyfin": Mock()}
        attempt = {"release_id": "a" * 40,
                   "snapshot": json.dumps({"identity_key": "movie:radarr:15",
                                             "release_id": "a" * 40})}
        with patch("movie_staging_executor.live_eligible", return_value=True), \
             patch("movie_staging_executor.candidates", return_value=[(5, candidate)]):
            result = fresh_recovery_snapshot(attempt, clients, {}, "/state.db", "user")
        self.assertEqual(result, candidate)
        self.assertEqual(radarr.request.call_count, 2)
        self.assertEqual(radarr.request.call_args_list[1].args[0], "/api/v3/release?movieId=15")

    def test_recovery_excludes_prior_hash_and_returns_none_if_only_candidate(self):
        attempt = {"release_id": "a" * 40,
                   "snapshot": json.dumps({"identity_key": "movie:radarr:15",
                                             "release_id": "a" * 40})}
        movie = {"id": 15, "title": "Movie", "year": 2020}
        old = {"identity_key": "movie:radarr:15", "title": "Old", "source_file_id": "2",
               "source_size_bytes": 20, "release_id": "a" * 40, "release_title": "Old",
               "release_size_bytes": 10, "indexer_id": "1"}
        radarr = Mock()
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.side_effect = [movie, []]
        radarr.request.return_value = response
        with patch("movie_staging_executor.live_eligible", return_value=True), \
             patch("movie_staging_executor.candidates", return_value=[(10, old)]):
            self.assertIsNone(fresh_recovery_snapshot(
                attempt, {"radarr": radarr, "jellyfin": Mock()}, {}, "/state.db", "user"))

    def test_recovery_excludes_entire_lineage_and_selects_only_new_hash(self):
        attempt = {"release_id": "b" * 40,
                   "excluded_release_ids": {"a" * 40, "b" * 40},
                   "snapshot": json.dumps({"identity_key": "movie:radarr:15"})}
        radarr = Mock()
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.side_effect = [{"id": 15}, []]
        radarr.request.return_value = response
        a = dict(identity_key="movie:radarr:15", title="A", source_file_id="2",
                 source_size_bytes=20, release_id="a" * 40, release_title="A",
                 release_size_bytes=10, indexer_id="1")
        b = dict(a, release_id="b" * 40, release_title="B")
        c = dict(a, release_id="c" * 40, release_title="C")
        with patch("movie_staging_executor.live_eligible", return_value=True), \
             patch("movie_staging_executor.candidates", return_value=[(10, a), (9, b), (1, c)]):
            result = fresh_recovery_snapshot(
                attempt, {"radarr": radarr, "jellyfin": Mock()}, {}, "/state.db", "user")
        self.assertEqual(result["release_id"], "c" * 40)


if __name__ == "__main__":
    unittest.main()
