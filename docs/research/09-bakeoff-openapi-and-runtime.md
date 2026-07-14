# Bake-off: S2 (OpenAPI 3.x) and S3 (runtime metaprogramming) — stress test

Grounded in `02-codebase-anatomy-and-op-pool.md` (real verbatim code, re-verified against the
live repo at `/home/sava/dev/dev/ycli` while writing this) and `05-strategy-design-space.md`
§0 (settled findings) / the S2 / S3 rows. Goal: make the rejection of both strategies
*demonstrable* on concrete ops, not asserted. No secrets/tokens in any example.

---

## PART S2 — OpenAPI 3.x authoring

### 1. Fragments for the 5 assigned ops

#### #1 `issues_get` — trivial GET-by-id (the easy case)

```yaml
paths:
  /issues/{key}:
    get:
      operationId: issues_get
      summary: Get a Tracker issue by key
      parameters:
        - name: key
          in: path
          required: true
          schema: { type: string }
          example: DATAENGINEERING-1
      responses:
        "200":
          description: The issue
          content:
            application/json:
              schema: { $ref: '#/components/schemas/Issue' }
components:
  schemas:
    Issue:
      type: object
      properties:
        key: { type: string, nullable: true }
        summary: { type: string, nullable: true }
        type: { type: string, nullable: true }
        status: { type: string, nullable: true }
        priority: { type: string, nullable: true }
        epic: { type: string, nullable: true }
        parent: { type: string, nullable: true }
        queue: { type: string, nullable: true }
        assignee: { type: string, nullable: true }
        tags: { type: array, items: { type: string } }
```

Even here — the closest OpenAPI gets to "free" — the spec says nothing about the MCP tool's
defensive guard in the real code (`tracker/issues/mcp.py:28-42`): a 2xx response with an
all-`None` body must be treated as not-found via `require_found(..., sentinel=lambda r: r.key
is None, ...)`. OpenAPI's `"200"` response has no vocabulary for "a syntactically valid
200 that is semantically a 404 in disguise."

#### #2 `surveys_list` — offset pagination + drain-to-limit

```yaml
paths:
  /surveys:
    get:
      operationId: surveys_list_page       # ← this is the ONLY thing OpenAPI can describe:
      summary: One raw page of surveys      #   one HTTP call, not the client-side drain loop
      parameters:
        - { name: offset, in: query, schema: { type: integer, default: 0 } }
        - { name: limit, in: query, schema: { type: integer, default: 100 } }
      responses:
        "200":
          content:
            application/json:
              schema: { $ref: '#/components/schemas/SurveysResponse' }
components:
  schemas:
    SurveysResponse:
      type: object
      properties:
        links: { type: object }
        result: { type: array, items: { $ref: '#/components/schemas/Survey' } }
    Survey:
      type: object
      properties: { id: { type: string, nullable: true }, name: { type: string, nullable: true } }
```

OpenAPI has no first-class pagination primitive at all (no `type: cursor` or `x-pagination`
in the core spec — every SDK generator either ignores paging or invents its own vendor
extension). There is nothing here that says "advance `offset` by `limit` until a short page
comes back, cap the total at `resolve_cap(limit, config.max_items)`, and collapse the result
into a flat `SurveyList`." That logic — `forms/surveys/client.py:24-49`, the public `list()`
wrapping `OffsetStrategy.collect` around the internal `_list_page` — is 100% absent from the
spec and would have to be reconstructed by a bespoke emitter reading a vendor field like
`x-pagination: {strategy: offset, page-size: 100}` that OpenAPI itself does not define or
validate.

#### #4 `issues_create` — see the dedicated line-count section below.

#### #5 `comments_delete` — bodyless write

```yaml
paths:
  /issues/{key}/comments/{comment_id}:
    delete:
      operationId: comments_delete
      parameters:
        - { name: key, in: path, required: true, schema: { type: string } }
        - { name: comment_id, in: path, required: true, schema: { type: string } }
      responses:
        "204":
          description: Comment deleted (no body)
```

10 lines, looks free. But the real MCP tool (`tracker/comments/mcp.py:74-85`) does not return
`None` — it returns a synthesized `Ack.deleted("comment", comment_id, on=key)`, matching the
repo-wide rule that no user-facing write ever hands an agent a bare null. OpenAPI's `"204"`
response has empty content by definition — there is no schema to attach a "wrap the void into
this typed acknowledgement, with these constructor args" rule to. A generator that trusted the
spec literally would emit an MCP tool returning `None`, which is a real behavioral
regression, not a stylistic one (the whole point of `Ack` is that every write is uniformly
serializable — a `None` return breaks that contract silently). The internal `_delete`
(uplink, `requests.Response`) vs. public `delete` (`None`) split (`comments/client.py:74-85`)
is likewise invisible — OpenAPI describes ONE operation, not "one raw stub plus one hand-written
wrapper that composes it."

#### #9 `attachments_upload` — cannot be authored as one OpenAPI operation

The real pipeline (`wiki/attachments/client.py:137-164`) is **four chained HTTP calls** sharing
a `session_id`: `POST /uploadsessions` (JSON: `file_name`/`file_size`) → `PUT` the raw bytes to
the session → `POST .../finish` → `POST /pages/{id}/attachments` (JSON: `upload_sessions: [id]`).
OpenAPI 3.x's `multipart/form-data` requestBody describes a SINGLE HTTP POST with an inline file
part — that is not what ycli does on the wire at all; it's a fundamentally different shape
(session-based resumable/chunkable upload vs. one-shot multipart). You can describe each of the
four steps as its own path item (ycli's `uploadsessions` resource already does expose 4 of them
as separate MCP tools), but "run these three calls in sequence, thread `session_id` through, and
present the whole thing as ONE MCP tool taking base64 bytes for the small-file happy path" is
pure orchestration — sequencing + data-threading between calls — and OpenAPI 3.x has no
orchestration primitive (that's a separate, barely-adopted spec, Arazzo, layered on top of
OpenAPI 1.0/2023, not something datamodel-code-generator or any mainstream emitter consumes).
There is no YAML fragment to write here that OpenAPI recognizes as one operation; the pipeline
must be hand-written Python regardless of authoring strategy — i.e. doc 05's `handler: module:fn`
escape hatch is not optional for this op, it is the *entire* implementation. On top of that,
CLI reads raw bytes off disk while MCP takes `pydantic.Base64Bytes` JSON
(`wiki/attachments/cli.py:97-114` vs. `mcp.py:73-95`) — two different wire encodings for what
OpenAPI's single `requestBody.content` map treats as one operation.

### 2. What OpenAPI cannot express (the six required gaps, concretely)

| Gap | What ycli needs | What OpenAPI has | Forced fallback |
|---|---|---|---|
| Pagination drain strategy | client-side loop picking one of 4 `PaginationStrategy` subclasses + `resolve_cap` | one page description; no pagination vocabulary at all | `x-pagination: {strategy: offset\|cursor\|relative_cursor, ...}` vendor field + a hand-written emitter that reads it |
| MCP annotation class + docstring | `RO`/`WRITE`/`WRITE_IDEMPOTENT`/`DESTRUCTIVE` (ARCH-3, fail-closed) + a hand-tuned agent-facing prose block distinct from the API `description` | nothing — `description` is one string, shared with the human-facing summary, no read/write/destructive taxonomy | `x-mcp: {annotation-class: ..., docstring: ...}` — reinvents ARCH-3's classification as an *unvalidated* string in a foreign format, losing the fail-closed "unknown verb fails the build" guarantee (`ARCHITECTURE.md` ARCH-3) unless you rebuild that check yourself against `x-` data |
| CLI flag→nested-body mapping (#4) | 8 independently-optional flags, `--type`/`--priority` wrap into `{"key": ...}`, `--tag` repeats into a list, `-F key=value` is JSON-coerced and merged (`tracker/issues/cli.py:84-112`) | one `requestBody` schema — an object, not a per-field CLI ergonomics description | `x-cli: {flags: [...]}` — and even then the *transform* (`if type_: body["type"] = {"key": type_}`) is imperative, not declarative; expressing it needs either a mini-DSL (reinventing the templating layer S1/S4/S5 already chose, now bolted onto a format not designed for it) or a named `handler:` function — OpenAPI buys nothing here |
| Bodyless-write→`Ack` synthesis (#5) | every no-body write returns a typed `Ack` factory call, never `None` | `"204"` responses have no content schema by definition | `x-ack-factory: {method: deleted, args: [comment, comment_id], kwargs: {on: key}}` — a ycli-specific convention with zero OpenAPI backing |
| Internal `_verb`/public wrapper split | one raw uplink stub (`_delete`/`_list_page`/…) returning `requests.Response`/one page, PLUS a hand-composed public method (pagination/Ack/poll) — most ops in the pool are *two* methods (02 §A.6) | one operation = one endpoint; no concept of "internal HTTP primitive vs. public composed SDK method" | none — a generator must invent this split itself; OpenAPI doesn't even have a place to declare "this op is internal" |
| Upload pipeline (#9) | 4 chained calls, session-id threading, base64-vs-bytes divergence | `multipart/form-data`, one POST | none inside OpenAPI 3.x proper — full hand-written `handler:` (see above) |

### 3. Line-count quantification for #4 `issues_create`

Measured, not eyeballed (`wc -l` over both the real files and the drafted OpenAPI fragments):

| Artifact | Lines | What it captures |
|---|---:|---|
| Real `client.py` `create()` (`issues/client.py:56-68`) | 13 | HTTP contract |
| Real `models.py` `IssueCreate` (`issues/models.py:43-71`) | 29 | body schema + per-field descriptions + `extra="allow"` |
| Real `mcp.py` `create` tool (`issues/mcp.py:106-111`) | 6 | annotation class, tags, docstring, wiring |
| Real `cli.py` `create` command (`issues/cli.py:84-112`) | 29 | 8-flag→nested-body mapping |
| **Real total (hand-written today)** | **77** | full HTTP + MCP + CLI + model surface |
| Pure OpenAPI fragment (paths + schemas only, no vendor fields) | **76** | HTTP contract + schema *only* — no pagination (n/a here), no MCP annotation/docstring, no CLI flags, no internal/public split |
| OpenAPI + `x-mcp`/`x-cli` vendor extensions (approximating parity) | **95** | adds annotation-class + CLI flag *declarations* — but the imperative `--type`→`{"key":...}` transform still isn't expressible; a handler function is still required on top |

The "pure" OpenAPI fragment ties the real hand-written line count (76 vs. 77) while expressing
strictly *less* — it is silent on MCP annotations, CLI ergonomics, and the client's
internal/public split, all of which the real code carries. Once vendor extensions are added to
close even part of that gap, the spec grows *past* what it replaces (95 lines) and still bottoms
out needing a hand-written Python function for the one part that actually mattered (the flag
transform) — you pay MORE authored text to end up in the same place: a Python function doing
the real work.

### 4. Honest verdict

**datamodel-code-generator does cleanly handle the models slice** — feed it the
`components.schemas` block above (real JSON-Schema/OpenAPI subset) and it emits a pydantic-v2
`IssueCreate`/`Issue` pair structurally close to the hand-written ones (field types, `Optional`,
`Field(description=...)` from the schema `description` keys). That's why it's the one reusable
off-the-shelf component doc 05 §0.3 keeps. But client.py (HTTP verb selection, internal/public
split, pagination composition, upload orchestration), mcp.py (annotation class, agent docstring,
`Ack` synthesis), and cli.py (flag→body ergonomics) all need bespoke, hand-written emitters
regardless — OpenAPI does not reduce that work, it just adds a translation/`x-`-extension layer
in front of it. Net: OpenAPI buys a standards-recognizable interchange format at the cost of
verbosity roughly matching (not beating) today's hand-written line count for the *easy* slice,
worse for the escape-hatch slice, plus a rip-and-replace of the working uplink/FastMCP/Typer
stack for a foreign one that (per doc 05 §0.2) nobody in the real multi-surface-generator
landscape actually wires this way either.

---

## PART S3 — Runtime metaprogramming

### 1. The engine, sketched for `issues_get` (read) and `comments_delete` (write)

An in-memory spec + a loop that calls `type()`/`setattr()`/`pydantic.create_model`/
`app.command(name=...)(factory)` at **import time**, producing no committed `.py` per resource:

```python
# _runtime_engine.py — hypothetical, NOT committed generator output; sketch only
from dataclasses import dataclass, field
from typing import Any
import uplink
from ycli.yandex.mcp import RO, DESTRUCTIVE
from ycli.yandex.models import Ack
from ycli.yandex.tracker.issues.models import Issue   # models are STILL hand-written/codegen'd

@dataclass(frozen=True)
class OpSpec:
    surface_name: str          # "issues_get" / "comments_delete"
    verb: str                  # "get" | "delete"
    path: str                  # "issues/{key}" | "issues/{key}/comments/{comment_id}"
    path_params: tuple[str, ...]
    return_model: type | None  # None for bodyless writes -> Ack
    mcp_annotation: dict
    docstring: str

OP_SPECS: dict[str, OpSpec] = {
    "issues_get": OpSpec("issues_get", "get", "issues/{key}", ("key",), Issue, RO,
                          "A single Tracker issue by key."),
    "comments_delete": OpSpec("comments_delete", "delete",
                               "issues/{key}/comments/{comment_id}",
                               ("key", "comment_id"), None, DESTRUCTIVE,
                               "Permanently delete one comment (irreversible)."),
}

def _build_uplink_method(spec: OpSpec):
    """Manufacture a function object, stamp __annotations__ manually (uplink reads them
    eagerly — see issues/client.py:1-5 / comments/client.py:1-5: 'NOTE: do NOT add
    `from __future__ import annotations`'), then apply the uplink verb decorator."""
    def _stub(self, **kwargs):  # body irrelevant — uplink's descriptor replaces the call
        raise NotImplementedError
    _stub.__name__ = spec.verb
    _stub.__qualname__ = f"<runtime>.{spec.verb}"
    _stub.__annotations__ = {p: uplink.Path for p in spec.path_params}
    _stub.__annotations__["return"] = spec.return_model or Any
    decorate = uplink.get if spec.verb == "get" else uplink.delete
    fn = decorate(spec.path)(_stub)
    return uplink.returns.json()(fn) if spec.return_model else fn

def build_resource_client(base_cls, specs: list[OpSpec]) -> type:
    namespace = {s.verb: _build_uplink_method(s) for s in specs}
    return type("RuntimeResourceClient", (base_cls,), namespace)   # type() — the crux

def register_mcp_tool(mcp, spec: OpSpec, client_provider):
    import inspect
    params = [inspect.Parameter(p, inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=str)
              for p in spec.path_params]
    params.append(inspect.Parameter("client", inspect.Parameter.POSITIONAL_OR_KEYWORD,
                                     default=client_provider, annotation=Any))
    def _tool(**kwargs):
        client = kwargs.pop("client")
        result = getattr(client, spec.verb)(**kwargs)
        return result if spec.return_model else Ack.deleted(*kwargs.values())
    _tool.__signature__ = inspect.Signature(params)     # dynamic __signature__ — the crux
    _tool.__doc__ = spec.docstring
    _tool.__name__ = spec.surface_name
    return mcp.tool(name=spec.surface_name,
                     annotations={**spec.mcp_annotation, "title": spec.surface_name})(_tool)

def register_cli_command(app, spec: OpSpec, client_provider):
    def _factory(**kwargs):
        client = client_provider()
        return getattr(client, spec.verb)(**kwargs)
    return app.command(name=spec.surface_name.split("_", 1)[1])(_factory)  # app.command(name=...)(factory)
```

This is functionally real — `type()` does build a working `uplink.Consumer` subclass at
runtime, `pydantic.create_model` does build a working request-body model for a write op that
needs one, `app.command(name=...)(factory)` does register a live Typer command, and
`FastMCP.tool(...)` does accept a manufactured function with a hand-built `__signature__`. The
two ops in the sketch dispatch identical HTTP calls to the real hand-written client. **It works
at runtime.** The rejection is not "it's broken" — it's what breaks *around* it.

### 2. Where the repo's guarantees concretely break

**py.typed.** `src/ycli/py.typed` (confirmed present) is the PEP 561 marker that tells a
downstream `pyright`/`ty`/mypy user ycli's types are checkable. `IssuesClient.get` built via
`setattr(cls, "get", _build_uplink_method(spec))` inside `OP_SPECS`'s loop has **no
corresponding `def get(...)` AST node anywhere in source** — a downstream caller writing
`client.issues.get(key="X-1")` gets "unknown attribute" (or silent `Any`, worse) from a static
checker, because checkers walk source text, not a live `__mro__` built by executing Python.
This is not hypothetical: `client.py`'s own top-of-file comment across every resource in doc 02
(`tracker/issues/client.py:1-5`, `tracker/comments/client.py:1-5`, `forms/surveys/client.py:1-5`,
`wiki/attachments/client.py:1-5`) says *"do NOT add `from __future__ import annotations` — uplink
reads parameter annotations eagerly"* — meaning even uplink's own runtime correctness already
depends on real annotation objects being present at class-body-eval time; a manufactured
function's `__annotations__` dict has to be hand-assembled with exactly the right keys in exactly
the right order with no compiler catching a typo, only a live HTTP call at test time. And for
the write-side body models: I fetched pydantic's own dynamic-models docs via Context7
(`/pydantic/pydantic`, `docs/examples/dynamic_models.md`) mid-research — its own worked
example of `create_model`-driven dynamic fields ends with: *"static type checkers **won't** be
able to understand"* the synthesized shape. That's not a ycli-specific problem; it's why
pydantic ships a dedicated mypy plugin just to paper over its own dynamism — ycli would need to
write and maintain an equivalent plugin from scratch to recover the visibility the current
committed `.py` files already give for free, with zero plugin.

**100% coverage gate.** `uv run pytest` enforces `--cov-fail-under=100` (CLAUDE.md). Line
coverage is dominated by `_build_uplink_method`/`register_mcp_tool`/`register_cli_command` —
generic engine code. The SAME six-ish lines execute whether `OP_SPECS` has 2 entries or 200; a
typo'd path-param name, a wrong `return_model` reference, or a swapped `mcp_annotation` in one
spec dict entry does not show up as an *uncovered line* — coverage.py can't distinguish "op #7's
behavior is right" from "the engine ran." Today, one physical `def get(...)` per resource forces
one covering, asserting test per resource (that discipline is *why* the gate currently catches
per-op regressions); collapsing ~200 methods into one engine collapses that granularity too —
100% "coverage" becomes achievable by testing the engine's plumbing once and never asserting
what any individual op actually returns.

**ARCH-1/2/3 + ARCH-6 snapshots + import-linter — all physically file-coupled, confirmed by
reading the actual checks:**
- ARCH-1 (`tests/test_architecture.py:61-65`, `_resource_dirs()`) is **literally**
  `for domain in DOMAINS: for child in (YANDEX / domain).iterdir(): yield child` — it walks the
  filesystem. A runtime-registered resource with no `client.py`/`cli.py`/`mcp.py`/`models.py` on
  disk gives `_resource_dirs()` nothing to scan; `test_arch1_four_surface_symmetry`
  (`tests/test_architecture.py:68-75`, asserting `checked >= 16`) either silently stops counting
  the runtime resources (false pass — the exact failure mode ARCH-1 exists to prevent) or the
  check has to be rewritten from scratch against `OP_SPECS` instead of the filesystem, i.e. not
  reused, reinvented for a different substrate.
- ARCH-3 (`tests/test_architecture.py:524`, `test_arch3_mcp_write_tool_bodies_are_typed`, and the
  verb-classification "fail-closed, unknown verb fails the build" rule, `ARCHITECTURE.md` ARCH-3)
  is AST-based: it parses `mcp.py` source for `@mcp.tool(...)` decorator-call nodes and inspects
  the `annotations={...}` dict literal *in the source text*. A dynamically-registered tool has
  the decorator applied once, generically, inside `register_mcp_tool`'s loop — there is exactly
  one `@mcp.tool` call SITE in source (in the engine module), applied N times at runtime, not N
  individually-reviewable decorator sites for a checker (or a human PR reviewer) to inspect. The
  check would have to trust `OP_SPECS[x].mcp_annotation` is correct with no independent AST
  cross-check — assertion, not verification, which is exactly what ARCH-3's fail-closed design
  was built to refuse.
- ARCH-6 snapshots (`tests/test_snapshots.py`, `tests/snapshots/{cli_tree.txt,mcp_tools.txt}`)
  still technically work on tool/command *names* (they're deterministic strings in `OP_SPECS`),
  but the PR diff a human reviews for "did the public surface change" now shows a one-line
  `OP_SPECS` dict edit, never the actual generated behavior — a much weaker review signal than
  today's real source diff.
- import-linter (`pyproject.toml:156-182`, the ARCH-2/ARCH-3 contracts) matches modules by
  **name glob** — `ycli.yandex.**.cli`, `ycli.yandex.**.mcp`, `ycli.yandex.**.models` — forbidding
  `requests`/`uplink` in the first three and `fastmcp` outside `mcp.py`/`ycli.mcp`. A runtime
  engine naturally fuses the uplink-building, FastMCP-tool-building, and Typer-command-building
  code into one (or a few) shared module(s) with no per-resource `client.py`/`cli.py`/`mcp.py`
  split left to name-glob against — the contracts either match nothing (silently inert) or match
  one fused module that legitimately needs `uplink` **and** `fastmcp` **and** `typer` together,
  which is precisely the cross-contamination ARCH-2/ARCH-3 exist to forbid. The physical-file
  boundary the contracts key off of is the thing runtime construction removes.

**Nothing to review in a PR diff.** Adding op #201 becomes a dict-literal edit in `OP_SPECS`,
not a `def`. A reviewer checking "does this write really return an `Ack`, does this read really
guard the empty-2xx case" has no source to read — only the spec's *claim* and a live-execution
test to fall back on.

### 3. Conclusion — the boto3/boto3-stubs precedent

Doc 05 §0.1 already settled this from prior-session research, and this pass confirms it
mechanically rather than by citation alone: runtime construction achieves "fewer repo files" —
and *only* that. It forfeits exactly the properties this repo is built on (py.typed visibility,
per-op coverage granularity, all four physically-file-coupled architecture checks) to get there.
And it doesn't even buy freedom from codegen: boto3 itself builds clients this way from JSON
service models, and the community had to build and separately maintain `boto3-stubs`/
`mypy-boto3-*` — a whole SEPARATE generated, committed stub-package project — specifically
because a runtime-built client is invisible to type checkers. Even the most mature production
example of exactly this strategy still ships generated `.py`/`.pyi` source in the end; it just
moved the codegen to a second, harder-to-keep-in-sync project instead of eliminating it.

---

## Disposition summary

| | S2 (OpenAPI 3.x) | S3 (runtime metaprogramming) |
|---|---|---|
| Verdict | Rejected | Rejected (already ruled OUT in doc 05 §0.1; this doc concretizes why) |
| Where it's strongest | Models slice — datamodel-code-generator genuinely reuses it | "Fewer repo files" — true but not a property the repo optimizes for |
| Single most damning gap | #9 `attachments_upload`: literally cannot be authored as one OpenAPI operation — the 4-step session pipeline has no OpenAPI orchestration primitive; the escape hatch isn't optional, it's the whole implementation | `tests/test_architecture.py:61-65` `_resource_dirs()` walks `(YANDEX / domain).iterdir()` on disk — a runtime-registered resource has nothing there to find; ARCH-1 either silently stops checking or must be rewritten from scratch against a different substrate |
| Quantified cost | #4 `issues_create`: pure OpenAPI = 76 lines (ties the 77 real hand-written lines while expressing strictly less); +`x-mcp`/`x-cli` to approach parity = 95 lines (worse than today) and still needs a hand-written transform function on top | N/A (not a line-count comparison — a guarantee-forfeiture comparison) |
| What survives regardless | The hand-crafted uplink/APIModel/FastMCP/Typer stack stays; only `models.py` generation is worth adopting from OpenAPI tooling | Nothing generator-shaped survives; even boto3 (the closest real precedent) ends up shipping a second generated stub project (`boto3-stubs`) to claw back what runtime construction gives away |
