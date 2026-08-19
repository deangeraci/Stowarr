from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import requests

from clients import ServiceClient


@dataclass
class PlaybackEvent:
    row_id: int
    started_at: datetime
    ended_at: datetime
    user_id: str
    item_id: str
    item_type: str
    item_name: str
    duration_seconds: int


READ_ONLY_QUERY = """
SELECT
    rowid,
    DateCreated,
    UserId,
    ItemId,
    ItemType,
    ItemName,
    PlayDuration
FROM PlaybackActivity
WHERE PlayDuration > 0
ORDER BY DateCreated DESC
LIMIT 100;
""".strip()


def _validate_select_only(query: str) -> None:
    normalized = query.strip().lower()

    if not normalized.startswith("select"):
        raise ValueError("Playback query must be SELECT-only")

    forbidden = (
        "update ",
        "delete ",
        "insert ",
        "drop ",
        "alter ",
        "replace ",
        "pragma ",
        "attach ",
        "detach ",
    )

    if any(token in normalized for token in forbidden):
        raise ValueError("Unsafe SQL detected")


def get_recent_playback_events(
    jellyfin: ServiceClient,
) -> list[PlaybackEvent]:
    _validate_select_only(READ_ONLY_QUERY)

    response = requests.post(
        f"{jellyfin.base_url}/user_usage_stats/submit_custom_query",
        headers=jellyfin._headers(),
        json={
            "customQueryString": READ_ONLY_QUERY,
            "replaceUserId": False,
        },
        timeout=10,
    )

    response.raise_for_status()

    payload = response.json()

    columns = payload.get("colums", [])
    rows = payload.get("results", [])

    indexes = {
        name: columns.index(name)
        for name in columns
    }

    events: list[PlaybackEvent] = []

    for row in rows:
        started = datetime.fromisoformat(
            str(row[indexes["DateCreated"]])
        )

        duration = int(
            row[indexes["PlayDuration"]]
        )

        events.append(
            PlaybackEvent(
                row_id=int(row[indexes["rowid"]]),
                started_at=started,
                ended_at=started + timedelta(seconds=duration),
                user_id=str(row[indexes["UserId"]]),
                item_id=str(row[indexes["ItemId"]]),
                item_type=str(row[indexes["ItemType"]]),
                item_name=str(row[indexes["ItemName"]]),
                duration_seconds=duration,
            )
        )

    return events
