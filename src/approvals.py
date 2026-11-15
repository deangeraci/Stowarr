"""Durable, release-specific staging approvals. No media execution capability."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

FIELDS = {"identity_key", "title", "source_file_id", "source_size_bytes",
          "release_id", "release_title", "release_size_bytes", "indexer_id"}


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def canonical(snapshot):
    if set(snapshot) != FIELDS:
        raise ValueError("Proposal must contain exactly the documented fields")
    for name in FIELDS - {"source_size_bytes", "release_size_bytes"}:
        if not isinstance(snapshot[name], str) or not snapshot[name].strip() or len(snapshot[name]) > 1024:
            raise ValueError("Invalid proposal identifier/title")
    for name in ("source_size_bytes", "release_size_bytes"):
        if type(snapshot[name]) is not int or snapshot[name] <= 0:
            raise ValueError("Sizes must be positive integer bytes")
    if snapshot["release_size_bytes"] >= snapshot["source_size_bytes"]:
        raise ValueError("Replacement must save space")
    return json.dumps(snapshot, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def fingerprint(snapshot):
    return hashlib.sha256(canonical(snapshot).encode()).hexdigest()


class ApprovalStore:
    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
              CREATE TABLE IF NOT EXISTS approval_requests (
                id TEXT PRIMARY KEY, snapshot TEXT NOT NULL,
                fingerprint TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL, expires_at TEXT NOT NULL,
                decided_at TEXT, actor TEXT);
              CREATE TABLE IF NOT EXISTS approval_events (
                id INTEGER PRIMARY KEY, request_id TEXT NOT NULL,
                event TEXT NOT NULL, actor TEXT NOT NULL, at TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS staging_attempts (
                request_id TEXT PRIMARY KEY,
                release_id TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'claimed'
                    CHECK(status IN ('claimed','submitting','confirmed','uncertain','failed','historical')),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_error TEXT,
                FOREIGN KEY(request_id) REFERENCES approval_requests(id)
              );
              CREATE INDEX IF NOT EXISTS approval_fingerprint ON approval_requests(fingerprint);
            ''')


        with self.connect() as db:
            columns = {
                row["name"]
                for row in db.execute("PRAGMA table_info(staging_attempts)")
            }
            if "lifecycle_status" not in columns:
                db.execute(
                    "ALTER TABLE staging_attempts "
                    "ADD COLUMN lifecycle_status TEXT"
                )
            if "last_observed_at" not in columns:
                db.execute(
                    "ALTER TABLE staging_attempts "
                    "ADD COLUMN last_observed_at TEXT"
                )
            if "recovery_request_id" not in columns:
                db.execute("ALTER TABLE staging_attempts ADD COLUMN recovery_request_id TEXT")
            # Consumed approvals created before staging_attempts existed are
            # retained as historical records so the October 8 backlog can be
            # reconciled without ever replaying the approval.
            # Use the pre-existing 'uncertain' value for the physical status:
            # old installations have a CHECK constraint that predates the
            # historical label. The lifecycle_status column carries the
            # migration marker on both old and new schemas.
            db.execute(
                "INSERT OR IGNORE INTO staging_attempts "
                "(request_id, release_id, status, created_at, updated_at, "
                "lifecycle_status, last_observed_at) "
                "SELECT r.id, json_extract(r.snapshot, '$.release_id'), "
                "'uncertain', r.created_at, r.created_at, 'historical', NULL "
                "FROM approval_requests r LEFT JOIN staging_attempts a "
                "ON a.request_id=r.id WHERE r.status='consumed' AND a.request_id IS NULL"
            )

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def propose(self, snapshot, ttl_hours=72):
        if type(ttl_hours) is not int or not 1 <= ttl_hours <= 720:
            raise ValueError("Expiry must be 1–720 hours")
        encoded = canonical(snapshot)
        digest = fingerprint(snapshot)
        now = timestamp()
        expires = (datetime.now(timezone.utc) + timedelta(hours=ttl_hours)).isoformat()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute("SELECT id FROM approval_requests WHERE fingerprint=? AND status IN ('pending','approved') AND expires_at>?", (digest, now)).fetchone()
            if existing:
                return existing["id"]
            rid = uuid.uuid4().hex
            db.execute("INSERT INTO approval_requests(id,snapshot,fingerprint,created_at,expires_at) VALUES(?,?,?,?,?)", (rid, encoded, digest, now, expires))
            db.execute("INSERT INTO approval_events(request_id,event,actor,at) VALUES(?,?,?,?)", (rid, "proposed", "cli", now))
            return rid

    def list(self):
        with self.connect() as db:
            rows = db.execute("SELECT * FROM approval_requests ORDER BY created_at DESC").fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["snapshot"] = json.loads(item["snapshot"])
            if item["expires_at"] <= timestamp() and item["status"] in {"pending", "approved"}:
                item["status"] = "expired"
            result.append(item)
        return result

    def decide(self, rid, digest, decision, actor):
        if decision not in {"approved", "rejected"} or not actor:
            raise ValueError("Invalid decision")
        now = timestamp()
        with self.connect() as db:
            changed = db.execute("UPDATE approval_requests SET status=?,decided_at=?,actor=? WHERE id=? AND fingerprint=? AND status='pending' AND expires_at>?", (decision, now, actor, rid, digest, now)).rowcount
            if changed != 1:
                raise ValueError("Request changed, expired, or already decided; refresh")
            db.execute("INSERT INTO approval_events(request_id,event,actor,at) VALUES(?,?,?,?)", (rid, decision, actor, now))

    def consume(self, rid, current_snapshot, actor="executor"):
        """Future executor hook: recheck live eligibility first, then claim once.

        Consumption is an at-most-once claim, NOT proof of a successful download.
        On execution failure, reconcile state and create a fresh request.
        """
        digest = fingerprint(current_snapshot)
        now = timestamp()
        with self.connect() as db:
            changed = db.execute("UPDATE approval_requests SET status='consumed' WHERE id=? AND fingerprint=? AND status='approved' AND expires_at>?", (rid, digest, now)).rowcount
            if changed != 1:
                raise ValueError("No current approval for this exact proposal")
            db.execute("INSERT INTO approval_events(request_id,event,actor,at) VALUES(?,?,?,?)", (rid, "consumed", actor, now))


    def claim_staging(self, rid, current_snapshot, actor="staging-executor"):
        """Atomically consume an approval and create its staging record."""
        digest = fingerprint(current_snapshot)
        now = timestamp()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            changed = db.execute(
                "UPDATE approval_requests SET status='consumed' "
                "WHERE id=? AND fingerprint=? AND status='approved' AND expires_at>?",
                (rid, digest, now)
            ).rowcount
            if changed != 1:
                raise ValueError("No current approval for this exact proposal")
            db.execute(
                "INSERT INTO staging_attempts "
                "(request_id, release_id, status, created_at, updated_at) "
                "VALUES (?, ?, 'claimed', ?, ?)",
                (rid, current_snapshot["release_id"], now, now)
            )
            db.execute(
                "INSERT INTO approval_events(request_id,event,actor,at) VALUES(?,?,?,?)",
                (rid, "consumed", actor, now)
            )


    def update_staging(self, rid, status, error=None, lifecycle_status=None,
                       observed_at=None):
        """Persist submission outcome without changing approval state."""
        if status not in {"submitting", "confirmed", "uncertain", "failed"}:
            raise ValueError("Invalid staging status")
        now = timestamp()
        with self.connect() as db:
            changed = db.execute(
                "UPDATE staging_attempts SET status=?, updated_at=?, last_error=?, "
                "lifecycle_status=COALESCE(?, lifecycle_status), "
                "last_observed_at=COALESCE(?, last_observed_at) "
                "WHERE request_id=?",
                (status, now, error, lifecycle_status, observed_at, rid)
            ).rowcount
            if changed != 1:
                raise ValueError("Staging attempt not found")


    def list_staging_attempts(self, statuses=None):
        """Read persistent staging records for reconciliation."""
        with self.connect() as db:
            rows = db.execute(
                "SELECT a.request_id, a.release_id, a.status, a.created_at, "
                "a.updated_at, a.lifecycle_status, a.last_observed_at, "
                "a.recovery_request_id, r.snapshot "
                "FROM staging_attempts a "
                "JOIN approval_requests r ON r.id=a.request_id "
                "ORDER BY a.created_at"
            ).fetchall()
        result = [dict(row) for row in rows]
        if statuses is not None:
            result = [r for r in result if r["status"] in statuses]
        return result

    def propose_recovery(self, rid, snapshot, actor="staging-reconciler"):
        """Create one pending approval for a freshly revalidated candidate."""
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT a.recovery_request_id, r.snapshot FROM staging_attempts a "
                "JOIN approval_requests r ON r.id=a.request_id WHERE a.request_id=?",
                (rid,),
            ).fetchone()
            if not row:
                raise ValueError("Staging attempt not found")
            if row["recovery_request_id"]:
                return row["recovery_request_id"]
            # The caller must have re-run live eligibility and candidate
            # discovery. Never clone the consumed release snapshot here.
            canonical(snapshot)
            new_id = uuid.uuid4().hex
            now = timestamp()
            expires = (datetime.now(timezone.utc) + timedelta(hours=72)).isoformat()
            db.execute(
                "INSERT INTO approval_requests(id,snapshot,fingerprint,status,created_at,expires_at) "
                "VALUES(?,?,?,?,?,?)", (new_id, canonical(snapshot), fingerprint(snapshot),
                                          "pending", now, expires)
            )
            db.execute("UPDATE staging_attempts SET recovery_request_id=? WHERE request_id=?",
                       (new_id, rid))
            db.execute("INSERT INTO approval_events(request_id,event,actor,at) VALUES(?,?,?,?)",
                       (new_id, "recovery_proposed", actor, now))
            return new_id


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=os.getenv("STOWARR_APPROVAL_DB", "/app/data/approvals.sqlite3"))
    subs = parser.add_subparsers(dest="command", required=True)
    sub = subs.add_parser("propose")
    sub.add_argument("file", help="Sanitized proposal JSON; no URLs or credentials")
    sub.add_argument("--ttl-hours", type=int, default=72)
    sub.add_argument("--notify", action="store_true")
    subs.add_parser("list")
    args = parser.parse_args()
    store = ApprovalStore(args.db)
    if args.command == "list":
        print(json.dumps(store.list(), indent=2))
    else:
        with open(args.file, encoding="utf-8") as f:
            proposal = json.load(f)
        rid = store.propose(proposal, args.ttl_hours)
        print("Approval request:", rid)
        if args.notify:
            from approval_notifications import notify
            try:
                notify(rid, proposal)
            except Exception:
                raise SystemExit("Notification delivery failed; request remains queued. Check local notification configuration.") from None


if __name__ == "__main__":
    main()
