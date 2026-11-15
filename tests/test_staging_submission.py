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
            {
                "STOWARR_RADARR_DOWNLOAD_CLIENT_ID": "2",
                "STOWARR_QBITTORRENT_CATEGORY": "stowarr",
                "STOWARR_REPLACEMENT_CATEGORY": "stowarr-replacement",
                "STOWARR_REPLACEMENT_PATH": "/data/replacements",
            }, clear=False)
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)
        self.snapshot = {
            "identity_key": "movie:radarr:15",
            "title": "Test Movie",
            "source_file_id": "9",
            "source_size_bytes": 2000,
            "release_id": "a" * 40,
            "indexer_id": "4",
            "release_title": "Test Release",
            "release_size_bytes": 1000,
        }
        self.request = {"id": "req1", "snapshot": self.snapshot}
        self.store = Mock()
        self.radarr = Mock()
        self.radarr.request.side_effect = [
            Mock(json=lambda: {"id": 15}),
            Mock(json=lambda: [{
                "infoHash": "a" * 40,
                "indexerId": 4,
                "title": "Test Release",
                "size": 1000,
                "downloadUrl": "magnet:?xt=urn:btih:" + "a" * 40,
            }]),
            Mock(json=lambda: [{"path": "/data/media/movies"}]),
            Mock(json=lambda: {"id": 2, "fields": [{"name": "movieCategory", "value": "stowarr"}]}),
        ]
        self.clients = {"radarr": self.radarr}
        self.qbit = Mock()
        self.qbit.categories.return_value = {"stowarr-replacement": {}}
        self.qbit.info.side_effect = [
            None,
            {"hash": "a" * 40, "category": "stowarr-replacement", "save_path": "/data/replacements"},
        ]

    @patch("movie_staging_executor.exact_release", return_value={})
    @patch("movie_staging_executor.live_eligible", return_value=True)
    def test_success_uses_qbit_and_never_posts_to_radarr(self, eligible, exact):
        result = stage_one(self.store, self.request, self.clients, {}, "", "", self.qbit)
        self.assertTrue(result.startswith("staged:"))
        self.store.claim_staging.assert_called_once()
        self.qbit.add_torrent.assert_called_once()
        self.radarr.post.assert_not_called()
        self.store.update_staging.assert_any_call(
            "req1", "confirmed", lifecycle_status="downloading",
            torrent_hash="a" * 40, staging_category="stowarr-replacement",
            download_path="/data/replacements")

    @patch("movie_staging_executor.exact_release", return_value={})
    @patch("movie_staging_executor.live_eligible", return_value=True)
    def test_timeout_is_uncertain_and_restart_can_reconcile(self, eligible, exact):
        self.qbit.add_torrent.side_effect = requests.Timeout("simulated")
        result = stage_one(self.store, self.request, self.clients, {}, "", "", self.qbit)
        self.assertTrue(result.startswith("uncertain:"))
        self.store.update_staging.assert_any_call(
            "req1", "uncertain", error="Timeout")

    @patch("movie_staging_executor.exact_release", return_value={})
    @patch("movie_staging_executor.live_eligible", return_value=True)
    def test_existing_wrong_category_fails_without_new_download(self, eligible, exact):
        self.qbit.info.side_effect = [{
            "hash": "a" * 40, "category": "stowarr", "save_path": "/data/replacements"
        }]
        result = stage_one(self.store, self.request, self.clients, {}, "", "", self.qbit)
        self.assertTrue(result.startswith("failed:"))
        self.qbit.add_torrent.assert_not_called()
        self.store.claim_staging.assert_not_called()


if __name__ == "__main__":
    unittest.main()
