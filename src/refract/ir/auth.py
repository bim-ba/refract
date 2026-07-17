from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class _Auth(BaseModel):
    model_config = ConfigDict(frozen=True)


class AuthInput(_Auth):
    """One named credential input + its default source (env var)."""

    name: str
    env: str | None = None  # env var name; None -> must be passed explicitly


class HeaderAuth(_Auth):
    """Single templated header, e.g. ``Authorization: Bearer {token}`` (most bearer APIs)."""

    kind: Literal["header"] = "header"
    header: str
    template: str  # "{token}" placeholders resolved from `inputs`
    inputs: tuple[AuthInput, ...]


class MultiHeaderAuth(_Auth):
    """>=1 templated headers (Cloudflare X-Auth-*; Yandex ``OAuth {token}`` + ``X-Org-Id``)."""

    kind: Literal["multi_header"] = "multi_header"
    headers: tuple[tuple[str, str], ...]  # (header-name, template) pairs; hashable ordered map
    inputs: tuple[AuthInput, ...]


AuthScheme = Annotated[HeaderAuth | MultiHeaderAuth, Field(discriminator="kind")]
