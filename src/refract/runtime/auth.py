from __future__ import annotations

from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from collections.abc import Generator


class HeaderAuth(httpx.Auth):
    """Single-header credential, e.g. ``Authorization: Bearer <token>``. No I/O -> sync+async."""

    def __init__(self, header: str, value: str) -> None:
        self._header = header
        self._value = value

    def auth_flow(self, request: httpx.Request) -> Generator[httpx.Request, httpx.Response, None]:
        request.headers[self._header] = self._value
        yield request


class MultiHeaderAuth(httpx.Auth):
    """>=1 constant headers (Cloudflare X-Auth-*; Yandex ``Authorization: OAuth ...`` +
    ``X-Org-Id``)."""

    def __init__(self, headers: dict[str, str]) -> None:
        self._headers = dict(headers)

    def auth_flow(self, request: httpx.Request) -> Generator[httpx.Request, httpx.Response, None]:
        request.headers.update(self._headers)
        yield request
