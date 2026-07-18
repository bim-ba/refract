from __future__ import annotations

from itertools import chain
from typing import assert_never

from refract.emitters.api import Import, RenderedType, TypeMapper
from refract.ir.types import ListType, MapType, NeutralType, RefType, ScalarType, UnionType

_SCALAR = {"string": "str", "integer": "int", "number": "float", "boolean": "bool"}


class PythonTypeMapper(TypeMapper):
    """Lower a NeutralType to a Python type string (+ the imports it needs)."""

    def render(self, neutral_type: NeutralType, *, optional: bool) -> RenderedType:
        base = self._base(neutral_type)
        if optional:
            return RenderedType(text=f"{base.text} | None", imports=base.imports)
        return base

    def null_default(self, neutral_type: NeutralType, *, optional: bool) -> str | None:
        return "None" if optional else None

    def _base(self, neutral_type: NeutralType) -> RenderedType:
        match neutral_type:
            case ScalarType(scalar="any"):
                return RenderedType(text="Any", imports=(Import("typing", "Any"),))
            case ScalarType(scalar=scalar):
                return RenderedType(text=_SCALAR[scalar])
            case RefType(target=target):
                return RenderedType(text=target)
            case ListType(item=item):
                inner = self._base(item)
                return RenderedType(text=f"list[{inner.text}]", imports=inner.imports)
            case MapType(key=key, value=value):
                kr, vr = self._base(key), self._base(value)
                return RenderedType(
                    text=f"dict[{kr.text}, {vr.text}]", imports=kr.imports + vr.imports
                )
            # Unguarded on `discriminator` so this arm covers the WHOLE UnionType (keeps the
            # `match` exhaustive for ty). Task 5 extends this arm to branch on the discriminator
            # (a discriminated union additionally carries `RenderedType.discriminator`); until then
            # both kinds lower to the bare PEP-604 union text, and no discriminated union is
            # rendered before Task 5.
            case UnionType(variants=variants):
                rendered = [self._base(v) for v in variants]
                text = " | ".join(r.text for r in rendered)
                return RenderedType(
                    text=text, imports=tuple(chain.from_iterable(r.imports for r in rendered))
                )
            case _:
                assert_never(neutral_type)
