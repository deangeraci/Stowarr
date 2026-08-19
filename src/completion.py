from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from clients import ServiceClient
from playback_history import PlaybackEvent


@dataclass
class CompletedItem:
    item_id: str
    item_type: str
    item_name: str
    completed_at: datetime
    eligible_at: datetime
    age_days: int
    eligible: bool


def parse_jellyfin_datetime(value: str | None) -> datetime | None:
    if not value:
        return None

    cleaned = value.replace("Z", "+00:00")

    try:
        parsed = datetime.fromisoformat(cleaned)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed.astimezone(timezone.utc)


def get_completed_items(
    jellyfin: ServiceClient,
    events: list[PlaybackEvent],
    timezone_name: str,
    grace_days: int,
) -> list[CompletedItem]:
    local_tz = ZoneInfo(timezone_name)
    now = datetime.now(timezone.utc)

    latest_by_item: dict[str, PlaybackEvent] = {}

    for event in events:
        existing = latest_by_item.get(event.item_id)

        if existing is None or event.started_at > existing.started_at:
            latest_by_item[event.item_id] = event

    completed: list[CompletedItem] = []

    for item_id, event in latest_by_item.items():
        response = jellyfin.request(
            f"/Users/{event.user_id}/Items/{item_id}"
        )
        response.raise_for_status()

        item = response.json()
        user_data = item.get("UserData", {})

        if user_data.get("Played") is not True:
            continue

        # Playback Reporting timestamps are stored as local wall-clock
        # timestamps without a timezone offset.
        local_start = event.started_at.replace(
            tzinfo=local_tz
        )

        completed_at = (
            local_start
            + timedelta(seconds=event.duration_seconds)
        ).astimezone(timezone.utc)

        eligible_at = completed_at + timedelta(
            days=grace_days
        )

        age_days = max(
            0,
            (now - completed_at).days,
        )

        completed.append(
            CompletedItem(
                item_id=item_id,
                item_type=event.item_type,
                item_name=event.item_name,
                completed_at=completed_at,
                eligible_at=eligible_at,
                age_days=age_days,
                eligible=now >= eligible_at,
            )
        )

    return sorted(
        completed,
        key=lambda item: item.completed_at,
        reverse=True,
    )
