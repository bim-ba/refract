from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Generic, TypeVar

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class Request(Generic[T]):  # noqa: UP046 -- Generic[T] pinned by the runtime spec (form D)
    """A pure, transport-agnostic description of one HTTP call - no I/O."""

    method: str
    path: str
    response_model: type[T]
    query: dict[str, Any] | None = None
    json_body: Any = None
