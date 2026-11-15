from __future__ import annotations

import os
import re
from dataclasses import dataclass

import requests


@dataclass
class ServiceResult:
    name: str
    url: str
    ok: bool
    status_code: int | None
    error: str | None = None


class ServiceClient:
    def __init__(
        self,
        name: str,
        base_url: str,
        api_key_env: str | None = None,
    ) -> None:
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.api_key_env = api_key_env

    def api_key(self) -> str | None:
        if not self.api_key_env:
            return None
        return os.environ.get(self.api_key_env)

    def _headers(self) -> dict[str, str]:
        key = self.api_key()

        if not key:
            return {}

        if self.name in {"sonarr", "radarr"}:
            return {"X-Api-Key": key}

        if self.name == "jellyfin":
            return {
                "Authorization":
                    f'MediaBrowser Token="{key}"'
            }

        return {}

    def request(
        self,
        path: str,
        timeout: int = 10,
    ) -> requests.Response:
        return requests.get(
            f"{self.base_url}{path}",
            headers=self._headers(),
            timeout=timeout,
        )

    def connectivity_test(self) -> ServiceResult:
        paths = {
            "jellyfin": "/System/Info/Public",
            "sonarr": "/ping",
            "radarr": "/ping",
        }
        try:
            response = self.request(paths[self.name])
            return ServiceResult(self.name, self.base_url, response.ok,
                                 response.status_code)
        except requests.RequestException as exc:
            return ServiceResult(self.name, self.base_url, False, None, str(exc))


class QbitTorrentClient:
    """Read-only qBittorrent adapter; it intentionally has no mutation methods."""

    def __init__(self, base_url, category="stowarr", username_env=None,
                 password_env=None, session=None):
        self.base_url = base_url.rstrip("/")
        self.category = category
        self.username_env = username_env
        self.password_env = password_env
        self.session = session or requests.Session()
        self.authenticated = False

    def _login_if_configured(self):
        if self.authenticated or not (self.username_env and self.password_env):
            return
        username = os.environ.get(self.username_env)
        password = os.environ.get(self.password_env)
        if not username and not password:
            return
        if not username or not password:
            raise requests.RequestException("qBittorrent credentials are not configured")
        response = self.session.post(
            self.base_url + "/api/v2/auth/login",
            data={"username": username, "password": password},
            timeout=30, allow_redirects=False)
        body = response.text.strip().lower()
        login_ok = (
            (response.status_code == 200 and body in {"ok", "ok."})
            or (response.status_code == 204 and not body)
        )
        # Use the login response's cookies so a stale session cannot satisfy this check.
        has_session_cookie = any(
            cookie.value and re.fullmatch(r"SID|QBT_SID_[0-9]+", cookie.name)
            for cookie in response.cookies
        )
        if not login_ok or not has_session_cookie:
            raise requests.RequestException("qBittorrent login failed")

        version = self.session.get(
            self.base_url + "/api/v2/app/version", timeout=30, allow_redirects=False)
        if version.status_code != 200 or not re.fullmatch(
                r"v?[0-9]+\.[0-9]+\.[0-9]+[A-Za-z0-9.+_-]*", version.text.strip()):
            raise requests.RequestException("qBittorrent session verification failed")
        self.authenticated = True

    def state(self, torrent_hash):
        self._login_if_configured()
        response = self.session.get(
            self.base_url + "/api/v2/torrents/info",
            params={"hashes": torrent_hash, "category": self.category},
            timeout=30,
        )
        if (response.status_code in {401, 403} and self.username_env and self.password_env
                and os.environ.get(self.username_env) and os.environ.get(self.password_env)):
            self.authenticated = False
            self._login_if_configured()
            response = self.session.get(
                self.base_url + "/api/v2/torrents/info",
                params={"hashes": torrent_hash, "category": self.category}, timeout=30)
        response.raise_for_status()
        rows = response.json()
        for row in rows:
            if str(row.get("hash", "")).lower() == torrent_hash.lower():
                # qBittorrent names are stable API values; callers only use
                # this method to classify existence and progress.
                return str(row.get("state", "")).strip()
        return "removed"
