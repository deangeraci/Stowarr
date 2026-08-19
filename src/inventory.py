from __future__ import annotations

from dataclasses import dataclass

from clients import ServiceClient


@dataclass
class InventorySummary:
    jellyfin_users: int
    sonarr_series: int
    sonarr_episode_files: int
    radarr_movies: int
    radarr_movie_files: int


def _json_get(client: ServiceClient, path: str):
    response = client.request(path)
    response.raise_for_status()
    return response.json()


def collect_inventory(
    jellyfin: ServiceClient,
    sonarr: ServiceClient,
    radarr: ServiceClient,
) -> InventorySummary:
    jellyfin_users = _json_get(
        jellyfin,
        "/Users",
    )

    sonarr_series = _json_get(
        sonarr,
        "/api/v3/series",
    )

    radarr_movies = _json_get(
        radarr,
        "/api/v3/movie",
    )

    sonarr_episode_files = sum(
        int(series.get("statistics", {}).get("episodeFileCount", 0))
        for series in sonarr_series
    )

    radarr_movie_files = sum(
        1
        for movie in radarr_movies
        if movie.get("hasFile", False)
    )

    return InventorySummary(
        jellyfin_users=len(jellyfin_users),
        sonarr_series=len(sonarr_series),
        sonarr_episode_files=sonarr_episode_files,
        radarr_movies=len(radarr_movies),
        radarr_movie_files=radarr_movie_files,
    )
