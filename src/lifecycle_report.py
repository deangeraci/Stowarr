from __future__ import annotations

import sqlite3

import yaml

from lifecycle import assess_lifecycle


DB = "/app/data/media-optimizer.db"
CONFIG = "/app/config/config.yaml"


def main() -> None:
    with open(CONFIG, "r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle)

    delay_days = int(
        config.get("lifecycle", {}).get(
            "watched_delay_days",
            30,
        )
    )

    con = sqlite3.connect(DB)

    try:
        rows = con.execute(
            """
            SELECT
                media_type,
                title,
                season_number,
                watched_state,
                completion_time,
                completion_confidence
            FROM media_state
            WHERE watched_state = 'complete'
            ORDER BY media_type, title, season_number
            """
        ).fetchall()

        print("Optimizer Lifecycle Report")
        print("==========================")
        print(f"watch delay: {delay_days} days")
        print()

        for (
            media_type,
            title,
            season,
            watched,
            completed,
            confidence,
        ) in rows:
            result = assess_lifecycle(
                watched_state=watched,
                completion_time=completed,
                completion_confidence=confidence,
                delay_days=delay_days,
            )

            label = title

            if media_type == "season":
                label += f" S{season:02d}"

            print(
                f"{label}: "
                f"{result.status} | "
                f"{result.reason}"
            )

        print()
        print("Lifecycle evaluation: READ-ONLY PASS")

    finally:
        con.close()


if __name__ == "__main__":
    main()
