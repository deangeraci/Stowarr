from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from clients import ServiceClient


@dataclass
class WatchedUser:
    id: str
    name: str


@dataclass
class WatchedSummary:
    user: WatchedUser
    last_seen: str | None
    total_play_time: str | None


def _json_get(client: ServiceClient, path: str):
    response = client.request(path)
    response.raise_for_status()
    return response.json()


def get_playback_users(
    jellyfin: ServiceClient,
) -> list[WatchedUser]:
    data = _json_get(
        jellyfin,
        "/user_usage_stats/user_list",
    )

    users: list[WatchedUser] = []

    for item in data:
        users.append(
            WatchedUser(
                id=str(item.get("id", "")),
                name=str(item.get("name", "")),
            )
        )

    return users


def get_user_activity_summary(
    jellyfin: ServiceClient,
    days: int = 3650,
) -> list[WatchedSummary]:
    data = _json_get(
        jellyfin,
        f"/user_usage_stats/user_activity?days={days}",
    )

    summaries: list[WatchedSummary] = []

    for item in data:
        summaries.append(
            WatchedSummary(
                user=WatchedUser(
                    id=str(item.get("user_id", "")),
                    name=str(item.get("user_name", "")),
                ),
                last_seen=(
                    str(item.get("latest_date"))
                    if item.get("latest_date")
                    else None
                ),
                total_play_time=(
                    str(item.get("total_play_time"))
                    if item.get("total_play_time")
                    else None
                ),
            )
        )

    return summaries


def days_since(
    value: str | None,
) -> int | None:
    if not value:
        return None

    cleaned = value.replace("Z", "+00:00")

    try:
        parsed = datetime.fromisoformat(cleaned)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    now = datetime.now(timezone.utc)

    return max(
        0,
        (now - parsed.astimezone(timezone.utc)).days,
    )
