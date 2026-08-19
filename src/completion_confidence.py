from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


MIN_COMPLETION_RATIO = 0.90
MAX_END_DRIFT_SECONDS = 15 * 60


@dataclass(frozen=True)
class CompletionEvidence:
    completion_time: datetime | None
    confidence: str
    reason: str


def parse_dt(value: str) -> datetime:
    value = value.replace("Z", "+00:00")
    result = datetime.fromisoformat(value)

    if result.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")

    return result.astimezone(timezone.utc)


def assess_completion(
    *,
    played: bool,
    runtime_seconds: int | None,
    session_started_at: str | None,
    session_duration_seconds: int | None,
    jellyfin_last_played_at: str | None,
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

    started = parse_dt(session_started_at)
    ended = started + timedelta(seconds=session_duration_seconds)

    if jellyfin_last_played_at:
        last_played = parse_dt(jellyfin_last_played_at)
        drift = abs((ended - last_played).total_seconds())

        if drift > MAX_END_DRIFT_SECONDS:
            return CompletionEvidence(
                None,
                "partial",
                "playback session does not align with Jellyfin last-played time",
            )

    return CompletionEvidence(
        ended,
        "high",
        "Jellyfin played state confirmed by credible playback session",
    )
