from __future__ import annotations

import json
from dataclasses import dataclass
from itertools import chain
from typing import assert_never

from refract.emitters.ports import Import, RenderedType, TypeMapper
from refract.ir.types import (
    ListType,
    LiteralType,
    MapType,
    NeutralType,
    RefType,
    ScalarType,
    UnionType,
)

_SCALAR = {"string": "str", "integer": "int", "number": "float", "boolean": "bool"}


@dataclass(frozen=True)
class _Coercion:
    """A `format` -> Python lowering: the base type it renders as (may differ from the plain
    scalar mapping, e.g. `rfc2822` -> `datetime`), the name of the hand-written `BeforeValidator`
    callable (lives in the shared base module - refract emits only the wiring), and any type
    imports the base itself needs."""

    base: str
    coercer: str
    type_imports: tuple[Import, ...] = ()


# Keyed by ScalarType.format. A format absent here (including None - no format) is a documented
# NO-OP: the bare scalar renders unchanged, with `coercer=None` - not an error, since refract
# does not need to coerce every format an upstream spec happens to name.
_FORMAT_COERCERS: dict[str, _Coercion] = {
    "int64": _Coercion(base="int", coercer="coerce_int64"),
    "rfc2822": _Coercion(
        base="datetime", coercer="coerce_rfc2822", type_imports=(Import("datetime", "datetime"),)
    ),
}


class PythonTypeMapper(TypeMapper):
    """Lower a NeutralType to a Python type string (+ the imports it needs)."""

    def render(self, neutral_type: NeutralType, *, optional: bool) -> RenderedType:
        base = self._base(neutral_type)
        if optional:
            return RenderedType(
                text=f"{base.text} | None",
                imports=base.imports,
                discriminator=base.discriminator,
                coercer=base.coercer,
            )
        return base

    def null_default(self, neutral_type: NeutralType, *, optional: bool) -> str | None:
        return "None" if optional else None

    def _base(self, neutral_type: NeutralType) -> RenderedType:
        match neutral_type:
            case ScalarType(scalar="any"):
                return RenderedType(text="Any", imports=(Import("typing", "Any"),))
            case ScalarType(scalar=scalar, format=fmt):
                coercion = _FORMAT_COERCERS.get(fmt) if fmt is not None else None
                if coercion is None:
                    return RenderedType(text=_SCALAR[scalar])
                return RenderedType(
                    text=coercion.base, imports=coercion.type_imports, coercer=coercion.coercer
                )
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
            # json.dumps (not a hand-quoted f-string) matches the `py_str` convention elsewhere in
            # the backend: double-quoted, proper escaping, non-ASCII stays literal.
            case LiteralType(value=value):
                return RenderedType(
                    text=f"Literal[{json.dumps(value, ensure_ascii=False)}]",
                    imports=(Import("typing", "Literal"),),
                )
            # Unguarded on `discriminator` so this ONE arm covers the WHOLE UnionType (keeps the
            # `match` exhaustive for ty, no shadowed/unreachable second arm). Both discriminated and
            # undiscriminated unions lower to the same bare PEP-604 union text (`_model_field` is
            # the single place that wraps a discriminated field in `Annotated[..., Field(...)]`);
            # only `discriminator` differs - None for undiscriminated, the tag name otherwise.
            case UnionType(variants=variants, discriminator=disc):
                rendered = [self._base(v) for v in variants]
                text = " | ".join(r.text for r in rendered)
                return RenderedType(
                    text=text,
                    imports=tuple(chain.from_iterable(r.imports for r in rendered)),
                    discriminator=disc,
                )
            case _:
                assert_never(neutral_type)
