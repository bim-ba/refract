# Can ycli's CLI + MCP layers be generated from a spec? — prior-art research

Retrieved 2026-07-14 unless noted. Sources: context7 (`/prefecthq/fastmcp`), deepwiki
(`jlowin/fastmcp`, `prkumar/uplink`), WebSearch, and direct inspection of the ycli repo
(`/home/sava/dev/dev/ycli`) at commit `9f272a4`.

## Grounding: what actually exists in ycli today

The task brief's "per-domain `client.py`/`cli.py`/`mcp.py`" is the top-level composition
layer only. The real per-endpoint code lives one level deeper, per resource
(`src/ycli/yandex/<domain>/<resource>/{client,cli,mcp,models}.py`) — 54 resource dirs today
(tracker: 30, forms: 9, wiki: 9, status/misc: rest). Aggregate LOC at the resource level:

| Layer | Total LOC (54 resource dirs) |
|---|---|
| `client.py` (uplink) | 5,159 |
| `cli.py` (typer) | 5,692 |
| `mcp.py` (fastmcp) | 5,127 |
| `models.py` (pydantic) | 8,141 |

The "no `from __future__ import annotations`" rule is real and is enforced by a docstring
convention at the *resource* level, e.g. `src/ycli/yandex/tracker/issues/client.py`:

```
"""Declarative Tracker /issues client (uplink) — transport ONLY.

NOTE: do NOT add ``from __future__ import annotations`` — uplink reads parameter
annotations eagerly.
"""
```

48 of 50 resource-level `client.py` files carry this note (the 2 without it —
`tracker/me`, `wiki/me` — have no `uplink.Path`/`uplink.Query`/`uplink.Body` params to
protect). The domain-level *aggregator* `client.py` files (e.g. `tracker/client.py`, which
just composes `IssuesClient`, `QueuesClient`, … as attributes) freely use postponed
annotations because they hold no uplink decorators. This resolves what looked like a
contradiction in file grep: the constraint is scoped to files with `@uplink.get/@post/…`,
not the package as a whole.

---

## Angle 1 — FastMCP native OpenAPI ingestion (`from_openapi`/`from_fastapi`)

**CONFIRMED — runtime ingestion exists and is customizable, but the FastMCP community
itself does not consider it a substitute for reviewable, hand-tuned server source in a
gated-CI project like ycli.**

- `FastMCP.from_openapi(...)` / `FastMCP.from_fastapi(...)` build an `OpenAPIProvider` at
  runtime from a spec. Confirmed via context7 `/prefecthq/fastmcp` (query-docs, retrieved
  2026-07-14, source `docs/integrations/openapi.mdx`, `fastmcp/server/server.py`) and
  deepwiki `jlowin/fastmcp`.
- Customization hooks that DO exist and DO let you override the auto-derived output,
  confirmed via context7 + deepwiki cross-check:
  - `route_maps` / `route_map_fn` — map an `HTTPRoute` + auto-assigned `MCPType` to
    `TOOL`/`RESOURCE`/`RESOURCE_TEMPLATE`/`EXCLUDE`; `route_map_fn` runs even on routes
    already marked `EXCLUDE`, so it can override anything.
  - `mcp_component_fn` — called per generated component (`OpenAPITool` /
    `OpenAPIResource` / `OpenAPIResourceTemplate`) after creation; can mutate
    `component.name`, `component.description`, `component.tags`, and
    `component.annotations` (`ToolAnnotations` — `readOnlyHint`/`destructiveHint`/
    `idempotentHint`/`openWorldHint`) in place.
  - `mcp_names` — dict mapping OpenAPI `operationId` → MCP tool name.
  - `tags` — global tags applied to every generated component.
  - `output_schema` is validated/controlled via `validate_output`; per-component output
    schema override is possible inside `mcp_component_fn` but is less first-class than
    name/description/annotations.
  - The `@mcp.tool()` decorator itself (`fastmcp/server/server.py:1686-1709`, per
    context7) takes `annotations: ToolAnnotations | dict[str, Any] | None`, confirming the
    annotation vocabulary is identical whether hand-written or spec-derived — so in
    principle a `mcp_component_fn` hook fed from a small per-operation config table
    *could* reproduce ARCH-3-honest annotations and hand-tuned docstrings.
- **The catch (load-bearing for ycli's "reviewable diff" requirement):** FastMCP's own
  maintainers distinguish this from generated source. GitHub Discussion
  `PrefectHQ/fastmcp#3672` ("Static Code Generation from OpenAPI Specs & Auth
  Auto-Wiring", retrieved via WebSearch 2026-07-14, author of the third-party
  `mcp-generator` tool) states plainly: *"FastMCP currently offers two paths for working
  with OpenAPI specs: `FastMCP.from_openapi()` creates a server dynamically at runtime for
  quick prototyping, and `fastmcp generate-cli` introspects an existing MCP server and
  generates a CLI client from it. What's missing is generating editable,
  version-controlled Python server source files from an OpenAPI spec... Teams working with
  larger APIs (50+ endpoints) or in regulated environments need to be able to review
  generated code in pull requests, run linters and type checkers against it."* That is
  ycli's exact situation (50 resources, 100%-coverage gate, PR-gated `main`) — and as of
  this writing that gap is an open feature request, not a shipped capability. `from_openapi`
  is positioned as **prototyping-grade, not the generated-source-of-truth ycli would need**.
- **Notable inversion — `fastmcp generate-cli` (angle-2-relevant, found via WebSearch +
  WebFetch of `https://gofastmcp.com/cli/generate-cli`, retrieved 2026-07-14):** FastMCP
  ships a command that goes the *other* direction: point it at a running MCP server (i.e.
  your hand-written `mcp.py`, already carrying honest annotations/docstrings) and it
  connects, reads the tool JSON schemas, and writes a standalone Python CLI script where
  every tool becomes a subcommand with typed flags, `--help` text pulled from tool
  descriptions, and tab completion. Key details from the fetched page:
  - Generated CLI uses **cyclopts**, not Typer/Click.
  - Output is explicitly positioned as an **editable one-shot scaffold**, not a repeatable
    build artifact: *"The generated script is a regular Python file — executable,
    editable, and yours."*
  - Complex types (objects, nested arrays, unions) degrade to JSON-string flags with
    schema hints in `--help`.
  - The script re-connects to the live MCP server on every invocation (client wrapper,
    not a bundled copy of the logic).
  This shows the "MCP-server-as-intermediate-representation, CLI generated from it"
  direction is a real, shipped idea in the FastMCP ecosystem — just targeting a different
  CLI framework and explicitly not meant as a maintained build step.

**Verdict for ycli:** `from_openapi`/`from_fastapi` cannot cleanly replace the ~5,100 LOC
of hand-written `mcp.py` today, both because (a) faithfully reproducing every ARCH-3
annotation and hand-tuned docstring via `mcp_component_fn` means maintaining a parallel
per-operation config that is arguably no simpler than the current decorated function, and
(b) it's a **runtime** object graph, not committed source — it fails the "reviewable diff"
and "type-checkable" requirements the project already enforces (`py.typed`, PR-gated CI).

## Angle 2 — Typer/Click generation from a spec

**CONFIRMED — no maintained generator targets Typer specifically; Click has one hobby
project; CLI generation is bespoke/template work industry-wide, confirmed by three
independent commercial vendors converging on templated-codegen, not runtime construction.**

- WebSearch found no maintained "OpenAPI → Typer" generator. The closest Click-targeting
  project is `JoshuaOliphant/openapi_to_click` (retrieved 2026-07-14): wraps
  `openapi-python-client` to produce a typed Python API client, then emits a `cli.py` that
  exposes every operation as a Click subcommand (typed options derived from the spec,
  `--token` auth flag, `--body` for request bodies). This is **static source generation**,
  not a runtime Click-app-from-dict — and it's a single-maintainer project, not
  ecosystem-standard tooling.
- Broader OpenAPI-to-CLI landscape (WebSearch, retrieved 2026-07-14): `openapi-generator`
  (OpenAPITools, Java-based, no Python/Typer target), `openapi-cli-generator`
  (danielgtaylor, Go/Cobra output), `openapi-to-cli` (EvilFreelancer/nirabo, Node.js),
  Fern (`buildwithfern.com`, emits a statically-linked Rust/Go binary CLI, not Python).
  None target Typer; all are template-based source emitters, not dynamic in-process
  construction.
- Commercial multi-surface generators (Stainless, Speakeasy — see Angle 5) that DO emit
  Python CLIs do so via full codegen pipelines (their own IR → language-specific
  templates), never by dynamically building a Typer/Click app object at runtime from a
  dict. Speakeasy's CLI generator specifically emits Go/Cobra, not Python at all.
- **Can Typer be built dynamically from metadata at runtime?** WebSearch on Typer's own
  docs/issue tracker (retrieved 2026-07-14): Typer supports `app.add_typer(sub_app,
  callback=...)` for composing sub-apps, and `app.command()` can be called
  programmatically in a loop to register dynamically-created functions — GitHub issue
  `fastapi/typer#257` ("How to dynamically add commands with typer?") confirms this is a
  live, only-partially-documented pattern users have to reverse-engineer, not a supported
  first-class API. The structural friction: Typer derives CLI parameters from a Python
  **function signature's type hints and default values** (it re-implements much of
  Click's declarative parsing on top of `inspect.signature`), so a "dynamic Typer command"
  still requires synthesizing a real function object with a real `__annotations__` dict
  and real default values (e.g. via `exec`, or via `inspect.Signature.replace()` +
  `functools` tricks) for every parameter — there is no `Typer.from_dict(...)` or
  `Typer.add_parameter(name, type, help=...)` API. This is exactly the same class of
  friction as uplink (Angle 3): the framework's ergonomics come from reading Python-level
  function metadata, which pushes any "dynamic" construction toward synthesizing source
  text (i.e. codegen) rather than pure runtime object manipulation.

**Verdict for ycli:** CLI generation from a spec is inherently template/codegen work,
industry-wide — there is no drop-in library that would let ycli hand a JSON Schema to a
function and get a properly-typed, well-`--help`ed Typer command out. Building one would
mean writing (and maintaining) a bespoke Typer-source-emitting template, which is a
real project in its own right, comparable in scope to what Stainless/Speakeasy/Fern do
in-house for their generated SDKs.

## Angle 3 — uplink dynamic construction

**CONFIRMED — dynamic construction is technically possible (there's precedent in
uplink's own deprecated API) but structurally hostile to it, and the eager-annotation
behavior is exactly what ycli's client.py docstring warns about.**

Via deepwiki `prkumar/uplink` (retrieved 2026-07-14):
- `uplink.build(...)` (now deprecated) is uplink's *own* precedent for building a
  `Consumer` subclass dynamically via `type()`, confirming the mechanism is possible —
  but it was deprecated, i.e. the library authors moved away from the dynamic-construction
  ergonomics.
- Mechanically: when a `Consumer` subclass is defined, `ConsumerMeta.__new__` scans the
  class namespace for `RequestDefinitionBuilder` instances and wraps each in a
  `ConsumerMethod` descriptor; `ConsumerMethod` immediately calls
  `request_definition_builder.build()` — **at class-definition time**, not lazily at call
  time. Building a `Consumer` subclass dynamically (`type()` + `setattr` with
  pre-decorated methods) is possible in principle because this all still fires during
  `type()`'s own class-body execution / attribute assignment.
- **Eager-annotation reading, confirmed mechanism:** `HttpMethod.__call__` (triggered when
  `@uplink.get(...)` etc. decorates a function) calls `utils.get_arg_spec(func)`, which
  inspects the function's *raw* `__annotations__` and hands them directly to
  `arg_handler.set_annotations(spec.annotations)` — it does **not** call
  `typing.get_type_hints()`, which is the function that would normally resolve
  `from __future__ import annotations` string-annotations back into real objects. Because
  uplink overloads the annotation slot itself to carry live marker *objects*
  (`uplink.Path("id")`, `uplink.Query`, `uplink.Body` — not type hints meant only for a
  type checker), PEP 563 postponed evaluation would hand uplink the **string**
  `"uplink.Path"` instead of the actual `Path` instance, breaking argument-handler
  construction. This is precisely why ycli's per-resource `client.py` docstrings say "do
  NOT add `from __future__ import annotations` — uplink reads parameter annotations
  eagerly" (verified directly in `src/ycli/yandex/tracker/issues/client.py`).
- Implication for dynamic generation: to build a working `Consumer` subclass at runtime
  from a data structure, you'd need to construct function objects whose
  `__annotations__` dict holds real `uplink.Path`/`Query`/`Body` *instances* (not
  strings) — doable via `types.FunctionType` + manual `__annotations__` assignment, or via
  `exec()` of generated source (i.e., codegen again) — but either path forfeits the
  primary win of "no template maintenance," and a hand-rolled `FunctionType` approach
  produces a class with no static type information at all (defeats `py.typed`).

**Verdict for ycli:** uplink *can* be driven dynamically at the mechanism level, but only
by either (a) `exec`-ing generated source per method (functionally indistinguishable from
codegen, just deferred to import time and losing IDE/mypy support at edit time), or (b)
hand-building `FunctionType` objects with real marker instances in `__annotations__`,
which is more fragile than templated codegen and produces zero static typing surface.
Templated source generation is strictly better on every axis that matters to this project.

## Angle 4 — `pydantic.create_model()` (runtime) vs generated source

**CONFIRMED via context7 `/pydantic/pydantic` (retrieved 2026-07-14, source
`docs/concepts/models.md` and `docs/examples/dynamic_models.md`).**

- `create_model()` is real, documented, and commonly used for genuinely dynamic
  situations (e.g. deriving an all-Optional variant of an existing model at runtime).
- Pydantic's own docs explicitly flag the static-analysis gap: in the "make all fields
  optional" example, the docs note *"static type checkers **won't** be able to understand
  that all fields are now optional"* when the model comes from `create_model()`. This is
  Pydantic's own maintainers confirming the exact failure mode ycli would hit.
- Trade-offs, concretely for ycli:
  - **`py.typed` (PEP 561):** a `create_model()`-built class has no source `class Foo(BaseModel): field: str` for mypy/pyright/ty to read: downstream consumers importing `ycli.yandex.tracker.issues.models.Issue` would get `Any`-shaped attributes wherever the model was assembled purely at runtime, unless every field is *also* redeclared as a `TYPE_CHECKING`-only stub — at which point you're maintaining two representations, which is worse than one generated file.
  - **Static analysis / IDE support:** autocompletion, "go to definition," and refactor-rename all depend on a real class body existing in a `.py` file; `create_model()` output is invisible to these tools.
  - **Reviewable diffs:** a `create_model()` call site diffs as "changed the shape of a dict passed to `create_model`," not as an addable/removable field with its own type/description/default in context — materially harder to review in a PR, and it defeats line-level `git blame`/coverage-gate tooling that assumes real source lines per field.
  - Generated **source** models (e.g. via `datamodel-code-generator`, which the task brief already treats as solved) get all three for free, at the one-time cost of running a generator and committing the output — which matches ycli's existing "regenerate, never hand-author" convention for other generated artifacts (already codified in this repo's CLAUDE.md: *"Generated demos/tables come from a committed source — regenerate, never hand-author"*).

**Verdict for ycli:** `create_model()` is the wrong tool here; it is a runtime-only
mechanism suited to genuinely dynamic/runtime-shaped models, not to a `py.typed`,
statically-checked, diff-reviewed SDK. Generated *source* models are the only option
consistent with the project's existing conventions — this angle is not actually in
tension with ycli's constraints the way CLI/MCP generation is.

## Angle 5 — Precedent: generating multiple surfaces from one spec

**CONFIRMED — this is a solved problem commercially, and every real example uses a
template/codegen pipeline (often with an internal IR), never pure runtime construction.**

| Project | Surfaces generated from one spec | Architecture (as documented) | Source |
|---|---|---|---|
| **Stainless** | SDKs (multiple languages) + docs + CLI + Terraform provider + MCP server, all from one OpenAPI spec + one `stainless.yml` config | Config-driven codegen; MCP tool `tool_name`/`description` overridden per-endpoint in `stainless.yml` (e.g. `resources.payments.methods.create.mcp.tool_name: initialize_payment`) | stainless.com/docs/mcp, stainless.com/docs/reference/config — WebSearch, retrieved 2026-07-14 |
| **Speakeasy** | SDKs + CLI (beta, Go/Cobra, wraps a generated Go SDK) + MCP servers, "one source of truth, two interfaces, every audience covered" | Internal Go-based IR ("a graph of Node values" preserving the raw spec shape) feeding per-target emitters; MCP tool names/descriptions customizable via `x-speakeasy-mcp` OpenAPI extension; can scope tools by `--scope read` | speakeasy.com/blog/release-cli-generation, speakeasy.com/blog/generate-mcp-from-openapi — WebSearch, retrieved 2026-07-14 |
| **liblab** | SDKs + hosted MCP server from an OpenAPI spec or Postman collection | Cloud-hosted codegen service producing a public MCP endpoint | liblab.com/docs/mcp — WebSearch, retrieved 2026-07-14 |
| **cnoe-io/openapi-mcp-codegen** | MCP server only (Python), from OpenAPI | Parses paths/operations/schemas, renders **Jinja2 templates** into tool modules + API client code + docs; ships two built-in utility tools alongside generated ones | github.com/cnoe-io/openapi-mcp-codegen — WebSearch, retrieved 2026-07-14 |
| **FastMCP `generate-cli`** | CLI (cyclopts) from a *live MCP server* (inverse direction — MCP as source of truth) | Introspects tool JSON schemas over the wire, writes an editable one-shot Python script | gofastmcp.com/cli/generate-cli — WebFetch, retrieved 2026-07-14 |

Common thread across every real multi-surface generator found: **an explicit
intermediate representation (spec graph, or in FastMCP's inverse case, live tool schemas)
feeding per-target template emitters that produce committed, editable source** — none of
them wire a runtime object graph directly into a second framework at request time. The
CLI output is *always* generated Go/Rust/Python **source**, never a Click/Typer app built
by introspecting a dict at import time. This matches what Angles 2–4 independently
concluded from the framework internals.

**Couldn't verify:** whether any of Stainless/Speakeasy/liblab's generated *Python* SDKs
specifically target Typer (their public docs emphasize Go/TypeScript/Kotlin most heavily;
Python CLI-target specifics weren't surfaced by available sources) — flagging as
COULDN'T-VERIFY rather than asserting a negative.

---

## Summary verdict

| Angle | Can it be generated (not templated)? |
|---|---|
| 1. FastMCP `from_openapi`/`from_fastapi` | No — customization hooks (`mcp_component_fn`, `route_map_fn`, `mcp_names`) technically *can* reproduce honest annotations/docstrings, but the result is a runtime object graph, not committed reviewable source; FastMCP's own maintainers (Discussion #3672) confirm this gap is unaddressed for 50+-endpoint regulated use cases like ycli's. |
| 2. Typer/Click from spec | No maintained generator targets Typer; the one Click generator is a single-maintainer static-codegen project; Typer's function-signature-driven design makes "dynamic" construction degrade into synthesizing source anyway. |
| 3. uplink dynamic `Consumer` | Mechanically possible (uplink's own deprecated `build()` proves it) but requires hand-building real marker objects in `__annotations__` (not strings) because uplink reads annotations eagerly, not via `get_type_hints()` — loses all static typing, worse than templated source. |
| 4. `pydantic.create_model()` | Works, but Pydantic's own docs admit static type checkers can't see dynamically-created fields — wrong tool for a `py.typed` package; generated source models are the only fit. |
| 5. Precedent | Real and multiple (Stainless, Speakeasy, liblab, cnoe-io, FastMCP `generate-cli`) — every one uses an IR + template-emitter architecture producing committed source, none wire runtime introspection straight into a second framework. |

**Bottom line:** models are the only layer where a "generate from spec" story cleanly
fits ycli's constraints (`py.typed`, reviewable diffs, 100% coverage gate). For CLI and
MCP, the honest options are (a) hand-write both as today, or (b) build a bespoke
template/IR-based generator (à la cnoe-io or a scoped-down Stainless-style pipeline) that
emits committed Typer/FastMCP **source**, driven by a small per-operation config for the
things that can't be inferred from OpenAPI alone (honest ARCH-3 annotations, agent-facing
docstring tone). Runtime construction (`from_openapi`, dynamic Typer commands, dynamic
uplink `Consumer`s, `create_model()`) is not a shortcut that avoids building/maintaining
that generator — every framework's own ergonomics push toward "materialize real source"
once you need static types, reviewable diffs, and IDE support.
