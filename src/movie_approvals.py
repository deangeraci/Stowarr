"""Queue a real movie staging proposal. All media-service requests are GETs."""
from __future__ import annotations

import argparse
import re
import sqlite3
from datetime import datetime, timedelta, timezone

import yaml

from approvals import ApprovalStore
from candidate_policy import evaluate_candidate
from clients import ServiceClient
from completion_config import configured_grace_days

GIB = 1073741824


def read_live_item(client, user_id, item_id):
    response = client.request("/Users/" + user_id + "/Items/" + item_id, timeout=180)
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return response.json()


def eligible_completion(row, played, delay, now):
    if row is None or row[0] != "complete" or row[1] not in {"high", "approved"} or not played or not row[2]:
        return False
    try:
        completed = datetime.fromisoformat(row[2].replace("Z", "+00:00"))
        return completed.tzinfo is not None and completed + timedelta(days=delay) <= now
    except (TypeError, ValueError):
        return False


def provider_matches(item, movie):
    ids = {k.lower(): str(v) for k, v in item.get("ProviderIds", {}).items()}
    return bool((ids.get("tmdb") and ids["tmdb"] == str(movie.get("tmdbId"))) or
                (ids.get("imdb") and ids["imdb"] == str(movie.get("imdbId"))))


def candidates(movie, releases, config):
    source = movie.get("movieFile") or {}
    size = int(source.get("size") or 0)
    source_id = source.get("id") or movie.get("movieFileId")
    if not source_id or size <= 0:
        raise ValueError("Current imported movie file is missing")
    limits = config.get("approvals", {})
    low = float(limits.get("minimum_candidate_gib", 4))
    high = float(limits.get("maximum_candidate_gib", 8))
    if not 0 < low <= high:
        raise ValueError("Invalid candidate size range")
    policy = config.get("optimization", {})
    results = []
    for release in releases:
        title = str(release.get("title") or "")
        quality = release.get("quality", {}).get("quality", {}).get("name", "")
        hash_value = str(release.get("infoHash") or "").lower()
        seeders = int(release.get("seeders") or 0)
        candidate_size = int(release.get("size") or 0)
        reasons = release.get("rejections", [])
        if not isinstance(reasons, list) or any(not isinstance(r, str) or not r.startswith("Existing file meets cutoff:") for r in reasons):
            continue
        if "1080p" not in quality or not re.search(r"\b(?:x265|h[ ._-]?265|hevc)\b", title, re.I):
            continue
        if not re.fullmatch(r"[a-f0-9]{40}", hash_value) or not release.get("indexerId") or seeders < 1:
            continue
        if not low <= candidate_size / GIB <= high or re.search(r"\b3d\b", title, re.I):
            continue
        evaluated = evaluate_candidate(current_size_bytes=size, candidate_size_bytes=candidate_size,
            resolution=1080, codec="hevc", release_title=title,
            minimum_resolution=int(policy.get("minimum_resolution", 1080)),
            minimum_savings_gb=float(policy.get("minimum_savings_gb", 5)),
            minimum_savings_percent=float(policy.get("minimum_savings_percent", 40)))
        if not evaluated.accepted:
            continue
        snapshot = dict(identity_key="movie:radarr:" + str(movie["id"]),
            title=movie["title"] + " (" + str(movie.get("year", "")) + ")",
            source_file_id=str(source_id), source_size_bytes=size,
            release_id=hash_value, release_title=title, release_size_bytes=candidate_size,
            indexer_id=str(release["indexerId"]))
        results.append((seeders, snapshot))
    return sorted(results, key=lambda r: (-r[0], r[1]["release_size_bytes"], r[1]["release_id"]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--movie-id", type=int, required=True)
    parser.add_argument("--user-id", required=True, help="Jellyfin user who completed this movie")
    parser.add_argument("--config", default="/app/config/config.yaml")
    parser.add_argument("--state-db", default="/app/data/media-optimizer.db")
    parser.add_argument("--approval-db", default="/app/data/approvals.sqlite3")
    parser.add_argument("--notify", action="store_true")
    args = parser.parse_args()
    if args.movie_id <= 0 or not re.fullmatch(r"[a-fA-F0-9]{32}", args.user_id):
        parser.error("Invalid movie ID or Jellyfin user ID")
    with open(args.config, encoding="utf-8") as f:
        config = yaml.safe_load(f)
    clients = {name: ServiceClient(name, service["url"], service["api_key_env"])
        for name, service in config["services"].items() if name in {"jellyfin", "radarr"}}
    def get(service, path):
        response = clients[service].request(path, timeout=180)
        response.raise_for_status()
        return response.json()
    movie = get("radarr", "/api/v3/movie/" + str(args.movie_id))
    with sqlite3.connect("file:" + args.state_db + "?mode=ro", uri=True) as db:
        rows = db.execute("SELECT item_id,watched_state,completion_confidence,completion_time FROM media_user_state WHERE user_id=? AND item_type='Movie'", (args.user_id,)).fetchall()
    matched = []
    now = datetime.now(timezone.utc)
    delay = configured_grace_days(config)
    for row in rows:
        if not eligible_completion(row[1:], True, delay, now):
            continue
        item = read_live_item(clients["jellyfin"], args.user_id, row[0])
        if item is None:
            continue
        if provider_matches(item, movie) and eligible_completion(row[1:], item.get("UserData", {}).get("Played") is True, delay, now):
            matched.append(item)
    if len(matched) != 1:
        raise SystemExit("No unique live ID match with trusted completion and configured grace period")
    releases = get("radarr", "/api/v3/release?movieId=" + str(args.movie_id))
    found = candidates(movie, releases, config)
    if not found:
        raise SystemExit("No qualifying 1080p HEVC staging candidate; nothing queued")
    seeders, snapshot = found[0]
    # Recheck source after a potentially slow indexer search.
    current = get("radarr", "/api/v3/movie/" + str(args.movie_id))
    file = current.get("movieFile") or {}
    if str(file.get("id") or current.get("movieFileId")) != snapshot["source_file_id"] or int(file.get("size") or 0) != snapshot["source_size_bytes"]:
        raise SystemExit("Source changed during search; nothing queued")
    request_id = ApprovalStore(args.approval_db).propose(snapshot)
    print("Queued:", snapshot["title"])
    print("Release:", snapshot["release_title"])
    print("Package GiB:", round(snapshot["release_size_bytes"] / GIB, 2), "| Reported seeders:", seeders)
    print("Estimated package savings GiB:", round((snapshot["source_size_bytes"] - snapshot["release_size_bytes"]) / GIB, 2))
    print("Request:", request_id)
    print("Scope: staging approval only; no download/import/replacement performed")
    if args.notify:
        from approval_notifications import notify
        try:
            notify(request_id, snapshot)
        except Exception:
            raise SystemExit("Notification failed; proposal remains queued") from None


if __name__ == "__main__":
    main()
