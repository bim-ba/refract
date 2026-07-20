from __future__ import annotations

from typing import TYPE_CHECKING, assert_never

from refract.emitters.ports import Import
from refract.emitters.python.resolve._common import (
    _referenced_model_names,
    render_imports,
    require_model,
)
from refract.emitters.python.views import TestsPageView
from refract.ir import ObjectModel, TestKind

if TYPE_CHECKING:
    from refract import ir
    from refract.emitters.ports import DocComments, EmitContext, Naming, TypeMapper

# Docstring for the require_found empty-response guard (structural - only the 200-empty case,
# tied to the sentinel ``r.login is None`` declared by the read-tool).
_EMPTY_GUARD_DOC = (
    "200 with empty body hits the login-is-None guard (e.g. bad permissions -> blank object)."
)


def _tests_module_doc(res: ir.Resource, ops: tuple[ir.Operation, ...], kinds: set[TestKind]) -> str:
    """Text of the test-module docstring: ``<Domain> /<path[+path...]> resource - <surfaces>,
    HTTP stubbed.`` Path segments are the UNIQUE ``op.path`` values across all tests-bearing ops,
    joined with `` + `` - byte-identical to the prior single-op form when only one op qualifies.
    """
    labels = []
    if TestKind.CLIENT in kinds:
        labels.append("client")
    if TestKind.CLI in kinds:
        labels.append("CLI")
    if kinds & {TestKind.MCP, TestKind.MCP_GUARD}:
        labels.append("MCP")
    surfaces = " + ".join(labels)
    paths = " + ".join(dict.fromkeys(op.path for op in ops))
    return f"{res.domain_title} /{paths} resource - {surfaces}, HTTP stubbed."


def _body_test_imports(
    res: ir.Resource, body: ir.Body, models_module: str, shared_module: str
) -> tuple[Import, ...]:
    """The body model's import, plus every model TRANSITIVELY reachable from its fields via
    RefType - unwrapping ListType/MapType/UnionType at any depth (``_referenced_model_names``),
    not just a directly-nested ``ref<...>`` field.

    A CLIENT-kind test's authored ``call`` constructs the body model literally in Python (e.g.
    ``PriorityCreate(name=LocalizedName(...))`` or, for a `list<ref<Item>>` field,
    ``Widget(items=[Item(...)])``), so every model named in that construction needs its own
    import - at any nesting depth, not one level only. A reachable name that is a SHARED model is
    imported from the per-domain ``shared_module`` (it lives in ``{domain}/shared_models.py``), not
    the resource's local ``models_module``. ``body.model`` itself is never shared - a shared model
    as a body is rejected at plan time - so it always imports from ``models_module``.
    """
    model = require_model(res, body.model)  # dangling body ref -> friendly SpecError, not KeyError
    imports = [Import(models_module, body.model)]
    if isinstance(model, ObjectModel):
        shared_names = {shared.name for shared in res.shared_models}
        for name in _referenced_model_names(model, res):
            if name in shared_names:
                imports.append(Import(shared_module, name))
            else:
                imports.append(Import(models_module, name))
    return tuple(imports)


def _tests_imports(
    res: ir.Resource,
    ops: tuple[ir.Operation, ...],
    ctx: EmitContext,
    kinds: set[TestKind],
    client_class: str,
) -> tuple[str, ...]:
    has_client = TestKind.CLIENT in kinds
    has_cli = TestKind.CLI in kinds
    has_mcp = TestKind.MCP in kinds
    has_mcp_guard = TestKind.MCP_GUARD in kinds

    stdlib: list[str] = []
    if has_mcp:
        stdlib.append("import asyncio")
    if has_cli:
        stdlib.append("import json")

    third_party: list[str] = []
    if has_mcp_guard:
        third_party.append("import pytest")
    third_party.append("import responses")
    if has_mcp or has_mcp_guard:
        third_party.append("from fastmcp import Client")
    if has_mcp_guard:
        third_party.append("from fastmcp.exceptions import ToolError")
    if has_cli:
        third_party.append("from typer.testing import CliRunner")

    first_party: list[str] = []
    if has_cli:
        first_party.append("import ycli.cli.app as cli")
    if has_mcp:
        first_party.append("from ycli.mcp import mcp as root_mcp")
    if has_client:
        first_party.append(f"from {ctx.package_root}.client import {client_class}")
    if has_mcp_guard:
        first_party.append(
            f"from {ctx.package_root}.{res.resource} import mcp as {res.resource}_mcp_module"
        )
    models_module = f"{ctx.package_root}.{res.resource}.models"
    shared_module = f"{ctx.package_root}.shared_models"
    model_imports: list[Import] = []
    for op in ops:
        has_client_case = any(case.kind is TestKind.CLIENT for case in op.tests)
        if has_client_case and op.response_model:
            model_imports.append(Import(models_module, op.response_model))
        if has_client_case and op.body is not None:
            model_imports.extend(_body_test_imports(res, op.body, models_module, shared_module))
    first_party.extend(render_imports(tuple(model_imports)))
    return (*stdlib, *third_party, *first_party)


def _tests_constants(
    res: ir.Resource, op: ir.Operation, ctx: EmitContext, kinds: set[TestKind]
) -> tuple[str, ...]:
    """Module constants: ``_URL_<op.name>`` (always), ``_PAYLOAD_<op.name>`` (client case),
    ``_runner`` (cli case, shared - not op-suffixed; harmlessly re-assigned to the same value if
    more than one op has CLI tests).

    ``_URL_<op.name>`` / ``_PAYLOAD_<op.name>`` are ALWAYS per-op suffixed - one rule, applied
    even when a single op has tests - so two tests-bearing ops never collide on the same
    constant name. Built from ``ctx.config.server.base_url`` (``base_url`` left ``Resource`` for
    ``ClientConfig``). ``response_json`` is authored data; ``!r`` produces a single-quote repr,
    which ruff normalizes to double-quote. No type lowering is needed."""
    if ctx.config is None:
        raise ValueError("tests surface requires ClientConfig (base_url)")
    lines = [f'_URL_{op.name} = "{ctx.config.server.base_url}/{op.path}"']
    # `_stub` references `_PAYLOAD_<op>` for EVERY non-guard case (client/cli/mcp) - only the
    # MCP_GUARD case inlines its own `{}`. So the payload constant must exist whenever any
    # non-guard case does, not merely when a CLIENT case does: a cli-only or mcp-only tested op
    # would otherwise reference an undefined name. Prefer the CLIENT case's fixture when present
    # (keeps the shared per-op payload deterministic and byte-identical on the current corpus),
    # else fall back to the first non-guard case.
    non_guard = [case for case in op.tests if case.kind is not TestKind.MCP_GUARD]
    client = [case for case in non_guard if case.kind is TestKind.CLIENT]
    payload_case = client[0] if client else non_guard[0] if non_guard else None
    if payload_case is not None:
        lines.append(f"_PAYLOAD_{op.name} = {payload_case.response_json!r}")
    if TestKind.CLI in kinds:
        lines.append("_runner = CliRunner()")
    return tuple(lines)


def _stub(op: ir.Operation, case: ir.TestCase) -> str:
    """The ``responses.add(...)`` line (``_PAYLOAD_<op.name>`` for reads, inline ``{}`` for guard
    cases), stubbing the per-op ``_URL_<op.name>`` constant."""
    json_arg = (
        repr(case.response_json) if case.kind is TestKind.MCP_GUARD else f"_PAYLOAD_{op.name}"
    )
    return (
        f"    responses.add(responses.{case.http_method}, _URL_{op.name}, "
        f"json={json_arg}, status={case.status})"
    )


def _asserts(case: ir.TestCase) -> list[str]:
    """One ``assert <expr>`` line per authored assert."""
    return [f"    assert {expr}" for expr in case.asserts]


def _client_test(res: ir.Resource, op: ir.Operation, case: ir.TestCase) -> str:
    """Client case - chain the client call, then the authored asserts."""
    lines = [
        "@responses.activate",
        f"def test_{case.name}(creds):",
        _stub(op, case),
        f"    {res.resource} = {case.call}",
        *_asserts(case),
    ]
    return "\n".join(lines)


def _cli_test(res: ir.Resource, op: ir.Operation, case: ir.TestCase) -> str:
    """CLI case - ``CliRunner`` json-invoke of the ``<domain> <resource> <command>`` command."""
    if op.cli is None:  # resolve_tests only calls this for cli-kind cases - fail loud otherwise
        raise ValueError(f"{op.name}: operation has no cli facet")
    argv = ", ".join(
        f'"{token}"' for token in ("--format", "json", res.domain, res.resource, op.cli.name)
    )
    lines = [
        "@responses.activate",
        f"def test_{case.name}(creds):",
        _stub(op, case),
        f"    res = _runner.invoke(cli.app, [{argv}])",
        *_asserts(case),
    ]
    return "\n".join(lines)


def _mcp_test(res: ir.Resource, op: ir.Operation, case: ir.TestCase) -> str:
    """MCP case - call the root-composed tool through ``root_mcp`` under ``asyncio.run``."""
    if op.mcp is None:  # resolve_tests only calls this for mcp-kind cases - fail loud otherwise
        raise ValueError(f"{op.name}: operation has no mcp facet")
    root_tool = f"{res.domain}_{op.mcp.name}"
    lines = [
        "@responses.activate",
        f"def test_{case.name}(creds):",
        _stub(op, case),
        "",
        "    async def go():",
        "        async with Client(root_mcp) as client:",
        f'            return await client.call_tool("{root_tool}", {{}})',
        "",
        "    result = asyncio.run(go())",
        *_asserts(case),
    ]
    return "\n".join(lines)


def _guard_test(res: ir.Resource, op: ir.Operation, case: ir.TestCase) -> str:
    """MCP guard case - the resource-local tool must raise ``ToolError`` (no asserts)."""
    if op.mcp is None:  # resolve_tests only calls this for guard cases - fail loud otherwise
        raise ValueError(f"{op.name}: operation has no mcp facet")
    lines = ["@responses.activate", f"async def test_{case.name}(creds):"]
    if case.status == 200:
        lines.append(f'    """{_EMPTY_GUARD_DOC}"""')
    lines += [
        _stub(op, case),
        f"    async with Client({res.resource}_mcp_module.mcp) as client:",
        "        with pytest.raises(ToolError):",
        f'            await client.call_tool("{op.mcp.name}", {{}})',
    ]
    return "\n".join(lines)


def _test_block(res: ir.Resource, op: ir.Operation, case: ir.TestCase) -> str:
    """Dispatch one authored ``TestCase`` to its per-kind renderer (identity on ``TestKind``)."""
    match case.kind:
        case TestKind.CLIENT:
            return _client_test(res, op, case)
        case TestKind.CLI:
            return _cli_test(res, op, case)
        case TestKind.MCP:
            return _mcp_test(res, op, case)
        case TestKind.MCP_GUARD:
            return _guard_test(res, op, case)
        case _:
            assert_never(case.kind)


def resolve_tests(
    res: ir.Resource,
    ctx: EmitContext,
    naming: Naming,
    type_mapper: TypeMapper,
    doc_comments: DocComments,
) -> TestsPageView:
    """IR -> TestsPageView. Iterates ALL tests-bearing operations (not just the first), unions
    their ``kinds`` (a set of ``TestKind``) to gate imports/module-doc, and renders one leaf per
    case across every such op. Constants are collected per op - ``_tests_constants`` always
    suffixes ``_URL``/``_PAYLOAD`` with ``op.name``, so only the shared, non-suffixed
    ``_runner = CliRunner()`` line could ever repeat (harmless: re-assigning the same value).
    ``type_mapper`` is unused here - all TestCase values are authored."""
    tested = tuple(operation for operation in res.operations if operation.tests)
    kinds = {case.kind for op in tested for case in op.tests}
    client_class = naming.class_name(res.domain, "Client")
    constants: list[str] = []
    tests: list[str] = []
    for op in tested:
        constants.extend(_tests_constants(res, op, ctx, {case.kind for case in op.tests}))
        tests.extend(_test_block(res, op, case) for case in op.tests)
    return TestsPageView(
        doc_block=doc_comments.render(_tests_module_doc(res, tested, kinds), ""),
        header_lines=("from __future__ import annotations",),
        import_lines=_tests_imports(res, tested, ctx, kinds, client_class),
        constants=tuple(constants),
        tests=tuple(tests),
    )
