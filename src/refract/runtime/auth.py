from __future__ import annotations

from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from collections.abc import Iterator


class HeaderAuth(httpx.Auth):
    """Single-header credential, e.g. ``Authorization: Bearer <token>``. No I/O -> sync+async."""

    def __init__(self, header: str, value: str) -> None:
        self._header = header
        self._value = value

    # Iterator[Request] (not httpx.Auth's declared Generator[Request, Response, None]) is
    # correct here: a single-yield, no-challenge flow never receives a sent-back Response.
    def auth_flow(  # ty: ignore[invalid-method-override]
        self, request: httpx.Request
    ) -> Iterator[httpx.Request]:
        request.headers[self._header] = self._value
        yield request


class MultiHeaderAuth(httpx.Auth):
    """>=1 constant headers (Cloudflare X-Auth-*; Yandex ``Authorization: OAuth ...`` +
    ``X-Org-Id``)."""

    def __init__(self, headers: dict[str, str]) -> None:
        self._headers = dict(headers)

    # See HeaderAuth.auth_flow above: Iterator[Request] is correct for a no-challenge flow.
    def auth_flow(  # ty: ignore[invalid-method-override]
        self, request: httpx.Request
    ) -> Iterator[httpx.Request]:
        request.headers.update(self._headers)
        yield request
