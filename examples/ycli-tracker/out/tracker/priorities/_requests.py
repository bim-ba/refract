"""Request builders for Tracker priorities - the single HTTP contract (sans-I/O)."""

from ycli.yandex.tracker.runtime import Request

from .models import Priority, PriorityCreate, PriorityList, PriorityUpdate


def list_() -> Request[PriorityList]:
    """``GET /priorities`` -> PriorityList request builder."""
    return Request(method="GET", path="priorities", response_model=PriorityList)


def create(body: PriorityCreate) -> Request[Priority]:
    """``POST /priorities/`` - create request from a typed body."""
    return Request(
        method="POST",
        path="priorities/",
        json_body=body.model_dump(by_alias=True, exclude_none=True),
        response_model=Priority,
    )


def edit(
    priority_id: str, body: PriorityUpdate, *, version: int | None = None
) -> Request[Priority]:
    """``PATCH /priorities/{priority_id}`` - edit request from a typed body."""
    return Request(
        method="PATCH",
        path=f"priorities/{priority_id}",
        query={"version": version},
        json_body=body.model_dump(by_alias=True, exclude_none=True),
        response_model=Priority,
    )
