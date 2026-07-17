from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, assert_never

from refract.emitters.api import Import
from refract.emitters.python.views import (
    ClientPageView,
    CliPageView,
    McpPageView,
    ModelsPageView,
    RequestsPageView,
    TestsPageView,
)
from refract.ir import ObjectModel, RootListModel, Safety, TestKind

if TYPE_CHECKING:
    from refract import ir
    from refract.emitters.api import Docstrings, EmitContext, Naming, TypeMapper


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


def param_decl(param: ir.Param, type_mapper: TypeMapper) -> tuple[str, tuple[Import, ...]]:
    """Render one parameter declaration `name: Type` (+ ` = default`) and its imports."""
    rt = type_mapper.render(param.type, optional=param.optional)
    default = param.default if param.default is not None else type_mapper.null_default(
        param.type, optional=param.optional
    )
    decl = f"{param.name}: {rt.text}"
    if default is not None:
        decl = f"{decl} = {default}"
    return decl, rt.imports


def path_expr(path: str) -> str:
    """Emit an f-string when the path has `{placeholders}`, else a plain string literal."""
    return f'f"{path}"' if "{" in path else f'"{path}"'


def _request_doc(op: ir.Operation, *, write: bool) -> str:
    if write:
        return f"``{op.method} /{op.path}`` - {op.name} request from a typed body."
    return f"``{op.method} /{op.path}`` -> {op.response_model} request builder."


def _request_function(
    op: ir.Operation, naming: Naming, type_mapper: TypeMapper, docstrings: Docstrings
) -> tuple[str, list[Import]]:
    body = op.body                       # write iff not None; narrowed to ir.Body below
    imports: list[Import] = []
    positional: list[str] = []
    for p in op.params:
        if p.loc == "path":
            decl, imp = param_decl(p, type_mapper)
            positional.append(decl)
            imports += imp
    if body is not None:                 # write: typed body positional + `.models` import
        positional.append(f"body: {body.model}")
        imports.append(Import(".models", body.model))
    keyword_only: list[str] = []
    for p in op.params:
        if p.loc == "query":
            decl, imp = param_decl(p, type_mapper)
            keyword_only.append(decl)
            imports += imp
    params = signature_params(tuple(positional), tuple(keyword_only))
    response_model = op.response_model
    if response_model is None:  # 204/no-body ops aren't in the walking skeleton yet - fail loud
        raise ValueError(f"{op.name}: operation has no response model (not yet supported)")
    imports.append(Import(".models", response_model))
    function_name = naming.module_function(op.name)
    param_list = ", ".join(params)
    sig = f"def {function_name}({param_list}) -> Request[{response_model}]:"

    kwargs = [f'method="{op.method}"', f"path={path_expr(op.path)}"]
    query_items = [f'"{p.alias or p.name}": {p.name}' for p in op.params if p.loc == "query"]
    if query_items:
        kwargs.append("query={" + ", ".join(query_items) + "}")
    if body is not None:                 # render model_dump flags straight off ir.Body (no .dump)
        kwargs.append(
            f"json_body=body.model_dump(by_alias={body.by_alias}, exclude_none={body.omit_none})"
        )
    kwargs.append(f"response_model={response_model}")

    doc = docstrings.render(_request_doc(op, write=body is not None), "    ")
    lines = [sig, *doc, f"    return Request({', '.join(kwargs)})"]
    return "\n".join(lines), imports


def resolve_requests(
    res: ir.Resource,
    ctx: EmitContext,
    naming: Naming,
    type_mapper: TypeMapper,
    docstrings: Docstrings,
) -> RequestsPageView:
    imports: list[Import] = [Import(f"{ctx.package_root}.runtime", "Request")]
    functions: list[str] = []
    for op in res.operations:
        text, fimports = _request_function(op, naming, type_mapper, docstrings)
        functions.append(text)
        imports += fimports
    module_doc = res.module_docs.requests or (
        f"Request builders for {res.domain_title} {res.resource} - "
        "the single HTTP contract (sans-I/O)."
    )
    return RequestsPageView(
        doc_block=docstrings.render(module_doc, ""),
        import_lines=render_imports(tuple(imports)),
        functions=tuple(functions),
    )


def _client_method(
    op: ir.Operation, naming: Naming, type_mapper: TypeMapper, docstrings: Docstrings
) -> tuple[str, list[Import]]:
    """One thin-sugar method leaf: `<op.name>` -> `return self._session.send(_requests.<fn>(...))`.

    Built at module nesting (docstring/body at 4 spaces), then indented one level to sit inside
    the class. Method name is verbatim `op.name`; the builder call uses `module_function(op.name)`
    (the shadow guard, so `list` -> `_requests.list_`). Docstring is the FULL `op.documentation`.
    """
    body = op.body                       # write iff not None (разд. D; narrowed to ir.Body below)
    imports: list[Import] = []
    positional: list[str] = ["self"]
    call_args: list[str] = []
    for p in op.params:
        if p.loc == "path":
            decl, imp = param_decl(p, type_mapper)
            positional.append(decl)
            call_args.append(p.name)
            imports += imp
    if body is not None:                 # write: typed body positional, forwarded through unchanged
        positional.append(f"body: {body.model}")
        call_args.append("body")
        imports.append(Import(".models", body.model))
    keyword_only: list[str] = []
    for p in op.params:
        if p.loc == "query":
            decl, imp = param_decl(p, type_mapper)
            keyword_only.append(decl)
            call_args.append(f"{p.name}={p.name}")
            imports += imp
    params = signature_params(tuple(positional), tuple(keyword_only))
    response_model = op.response_model
    if response_model is None:  # 204/no-body ops aren't in the walking skeleton yet - fail loud
        raise ValueError(f"{op.name}: operation has no response model (not yet supported)")
    imports.append(Import(".models", response_model))
    sig = f"def {op.name}({', '.join(params)}) -> {response_model}:"
    call = f"_requests.{naming.module_function(op.name)}({', '.join(call_args)})"
    doc = docstrings.render(op.documentation, "    ")
    body_lines = (sig, *doc, f"    return self._session.send({call})")
    return "\n".join(indent_lines(body_lines, "    ")), imports


def resolve_client(
    res: ir.Resource,
    ctx: EmitContext,
    naming: Naming,
    type_mapper: TypeMapper,
    docstrings: Docstrings,
) -> ClientPageView:
    base_class = naming.class_name(res.domain, "Resource")
    imports: list[Import] = [
        Import(f"{ctx.package_root}.base", base_class),
        Import(".", "_requests"),
    ]
    methods: list[str] = []
    for op in res.operations:
        text, method_imports = _client_method(op, naming, type_mapper, docstrings)
        methods.append(text)
        imports += method_imports
    return ClientPageView(
        doc_block=docstrings.render(res.module_docs.client, ""),
        import_lines=render_imports(tuple(imports)),
        class_header=f"class {naming.class_name(res.resource, 'Client')}({base_class}):",
        class_doc_lines=docstrings.render(res.module_docs.client_class, "    "),
        methods=tuple(methods),
    )


def _shared_models_module(ctx: EmitContext) -> str:
    """The shared base module (``APIModel``/``require_found``) - one level above the domain.

    ``ycli.yandex.tracker`` -> ``ycli.yandex.models`` (derived, not hardcoded)."""
    return f"{ctx.package_root.rsplit('.', 1)[0]}.models"


def _model_field(field: ir.Field, type_mapper: TypeMapper) -> tuple[str, list[Import]]:
    """One model field line: ``name: Type = default`` or ``Field(...)`` for a described field.

    The type renders from NeutralType via TypeMapper (the key port shift); the default is the
    explicit ``field.default`` or, absent that, ``type_mapper.null_default(...)`` (implied-null).
    A described field renders ``Field(...)``: optional carries ``default=<default>`` before
    ``description=``, required carries only ``description=``. Long calls stay one line - ruff
    wraps them.
    """
    rendered = type_mapper.render(field.type, optional=field.optional)
    imports = list(rendered.imports)
    default = (
        field.default
        if field.default is not None
        else type_mapper.null_default(field.type, optional=field.optional)
    )
    if not field.description:
        return f"    {field.name}: {rendered.text} = {default}", imports
    arguments: list[str] = []
    if default is not None:
        arguments.append(f"default={default}")
    arguments.append(f'description="{field.description}"')
    return f"    {field.name}: {rendered.text} = Field({', '.join(arguments)})", imports


def _model_class(
    model: ir.Model, type_mapper: TypeMapper, docstrings: Docstrings
) -> tuple[str, list[Import]]:
    """The finished source for one model class - dispatches over the ``Model`` union.

    ``RootListModel`` -> ``RootModel[list[Item]]`` with just a docstring; ``ObjectModel`` ->
    docstring, blank line, then fields. ``model.item`` is the model name (a str, not a
    NeutralType) and renders verbatim. ``assert_never`` keeps the union exhaustive - a new
    variant is a type error, not a silent no-op.
    """
    match model:
        case RootListModel():
            lines = [
                f"class {model.name}(RootModel[list[{model.item}]]):",
                *docstrings.render(model.documentation, "    "),
            ]
            return "\n".join(lines), []
        case ObjectModel():
            lines = [f"class {model.name}(APIModel):"]
            lines += docstrings.render(model.documentation, "    ")
            lines.append("")
            imports: list[Import] = []
            for field in model.fields:
                decl, field_imports = _model_field(field, type_mapper)
                lines.append(decl)
                imports += field_imports
            return "\n".join(lines), imports
        case _:
            assert_never(model)


def resolve_models(
    res: ir.Resource,
    ctx: EmitContext,
    naming: Naming,
    type_mapper: TypeMapper,
    docstrings: Docstrings,
) -> ModelsPageView:
    """IR -> ModelsPageView: module docstring, imports (APIModel + pydantic + those collected
    from types), finished classes. ``APIModel`` is always imported (as in the previous emitter).
    """
    imports: list[Import] = [Import(_shared_models_module(ctx), "APIModel")]
    if any(
        field.description
        for model in res.models
        if isinstance(model, ObjectModel)
        for field in model.fields
    ):
        imports.append(Import("pydantic", "Field"))
    if any(isinstance(model, RootListModel) for model in res.models):
        imports.append(Import("pydantic", "RootModel"))
    classes: list[str] = []
    for model in res.models:
        text, class_imports = _model_class(model, type_mapper, docstrings)
        classes.append(text)
        imports += class_imports
    return ModelsPageView(
        doc_block=docstrings.render(res.module_docs.models, ""),
        header_lines=("from __future__ import annotations",),
        import_lines=render_imports(tuple(imports)),
        classes=tuple(classes),
    )


_GROUP_DOC = "Group anchor - forces subcommand dispatch (no eager DI, so --help stays cred-free)."


def _cli_command(res: ir.Resource, op: ir.Operation, docstrings: Docstrings) -> str:
    """The finished text for one passthrough ``@app.command()`` leaf.

    Param-less (mirrors the current `me` emitter): resolves ``AppContext`` and forwards the call
    to ``app_ctx.<domain>.<resource>.<op>()`` through ``Serializer.serialize``. The command name
    is author-controlled via ``op.cli.name`` (not necessarily ``op.name``).
    """
    meta = op.cli
    if meta is None:  # resolve_cli only calls this for cli-faceted ops - fail loud if that changes
        raise ValueError(f"{op.name}: operation has no cli facet")
    call = f"app_ctx.{res.domain}.{res.resource}.{op.name}()"
    lines = [
        "@app.command()",
        f"def {meta.name}(ctx: typer.Context) -> None:",
        *docstrings.render(meta.documentation, "    "),
        "    app_ctx = AppContext.from_typer_context(ctx)",
        f"    Serializer.serialize({call}, app_ctx.strategy, app_ctx.console)",
    ]
    return "\n".join(lines)


def resolve_cli(
    res: ir.Resource,
    ctx: EmitContext,
    naming: Naming,
    type_mapper: TypeMapper,
    docstrings: Docstrings,
) -> CliPageView:
    """IR -> CliPageView: module docstring, fixed imports, body = group+callback then commands."""
    group_block = "\n".join(
        [
            f'app = typer.Typer(name="{res.resource}", '
            f'help="{res.module_docs.cli_group_help}", no_args_is_help=True)',
            "",
            "",
            "@app.callback()",
            "def _group() -> None:",
            f'    """{_GROUP_DOC}"""',
        ]
    )
    blocks = [group_block]
    for op in res.operations:
        if op.cli is not None:
            blocks.append(_cli_command(res, op, docstrings))
    return CliPageView(
        doc_block=docstrings.render(res.module_docs.cli, ""),
        header_lines=("from __future__ import annotations",),
        import_lines=(
            "import typer",
            "from ycli.cli.context import AppContext",
            "from ycli.cli.output import Serializer",
        ),
        blocks=tuple(blocks),
    )


def _tags_symbol(safety: Safety) -> str:
    """The tags constant for a safety class (reads: ``TAGS``; writes: ``WRITE_TAGS``)."""
    return "TAGS" if safety is Safety.RO else "WRITE_TAGS"


def _mcp_signature(
    res: ir.Resource, op: ir.Operation, naming: Naming, type_mapper: TypeMapper
) -> tuple[list[str], list[Import]]:
    """Tool-function parameters in order: path, typed ``body``, query, then the DI client.

    Path/query go through ``param_decl`` (TypeMapper) - the previous emitter took the already
    prose-rendered ``param.type``. Parameters stay flat (not keyword-only): fastmcp reads them
    as ordinary arguments."""
    parameters: list[str] = []
    imports: list[Import] = []
    for param in op.params:
        if param.loc == "path":
            decl, param_imports = param_decl(param, type_mapper)
            parameters.append(decl)
            imports += param_imports
    if op.body is not None:
        parameters.append(f"body: {op.body.model}")
    for param in op.params:
        if param.loc == "query":
            decl, param_imports = param_decl(param, type_mapper)
            parameters.append(decl)
            imports += param_imports
    parameters.append(
        f"client: {naming.class_name(res.domain, 'Client')} = Depends({res.domain}_client)"
    )
    return parameters, imports


def _mcp_call_args(op: ir.Operation) -> str:
    """Arguments forwarded to the client call: path, ``body``, then keyword query."""
    arguments = [param.name for param in op.params if param.loc == "path"]
    if op.body is not None:
        arguments.append("body")
    arguments += [f"{param.name}={param.name}" for param in op.params if param.loc == "query"]
    return ", ".join(arguments)


def _mcp_tool(
    res: ir.Resource,
    op: ir.Operation,
    naming: Naming,
    type_mapper: TypeMapper,
    docstrings: Docstrings,
) -> tuple[str, list[Import]]:
    """The finished text for one ``@mcp.tool`` function, forwarding into the client (with a
    guard when ``require_found`` is declared).

    The def name is ``naming.module_function`` (``list`` -> ``list_``). The safety symbol goes
    into the generated code as ``meta.safety.value`` (the raw ``"RO"``/``"WRITE"``/...). The
    guard is formatted as one logical ``require_found(...)`` call - ruff wraps it to match the
    golden multi-line form."""
    meta = op.mcp
    if meta is None:  # resolve_mcp only calls this for mcp-faceted ops - fail loud if that changes
        raise ValueError(f"{op.name}: operation has no mcp facet")
    annotations = f'{{**{meta.safety.value}, "title": "{meta.title}"}}'
    decorator = (
        f'@mcp.tool(name="{meta.name}", annotations={annotations}, '
        f"tags={_tags_symbol(meta.safety)})"
    )
    parameters, imports = _mcp_signature(res, op, naming, type_mapper)
    signature = (
        f"def {naming.module_function(op.name)}({', '.join(parameters)}) -> {op.response_model}:"
    )
    call = f"client.{res.resource}.{op.name}({_mcp_call_args(op)})"
    guard = meta.require_found
    if guard is None:
        body = [f"    return {call}"]
    else:
        body = [
            f"    result = {call}",
            "    return require_found("
            f"result, sentinel=lambda r: {guard.sentinel}, "
            f'message="{guard.message}")',
        ]
    lines = [decorator, signature, *docstrings.render(meta.documentation, "    "), *body]
    return "\n".join(lines), imports


def resolve_mcp(
    res: ir.Resource,
    ctx: EmitContext,
    naming: Naming,
    type_mapper: TypeMapper,
    docstrings: Docstrings,
) -> McpPageView:
    """IR -> McpPageView: module docstring, imports (fastmcp + package_root-domain modules +
    those collected from types), ``mcp = FastMCP(...)`` plus the finished tools. Iterates only
    the operations carrying an mcp facet. ``meta.safety.value`` is the raw safety-symbol name
    (StrEnum -> str) used for the ``dependencies`` import."""
    dependencies_module = f"{ctx.package_root}.dependencies"
    models_module = f"{ctx.package_root}.{res.resource}.models"
    imports: list[Import] = [
        Import("fastmcp", "FastMCP"),
        Import("fastmcp.dependencies", "Depends"),
        Import(f"{ctx.package_root}.client", naming.class_name(res.domain, "Client")),
        Import(dependencies_module, f"{res.domain}_client"),
    ]
    tools: list[str] = []
    for op in res.operations:
        meta = op.mcp
        if meta is None:
            continue
        imports.append(Import(dependencies_module, meta.safety.value))
        imports.append(Import(dependencies_module, _tags_symbol(meta.safety)))
        if op.response_model:
            imports.append(Import(models_module, op.response_model))
        if op.body is not None:
            imports.append(Import(models_module, op.body.model))
        if meta.require_found is not None:
            imports.append(Import(_shared_models_module(ctx), "require_found"))
        text, tool_imports = _mcp_tool(res, op, naming, type_mapper, docstrings)
        tools.append(text)
        imports += tool_imports
    return McpPageView(
        doc_block=docstrings.render(res.module_docs.mcp, ""),
        import_lines=render_imports(tuple(imports)),
        server_line=f'mcp = FastMCP("{res.module_docs.mcp_server}")',
        tools=tuple(tools),
    )


# Docstring for the require_found empty-response guard (structural - only the 200-empty case,
# tied to the sentinel ``r.login is None`` declared by the read-tool).
_EMPTY_GUARD_DOC = (
    "200 with empty body hits the login-is-None guard (e.g. bad permissions -> blank object)."
)


def _tests_module_doc(res: ir.Resource, op: ir.Operation, kinds: set[TestKind]) -> str:
    """Text of the test-module docstring: ``<Domain> /<path> resource - <surfaces>, stubbed.``"""
    labels = []
    if TestKind.CLIENT in kinds:
        labels.append("client")
    if TestKind.CLI in kinds:
        labels.append("CLI")
    if kinds & {TestKind.MCP, TestKind.MCP_GUARD}:
        labels.append("MCP")
    surfaces = " + ".join(labels)
    return f"{res.domain_title} /{op.path} resource - {surfaces}, HTTP stubbed."


def _tests_imports(
    res: ir.Resource, op: ir.Operation, ctx: EmitContext, kinds: set[TestKind], client_class: str
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
    if has_client:
        first_party.append(
            f"from {ctx.package_root}.{res.resource}.models import {op.response_model}"
        )
    return (*stdlib, *third_party, *first_party)


def _tests_constants(
    res: ir.Resource, op: ir.Operation, ctx: EmitContext, kinds: set[TestKind]
) -> tuple[str, ...]:
    """Module constants: ``_URL`` (always), ``_PAYLOAD`` (client case), ``_runner`` (cli case).

    ``_URL`` is built from ``ctx.config.server.base_url`` (``base_url`` left ``Resource`` for
    ``ClientConfig``). ``response_json`` is authored data; ``!r`` produces a single-quote repr,
    which ruff normalizes to double-quote (matching the golden). No type lowering is needed."""
    if ctx.config is None:
        raise ValueError("tests surface requires ClientConfig (base_url)")
    lines = [f'_URL = "{ctx.config.server.base_url}/{op.path}"']
    if TestKind.CLIENT in kinds:
        client_case = next(case for case in op.tests if case.kind is TestKind.CLIENT)
        lines.append(f"_PAYLOAD = {client_case.response_json!r}")
    if TestKind.CLI in kinds:
        lines.append("_runner = CliRunner()")
    return tuple(lines)


def _stub(case: ir.TestCase) -> str:
    """The ``responses.add(...)`` line (``_PAYLOAD`` for reads, inline ``{}`` for guard cases)."""
    json_arg = repr(case.response_json) if case.kind is TestKind.MCP_GUARD else "_PAYLOAD"
    return (
        f"    responses.add(responses.{case.http_method}, _URL, "
        f"json={json_arg}, status={case.status})"
    )


def _asserts(case: ir.TestCase) -> list[str]:
    """One ``assert <expr>`` line per authored assert."""
    return [f"    assert {expr}" for expr in case.asserts]


def _client_test(res: ir.Resource, case: ir.TestCase) -> str:
    """Client case - chain the client call, then the authored asserts."""
    lines = [
        "@responses.activate",
        f"def test_{case.name}(creds):",
        _stub(case),
        f"    {res.resource} = {case.call}",
        *_asserts(case),
    ]
    return "\n".join(lines)


def _cli_test(res: ir.Resource, op: ir.Operation, case: ir.TestCase) -> str:
    """CLI case - ``CliRunner`` json-invoke of the ``<domain> <resource> <command>`` command."""
    assert op.cli is not None
    argv = ", ".join(
        f'"{token}"' for token in ("--format", "json", res.domain, res.resource, op.cli.name)
    )
    lines = [
        "@responses.activate",
        f"def test_{case.name}(creds):",
        _stub(case),
        f"    res = _runner.invoke(cli.app, [{argv}])",
        *_asserts(case),
    ]
    return "\n".join(lines)


def _mcp_test(res: ir.Resource, op: ir.Operation, case: ir.TestCase) -> str:
    """MCP case - call the root-composed tool through ``root_mcp`` under ``asyncio.run``."""
    assert op.mcp is not None
    root_tool = f"{res.domain}_{op.mcp.name}"
    lines = [
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
    return "\n".join(lines)


def _guard_test(res: ir.Resource, op: ir.Operation, case: ir.TestCase) -> str:
    """MCP guard case - the resource-local tool must raise ``ToolError`` (no asserts)."""
    assert op.mcp is not None
    lines = ["@responses.activate", f"async def test_{case.name}(creds):"]
    if case.status == 200:
        lines.append(f'    """{_EMPTY_GUARD_DOC}"""')
    lines += [
        _stub(case),
        f"    async with Client({res.resource}_mcp_module.mcp) as client:",
        "        with pytest.raises(ToolError):",
        f'            await client.call_tool("{op.mcp.name}", {{}})',
    ]
    return "\n".join(lines)


def _test_block(res: ir.Resource, op: ir.Operation, case: ir.TestCase) -> str:
    """Dispatch one authored ``TestCase`` to its per-kind renderer (identity on ``TestKind``)."""
    if case.kind is TestKind.CLIENT:
        return _client_test(res, case)
    if case.kind is TestKind.CLI:
        return _cli_test(res, op, case)
    if case.kind is TestKind.MCP:
        return _mcp_test(res, op, case)
    return _guard_test(res, op, case)  # TestKind.MCP_GUARD


def resolve_tests(
    res: ir.Resource,
    ctx: EmitContext,
    naming: Naming,
    type_mapper: TypeMapper,
    docstrings: Docstrings,
) -> TestsPageView:
    """IR -> TestsPageView. Takes the single operation carrying tests (walking-skeleton `me`),
    gates imports/constants on its ``kinds`` (a set of ``TestKind``), and renders one leaf per
    case. ``type_mapper`` is unused here - all TestCase values are authored."""
    op = next(operation for operation in res.operations if operation.tests)
    kinds = {case.kind for case in op.tests}
    client_class = naming.class_name(res.domain, "Client")
    return TestsPageView(
        doc_block=docstrings.render(_tests_module_doc(res, op, kinds), ""),
        header_lines=("from __future__ import annotations",),
        import_lines=_tests_imports(res, op, ctx, kinds, client_class),
        constants=_tests_constants(res, op, ctx, kinds),
        tests=tuple(_test_block(res, op, case) for case in op.tests),
    )
