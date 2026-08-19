from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

import yaml

from clients import ServiceClient
from state import initialize_database, identity_key


DB = "/app/data/media-optimizer.db"


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_title(value: str) -> str:
    return "".join(
        char.lower()
        for char in value
        if char.isalnum()
    )


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

    radarr = ServiceClient(
        name="radarr",
        base_url=services["radarr"]["url"],
        api_key_env=services["radarr"]["api_key_env"],
    )

    users = jellyfin.request("/Users")
    users.raise_for_status()

    user_list = users.json()

    if not user_list:
        raise RuntimeError("No Jellyfin users found")

    user_id = user_list[0]["Id"]

    jf_response = jellyfin.request(
        f"/Users/{user_id}/Items"
        "?Recursive=true"
        "&IncludeItemTypes=Movie"
    )
    jf_response.raise_for_status()

    jellyfin_movies = jf_response.json().get("Items", [])

    radarr_response = radarr.request(
        "/api/v3/movie"
    )
    radarr_response.raise_for_status()

    radarr_movies = radarr_response.json()

    radarr_by_title = {
        normalize_title(str(movie.get("title", ""))): movie
        for movie in radarr_movies
    }

    connection = sqlite3.connect(DB)

    try:
        stored = 0

        for item in jellyfin_movies:
            title = str(item.get("Name", "")).strip()

            if not title:
                continue

            userdata = item.get("UserData", {})
            played = userdata.get("Played") is True

            radarr_movie = radarr_by_title.get(
                normalize_title(title)
            )

            size_bytes = None
            external_id = str(item.get("Id", ""))

            if radarr_movie is not None:
                movie_file = radarr_movie.get("movieFile") or {}

                size_bytes = int(
                    movie_file.get("size", 0) or 0
                )

                radarr_id = radarr_movie.get("id")

                if radarr_id is not None:
                    external_id = f"radarr:{radarr_id}"

            key = identity_key(
                "movie",
                external_id,
                None,
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
                VALUES (?, ?, ?, ?, NULL, ?, ?, ?, ?, ?)
                ON CONFLICT(identity_key)
                DO UPDATE SET
                    title = excluded.title,
                    watched_state = excluded.watched_state,
                    current_size_bytes = excluded.current_size_bytes,
                    updated_at = excluded.updated_at
                """,
                (
                    key,
                    "movie",
                    external_id,
                    title,
                    "complete" if played else "incomplete",
                    "unknown",
                    "pending",
                    size_bytes,
                    now_utc(),
                ),
            )

            stored += 1

        connection.commit()

        rows = connection.execute(
            """
            SELECT
                title,
                watched_state,
                ROUND(
                    COALESCE(current_size_bytes, 0)
                    / 1073741824.0,
                    2
                )
            FROM media_state
            WHERE media_type = 'movie'
            ORDER BY title;
            """
        ).fetchall()

        print("Optimizer Movie State")
        print("=====================")

        for title, state, size_gib in rows:
            print(
                f"{title}: "
                f"{state:<10} "
                f"{size_gib:.2f} GiB"
            )

        print()
        print(f"Movie records stored: {len(rows)}")
        print("READ-ONLY movie synchronization: PASS")

    finally:
        connection.close()


if __name__ == "__main__":
    main()
