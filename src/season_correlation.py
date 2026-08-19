from __future__ import annotations

from dataclasses import dataclass

from clients import ServiceClient


@dataclass
class SonarrSeason:
    series_title: str
    season_number: int
    size_bytes: int
    episode_count: int
    episode_file_count: int


def normalize_title(value: str) -> str:
    return "".join(
        char.lower()
        for char in value
        if char.isalnum()
    )


def get_sonarr_seasons(
    sonarr: ServiceClient,
) -> list[SonarrSeason]:
    response = sonarr.request(
        "/api/v3/series"
    )
    response.raise_for_status()

    results: list[SonarrSeason] = []

    for series in response.json():
        title = str(series.get("title", ""))

        for season in series.get("seasons", []):
            number = season.get("seasonNumber")

            if number is None or int(number) == 0:
                continue

            stats = season.get("statistics", {})

            results.append(
                SonarrSeason(
                    series_title=title,
                    season_number=int(number),
                    size_bytes=int(
                        stats.get("sizeOnDisk", 0) or 0
                    ),
                    episode_count=int(
                        stats.get("totalEpisodeCount", 0) or 0
                    ),
                    episode_file_count=int(
                        stats.get("episodeFileCount", 0) or 0
                    ),
                )
            )

    return results


def find_sonarr_season(
    seasons: list[SonarrSeason],
    series_title: str,
    season_number: int,
) -> SonarrSeason | None:
    wanted = normalize_title(series_title)

    for season in seasons:
        if (
            normalize_title(season.series_title) == wanted
            and season.season_number == season_number
        ):
            return season

    return None
