"""Fail-closed checks that keep replacement downloads outside Radarr handling."""
from __future__ import annotations

import posixpath
import os
from urllib.parse import urlsplit


class IsolationError(ValueError):
    """The replacement target cannot be proven isolated."""


def _normal_path(value):
    if not isinstance(value, str) or not value.startswith("/"):
        raise IsolationError("replacement path must be an absolute container path")
    if ".." in value.split("/"):
        raise IsolationError("replacement path cannot contain parent traversal")
    normalized = posixpath.normpath(value)
    if normalized == "/" or normalized.startswith("/../"):
        raise IsolationError("replacement path is unsafe")
    return normalized


def _canonical_path(value, require_exists=False):
    normalized = _normal_path(value)
    if require_exists and not os.path.isdir(normalized):
        raise IsolationError("staging path is not an existing directory")
    # realpath resolves symlinks when the container can see them. If a path is
    # not visible, callers must provide an explicit mapping instead of guessing.
    return posixpath.normpath(os.path.realpath(normalized).replace("\\", "/"))


def _under(path, parent):
    return path == parent or path.startswith(parent.rstrip("/") + "/")


def path_is_within(path, parent):
    return _under(_canonical_path(path), _canonical_path(parent))


def _radarr_category(resource):
    fields = resource.get("fields")
    if not isinstance(fields, list):
        raise IsolationError("Radarr download client fields are unavailable")
    for field in fields:
        if field.get("name") in {"movieCategory", "category"}:
            value = field.get("value")
            if isinstance(value, str) and value.strip():
                return value.strip()
    raise IsolationError("Radarr monitored category is unavailable")


def _enabled(resource):
    return resource.get("enable", resource.get("enabled", True)) is not False


def verify_replacement_isolation(radarr, qbit, client_id, monitored_category,
                                replacement_category, replacement_path,
                                radarr_root_paths, radarr_download_clients=None,
                                path_mappings=None):
    """Verify category, path, and qBittorrent API boundaries before submit."""
    if not isinstance(replacement_category, str) or not replacement_category.strip():
        raise IsolationError("replacement category is required")
    if replacement_category == monitored_category:
        raise IsolationError("replacement category is Radarr's monitored category")
    if not isinstance(client_id, int) or client_id <= 0:
        raise IsolationError("Radarr monitored client ID is invalid")

    resource_response = radarr.request(f"/api/v3/downloadclient/{client_id}", timeout=30)
    resource_response.raise_for_status()
    configured = resource_response.json()
    if _radarr_category(configured) != monitored_category or not _enabled(configured):
        raise IsolationError("Radarr monitored category changed unexpectedly")

    if radarr_download_clients is None:
        clients_response = radarr.request("/api/v3/downloadclient", timeout=30)
        clients_response.raise_for_status()
        radarr_download_clients = clients_response.json()
    if not isinstance(radarr_download_clients, list) or not radarr_download_clients:
        raise IsolationError("Radarr download clients could not be enumerated")
    for resource in radarr_download_clients:
        if not isinstance(resource, dict):
            raise IsolationError("Radarr download client data is invalid")
        if _enabled(resource) and _radarr_category(resource) == replacement_category:
            raise IsolationError("replacement category is monitored by Radarr")

    target = _canonical_path(replacement_path, require_exists=True)
    path_mappings = path_mappings or {}
    roots = []
    for path in radarr_root_paths:
        mapped = path_mappings.get(path, path) if isinstance(path_mappings, dict) else path
        roots.append(_canonical_path(mapped, require_exists=True))
    if any(_under(target, root) or _under(root, target) for root in roots):
        raise IsolationError("replacement path overlaps a Radarr root folder")

    categories = qbit.categories()
    category_config = categories.get(replacement_category)
    if not isinstance(category_config, dict):
        raise IsolationError("replacement category is not pre-created in qBittorrent")
    qbit_path = category_config.get("savePath") or category_config.get("save_path")
    if not isinstance(qbit_path, str):
        raise IsolationError("qBittorrent replacement save path is unavailable")
    if _canonical_path(qbit_path) != target:
        raise IsolationError("qBittorrent category save path is not isolated")
    return target


def validate_source_url(source_url):
    """Accept only release URLs that qBittorrent can fetch without a redirect."""
    if not isinstance(source_url, str) or not source_url.strip():
        raise IsolationError("release has no qBittorrent source URL")
    parsed = urlsplit(source_url)
    if parsed.scheme not in {"http", "https", "magnet"} or parsed.username or parsed.password:
        raise IsolationError("release source URL is not an allowed qBittorrent URL")
    return source_url
