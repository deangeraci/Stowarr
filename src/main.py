from __future__ import annotations

import os
import sys
import yaml

from clients import ServiceClient
from inventory import collect_inventory
from playback_probe import probe_playback_reporting
from watched import (
    days_since,
    get_playback_users,
    get_user_activity_summary,
)


def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def validate_safety(config: dict) -> bool:
    mode = config.get("mode")
    safety = config.get("safety", {})

    print(f"Mode: {mode}")
    print(
        "Safety:"
        f" download={safety.get('allow_download')}"
        f" import={safety.get('allow_import')}"
        f" delete={safety.get('allow_delete')}"
    )

    if mode != "dry-run":
        print("ERROR: v0.1 only supports dry-run mode")
        return False

    if any(
        (
            safety.get("allow_download"),
            safety.get("allow_import"),
            safety.get("allow_delete"),
        )
    ):
        print("ERROR: write capability enabled in v0.1")
        return False

    print("Safety validation: PASS")
    return True


def build_clients(config: dict) -> dict[str, ServiceClient]:
    services = config.get("services", {})

    return {
        name: ServiceClient(
            name=name,
            base_url=services[name]["url"],
            api_key_env=services[name].get("api_key_env"),
        )
        for name in ("jellyfin", "sonarr", "radarr")
    }


def main() -> int:
    config_path = os.environ.get(
        "MEDIA_OPTIMIZER_CONFIG",
        "/app/config/config.yaml",
    )

    print("Media Optimizer")
    print("===============")

    if not os.path.exists(config_path):
        print("ERROR: config file not found")
        return 1

    config = load_config(config_path)

    if not validate_safety(config):
        return 2

    clients = build_clients(config)

    summary = collect_inventory(
        jellyfin=clients["jellyfin"],
        sonarr=clients["sonarr"],
        radarr=clients["radarr"],
    )

    print()
    print("Authenticated inventory")
    print("-----------------------")
    print(f"Jellyfin users:       {summary.jellyfin_users}")
    print(f"Sonarr series:        {summary.sonarr_series}")
    print(f"Sonarr episode files: {summary.sonarr_episode_files}")
    print(f"Radarr movies:        {summary.radarr_movies}")
    print(f"Radarr movie files:   {summary.radarr_movie_files}")

    status, _ = probe_playback_reporting(
        clients["jellyfin"]
    )

    print()
    print("Playback Reporting")
    print("------------------")
    print(f"API status: HTTP {status}")

    users = get_playback_users(
        clients["jellyfin"]
    )

    activity = get_user_activity_summary(
        clients["jellyfin"]
    )

    print()
    print("Playback users")
    print("--------------")

    for user in users:
        print(f"- {user.name} ({user.id})")

    print()
    print("User activity")
    print("-------------")

    if not activity:
        print("No playback activity returned.")
    else:
        for item in activity:
            age = days_since(item.last_seen)

            print(
                f"- {item.user.name}: "
                f"last_seen={item.last_seen} "
                f"age_days={age} "
                f"play_time={item.total_play_time}"
            )

    print()
    print("READ-ONLY execution complete.")
    print("No release searches were performed.")
    print("No downloads/imports/deletions were performed.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
