from __future__ import annotations

from collections import defaultdict
import sqlite3

import yaml

from clients import ServiceClient
from completion_selector import (
    PlaybackSession,
    select_completion,
)
from completion_state import persist_completion_state
from playback_history import get_recent_playback_events
from state import initialize_database


CONFIG = "/app/config/config.yaml"
DB = "/app/data/media-optimizer.db"


def main() -> None:
    initialize_database(DB)

    with open(CONFIG, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    timezone_name = config["timezone"]
    grace_days = int(
        config.get("watched_delay_days", 30)
    )

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

    connection = sqlite3.connect(DB)

    try:
        stored = 0

        for (user_id, item_id), item_events in grouped.items():
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

            persist_completion_state(
                connection,
                user_id=user_id,
                item_id=item_id,
                item_type=item.get("Type"),
                item_name=item.get("Name"),
                played=user_data.get("Played") is True,
                evidence=evidence,
                grace_days=grace_days,
            )

            stored += 1

        connection.commit()

        rows = connection.execute(
            """
            SELECT
                item_name,
                watched_state,
                completion_confidence,
                completion_time,
                eligible_at
            FROM media_user_state
            ORDER BY completion_time DESC NULLS LAST,
                     item_name
            """
        ).fetchall()

        print("Stowarr Completion State")
        print("========================")

        for (
            name,
            watched,
            confidence,
            completed,
            eligible,
        ) in rows:
            print(
                f"{name}: "
                f"{watched} | "
                f"{confidence} | "
                f"completed={completed} | "
                f"eligible={eligible}"
            )

        print()
        print(f"Records synchronized: {stored}")
        print("STOWARR-LOCAL completion-state sync: PASS")

    finally:
        connection.close()


if __name__ == "__main__":
    main()
