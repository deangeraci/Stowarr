"""Read-only reconciliation of staging attempts across Radarr and qBittorrent."""

import json
import logging
import re
from datetime import datetime, timezone

LOG = logging.getLogger("stowarr.staging")
ACTIVE = {"claimed", "submitting", "confirmed", "uncertain", "historical"}
DOWNLOADING = {"downloading", "metaDL", "forcedDL", "queuedDL", "checkingDL", "checkingResumeData"}
STALLED = {"stalledDL", "pausedDL", "pausedUP", "missingFiles"}
COMPLETE = {"uploading", "stalledUP", "pausedUP", "queuedUP", "checkingUP"}


def _history_state(records, movie_id, release_id):
    state = None
    for record in records:
        if record.get("movieId") != movie_id:
            continue
        data = record.get("data") or {}
        download_id = str(record.get("downloadId") or "").lower()
        torrent_hash = str(data.get("torrentInfoHash") or "").lower()
        ids = {download_id, torrent_hash}
        if release_id not in ids:
            continue
        event = str(record.get("eventType") or "").lower()
        if event == "grabbed" and (not download_id or download_id != torrent_hash):
            continue
        if event in {"downloadimported", "downloadfolderimported", "imported"}:
            state = "imported"
        elif event in {"downloadfailed", "failed"}:
            state = "failed"
        elif event == "grabbed" and state is None:
            state = "grabbed"
    return state


def _direct_qbit_state(qbit, release_id, category):
    row = None
    if hasattr(qbit, "info"):
        row = qbit.info(release_id, category)
    if not isinstance(row, dict):
        state = qbit.state(release_id, category)
        return state, None
    state = str(row.get("state") or "").strip()
    if state in COMPLETE and float(row.get("progress") or 0) >= 1 and int(row.get("amount_left") or 0) == 0:
        return "complete_unverified", row
    return state, row


def reconcile_attempts(store, radarr, qbit=None, page_size=100, recovery_factory=None):
    attempts = [attempt for attempt in store.list_staging_attempts(ACTIVE)
                if attempt.get("lifecycle_status") not in {"imported", "failed", "verified"}
                and not (attempt.get("lifecycle_status") == "missing"
                         and attempt.get("recovery_request_id"))]
    if not attempts:
        return []
    targets = {}
    for attempt in attempts:
        snapshot = json.loads(attempt["snapshot"])
        match = re.fullmatch(r"movie:radarr:([1-9][0-9]*)", snapshot["identity_key"])
        if not match:
            raise ValueError("Invalid staging movie identity")
        targets[attempt["request_id"]] = (int(match.group(1)), attempt["release_id"].lower())

    records = []
    page = 1
    legacy_attempts = [attempt for attempt in attempts if not attempt.get("staging_category")]
    while legacy_attempts:
        response = radarr.request(f"/api/v3/history?page={page}&pageSize={page_size}", timeout=30)
        response.raise_for_status()
        data = response.json()
        records.extend(data.get("records", []))
        total = int(data.get("totalRecords", 0))
        if page * page_size >= total or not data.get("records"):
            break
        page += 1

    results = []
    for attempt in attempts:
        rid = attempt["request_id"]
        movie_id, release_id = targets[rid]
        direct = bool(attempt.get("staging_category"))
        history_state = None if direct else _history_state(records, movie_id, release_id)
        state = history_state
        qbit_state = None
        if direct and qbit is not None:
            qbit_state, _ = _direct_qbit_state(
                qbit, release_id, attempt.get("staging_category"))
            if qbit_state in DOWNLOADING:
                state = "downloading"
            elif qbit_state == "complete_unverified":
                state = "complete_unverified"
            elif qbit_state in STALLED:
                state = "stalled"
            elif qbit_state == "removed":
                state = "ambiguous" if attempt.get("status") == "uncertain" else "missing"
            elif qbit_state:
                state = "ambiguous"
        elif history_state not in {"imported", "failed"} and qbit is not None:
            qbit_state = qbit.state(release_id)
            if qbit_state in DOWNLOADING:
                state = "downloading"
            elif qbit_state in STALLED:
                state = "stalled"
            elif qbit_state == "removed":
                state = "missing" if history_state in {"grabbed", "downloading"} else "ambiguous"
        if state is None:
            if qbit is None:
                results.append((rid, "unresolved"))
                continue
            state = "ambiguous"
        observed = datetime.now(timezone.utc).isoformat()
        legacy = not direct and qbit is None
        if legacy and state == "grabbed":
            status = "confirmed"
        else:
            status = "confirmed" if state in {"imported", "complete_unverified"} else ("failed" if state == "failed" else "uncertain")
        recovery = None
        if state == "missing" and recovery_factory is not None:
            recovery_attempt = dict(attempt)
            try:
                excluded = set(store.attempted_release_ids(rid))
            except (AttributeError, TypeError):
                excluded = {attempt["release_id"]}
            recovery_attempt["excluded_release_ids"] = excluded
            fresh_snapshot = recovery_factory(recovery_attempt)
            if fresh_snapshot is not None:
                recovery = store.propose_recovery(rid, fresh_snapshot)
                LOG.warning("staging_missing request_id=%s recovery_request_id=%s", rid, recovery)
        if legacy and state == "grabbed":
            store.update_staging(rid, "confirmed")
        else:
            store.update_staging(rid, status, lifecycle_status=state, observed_at=observed)
        results.append((rid, ("confirmed" if legacy and state == "grabbed" else state), recovery) if not legacy
                       else (rid, "confirmed" if state == "grabbed" else state))
        LOG.info("staging_reconciled request_id=%s lifecycle=%s qbit=%s", rid, state, qbit_state)
    return results
