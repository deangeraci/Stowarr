"""Completion lifecycle configuration, with legacy-key compatibility."""


def configured_grace_days(config: dict) -> int:
    lifecycle = config.get("lifecycle", {})
    if not isinstance(lifecycle, dict):
        raise ValueError("lifecycle must be a mapping")
    raw = lifecycle.get("watched_delay_days", config.get("watched_delay_days", 30))
    if type(raw) is not int and not (isinstance(raw, str) and raw.isdecimal()):
        raise ValueError("watched_delay_days must be a nonnegative integer")
    days = int(raw)
    if days < 0:
        raise ValueError("watched_delay_days cannot be negative")
    return days
