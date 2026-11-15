"""Read-only verification for a completed replacement download."""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path


MEDIA_SUFFIXES = {".mkv", ".mp4", ".m4v", ".avi", ".ts", ".mov"}
MAX_VERIFY_BYTES = 16 * 1024 * 1024 * 1024
MAX_VERIFY_SECONDS = 1800


class VerificationError(ValueError):
    """The staged media cannot be proven safe to use."""


def _candidate_file(path):
    path = Path(path)
    if path.is_file():
        return path
    if not path.is_dir():
        raise VerificationError("staged content path does not exist")
    files = sorted(
        item for item in path.rglob("*")
        if item.is_file() and item.suffix.lower() in MEDIA_SUFFIXES
    )
    if len(files) != 1:
        raise VerificationError("staged content must contain exactly one media file")
    return files[0]


def _run(command, timeout):
    try:
        return subprocess.run(command, check=True, capture_output=True,
                              text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as exc:
        raise VerificationError("media integrity command failed") from exc


def _sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_media(path, expected_size=None, ffprobe="ffprobe", ffmpeg="ffmpeg",
                 max_bytes=MAX_VERIFY_BYTES, max_seconds=MAX_VERIFY_SECONDS):
    """Probe and decode one file without modifying it, returning a manifest."""
    if (type(max_bytes) is not int or max_bytes <= 0 or
            type(max_seconds) is not int or max_seconds <= 0):
        raise VerificationError("verification limits are invalid")
    media = _candidate_file(path)
    actual_size = media.stat().st_size
    if actual_size <= 0:
        raise VerificationError("staged media file is empty")
    if actual_size > max_bytes:
        raise VerificationError("staged media exceeds verification size limit")
    if expected_size is not None:
        if type(expected_size) is not int or expected_size <= 0:
            raise VerificationError("expected release size is invalid")
        if not 0.5 <= actual_size / expected_size <= 1.5:
            raise VerificationError("staged media size differs from approved release")

    probe = _run([
        ffprobe, "-v", "error", "-print_format", "json",
        "-show_format", "-show_streams", str(media),
    ], timeout=120)
    try:
        metadata = json.loads(probe.stdout)
        streams = metadata["streams"]
        video = next(stream for stream in streams if stream.get("codec_type") == "video")
        duration = float(metadata["format"]["duration"])
    except (KeyError, StopIteration, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise VerificationError("ffprobe returned incomplete media metadata") from exc
    if duration <= 0 or int(video.get("height") or 0) < 1080:
        raise VerificationError("media does not meet the minimum video profile")
    if str(video.get("codec_name", "")).lower() not in {"hevc", "h265"}:
        raise VerificationError("media is not an HEVC video")

    timeout = min(max_seconds, max(60, media.stat().st_size // (1024 * 1024) + 300))
    _run([ffmpeg, "-v", "error", "-threads", "1", "-filter_threads", "1",
          "-filter_complex_threads", "1", "-i", str(media), "-map", "0:v:0",
          "-f", "null", "-"], timeout=timeout)
    return {
        "path": str(media),
        "size_bytes": actual_size,
        "sha256": _sha256(media),
        "duration_seconds": duration,
        "video_codec": video.get("codec_name"),
        "video_height": int(video["height"]),
        "stream_count": len(streams),
    }
