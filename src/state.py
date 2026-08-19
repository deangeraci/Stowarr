from __future__ import annotations

import sqlite3
from pathlib import Path


CURRENT_SCHEMA_VERSION = 2


SCHEMA = """
CREATE TABLE IF NOT EXISTS media_state (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    identity_key TEXT,

    media_type TEXT NOT NULL,
    external_id TEXT NOT NULL,
    title TEXT NOT NULL,

    season_number INTEGER,

    watched_state TEXT NOT NULL DEFAULT 'unknown',

    completion_time TEXT,
    completion_confidence TEXT NOT NULL DEFAULT 'unknown',

    eligible_at TEXT,
    decision TEXT NOT NULL DEFAULT 'pending',

    current_size_bytes INTEGER,

    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS schema_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    event_type TEXT NOT NULL,
    identity_key TEXT,
    details_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_media_state_decision
ON media_state(decision);

CREATE INDEX IF NOT EXISTS idx_media_state_eligible
ON media_state(eligible_at);

CREATE INDEX IF NOT EXISTS idx_audit_log_created
ON audit_log(created_at);

CREATE INDEX IF NOT EXISTS idx_audit_log_identity
ON audit_log(identity_key);
"""


def identity_key(
    media_type: str,
    external_id: str,
    season_number: int | None = None,
) -> str:
    if season_number is None:
        return f"{media_type}:{external_id}"

    suffix = f":season:{season_number}"

    if external_id.endswith(suffix):
        return f"{media_type}:{external_id}"

    return f"{media_type}:{external_id}{suffix}"


def initialize_database(path: str) -> None:
    db_path = Path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(db_path)

    try:
        connection.executescript(SCHEMA)

        columns = {
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(media_state)"
            )
        }

        if "identity_key" not in columns:
            connection.execute(
                """
                ALTER TABLE media_state
                ADD COLUMN identity_key TEXT
                """
            )

        rows = connection.execute(
            """
            SELECT
                id,
                media_type,
                external_id,
                season_number
            FROM media_state
            """
        ).fetchall()

        for (
            row_id,
            media_type,
            external_id,
            season_number,
        ) in rows:
            key = identity_key(
                media_type,
                external_id,
                season_number,
            )

            connection.execute(
                """
                UPDATE media_state
                SET identity_key = ?
                WHERE id = ?
                """,
                (key, row_id),
            )

        connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS
            idx_media_state_identity
            ON media_state(identity_key)
            """
        )

        connection.execute(
            """
            INSERT INTO schema_metadata(key, value)
            VALUES ('schema_version', ?)
            ON CONFLICT(key)
            DO UPDATE SET value = excluded.value
            """,
            (str(CURRENT_SCHEMA_VERSION),),
        )

        connection.commit()

    finally:
        connection.close()
