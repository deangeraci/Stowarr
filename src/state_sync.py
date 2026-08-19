from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

import yaml

from clients import ServiceClient
from season_correlation import (
    find_sonarr_season,
    get_sonarr_seasons,
)
from state import initialize_database, identity_key


DB = "/app/data/media-optimizer.db"


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def main() -> None:
    initialize_database(DB)

    with open(
        "/app/config/config.yaml",
        "r",
        encoding="utf-8",
    ) as f:
        config = yaml.safe_load(f)

    services = config["services"]

    jellyfin = ServiceClient(
        name="jellyfin",
        base_url=services["jellyfin"]["url"],
        api_key_env=services["jellyfin"]["api_key_env"],
    )

    sonarr = ServiceClient(
        name="sonarr",
        base_url=services["sonarr"]["url"],
        api_key_env=services["sonarr"]["api_key_env"],
    )

    users = jellyfin.request("/Users")
    users.raise_for_status()

    user_list = users.json()

    if not user_list:
        raise RuntimeError("No Jellyfin users found")

    user_id = user_list[0]["Id"]

    response = jellyfin.request(
        f"/Users/{user_id}/Items"
        "?Recursive=true"
        "&IncludeItemTypes=Episode"
    )
    response.raise_for_status()

    episodes = response.json().get("Items", [])

    grouped: dict[tuple[str, int], list[dict]] = {}

    for episode in episodes:
        series = episode.get("SeriesName")
        season = episode.get("ParentIndexNumber")
        number = episode.get("IndexNumber")

        if (
            not series
            or season is None
            or number is None
        ):
            continue

        grouped.setdefault(
            (series, int(season)),
            [],
        ).append(episode)

    sonarr_seasons = get_sonarr_seasons(sonarr)

    connection = sqlite3.connect(DB)

    try:
        for (series, season_number), items in grouped.items():
            watched = sum(
                1
                for item in items
                if item.get("UserData", {}).get("Played") is True
            )

            complete = watched == len(items)

            match = find_sonarr_season(
                sonarr_seasons,
                series,
                season_number,
            )

            current_size = (
                match.size_bytes
                if match is not None
                else None
            )

            external_id = (
                f"{series}:season:{season_number}"
            )

            watched_state = (
                "complete"
                if complete
                else "incomplete"
            )

            key = identity_key(
                "season",
                external_id,
                season_number,
            )

            connection.execute(
                """
                INSERT INTO media_state (
                    identity_key,
                    media_type,
                    external_id,
                    title,
                    season_number,
                    watched_state,
                    completion_confidence,
                    decision,
                    current_size_bytes,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(identity_key)
                DO UPDATE SET
                    title = excluded.title,
                    watched_state = excluded.watched_state,
                    current_size_bytes = excluded.current_size_bytes,
                    updated_at = excluded.updated_at
                """,
                (
                    key,
                    "season",
                    external_id,
                    series,
                    season_number,
                    watched_state,
                    "unknown",
                    "pending",
                    current_size,
                    now_utc(),
                ),
            )

        connection.commit()

        rows = connection.execute(
            """
            SELECT
                title,
                season_number,
                watched_state,
                ROUND(
                    COALESCE(current_size_bytes, 0)
                    / 1073741824.0,
                    2
                )
            FROM media_state
            WHERE media_type = 'season'
            ORDER BY title, season_number;
            """
        ).fetchall()

        print("Optimizer TV State")
        print("==================")

        for title, season, state, size_gib in rows:
            print(
                f"{title} S{season:02d}: "
                f"{state:<10} "
                f"{size_gib:.2f} GiB"
            )

        print()
        print(f"Season records stored: {len(rows)}")
        print("READ-ONLY source synchronization: PASS")

    finally:
        connection.close()


if __name__ == "__main__":
    main()
