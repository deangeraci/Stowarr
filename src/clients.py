from __future__ import annotations

import os
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

        path = paths[self.name]

        try:
            response = self.request(path)

            return ServiceResult(
                name=self.name,
                url=self.base_url,
                ok=response.ok,
                status_code=response.status_code,
            )

        except requests.RequestException as exc:
            return ServiceResult(
                name=self.name,
                url=self.base_url,
                ok=False,
                status_code=None,
                error=str(exc),
            )
