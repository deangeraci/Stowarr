"""Verify completed replacement downloads without importing or moving them."""
from __future__ import annotations

import argparse
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from approvals import ApprovalStore
from clients import QbitTorrentClient
from media_verification import VerificationError, verify_media
from staging_isolation import path_is_within


def verify_attempt(store, qbit, attempt, ffprobe="ffprobe", ffmpeg="ffmpeg",
                   max_bytes=None, max_seconds=None):
    release_id = attempt["torrent_hash"] or attempt["release_id"]
    category = attempt.get("staging_category")
    if not category or not attempt.get("download_path"):
        raise VerificationError("attempt has no Phase 1 isolation metadata")
    row = qbit.info(release_id, category)
    if not isinstance(row, dict):
        raise VerificationError("replacement torrent is not observable")
    if (str(row.get("category") or "") != category or
            not path_is_within(str(row.get("content_path") or ""), attempt["download_path"])):
        raise VerificationError("replacement content path is outside staging isolation")
    if int(row.get("amount_left") or 0) != 0 or float(row.get("progress") or 0) < 1:
        store.update_staging(attempt["request_id"], "confirmed",
                             lifecycle_status="downloading",
                             observed_at=datetime.now(timezone.utc).isoformat())
        return None
    snapshot = json.loads(attempt["snapshot"])
    options = {"expected_size": snapshot["release_size_bytes"],
               "ffprobe": ffprobe, "ffmpeg": ffmpeg}
    if max_bytes is not None:
        options["max_bytes"] = max_bytes
    if max_seconds is not None:
        options["max_seconds"] = max_seconds
    manifest = verify_media(row["content_path"], **options)
    store.update_staging(
        attempt["request_id"], "confirmed", lifecycle_status="verified",
        observed_at=datetime.now(timezone.utc).isoformat(),
        verification_json=json.dumps(manifest, sort_keys=True),
    )
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--approval-db", default="/app/data/approvals.sqlite3")
    parser.add_argument("--request-id")
    parser.add_argument("--ffprobe", default="ffprobe")
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--workers", type=int,
                        default=int(os.getenv("STOWARR_VERIFY_WORKERS", "4")))
    parser.add_argument("--max-bytes", type=int,
                        default=int(os.getenv("STOWARR_VERIFY_MAX_BYTES", str(16 * 1024 ** 3)))
                        )
    parser.add_argument("--max-seconds", type=int,
                        default=int(os.getenv("STOWARR_VERIFY_MAX_SECONDS", "1800")))
    args = parser.parse_args()
    store = ApprovalStore(args.approval_db)
    qbit = QbitTorrentClient(
        os.getenv("STOWARR_QBITTORRENT_URL", "http://gluetun:8090"),
        username_env=os.getenv("STOWARR_QBITTORRENT_USERNAME_ENV", "STOWARR_QBITTORRENT_USERNAME"),
        password_env=os.getenv("STOWARR_QBITTORRENT_PASSWORD_ENV", "STOWARR_QBITTORRENT_PASSWORD"),
    )
    attempts = store.list_staging_attempts({"confirmed", "uncertain"})
    if args.request_id:
        attempts = [attempt for attempt in attempts if attempt["request_id"] == args.request_id]
    if not 1 <= args.workers <= 4:
        raise SystemExit("Verification workers must be between 1 and 4")
    if args.max_bytes <= 0 or args.max_seconds <= 0:
        raise SystemExit("Verification limits must be positive")

    def run(attempt):
        return attempt, verify_attempt(store, qbit, attempt, args.ffprobe, args.ffmpeg,
                                       args.max_bytes, args.max_seconds)

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(run, attempt): attempt for attempt in attempts}
        for future in as_completed(futures):
            attempt = futures[future]
            try:
                _, manifest = future.result()
                print(f"{attempt['request_id']} | " +
                      ("verified" if manifest else "downloading"))
            except VerificationError as exc:
                store.update_staging(attempt["request_id"], "failed", error=str(exc),
                                     lifecycle_status="verification_failed")
                print(f"{attempt['request_id']} | verification_failed")


if __name__ == "__main__":
    main()
