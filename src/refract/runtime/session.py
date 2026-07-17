from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar

from pydantic import BaseModel

if TYPE_CHECKING:
    import httpx

    from refract.runtime.request import Request

T = TypeVar("T", bound=BaseModel)


class Session:
    """Executes any Request over a PRE-CONFIGURED httpx.Client. AUTH-AGNOSTIC: auth lives on the
    injected client (httpx.Auth), not here. Owns base_url + minimal error policy (the ONLY I/O)."""

    def __init__(self, base_url: str, *, client: httpx.Client) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = client

    def send(self, request: Request[T]) -> T:
        params = {k: v for k, v in (request.query or {}).items() if v is not None}
        response = self._client.request(
            request.method,
            f"{self._base_url}/{request.path}",
            params=params or None,
            json=request.json_body,
        )
        response.raise_for_status()
        # T is unbound (Request is transport-agnostic, not pydantic-specific); response_model is
        # expected to expose model_validate() by convention (a pydantic BaseModel in practice).
        model = request.response_model
        return model.model_validate(response.json())
