"""Reconcile Stowarr submissions against Radarr history without retrying."""

import json
import re


def reconcile_attempts(store, radarr, page_size=100):
    attempts = store.list_staging_attempts(
        {"claimed", "submitting", "uncertain"}
    )
    if not attempts:
        return []

    targets = {}
    for attempt in attempts:
        snapshot = json.loads(attempt["snapshot"])
        identity = snapshot["identity_key"]
        match = re.fullmatch(r"movie:radarr:([1-9][0-9]*)", identity)
        if not match:
            raise ValueError("Invalid staging movie identity")
        targets[attempt["request_id"]] = (
            int(match.group(1)),
            attempt["release_id"].lower(),
        )

    found = set()
    page = 1

    while True:
        response = radarr.request(
            f"/api/v3/history?page={page}&pageSize={page_size}",
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()

        for record in data.get("records", []):
            if str(record.get("eventType", "")).lower() != "grabbed":
                continue

            download_id = str(record.get("downloadId") or "").lower()
            torrent_hash = str(
                record.get("data", {}).get("torrentInfoHash") or ""
            ).lower()

            if not download_id or download_id != torrent_hash:
                continue

            for rid, (movie_id, expected_hash) in targets.items():
                if (
                    record.get("movieId") == movie_id
                    and download_id == expected_hash
                ):
                    found.add(rid)

        total = int(data.get("totalRecords", 0))
        if page * page_size >= total:
            break
        page += 1

    results = []
    for attempt in attempts:
        rid = attempt["request_id"]
        if rid in found:
            store.update_staging(rid, "confirmed")
            results.append((rid, "confirmed"))
        else:
            results.append((rid, "unresolved"))

    return results
