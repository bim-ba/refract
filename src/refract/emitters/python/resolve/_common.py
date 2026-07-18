from __future__ import annotations

import json
from collections import defaultdict
from typing import TYPE_CHECKING

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
