from __future__ import annotations

from refract.ir.types import ListType, MapType, NeutralType, RefType, ScalarType

__all__ = ["SpecError", "parse_neutral_type"]

_SCALARS = frozenset({"string", "integer", "number", "boolean", "any"})


class SpecError(Exception):
    """A malformed spec - carries the file path and the underlying validation message."""


def _split_top_comma(inner: str) -> tuple[str, str]:
    """Split ``K,V`` on the FIRST top-level comma (bracket-depth aware)."""
    depth = 0
    for i, ch in enumerate(inner):
        if ch == "<":
            depth += 1
        elif ch == ">":
            depth -= 1
        elif ch == "," and depth == 0:
            return inner[:i], inner[i + 1 :]
    raise SpecError(f"expected 'K,V' in map<...>, got {inner!r}")


def parse_neutral_type(text: str) -> NeutralType:
    """Parse one neutral spec type string into a NeutralType (see section A grammar)."""
    text = text.strip()
    if text in _SCALARS:
        return ScalarType(scalar=text)  # type: ignore[arg-type]
    for prefix, build in (
        ("ref<", lambda body: RefType(target=body.strip())),
        ("list<", lambda body: ListType(item=parse_neutral_type(body))),
    ):
        if text.startswith(prefix) and text.endswith(">"):
            body = text[len(prefix) : -1]
            if not body.strip():
                raise SpecError(f"empty type argument in {text!r}")
            return build(body)
    if text.startswith("map<") and text.endswith(">"):
        key, value = _split_top_comma(text[4:-1])
        return MapType(key=parse_neutral_type(key), value=parse_neutral_type(value))
    raise SpecError(f"unknown neutral type: {text!r}")
