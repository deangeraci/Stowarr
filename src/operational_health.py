"""Check Stowarr from a running service container without starting a worker."""
import argparse
import os
import re
import sqlite3
from contextlib import closing
from pathlib import Path
from urllib.parse import urlsplit

import requests
import yaml

from clients import QbitTorrentClient
from state import CURRENT_SCHEMA_VERSION


APPROVAL_QUERIES = (
    "SELECT id, snapshot, fingerprint, status, expires_at, recovery_parent_request_id "
    "FROM approval_requests LIMIT 1",
    "SELECT request_id, event, actor, at FROM approval_events LIMIT 1",
    "SELECT request_id, release_id, status, updated_at FROM staging_attempts LIMIT 1",
)
STATE_QUERIES = (
    "SELECT identity_key, completion_time, completion_confidence FROM media_state LIMIT 1",
    "SELECT user_id, item_id, eligible_at FROM media_user_state LIMIT 1",
    "SELECT event_type, identity_key FROM audit_log LIMIT 1",
)


def check_database(path, queries, version=None):
    uri = Path(path).resolve(strict=True).as_uri() + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True, timeout=3)) as db:
        db.execute("PRAGMA query_only = ON")
        if version is not None:
            row = db.execute("SELECT value FROM schema_metadata WHERE key='schema_version'").fetchone()
            if row != (str(version),):
                raise ValueError("unexpected state schema version")
        for query in queries:
            db.execute(query).fetchone()


def service_url(value):
    url = urlsplit(value)
    if (url.scheme not in {"http", "https"} or not url.hostname
            or url.username is not None or url.query or url.fragment):
        raise ValueError("expected a service URL without embedded credentials")
    return value.rstrip("/")


def get(session, url, **kwargs):
    response = session.get(url, timeout=5, allow_redirects=False, **kwargs)
    if response.status_code != 200:
        raise ValueError("unexpected HTTP response")
    return response


def check_approvals(session):
    username = os.getenv("STOWARR_APPROVAL_USER", "stowarr")
    password = os.environ["STOWARR_APPROVAL_PASSWORD"]
    response = get(session, "http://127.0.0.1:8787/", auth=(username, password))
    if "Stowarr approvals" not in response.text:
        raise ValueError("unexpected approvals page")


def check_staging_config(path):
    with open(path, encoding="utf-8") as stream:
        config = yaml.safe_load(stream)
    safety = config["safety"]
    if any(safety[key] is not False for key in ("allow_download", "allow_import", "allow_delete")):
        raise ValueError("expected disabled write gates")
    if not re.fullmatch(r"[0-9a-fA-F]{32}", os.environ["STOWARR_EXECUTOR_JELLYFIN_USER_ID"]):
        raise ValueError("invalid executor user ID")
    radarr = config["services"]["radarr"]
    radarr_url = service_url(radarr["url"])
    key = os.environ[radarr["api_key_env"]]
    client_id = int(os.environ["STOWARR_RADARR_DOWNLOAD_CLIENT_ID"])
    qbit_url = service_url(os.getenv("STOWARR_QBITTORRENT_URL", "http://gluetun:8090"))
    category = os.getenv("STOWARR_QBITTORRENT_CATEGORY", "stowarr")
    if not key.strip() or client_id <= 0 or not category.strip():
        raise ValueError("missing staging settings")
    return radarr_url, key, client_id, qbit_url, category


def check_radarr(session, url, key, client_id, category):
    client = get(session, f"{url}/api/v3/downloadclient/{client_id}",
                 headers={"X-Api-Key": key}).json()
    if not isinstance(client, dict) or client.get("id") != client_id:
        raise ValueError("unexpected Radarr download client response")
    if client.get("enable") is not True or client.get("implementation") != "QBittorrent":
        raise ValueError("expected enabled qBittorrent download client")
    fields = {field["name"]: field.get("value") for field in client["fields"]}
    if fields.get("movieCategory") != category:
        raise ValueError("Radarr movie category does not match Stowarr")


def check_qbit(session, url, category):
    client = QbitTorrentClient(
        url,
        category,
        os.getenv("STOWARR_QBITTORRENT_USERNAME_ENV", "STOWARR_QBITTORRENT_USERNAME"),
        os.getenv("STOWARR_QBITTORRENT_PASSWORD_ENV", "STOWARR_QBITTORRENT_PASSWORD"),
        session=session,
    )
    client._login_if_configured()
    categories = get(session, f"{url}/api/v2/torrents/categories").json()
    if not isinstance(categories, dict) or category not in categories:
        raise ValueError("expected qBittorrent category is absent")


def report(label, check, *args):
    try:
        result = check(*args)
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error,
            requests.RequestException, yaml.YAMLError):
        # Exceptions and responses can contain paths, credentials, or service settings.
        print(f"FAIL {label}")
        return False, None
    print(f"PASS {label}")
    return True, result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("service", choices=("approvals", "staging"))
    parser.add_argument("--config", default="/app/config/config.yaml")
    parser.add_argument("--state-db", default="/app/data/media-optimizer.db")
    parser.add_argument("--approval-db")
    args = parser.parse_args()

    approval_db = args.approval_db or "/app/data/approvals.sqlite3"
    if args.service == "approvals":
        approval_db = args.approval_db or os.getenv("STOWARR_APPROVAL_DB", approval_db)
    outcomes = [report("approvals database schema and readability",
                       check_database, approval_db, APPROVAL_QUERIES)[0]]
    with requests.Session() as session:
        session.trust_env = False
        session.max_redirects = 0
        if args.service == "approvals":
            outcomes.append(report("authenticated approvals HTTP readiness",
                                   check_approvals, session)[0])
        else:
            outcomes.append(report("state database schema and readability", check_database,
                                   args.state_db, STATE_QUERIES, CURRENT_SCHEMA_VERSION)[0])
            ok, settings = report("staging configuration", check_staging_config, args.config)
            outcomes.append(ok)
            if ok:
                radarr_url, key, client_id, qbit_url, category = settings
                outcomes.append(report("Radarr download client and category", check_radarr,
                                       session, radarr_url, key, client_id, category)[0])
                outcomes.append(report("qBittorrent connectivity and category", check_qbit,
                                       session, qbit_url, category)[0])
    return 0 if all(outcomes) else 1


if __name__ == "__main__":
    raise SystemExit(main())
