"""The neutral type system - a closed, frozen, hashable sum the IR carries verbatim.

Emitters lower a NeutralType to a language type via their TypeMapper; nothing here is
Python-specific (that was the loader's leak this replaces). Dispatch is exhaustive
(`match` + `assert_never`); recursive variants use string forward-refs + model_rebuild().
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["ListType", "MapType", "NeutralType", "RefType", "ScalarType"]

Scalar = Literal["string", "integer", "number", "boolean", "any"]


class _Node(BaseModel):
    model_config = ConfigDict(frozen=True)


class ScalarType(_Node):
    kind: Literal["scalar"] = "scalar"
    scalar: Scalar


class RefType(_Node):
    kind: Literal["ref"] = "ref"
    target: str  # a declared Model name


class ListType(_Node):
    kind: Literal["list"] = "list"
    item: NeutralType


class MapType(_Node):
    kind: Literal["map"] = "map"
    key: NeutralType
    value: NeutralType


NeutralType = Annotated[
    ScalarType | RefType | ListType | MapType,
    Field(discriminator="kind"),
]

ListType.model_rebuild()
MapType.model_rebuild()
