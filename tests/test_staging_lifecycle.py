import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from approvals import ApprovalStore


class StagingLifecycleTests(unittest.TestCase):
    def test_lifecycle_fields_survive_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "approvals.sqlite3"
            ApprovalStore(path)

            with sqlite3.connect(path) as db:
                db.execute("""
                    INSERT INTO approval_requests
                    (id, snapshot, fingerprint, status, created_at, expires_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    "test1", "{}", "test", "consumed",
                    "2026-01-01", "2027-01-01"
                ))
                db.execute("""
                    INSERT INTO staging_attempts
                    (request_id, release_id, status, created_at,
                     updated_at, lifecycle_status, last_observed_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    "test1", "a" * 40, "confirmed",
                    "2026-01-01", "2026-01-01",
                    "downloading", "2026-01-02"
                ))

            ApprovalStore(path)

            with sqlite3.connect(path) as db:
                row = db.execute("""
                    SELECT lifecycle_status, last_observed_at
                    FROM staging_attempts WHERE request_id='test1'
                """).fetchone()

            self.assertEqual(row, ("downloading", "2026-01-02"))


if __name__ == "__main__":
    unittest.main()
