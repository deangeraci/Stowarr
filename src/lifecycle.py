from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


TRUSTED_CONFIDENCE = {"high", "approved"}


@dataclass(frozen=True)
class LifecycleResult:
    status: str
    eligible_at: datetime | None
    reason: str


def parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None

    value = value.replace("Z", "+00:00")
    result = datetime.fromisoformat(value)

    if result.tzinfo is None:
        raise ValueError("completion timestamp must include timezone")

    return result.astimezone(timezone.utc)


def assess_lifecycle(
    *,
    watched_state: str,
    completion_time: str | None,
    completion_confidence: str,
    delay_days: int,
    now: datetime | None = None,
) -> LifecycleResult:
    if watched_state != "complete":
        return LifecycleResult(
            "BLOCKED",
            None,
            "not fully watched",
        )

    completed_at = parse_timestamp(completion_time)

    if completed_at is None:
        return LifecycleResult(
            "BLOCKED",
            None,
            "completion timestamp unavailable",
        )

    if completion_confidence not in TRUSTED_CONFIDENCE:
        return LifecycleResult(
            "BLOCKED",
            None,
            f"completion confidence is {completion_confidence}",
        )

    eligible_at = completed_at + timedelta(days=delay_days)

    current = now or datetime.now(timezone.utc)

    if current >= eligible_at:
        return LifecycleResult(
            "ELIGIBLE",
            eligible_at,
            "watch delay satisfied",
        )

    return LifecycleResult(
        "WAIT",
        eligible_at,
        "watch delay not yet satisfied",
    )
