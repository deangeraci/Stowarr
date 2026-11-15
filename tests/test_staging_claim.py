import concurrent.futures
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from approvals import ApprovalStore, fingerprint


class StagingClaimTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = ApprovalStore(Path(self.tmp.name) / "approvals.sqlite3")
        self.snapshot = {
            "identity_key": "movie:radarr:15",
            "title": "Test Movie",
            "source_file_id": "10",
            "source_size_bytes": 20_000_000_000,
            "release_id": "a" * 40,
            "release_title": "Test Movie 1080p HEVC",
            "release_size_bytes": 6_000_000_000,
            "indexer_id": "1",
        }
        self.rid = self.store.propose(self.snapshot)
        self.store.decide(
            self.rid, fingerprint(self.snapshot), "approved", "test"
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_claim_is_atomic(self):
        self.store.claim_staging(self.rid, self.snapshot)
        with sqlite3.connect(self.store.path) as db:
            status = db.execute(
                "SELECT status FROM approval_requests WHERE id=?",
                (self.rid,),
            ).fetchone()[0]
            attempts = db.execute(
                "SELECT status FROM staging_attempts WHERE request_id=?",
                (self.rid,),
            ).fetchall()
        self.assertEqual(status, "consumed")
        self.assertEqual(attempts, [("claimed",)])

    def test_concurrent_claims_only_one_succeeds(self):
        def claim(_):
            try:
                self.store.claim_staging(self.rid, self.snapshot)
                return True
            except ValueError:
                return False

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(claim, range(4)))
        self.assertEqual(sum(results), 1)

    def test_restart_cannot_claim_same_approval_twice(self):
        self.store.claim_staging(self.rid, self.snapshot)

        restarted = ApprovalStore(self.store.path)
        with self.assertRaises(ValueError):
            restarted.claim_staging(self.rid, self.snapshot)

        attempts = restarted.list_staging_attempts({"claimed"})
        self.assertEqual(len(attempts), 1)
        self.assertEqual(attempts[0]["request_id"], self.rid)

    def test_failed_insert_rolls_back_approval(self):
        with sqlite3.connect(self.store.path) as db:
            db.execute("""
                CREATE TRIGGER reject_staging
                BEFORE INSERT ON staging_attempts
                BEGIN
                    SELECT RAISE(ABORT, 'simulated insert failure');
                END
            """)

        with self.assertRaises(sqlite3.IntegrityError):
            self.store.claim_staging(self.rid, self.snapshot)

        with sqlite3.connect(self.store.path) as db:
            status = db.execute(
                "SELECT status FROM approval_requests WHERE id=?",
                (self.rid,),
            ).fetchone()[0]
            count = db.execute(
                "SELECT COUNT(*) FROM staging_attempts"
            ).fetchone()[0]

        self.assertEqual(status, "approved")
        self.assertEqual(count, 0)

    def test_recovery_persists_fresh_snapshot_once(self):
        self.store.claim_staging(self.rid, self.snapshot)
        fresh = dict(self.snapshot, release_id="b" * 40,
                     release_title="Fresh Release")
        first = self.store.propose_recovery(self.rid, fresh)
        second = self.store.propose_recovery(self.rid, dict(self.snapshot))
        self.assertEqual(first, second)
        row = self.store.list()[0]
        self.assertEqual(row["id"], first)
        self.assertEqual(row["snapshot"]["release_id"], "b" * 40)

    def test_recovery_lineage_contains_all_prior_hashes(self):
        self.store.claim_staging(self.rid, self.snapshot)
        b = dict(self.snapshot, release_id="b" * 40, release_title="Release B")
        b_request = self.store.propose_recovery(self.rid, b)
        self.store.decide(b_request, fingerprint(b), "approved", "test")
        self.store.claim_staging(b_request, b)
        self.assertEqual(self.store.attempted_release_ids(b_request), {"a" * 40, "b" * 40})


if __name__ == "__main__":
    unittest.main()
