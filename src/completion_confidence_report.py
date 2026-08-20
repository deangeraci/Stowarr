from __future__ import annotations

from collections import defaultdict

import yaml

from clients import ServiceClient
from completion_selector import (
    PlaybackSession,
    select_completion,
)
from playback_history import get_recent_playback_events


CONFIG = "/app/config/config.yaml"


def main() -> None:
    with open(CONFIG, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    timezone_name = config["timezone"]
    service = config["services"]["jellyfin"]

    jellyfin = ServiceClient(
        name="jellyfin",
        base_url=service["url"],
        api_key_env=service["api_key_env"],
    )

    events = get_recent_playback_events(jellyfin)

    grouped = defaultdict(list)

    for event in events:
        grouped[
            (event.user_id, event.item_id)
        ].append(event)

    print("Stowarr Completion Confidence Report")
    print("===================================")

    rows = sorted(
        grouped.items(),
        key=lambda pair: max(
            event.started_at
            for event in pair[1]
        ),
        reverse=True,
    )

    for (user_id, item_id), item_events in rows:
        response = jellyfin.request(
            f"/Users/{user_id}/Items/{item_id}"
        )

        if response.status_code == 404:
            continue

        response.raise_for_status()

        item = response.json()
        user_data = item.get("UserData", {})

        runtime_ticks = int(
            item.get("RunTimeTicks", 0) or 0
        )

        runtime_seconds = (
            runtime_ticks // 10_000_000
            if runtime_ticks
            else None
        )

        sessions = [
            PlaybackSession(
                started_at=event.started_at,
                duration_seconds=event.duration_seconds,
            )
            for event in item_events
        ]

        evidence = select_completion(
            played=user_data.get("Played") is True,
            runtime_seconds=runtime_seconds,
            sessions=sessions,
            jellyfin_last_played_at=user_data.get(
                "LastPlayedDate"
            ),
            timezone_name=timezone_name,
        )

        longest = max(
            item_events,
            key=lambda event: event.duration_seconds,
        )

        coverage = None

        if runtime_seconds:
            coverage = (
                longest.duration_seconds
                / runtime_seconds
                * 100
            )

        print()
        print(longest.item_name)
        print(f"  user_id:     {user_id}")
        print(f"  item_id:     {item_id}")
        print(f"  sessions:    {len(item_events)}")
        print(f"  played:      {user_data.get('Played')}")

        if coverage is not None:
            print(f"  best_cover:  {coverage:.1f}%")

        print(f"  confidence:  {evidence.confidence}")
        print(f"  reason:      {evidence.reason}")

        if evidence.completion_time is not None:
            print(
                "  completed_at: "
                f"{evidence.completion_time.isoformat()}"
            )


if __name__ == "__main__":
    main()
