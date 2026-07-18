"""The neutral type system - a closed, frozen, hashable sum the IR carries verbatim.

Emitters lower a NeutralType to a language type via their TypeMapper; nothing here is
Python-specific (that was the loader's leak this replaces). Dispatch is exhaustive
(`match` + `assert_never`); recursive variants use string forward-refs + model_rebuild().
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

__all__ = [
    "ListType",
    "LiteralType",
    "MapType",
    "NeutralType",
    "RefType",
    "ScalarType",
    "UnionType",
]

Scalar = Literal["string", "integer", "number", "boolean", "any"]


class _Node(BaseModel):
    model_config = ConfigDict(frozen=True)


class ScalarType(_Node):
    kind: Literal["scalar"] = "scalar"
    scalar: Scalar
    format: str | None = None  # "int64" | "date-time" | "rfc2822" | ...; None = no coercion


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


class UnionType(_Node):
    kind: Literal["union"] = "union"
    variants: tuple[NeutralType, ...]
    discriminator: str | None = None

    @model_validator(mode="after")
    def _at_least_two_variants(self) -> UnionType:
        if len(self.variants) < 2:
            raise ValueError("a union needs >= 2 variants")
        return self


class LiteralType(_Node):
    """A single-value ``Literal[<value>]`` - the loader synthesizes this onto a discriminated-
    union variant's tag field (default B: nobody hand-writes the tag). No recursive field, so
    unlike its siblings above it needs no ``model_rebuild()``."""

    kind: Literal["literal"] = "literal"
    value: str


NeutralType = Annotated[
    ScalarType | RefType | ListType | MapType | UnionType | LiteralType,
    Field(discriminator="kind"),
]

ListType.model_rebuild()
MapType.model_rebuild()
UnionType.model_rebuild()
