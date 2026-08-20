from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo


MIN_COMPLETION_RATIO = 0.90
MAX_START_DRIFT_SECONDS = 15 * 60


@dataclass(frozen=True)
class CompletionEvidence:
    completion_time: datetime | None
    confidence: str
    reason: str


def parse_utc_datetime(value: str) -> datetime:
    cleaned = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(cleaned)

    if parsed.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")

    return parsed.astimezone(timezone.utc)


def local_wall_clock_to_utc(
    value: str,
    timezone_name: str,
) -> datetime:
    parsed = datetime.fromisoformat(value)

    if parsed.tzinfo is not None:
        return parsed.astimezone(timezone.utc)

    return parsed.replace(
        tzinfo=ZoneInfo(timezone_name)
    ).astimezone(timezone.utc)


def assess_completion(
    *,
    played: bool,
    runtime_seconds: int | None,
    session_started_at: str | None,
    session_duration_seconds: int | None,
    jellyfin_last_played_at: str | None,
    timezone_name: str,
) -> CompletionEvidence:
    if not played:
        return CompletionEvidence(
            None,
            "none",
            "Jellyfin item is not marked played",
        )

    if not runtime_seconds or runtime_seconds <= 0:
        return CompletionEvidence(
            None,
            "partial",
            "runtime unavailable",
        )

    if not session_started_at or not session_duration_seconds:
        return CompletionEvidence(
            None,
            "partial",
            "credible playback session unavailable",
        )

    ratio = session_duration_seconds / runtime_seconds

    if ratio < MIN_COMPLETION_RATIO:
        return CompletionEvidence(
            None,
            "partial",
            f"playback session covered only {ratio:.1%} of runtime",
        )

    session_start_utc = local_wall_clock_to_utc(
        session_started_at,
        timezone_name,
    )

    completion_time = session_start_utc + timedelta(
        seconds=session_duration_seconds
    )

    if jellyfin_last_played_at:
        last_played = parse_utc_datetime(
            jellyfin_last_played_at
        )

        if (
            last_played
            < session_start_utc
            - timedelta(seconds=MAX_START_DRIFT_SECONDS)
        ):
            return CompletionEvidence(
                None,
                "partial",
                "Jellyfin last-played time predates the playback session",
            )

        drift = abs(
            (last_played - session_start_utc).total_seconds()
        )

        if drift <= MAX_START_DRIFT_SECONDS:
            reason = (
                "Jellyfin played state confirmed by aligned "
                "credible playback session"
            )
        else:
            reason = (
                "Jellyfin played state confirmed by credible "
                "historical playback session"
            )
    else:
        reason = (
            "Jellyfin played state confirmed by credible "
            "playback session"
        )

    return CompletionEvidence(
        completion_time,
        "high",
        reason,
    )
