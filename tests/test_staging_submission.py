import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from movie_staging_executor import stage_one


class SubmissionTests(unittest.TestCase):
    def setUp(self):
        self.env_patch = patch.dict(
            "os.environ",
            {"STOWARR_RADARR_DOWNLOAD_CLIENT_ID": "2"}
        )
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)
        self.snapshot = {
            "identity_key": "movie:radarr:15",
            "title": "Test Movie",
            "release_id": "a" * 40,
            "indexer_id": "4",
            "release_title": "Test Release",
            "release_size_bytes": 1000,
        }
        self.request = {"id": "req1", "snapshot": self.snapshot}
        self.store = Mock()
        self.radarr = Mock()
        self.radarr.base_url = "http://radarr:7878"
        self.radarr._headers.return_value = {}
        self.radarr.request.side_effect = [
            Mock(json=lambda: {"id": 15}),
            Mock(json=lambda: [{
                "infoHash": "a" * 40,
                "indexerId": 4,
                "title": "Test Release",
                "size": 1000,
            }]),
        ]
        self.clients = {"radarr": self.radarr}

    @patch("movie_staging_executor.requests.post")
    @patch("movie_staging_executor.exact_release", return_value={})
    @patch("movie_staging_executor.live_eligible", return_value=True)
    def test_success(self, eligible, exact, post):
        result = stage_one(
            self.store, self.request, self.clients, {}, "", ""
        )
        self.assertTrue(result.startswith("staged:"))
        self.store.claim_staging.assert_called_once()
        self.assertEqual(
            post.call_args.kwargs["json"]["downloadClientId"], 2
        )
        self.store.update_staging.assert_any_call("req1", "confirmed")

    @patch("movie_staging_executor.requests.post",
           side_effect=requests.Timeout("simulated"))
    @patch("movie_staging_executor.exact_release", return_value={})
    @patch("movie_staging_executor.live_eligible", return_value=True)
    def test_timeout_is_uncertain(self, eligible, exact, post):
        result = stage_one(
            self.store, self.request, self.clients, {}, "", ""
        )
        self.assertTrue(result.startswith("uncertain:"))
        self.store.update_staging.assert_any_call("req1", "uncertain")


if __name__ == "__main__":
    unittest.main()
