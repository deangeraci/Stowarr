from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from completion_confidence import (
    CompletionEvidence,
    assess_completion,
)


@dataclass(frozen=True)
class PlaybackSession:
    started_at: datetime
    duration_seconds: int


def select_completion(
    *,
    played: bool,
    runtime_seconds: int | None,
    sessions: list[PlaybackSession],
    jellyfin_last_played_at: str | None,
    timezone_name: str,
) -> CompletionEvidence:
    if not played:
        return CompletionEvidence(
            None,
            "none",
            "Jellyfin item is not marked played",
        )

    if not sessions:
        return CompletionEvidence(
            None,
            "partial",
            "no playback sessions available",
        )

    candidates: list[CompletionEvidence] = []

    for session in sessions:
        evidence = assess_completion(
            played=played,
            runtime_seconds=runtime_seconds,
            session_started_at=session.started_at.isoformat(),
            session_duration_seconds=session.duration_seconds,
            jellyfin_last_played_at=jellyfin_last_played_at,
            timezone_name=timezone_name,
        )

        if (
            evidence.confidence == "high"
            and evidence.completion_time is not None
        ):
            candidates.append(evidence)

    if not candidates:
        return CompletionEvidence(
            None,
            "partial",
            "no credible full playback session available",
        )

    return max(
        candidates,
        key=lambda evidence: evidence.completion_time,
    )
