import json
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from staging_reconciliation import reconcile_attempts


class ReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.store = Mock()
        self.store.list_staging_attempts.return_value = [
            {
                "request_id": "req1",
                "release_id": "abc123",
                "snapshot": json.dumps({"identity_key": "movie:radarr:15"}),
            },
            {
                "request_id": "req2",
                "release_id": "def456",
                "snapshot": json.dumps({"identity_key": "movie:radarr:16"}),
            },
        ]
        self.radarr = Mock()

    def history(self, records, total=None):
        response = Mock()
        response.json.return_value = {
            "totalRecords": len(records) if total is None else total,
            "records": records,
        }
        return response

    def grab(self, movie_id, hash_):
        return {
            "movieId": movie_id,
            "downloadId": hash_,
            "eventType": "grabbed",
            "data": {"torrentInfoHash": hash_},
        }

    def test_matching_movie_and_hash(self):
        self.radarr.request.return_value = self.history([
            self.grab(15, "abc123"),
            self.grab(99, "def456"),
        ])
        result = reconcile_attempts(self.store, self.radarr)
        self.assertEqual(result, [
            ("req1", "confirmed"),
            ("req2", "unresolved"),
        ])
        self.store.update_staging.assert_called_once_with(
            "req1", "confirmed"
        )

    def test_missing_history_never_retries(self):
        self.radarr.request.return_value = self.history([])
        result = reconcile_attempts(self.store, self.radarr)
        self.assertTrue(all(s == "unresolved" for _, s in result))
        self.store.update_staging.assert_not_called()

    def test_pagination(self):
        self.radarr.request.side_effect = [
            self.history([self.grab(99, "other")], total=2),
            self.history([self.grab(16, "def456")], total=2),
        ]
        result = reconcile_attempts(
            self.store, self.radarr, page_size=1
        )
        self.assertIn(("req2", "confirmed"), result)
        self.assertEqual(self.radarr.request.call_count, 2)

    def test_mismatched_torrent_hash_rejected(self):
        record = self.grab(15, "abc123")
        record["data"]["torrentInfoHash"] = "different"
        self.radarr.request.return_value = self.history([record])
        result = reconcile_attempts(self.store, self.radarr)
        self.assertEqual(result[0], ("req1", "unresolved"))
        self.store.update_staging.assert_not_called()


if __name__ == "__main__":
    unittest.main()
