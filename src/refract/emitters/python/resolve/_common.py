from __future__ import annotations

import json
from collections import defaultdict
from typing import TYPE_CHECKING, assert_never

from refract.ir import ListType, LiteralType, MapType, ObjectModel, RefType, ScalarType, UnionType
from refract.spec import SpecError

if TYPE_CHECKING:
    from refract import ir
    from refract.emitters.api import EmitContext, Import, Naming, TypeMapper


def render_imports(imports: tuple[Import, ...]) -> tuple[str, ...]:
    """Union -> group-by-module -> merge names -> `from <module> import <names>` (ruff orders)."""
    by_module: dict[str, set[str]] = defaultdict(set)
    for imp in imports:
        by_module[imp.module].add(imp.name)
    return tuple(
        f"from {module} import {', '.join(sorted(names))}" for module, names in by_module.items()
    )


def signature_params(positional: tuple[str, ...], keyword_only: tuple[str, ...]) -> tuple[str, ...]:
    """Assemble a param list, inserting the `*` marker before the first keyword-only param."""
    if keyword_only:
        return (*positional, "*", *keyword_only)
    return positional


def indent_lines(lines: tuple[str, ...], prefix: str) -> tuple[str, ...]:
    """Prefix every non-blank line (blank lines stay empty)."""
    return tuple(f"{prefix}{line}" if line else "" for line in lines)


def param_decl(
    param: ir.Param, type_mapper: TypeMapper, naming: Naming
) -> tuple[str, tuple[Import, ...]]:
    """Render one parameter declaration `name: Type` (+ ` = default`) and its imports.

    The declared identifier is shadow-guarded (`id` -> `id_`); the wire name (path placeholder,
    query alias/key) is preserved by the CALLER, not here."""
    rt = type_mapper.render(param.type, optional=param.optional)
    default = (
        param.default
        if param.default is not None
        else type_mapper.null_default(param.type, optional=param.optional)
    )
    decl = f"{naming.safe_param(param.name)}: {rt.text}"
    if default is not None:
        decl = f"{decl} = {default}"
    return decl, rt.imports


def py_str(value: str) -> str:
    """A safely-quoted Python string literal for free text (escapes quotes/backslashes/newlines).

    Uses json.dumps: double-quoted with proper escaping, matching the backend's double-quote
    style, so a quote-free value renders exactly as a hand-written "..." literal (ruff format is
    a no-op on it). ``ensure_ascii=False`` keeps non-ASCII text (em-dashes, Cyrillic, ...) literal
    instead of ``\\uXXXX`` escapes - both are valid Python, but literal matches the prior
    hand-quoted output byte-for-byte.
    """
    return json.dumps(value, ensure_ascii=False)


def signature_and_call(
    op: ir.Operation, type_mapper: TypeMapper, naming: Naming
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...], tuple[Import, ...]]:
    """(positional_decls, keyword_only_decls, call_args, param_type_imports).

    positional_decls = path-param decls (+ `body: <model>` when op.body); keyword_only_decls =
    query-param decls; call_args = path names (+ "body") + `name=name` for query. imports carries
    ONLY the param TYPE imports (from param_decl). Callers add their own prefix (`self`), suffix
    (`client=Depends(...)`), the `*` marker, the response/body MODEL imports (whose module differs
    per caller), and - for requests - the alias-keyed query dict.
    """
    positional: list[str] = []
    call_args: list[str] = []
    imports: list[Import] = []
    for p in op.params:
        if p.loc == "path":
            decl, imp = param_decl(p, type_mapper, naming)
            positional.append(decl)
            call_args.append(naming.safe_param(p.name))
            imports += imp
    if op.body is not None:
        positional.append(f"body: {op.body.model}")
        call_args.append("body")
    keyword_only: list[str] = []
    for p in op.params:
        if p.loc == "query":
            decl, imp = param_decl(p, type_mapper, naming)
            keyword_only.append(decl)
            call_args.append(f"{naming.safe_param(p.name)}={naming.safe_param(p.name)}")
            imports += imp
    return tuple(positional), tuple(keyword_only), tuple(call_args), tuple(imports)


def _shared_models_module(ctx: EmitContext) -> str:
    """The shared base module (``APIModel``/``require_found``) - one level above the domain.

    ``ycli.yandex.tracker`` -> ``ycli.yandex.models`` (derived, not hardcoded)."""
    return f"{ctx.package_root.rsplit('.', 1)[0]}.models"


def require_model(res: ir.Resource, name: str) -> ir.Model:
    """``res.model`` with the project's fail-loud contract: a dangling ref (an undeclared target) is
    reported as a friendly ``SpecError``, not the bare ``KeyError`` ``res.model`` raises. Every
    emitter site resolving a model NAME to its definition goes through here so the malformed-spec
    message is uniform across surfaces (the recursive walker, cli body-flatten, test imports)."""
    try:
        return res.model(name)
    except KeyError as error:
        raise SpecError(f"{res.resource}: reference to undeclared model {name!r}") from error


def _type_ref_targets(neutral: ir.NeutralType) -> tuple[str, ...]:
    """The model names a rendered type NAMES via RefType, unwrapping list/map/union at any depth.

    Unlike `_referenced_model_names`, this does NOT recurse into a referenced model's own fields - a
    type annotation names only its own top-level targets; a referenced model's internals live in
    that model's own module. So `ref<A>` -> ('A',), `list<ref<A>>` -> ('A',),
    `map<ref<K>, ref<V>>` -> ('K', 'V'), `oneof<ref<A>|ref<B>>` -> ('A', 'B'). Used for the
    same-file-vs-shared import decision (a field's rendered type must import every model it names).
    """
    match neutral:
        case RefType(target=target):
            return (target,)
        case ListType(item=item):
            return _type_ref_targets(item)
        case MapType(key=key, value=value):
            return (*_type_ref_targets(key), *_type_ref_targets(value))
        case UnionType(variants=variants):
            names: tuple[str, ...] = ()
            for variant in variants:
                names += _type_ref_targets(variant)
            return names
        case ScalarType() | LiteralType():
            return ()
        case _:
            assert_never(neutral)


def _referenced_model_names(model: ObjectModel, res: ir.Resource) -> tuple[str, ...]:
    """Every model name transitively reachable from `model`'s fields via RefType - unwraps
    ListType/MapType/UnionType at any depth, recurses into each referenced ObjectModel's own
    fields. De-duplicated, first-seen order.

    Fixes the M1 bug: a body model's `list<ref<Item>>` (or `oneof<A|B>`) field is now imported for
    a generated test's authored `call` (e.g. ``Widget(items=[Item(...)])``) - previously only a
    DIRECT `ref<...>` field was ever seen (``_body_test_imports`` walked one level by hand).

    A `seen` set of already-discovered names guards a structural cycle (an ``A -> B -> A`` ref
    loop) from infinite recursion - the START model's own name is never seeded into `seen`, so a
    cyclic self-reference is still listed once, the first time it comes back around. For a
    ``Widget{items: list<ref<Item>>}`` where ``Item{v: ref<Leaf>}`` and ``Leaf`` is bare:
    ``_referenced_model_names(widget, res) == ("Item", "Leaf")``.
    """
    names, _seen = _walk_model(model, res, frozenset())
    return names


def _walk_model(
    model: ObjectModel, res: ir.Resource, seen: frozenset[str]
) -> tuple[tuple[str, ...], frozenset[str]]:
    """Fold every field's reachable names left-to-right, threading `seen` so a later field (or a
    later recursion frame) never re-lists a name an earlier one already found."""
    names: tuple[str, ...] = ()
    for field in model.fields:
        found, seen = _walk_type(field.type, res, seen)
        names += found
    return names, seen


def _walk_type(
    neutral: ir.NeutralType, res: ir.Resource, seen: frozenset[str]
) -> tuple[tuple[str, ...], frozenset[str]]:
    """One NeutralType node -> the model names it reaches (+ the updated `seen`).

    ScalarType/LiteralType are terminal (carry no ref). List/Map/Union unwrap into their nested
    type(s) at any depth. A RefType resolves via ``res.model`` (shared-aware post-Task-9) and, for
    an ObjectModel target, recurses into ITS fields; a RootListModel target carries no `.fields` to
    recurse into, so its name is listed but not expanded. A dangling ref (an undeclared target) is
    reported as a friendly ``SpecError`` (the project's fail-loud contract for malformed spec), not
    the bare ``KeyError`` ``res.model`` raises.
    """
    match neutral:
        case RefType(target=target):
            if target in seen:  # cycle guard - already discovered up this walk
                return (), seen
            seen = seen | {target}
            resolved = require_model(
                res, target
            )  # dangling ref -> friendly SpecError, not KeyError
            if isinstance(resolved, ObjectModel):
                nested, seen = _walk_model(resolved, res, seen)
            else:
                nested = ()
            return (target, *nested), seen
        case ListType(item=item):
            return _walk_type(item, res, seen)
        case MapType(key=key, value=value):
            key_names, seen = _walk_type(key, res, seen)
            value_names, seen = _walk_type(value, res, seen)
            return (*key_names, *value_names), seen
        case UnionType(variants=variants):
            names: tuple[str, ...] = ()
            for variant in variants:
                found, seen = _walk_type(variant, res, seen)
                names += found
            return names, seen
        case ScalarType() | LiteralType():
            return (), seen
        case _:
            assert_never(neutral)
