"""Request builders for Github users - the single HTTP contract (sans-I/O)."""

from ycli.yandex.github.runtime import Request

from .models import User


def me() -> Request[User]:
    """``GET /user`` -> User request builder."""
    return Request(method="GET", path="user", response_model=User)


def get(username: str) -> Request[User]:
    """``GET /users/{username}`` -> User request builder."""
    return Request(method="GET", path=f"users/{username}", response_model=User)
