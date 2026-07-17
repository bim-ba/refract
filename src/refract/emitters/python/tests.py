"""Emit ``test_<resource>.py`` — the strategy-driven auto-suite (client + CLI + MCP, HTTP stubbed).

Reproduces ycli's hand-written ``tests/yandex/<domain>/test_<resource>.py`` for the ``me`` walking
skeleton: one ``responses``-stubbed test per authored surface (client / cli / mcp) plus the MCP
guard tests — a 401 auth guard and, when the read tool declares a ``require_found`` empty-result
guard, a 200-empty-body guard. Each surface test's fixtures (``_PAYLOAD``, status, path) and asserts
are authored data from the spec's ``tests:`` list; the guard bodies (``pytest.raises(ToolError)``)
are structural — rendered from ``kind == "mcp_guard"`` + status, not from authored asserts. The
imports and module constants are emitted only for the surfaces the cases actually exercise.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from refract.emitters.python._common import domain_client_class
from refract.format import ruff_format

if TYPE_CHECKING:
    from refract import ir

# The require_found empty-response guard's docstring (structural — the 200-empty case only, keyed
# on the ``r.login is None`` sentinel the read tool declares).
_EMPTY_GUARD_DOC = (
    "200 with empty body hits the login-is-None guard (e.g. bad permissions → blank object)."
)


def _module_doc(res: ir.Resource, op: ir.Operation, kinds: set[str]) -> str:
    """The test-module docstring — ``<Domain> /<path> resource — <surfaces>, HTTP stubbed.``"""
    labels = []
    if "client" in kinds:
        labels.append("client")
    if "cli" in kinds:
        labels.append("CLI")
    if kinds & {"mcp", "mcp_guard"}:
        labels.append("MCP")
    surfaces = " + ".join(labels)
    return f'"""{res.domain_title} /{op.path} resource — {surfaces}, HTTP stubbed."""'


def _imports(
    res: ir.Resource, op: ir.Operation, kinds: set[str]
) -> tuple[list[str], list[str], list[str]]:
    """The (stdlib, third-party, first-party) import blocks, isort-ordered, gated on surfaces."""
    has_client = "client" in kinds
    has_cli = "cli" in kinds
    has_mcp = "mcp" in kinds
    has_mcp_guard = "mcp_guard" in kinds

    stdlib = []
    if has_mcp:
        stdlib.append("import asyncio")
    if has_cli:
        stdlib.append("import json")

    third_party = []
    if has_mcp_guard:
        third_party.append("import pytest")
    third_party.append("import responses")
    if has_mcp or has_mcp_guard:
        third_party.append("from fastmcp import Client")
    if has_mcp_guard:
        third_party.append("from fastmcp.exceptions import ToolError")
    if has_cli:
        third_party.append("from typer.testing import CliRunner")

    first_party = []
    if has_cli:
        first_party.append("import ycli.cli.app as cli")
    if has_mcp:
        first_party.append("from ycli.mcp import mcp as root_mcp")
    if has_client:
        first_party.append(
            f"from ycli.yandex.{res.domain}.client import {domain_client_class(res)}"
        )
    if has_mcp_guard:
        first_party.append(
            f"from ycli.yandex.{res.domain}.{res.resource} import mcp as {res.resource}_mcp_module"
        )
    if has_client:
        first_party.append(
            f"from ycli.yandex.{res.domain}.{res.resource}.models import {op.response_model}"
        )
    return stdlib, third_party, first_party


def _constants(res: ir.Resource, op: ir.Operation, kinds: set[str]) -> list[str]:
    """The module constants — ``_URL`` (always), ``_PAYLOAD`` (client case), ``_runner`` (cli)."""
    lines = [f'_URL = "{res.base_url}/{op.path}"']
    if "client" in kinds:
        client_case = next(case for case in op.tests if case.kind == "client")
        lines.append(f"_PAYLOAD = {client_case.response_json!r}")
    if "cli" in kinds:
        lines.append("_runner = CliRunner()")
    return lines


def _stub(case: ir.TestCase) -> str:
    """The ``responses.add(...)`` stub line (``_PAYLOAD`` for reads, inline ``{}`` for guards)."""
    json_arg = repr(case.response_json) if case.kind == "mcp_guard" else "_PAYLOAD"
    return (
        f"    responses.add(responses.{case.http_method}, _URL, "
        f"json={json_arg}, status={case.status})"
    )


def _asserts(case: ir.TestCase) -> list[str]:
    """One ``assert <expr>`` line per authored assert string."""
    return [f"    assert {expr}" for expr in case.asserts]


def _client_test(res: ir.Resource, case: ir.TestCase) -> list[str]:
    """The client surface test — bind the chained client call, then the authored asserts."""
    return [
        "@responses.activate",
        f"def test_{case.name}(creds):",
        _stub(case),
        f"    {res.resource} = {case.call}",
        *_asserts(case),
    ]


def _cli_test(res: ir.Resource, op: ir.Operation, case: ir.TestCase) -> list[str]:
    """The CLI surface test — a ``CliRunner`` json invoke of ``<domain> <resource> <command>``."""
    assert op.cli is not None  # every me operation carries a cli facet
    argv = ", ".join(
        f'"{token}"' for token in ("--format", "json", res.domain, res.resource, op.cli.name)
    )
    return [
        "@responses.activate",
        f"def test_{case.name}(creds):",
        _stub(case),
        f"    res = _runner.invoke(cli.app, [{argv}])",
        *_asserts(case),
    ]


def _mcp_test(res: ir.Resource, op: ir.Operation, case: ir.TestCase) -> list[str]:
    """The MCP surface test — call the root-composed tool over ``root_mcp`` via ``asyncio.run``."""
    assert op.mcp is not None  # every me operation carries an mcp facet
    root_tool = f"{res.domain}_{op.mcp.name}"
    return [
        "@responses.activate",
        f"def test_{case.name}(creds):",
        _stub(case),
        "",
        "    async def go():",
        "        async with Client(root_mcp) as client:",
        f'            return await client.call_tool("{root_tool}", {{}})',
        "",
        "    result = asyncio.run(go())",
        *_asserts(case),
    ]


def _guard_test(res: ir.Resource, op: ir.Operation, case: ir.TestCase) -> list[str]:
    """An MCP guard test — the resource-local tool must raise ``ToolError`` (structural)."""
    assert op.mcp is not None  # every me operation carries an mcp facet
    lines = [
        "@responses.activate",
        f"async def test_{case.name}(creds):",
    ]
    if case.status == 200:
        lines.append(f'    """{_EMPTY_GUARD_DOC}"""')
    lines += [
        _stub(case),
        f"    async with Client({res.resource}_mcp_module.mcp) as client:",
        "        with pytest.raises(ToolError):",
        f'            await client.call_tool("{op.mcp.name}", {{}})',
    ]
    return lines


def _test_block(res: ir.Resource, op: ir.Operation, case: ir.TestCase) -> list[str]:
    """Dispatch one authored ``TestCase`` to its per-kind renderer."""
    if case.kind == "client":
        return _client_test(res, case)
    if case.kind == "cli":
        return _cli_test(res, op, case)
    if case.kind == "mcp":
        return _mcp_test(res, op, case)
    return _guard_test(res, op, case)  # mcp_guard


def emit(res: ir.Resource) -> str:
    """Render the whole ``test_<resource>.py`` for ``res`` (ruff-formatted)."""
    op = next(operation for operation in res.operations if operation.tests)
    kinds = {case.kind for case in op.tests}
    stdlib, third_party, first_party = _imports(res, op, kinds)
    out = [
        _module_doc(res, op, kinds),
        "",
        "from __future__ import annotations",
        "",
        *stdlib,
        "",
        *third_party,
        "",
        *first_party,
        "",
        *_constants(res, op, kinds),
    ]
    for case in op.tests:
        out += ["", "", *_test_block(res, op, case)]
    rendered = "\n".join(out).rstrip() + "\n"
    return ruff_format(rendered)
