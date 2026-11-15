"""Stage approved, exact Radarr movie releases; never import or replace media."""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sqlite3
import time
from datetime import datetime, timezone

import requests
import yaml

from approvals import ApprovalStore
from staging_reconciliation import reconcile_attempts
from clients import QbitTorrentClient, ServiceClient
from completion_config import configured_grace_days
from movie_approvals import candidates, eligible_completion, provider_matches, read_live_item


def movie_id(snapshot):
    match = re.fullmatch(r"movie:radarr:([1-9][0-9]*)", snapshot["identity_key"])
    if not match:
        raise ValueError("Unsupported approval identity")
    return int(match.group(1))


def exact_release(snapshot, movie, releases, config):
    wanted = {key: snapshot[key] for key in (
        "source_file_id", "source_size_bytes", "release_id", "release_title",
        "release_size_bytes", "indexer_id",
    )}
    for _, candidate in candidates(movie, releases, config):
        if all(candidate[key] == wanted[key] for key in wanted):
            return candidate
    return None


def live_eligible(clients, state_db, user_id, movie, delay):
    with sqlite3.connect("file:" + state_db + "?mode=ro", uri=True) as db:
        rows = db.execute(
            "SELECT item_id, watched_state, completion_confidence, completion_time "
            "FROM media_user_state WHERE user_id=? AND item_type='Movie'", (user_id,)
        ).fetchall()
    now = datetime.now(timezone.utc)
    matches = []
    for item_id, watched, confidence, completed in rows:
        if not eligible_completion((watched, confidence, completed), True, delay, now):
            continue
        item = read_live_item(clients["jellyfin"], user_id, item_id)
        if item and provider_matches(item, movie) and eligible_completion(
            (watched, confidence, completed), item.get("UserData", {}).get("Played") is True, delay, now
        ):
            matches.append(item)
    return len(matches) == 1


def fresh_recovery_snapshot(attempt, clients, config, state_db, user_id):
    """Re-run read-only eligibility and candidate discovery for recovery."""
    old = json.loads(attempt["snapshot"])
    mid = movie_id(old)
    response = clients["radarr"].request(f"/api/v3/movie/{mid}", timeout=180)
    response.raise_for_status()
    movie = response.json()
    if not live_eligible(clients, state_db, user_id, movie, configured_grace_days(config)):
        return None
    response = clients["radarr"].request(f"/api/v3/release?movieId={mid}", timeout=180)
    response.raise_for_status()
    found = candidates(movie, response.json(), config)
    excluded = {str(value).lower() for value in attempt.get("excluded_release_ids", set())}
    excluded.add(str(attempt.get("release_id") or "").lower())
    for _, snapshot in found:
        if snapshot["release_id"].lower() not in excluded:
            return snapshot
    return None


def stage_one(store, request, clients, config, state_db, user_id):
    snapshot = request["snapshot"]
    try:
        mid = movie_id(snapshot)
        response = clients["radarr"].request("/api/v3/movie/" + str(mid), timeout=180)
        response.raise_for_status()
        movie = response.json()
        if not live_eligible(clients, state_db, user_id, movie, configured_grace_days(config)):
            return "deferred: live watch eligibility changed"
        response = clients["radarr"].request("/api/v3/release?movieId=" + str(mid), timeout=180)
        response.raise_for_status()
        releases = response.json()
        if exact_release(snapshot, movie, releases, config) is None:
            return "deferred: approved release is no longer available or no longer qualifies"
        raw = next((r for r in releases if str(r.get("infoHash", "")).lower() == snapshot["release_id"]
                    and str(r.get("indexerId")) == snapshot["indexer_id"]
                    and r.get("title") == snapshot["release_title"]
                    and int(r.get("size") or 0) == snapshot["release_size_bytes"]), None)
        if raw is None:
            return "deferred: exact release payload changed"
        client_id = int(os.environ.get("STOWARR_RADARR_DOWNLOAD_CLIENT_ID", "0"))
        if client_id <= 0:
            return "deferred: dedicated Radarr download client not configured"
        raw["downloadClientId"] = client_id
        raw["category"] = os.environ.get("STOWARR_QBITTORRENT_CATEGORY", "stowarr")
        store.claim_staging(request["id"], snapshot, actor="staging-executor")
        store.update_staging(request["id"], "submitting")
        try:
            response = requests.post(clients["radarr"].base_url + "/api/v3/release",
                headers=clients["radarr"]._headers(), json=raw, timeout=180)
            response.raise_for_status()
        except requests.HTTPError as exc:
            response = exc.response
            if response is not None and 400 <= response.status_code < 500 and response.status_code not in {408, 429}:
                store.update_staging(request["id"], "failed")
                return "failed: Radarr rejected the exact release"
            store.update_staging(request["id"], "uncertain")
            return "uncertain: Radarr submission requires reconciliation"
        except requests.RequestException as exc:
            store.update_staging(request["id"], "uncertain")
            return "uncertain: Radarr submission requires reconciliation"
        store.update_staging(request["id"], "confirmed")
        return "staged: " + snapshot["title"]
    except (ValueError, requests.RequestException, sqlite3.Error) as exc:
        return "failed: " + str(exc)


def run_once(store, clients, config, state_db, user_id):
    for request in store.list():
        if request["status"] == "approved":
            print(request["id"] + " | " + stage_one(
                store, request, clients, config, state_db, user_id
            ), flush=True)


def main():
    logging.basicConfig(level=os.environ.get("STOWARR_LOG_LEVEL", "INFO"),
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="/app/config/config.yaml")
    parser.add_argument("--state-db", default="/app/data/media-optimizer.db")
    parser.add_argument("--approval-db", default="/app/data/approvals.sqlite3")
    parser.add_argument("--interval-seconds", type=int, default=60)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    user_id = os.environ.get("STOWARR_EXECUTOR_JELLYFIN_USER_ID", "")
    if not re.fullmatch(r"[a-fA-F0-9]{32}", user_id):
        raise SystemExit("Set STOWARR_EXECUTOR_JELLYFIN_USER_ID to the eligible Jellyfin user ID")
    if args.interval_seconds < 10:
        raise SystemExit("Interval must be at least 10 seconds")
    with open(args.config, encoding="utf-8") as f:
        config = yaml.safe_load(f)
    clients = {name: ServiceClient(name, service["url"], service["api_key_env"])
        for name, service in config["services"].items() if name in {"jellyfin", "radarr"}}
    if set(clients) != {"jellyfin", "radarr"}:
        raise SystemExit("Jellyfin and Radarr services must be configured")
    store = ApprovalStore(args.approval_db)
    qbit = QbitTorrentClient(
        os.environ.get("STOWARR_QBITTORRENT_URL", "http://gluetun:8090"),
        os.environ.get("STOWARR_QBITTORRENT_CATEGORY", "stowarr"),
        os.environ.get("STOWARR_QBITTORRENT_USERNAME_ENV", "STOWARR_QBITTORRENT_USERNAME"),
        os.environ.get("STOWARR_QBITTORRENT_PASSWORD_ENV", "STOWARR_QBITTORRENT_PASSWORD"),
    )
    def recovery_factory(attempt):
        return fresh_recovery_snapshot(attempt, clients, config, args.state_db, user_id)
    last_reconciliation = None
    while True:
        now = time.monotonic()
        if last_reconciliation is None or now - last_reconciliation >= 900:
            last_reconciliation = now
            try:
                for result in reconcile_attempts(store, clients["radarr"], qbit,
                                                 recovery_factory=recovery_factory):
                    rid, status, *recovery = result
                    print(f"{rid} | reconciled: {status}" +
                          (f"; fresh approval {recovery[0]}" if recovery and recovery[0] else ""),
                          flush=True)
            except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
                print(f"Staging reconciliation failed: {type(exc).__name__}", flush=True)

        run_once(store, clients, config, args.state_db, user_id)
        if args.once:
            return
        time.sleep(args.interval_seconds)

if __name__ == "__main__":
    main()
