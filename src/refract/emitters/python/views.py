from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class _View(BaseModel):
    """Base for every view-model: frozen, and every field a resolved primitive.

    No ir/shape tags leak into the fields.
    """

    model_config = ConfigDict(frozen=True)
