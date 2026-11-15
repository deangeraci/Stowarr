import json
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from staging_verification import verify_attempt


class StagingVerificationTests(unittest.TestCase):
    def test_completed_candidate_records_manifest_without_import(self):
        store = Mock()
        qbit = Mock()
        qbit.info.return_value = {
            "category": "stowarr-replacement",
            "content_path": "/data/replacements/movie.mkv",
            "amount_left": 0, "progress": 1,
        }
        attempt = {
            "request_id": "r1", "release_id": "a" * 40,
            "torrent_hash": "a" * 40, "staging_category": "stowarr-replacement",
            "download_path": "/data/replacements",
            "snapshot": json.dumps({"release_size_bytes": 1000}),
        }
        manifest = {"sha256": "abc", "size_bytes": 1000}
        with patch("staging_verification.verify_media", return_value=manifest):
            self.assertEqual(verify_attempt(store, qbit, attempt), manifest)
        self.assertEqual(store.update_staging.call_args.kwargs["lifecycle_status"], "verified")
        self.assertNotIn("import", str(qbit.mock_calls).lower())

    def test_incomplete_candidate_remains_downloading(self):
        store = Mock()
        qbit = Mock()
        qbit.info.return_value = {
            "category": "stowarr-replacement",
            "content_path": "/data/replacements/movie.mkv",
            "amount_left": 10, "progress": 0.9,
        }
        attempt = {
            "request_id": "r1", "release_id": "a" * 40,
            "torrent_hash": "a" * 40, "staging_category": "stowarr-replacement",
            "download_path": "/data/replacements", "snapshot": "{}",
        }
        self.assertIsNone(verify_attempt(store, qbit, attempt))
        self.assertEqual(store.update_staging.call_args.kwargs["lifecycle_status"], "downloading")


if __name__ == "__main__":
    unittest.main()
