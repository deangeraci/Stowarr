from __future__ import annotations

import json
import sqlite3
from typing import Any


def record_event(
    connection: sqlite3.Connection,
    *,
    event_type: str,
    identity_key: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    payload = (
        json.dumps(
            details,
            sort_keys=True,
            separators=(",", ":"),
        )
        if details is not None
        else None
    )

    connection.execute(
        """
        INSERT INTO audit_log (
            event_type,
            identity_key,
            details_json
        )
        VALUES (?, ?, ?)
        """,
        (
            event_type,
            identity_key,
            payload,
        ),
    )
