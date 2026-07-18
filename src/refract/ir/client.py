from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from refract.ir.auth import AuthScheme  # discriminated-union alias


class _Client(BaseModel):
    model_config = ConfigDict(frozen=True)


class Server(_Client):
    """Fixed base URL for the walking skeleton; a templated server (variables) grows later."""

    base_url: str


class ClientConfig(_Client):
    """Per-API glue config (from client.yaml): server + default headers + named auth schemes."""

    name: str  # API name, e.g. "tracker"
    server: Server
    default_headers: tuple[tuple[str, str], ...] = ()
    auth: tuple[tuple[str, AuthScheme], ...] = ()  # scheme-name -> scheme (ordered, hashable)
