from __future__ import annotations

import sqlite3
from datetime import timedelta

from completion_confidence import CompletionEvidence


TRUSTED_CONFIDENCE = {"high", "approved"}


def persist_completion_state(
    connection: sqlite3.Connection,
    *,
    user_id: str,
    item_id: str,
    item_type: str | None,
    item_name: str | None,
    played: bool,
    evidence: CompletionEvidence,
    grace_days: int,
) -> None:
    existing = connection.execute(
        """
        SELECT
            completion_time,
            completion_confidence,
            eligible_at
        FROM media_user_state
        WHERE user_id = ?
          AND item_id = ?
        """,
        (user_id, item_id),
    ).fetchone()

    trusted = (
        evidence.confidence in TRUSTED_CONFIDENCE
        and evidence.completion_time is not None
    )

    completion_time = None
    completion_confidence = evidence.confidence
    eligible_at = None

    if trusted:
        completion_time = evidence.completion_time.isoformat()
        eligible_at = (
            evidence.completion_time
            + timedelta(days=grace_days)
        ).isoformat()

    elif existing and existing[1] in TRUSTED_CONFIDENCE:
        # Never erase previously trusted completion evidence
        # because of a later replay or incomplete observation.
        completion_time = existing[0]
        completion_confidence = existing[1]
        eligible_at = existing[2]

    connection.execute(
        """
        INSERT INTO media_user_state (
            user_id,
            item_id,
            item_type,
            item_name,
            watched_state,
            completion_time,
            completion_confidence,
            eligible_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(user_id, item_id)
        DO UPDATE SET
            item_type = excluded.item_type,
            item_name = excluded.item_name,
            watched_state = excluded.watched_state,
            completion_time = excluded.completion_time,
            completion_confidence = excluded.completion_confidence,
            eligible_at = excluded.eligible_at,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            user_id,
            item_id,
            item_type,
            item_name,
            "complete" if played else "incomplete",
            completion_time,
            completion_confidence,
            eligible_at,
        ),
    )
