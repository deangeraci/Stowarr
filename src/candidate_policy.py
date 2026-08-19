from __future__ import annotations

from dataclasses import dataclass


GIB = 1024 ** 3

REJECT_TERMS = {
    "remux",
    "raw-hd",
    "rawhd",
    "br-disk",
    "brdisk",
    "cam",
    "telesync",
    "tele-sync",
}

PREFERRED_CODECS = {
    "x265",
    "hevc",
    "h265",
    "h.265",
}


@dataclass(frozen=True)
class CandidateResult:
    accepted: bool
    reason: str

    savings_bytes: int
    savings_percent: float

    preferred_codec: bool


def evaluate_candidate(
    *,
    current_size_bytes: int,
    candidate_size_bytes: int,
    resolution: int,
    codec: str,
    release_title: str,
    minimum_resolution: int = 1080,
    minimum_savings_gb: float = 5,
    minimum_savings_percent: float = 40,
) -> CandidateResult:

    savings_bytes = (
        current_size_bytes - candidate_size_bytes
    )

    if current_size_bytes <= 0:
        savings_percent = 0.0
    else:
        savings_percent = (
            savings_bytes / current_size_bytes
        ) * 100

    codec_lower = codec.lower()
    title_lower = release_title.lower()

    preferred_codec = any(
        token in codec_lower
        for token in PREFERRED_CODECS
    )

    if candidate_size_bytes <= 0:
        return CandidateResult(
            False,
            "invalid candidate size",
            savings_bytes,
            savings_percent,
            preferred_codec,
        )

    if candidate_size_bytes >= current_size_bytes:
        return CandidateResult(
            False,
            "candidate is not smaller",
            savings_bytes,
            savings_percent,
            preferred_codec,
        )

    if resolution < minimum_resolution:
        return CandidateResult(
            False,
            "resolution below minimum",
            savings_bytes,
            savings_percent,
            preferred_codec,
        )

    if any(
        token in title_lower
        for token in REJECT_TERMS
    ):
        return CandidateResult(
            False,
            "release contains rejected format",
            savings_bytes,
            savings_percent,
            preferred_codec,
        )

    minimum_bytes = int(
        minimum_savings_gb * GIB
    )

    enough_absolute = (
        savings_bytes >= minimum_bytes
    )

    enough_percent = (
        savings_percent >= minimum_savings_percent
    )

    if not (
        enough_absolute
        or enough_percent
    ):
        return CandidateResult(
            False,
            "insufficient storage savings",
            savings_bytes,
            savings_percent,
            preferred_codec,
        )

    return CandidateResult(
        True,
        "candidate satisfies base policy",
        savings_bytes,
        savings_percent,
        preferred_codec,
    )
