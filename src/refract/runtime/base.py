from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from refract.runtime.session import Session


class Resource:
    def __init__(self, session: Session) -> None:
        self._session = session
