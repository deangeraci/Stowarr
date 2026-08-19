from __future__ import annotations

from clients import ServiceClient


def probe_playback_reporting(jellyfin: ServiceClient) -> tuple[int, str]:
    response = jellyfin.request(
        "/user_usage_stats/user_list"
    )

    content_type = response.headers.get("content-type", "")

    return response.status_code, content_type
