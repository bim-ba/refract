# Bake-off — Strategy S5: declarative-Python descriptor → committed-source codegen

Rendering the 12-op pool (doc 06) under **S5**: a human writes one typed-Python *descriptor*
per resource (`spec.py`); a **build-time materializer** walks it and emits the committed
`client.py`/`cli.py`/`mcp.py` (+ registrations), exactly the code doc 02 quotes verbatim. Models
stay hand-written pydantic (as today) and are *referenced* by the descriptor, not generated.
This is the committed-source path (doc 05 §0.1 — runtime is ruled out); the emitter output is
normal `.py`, so `py.typed`, the 100% gate, ARCH-1..11 and reviewable diffs all survive.

Ground truth for every "generated output" block is doc 02's real code; divergences are flagged.

---

## Part 0 — The descriptor vocabulary (the design)

The whole point of S5 is that **the spec is Python the same `ty` checker guards** — so the
vocabulary is a set of frozen dataclasses in `src/ycli/_codegen/dsl.py` (written once, ~260 LOC,
the "framework"). A resource author imports them and writes data. No YAML, no JSON-Schema, no
`type: "str | None"` strings — a return model is a *class object* (`returns=Issue`), a poll
target is the *Operation object* it points at, and an escape hatch is a *function object*
(`handler=upload_pipeline`) whose reference `ty` resolves at author time.

```python
# src/ycli/_codegen/dsl.py — authored ONCE; this is the S5 "framework"
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

_UNSET: Any = object()

# ---- MCP intent → RO / WRITE / WRITE_IDEMPOTENT / DESTRUCTIVE (ARCH-3 as DATA) ----
@dataclass(frozen=True)
class Read:
    title: str                       # MCP tool title
    doc: str                         # agent-facing MCP docstring (verbatim)
    cli_help: str = ""               # CLI command help; "" → first line of doc
    found: "Found | None" = None     # emit a require_found(...) guard in mcp.py

@dataclass(frozen=True)
class Write:
    title: str
    doc: str
    idempotent: bool = False         # → WRITE_IDEMPOTENT
    destructive: bool = False        # → DESTRUCTIVE
    cli_help: str = ""

@dataclass(frozen=True)
class Found:                         # → require_found(result, sentinel=lambda r: r.<f> is None, ...)
    sentinel: str                    # model field name that is None on an empty parse
    message: str

# ---- params ----
@dataclass(frozen=True)
class Path:  name: str
@dataclass(frozen=True)
class Query:
    name: str
    alias: str | None = None         # uplink.Query("perPage")
    default: Any = _UNSET

# ---- body modes (doc 05 §3: NOT "typed model everywhere") ----
@dataclass(frozen=True)
class ModelBody:                     # the 85% case
    model: type
    by_alias: bool = False           # model_dump(by_alias=…, exclude_none=True)
@dataclass(frozen=True)
class ScalarBody:                    # scalar MCP params assembled into a dict inline (pages_update)
    fields: tuple["Query", ...]
    required: tuple[str, ...] = ()
@dataclass(frozen=True)
class RawDict:                       # allowlisted raw-dict exception (set_permissions)
    reason: str                      # copied into the docstring NOTE *and* the ARCH-3 allowlist
@dataclass(frozen=True)
class Base64Upload: pass             # MCP takes Base64Bytes; CLI reads bytes off disk

# ---- pagination (1:1 with ycli.yandex.pagination.*) ----
@dataclass(frozen=True)
class Offset:   page_size: int; extract: str
@dataclass(frozen=True)
class Cursor:   page_size: int; extract: str; next: str; wrap: type
@dataclass(frozen=True)
class Relative: extract: str; id_of: Callable[[Any], str | None]; max_page_size: int = 100

# ---- async trigger→poll linkage ----
@dataclass(frozen=True)
class Poll:
    target: "Operation"              # a real Operation object (the RO poll op)
    id_field: str                    # "operation.id"
    done: str                        # terminal-state property, e.g. "is_terminal"

# ---- bodyless write → synthesized Ack ----
@dataclass(frozen=True)
class AckOf:
    factory: str                     # "deleted" / "published" / …
    kind: str                        # "comment"
    ident: str                       # param name carrying the id
    on: str | None = None            # param name for the on=… qualifier

# ---- the operation ----
@dataclass(frozen=True)
class Operation:
    name: str                        # op suffix: get / list / create / comments_create
    verb: str                        # get / post / patch / delete
    path: str
    mcp: Read | Write
    returns: type | None = None      # a model class, or None
    scalar_returns: type | None = None   # e.g. int (issues_count) — bare scalar, no model
    params: tuple[Any, ...] = ()
    body: Any = None                 # ModelBody | ScalarBody | RawDict | Base64Upload | None
    page: Any = None                 # Offset | Cursor | Relative | None
    page_model: type | None = None   # internal per-page envelope type
    ack: AckOf | None = None
    poll: Poll | None = None
    group: str | None = None         # god-resource section banner ("comments")
    client_doc: str = ""             # client.py method docstring (incl. doctest)
    handler: Callable[..., Any] | None = None      # ESCAPE HATCH — public client method
    cli: Callable[..., Any] | None = None          # ESCAPE HATCH — a bespoke Typer command

@dataclass(frozen=True)
class Resource:
    domain: str                      # tracker / wiki / forms
    name: str                        # issues / surveys / …
    operations: tuple[Operation, ...]
```

**The materializer** (`python -m ycli._codegen build [--check]`) imports every `spec.py`, and for
each `Operation` runs the layer emitters:

- `emit_client` — for a plain op, one uplink method. For a paginated op it emits **both** the
  internal `_verb` uplink stub *and* the public wrapper that calls the matching
  `OffsetStrategy`/`CursorStrategy`/`_drain_relative` recipe (the internal/public split, doc 02
  §A.6). If `handler=` is set, it emits the raw uplink stub (if any) and copies the referenced
  function in as the public method — no synthesis.
- `emit_mcp` — `@mcp.tool(name="<res>_<op>", annotations={**<intent>, "title": …}, tags=…)`,
  `Depends(<domain>_client)` last param, `model_dump(exclude_none=True[, by_alias=True])`, the
  `require_found` guard from `Found`, the `Ack.<factory>(…)` return from `AckOf`.
- `emit_cli` — `ctx`-first command ending in `Serializer.serialize(...)`; list commands get
  `LimitOption`/`AllOption` + `resolve_cap`. If `cli=` is set, the bespoke command is used verbatim.
- `emit_registration` — appends `self.<res> = …` / `add_typer` / `mcp.mount` lines.

`--check` re-emits into a temp tree and diffs against the committed files (CI gate). Because the
emitters always produce the quartet + registration, **ARCH-1 op-parity holds by construction** and
its test becomes a free generator-correctness check (doc 05 §2).

**Materializer ≠ runtime.** Nothing here imports at *app* start; `spec.py` is read only by the
build tool. The committed output is byte-identical to what doc 02 shows a human wrote — proven in
Part 2.

---

## Part 1 — Authored spec for all 12 ops

One `Resource(...)` per file; I group by resource as the repo does. Prose (`doc`/`client_doc`/
`cli_help`) is reproduced verbatim from doc 02 — it is the irreducible creative surface (Part 3).

### issues (`src/ycli/yandex/tracker/issues/spec.py`)

```python
from ycli._codegen.dsl import (
    Operation, Resource, Path, ModelBody, Read, Write, Found,
)
from .models import Issue, IssueList, IssueCreate, IssueUpdate

# ---- #1 issues_get ----
issues_get = Operation(
    name="get", verb="get", path="issues/{key}",
    params=(Path("key"),), returns=Issue,
    client_doc=(
        "``GET /issues/{key}`` → a single ``Issue`` (raises on non-2xx).\n\n"
        "Example:\n"
        "    >>> client = TrackerClient(oauth_token=\"…\", organization_id=\"…\")  # doctest: +SKIP\n"
        "    >>> client.issues.get(key=\"DATAENGINEERING-1\").status  # doctest: +SKIP\n"
        "    'inProgress'\n"
    ),
    mcp=Read(
        title="Get Tracker issue",
        found=Found(
            sentinel="key",
            message="issue {key!r} not found (got empty response — check key or permissions)",
        ),
        doc=(
            "A single Tracker issue by key (raises if not found).\n\n"
            "In production the Transport response hook raises ``YandexNotFoundError`` on a 404\n"
            "before this guard is reached. This check only fires for a 2xx response that carries\n"
            "an empty body (key=None) — an edge case unlikely in practice but defended here for\n"
            "safety (e.g. incorrect permissions returning a blank object instead of a 403)."
        ),
    ),
)

# ---- #4 issues_create (typed body; rich CLI via escape hatch — see below) ----
issues_create = Operation(
    name="create", verb="post", path="issues/",
    body=ModelBody(IssueCreate), returns=Issue,
    client_doc=(
        "``POST /issues/`` — create from a ready body. Returns the created ``Issue``.\n\n"
        "Example:\n"
        "    >>> client = TrackerClient(oauth_token=\"…\", organization_id=\"…\")  # doctest: +SKIP\n"
        "    >>> client.issues.create(\n"
        "    ...     {\"queue\": \"DATAENGINEERING\", \"summary\": \"New\", "
        "\"type\": {\"key\": \"improvement\"}}\n"
        "    ... ).key  # doctest: +SKIP\n"
        "    'DATAENGINEERING-200'\n"
    ),
    mcp=Write(title="Create Tracker issue",
              doc="Create a Tracker issue; returns the new issue with its key."),
    cli=issues_create_command,          # ← escape hatch, defined in _handlers.py, imported below
)

issues = Resource(domain="tracker", name="issues", operations=(issues_get, issues_create))
```

The rich CLI create (flag→body assembly with `type`/`priority` wrapping to `{"key": …}`, bare
`queue`/`parent`, `-F` custom fields via `parse_fields`) is genuinely bespoke imperative logic.
S5's honest move is **not** to encode it as data but to reference the real Typer function — a
first-class object `ty` type-checks:

```python
# src/ycli/yandex/tracker/issues/_handlers.py  (hand-written; imported by spec.py)
from typing import Annotated, Any
import typer
from ycli.cli.context import AppContext
from ycli.cli.output import Serializer
from ycli.cli.typedefs import FieldOpt          # existing shared alias
from ycli.yandex.tracker.utils import parse_fields

def issues_create_command(
    ctx: typer.Context,
    queue: Annotated[str, typer.Option(help="Target queue key.")],
    summary: Annotated[str, typer.Option(help="Issue summary (title).")],
    type_: Annotated[str, typer.Option("--type", help="Issue type key, e.g. task.")] = "",
    priority: Annotated[str, typer.Option(help="Priority key, e.g. normal.")] = "",
    parent: Annotated[str, typer.Option(help="Parent issue key.")] = "",
    description: Annotated[str, typer.Option(help='Markdown body — pass "$(cat file.md)".')] = "",
    tag: Annotated[list[str] | None, typer.Option("--tag", help="Tag (repeatable).")] = None,
    field: FieldOpt = None,
) -> None:
    """Create an issue (POST /issues/). type/priority wrap to {"key": …}; queue/parent stay bare."""
    body: dict[str, Any] = {"queue": queue, "summary": summary}
    if type_:
        body["type"] = {"key": type_}
    if priority:
        body["priority"] = {"key": priority}
    if parent:
        body["parent"] = parent
    if description:
        body["description"] = description
    if tag:
        body["tags"] = tag
    body |= parse_fields(field)
    app_ctx = AppContext.from_typer_context(ctx)
    Serializer.serialize(
        app_ctx.tracker.issues.create(body=body), app_ctx.strategy, app_ctx.console
    )
```

> **Design note:** the descriptor references `issues_create_command` by *object*, not by a
> `"module:issues_create_command"` string. A rename/typo is a `ty`/import error at author time,
> not a runtime `ImportError`. This is the S5 escape hatch's core advantage over YAML's `module:fn`.

### comments (`src/ycli/yandex/tracker/comments/spec.py`)

```python
from ycli._codegen.dsl import Operation, Resource, Path, Query, Relative, Read, DESTRUCTIVE_ACK  # noqa
from ycli._codegen.dsl import AckOf, Read, Write
from .models import Comment, CommentList

# ---- #3 comments_list — relative-cursor drain ----
comments_list = Operation(
    name="list", verb="get", path="issues/{key}/comments",
    params=(Path("key"), Query("comment_id", alias="id", default=None),
            Query("per_page", alias="perPage", default=100)),
    page=Relative(
        extract="root",
        id_of=lambda comment: str(comment.id) if comment.id is not None else None,
    ),
    returns=CommentList, page_model=CommentList,
    client_doc=(
        "All comments on an issue, draining the ``id=<last comment id>`` relative cursor.\n\n"
        "``GET /issues/{key}/comments`` returns one page at a time (50 comments by default);\n"
        "each next page repeats with ``id=<id of the last comment seen>`` until a page comes\n"
        "back empty. Capped at ``limit`` (``None`` = every comment)."
    ),
    mcp=Read(
        title="List Tracker issue comments",
        doc=(
            "All comments on a Tracker issue, auto-paginated via the relative id-cursor.\n\n"
            "Capped at YCLI_MAX_ITEMS (default 500) unless ``limit`` is given, so very long "
            "threads\nare truncated at the cap rather than fetched forever."
        ),
    ),
)

# ---- #5 comments_delete — bodyless write → Ack, internal/public split ----
comments_delete = Operation(
    name="delete", verb="delete", path="issues/{key}/comments/{comment_id}",
    params=(Path("key"), Path("comment_id")),
    ack=AckOf(factory="deleted", kind="comment", ident="comment_id", on="key"),
    client_doc="Delete a comment (``DELETE …/comments/{id}`` → 204). Raises on non-2xx.",
    mcp=Write(
        title="Delete Tracker issue comment", destructive=True,
        doc=(
            "Permanently delete one comment from a Tracker issue (irreversible).\n\n"
            "Get ``comment_id`` from ``comments_list``. Returns an acknowledgement on success."
        ),
    ),
)

comments = Resource("tracker", "comments", (comments_list, comments_delete))
```

`ack=AckOf(...)` tells `emit_client` to produce the internal `_delete` uplink stub + a public
`delete` returning `None`, and tells `emit_mcp` to `return Ack.deleted("comment", comment_id, on=key)`.

The `id_of=lambda comment: …` on `Relative` is a **real function object in the spec** — the
last-item-id extraction is per-model and irregular (str-cast + None-guard), so it lives as a tiny
native lambda, not a stringly-typed path. (For most Tracker relative drains it's the identical
one-liner; the DSL could default it, but showing it explicit here.)

### transitions (`src/ycli/yandex/tracker/transitions/spec.py`)

```python
# ---- #6 transitions_execute — action, open-ended extra=allow body ----
transitions_execute = Operation(
    name="execute", verb="post",
    path="issues/{key}/transitions/{transition_id}/_execute",
    params=(Path("key"), Path("transition_id")),
    body=ModelBody(TransitionExecute), returns=TransitionList,
    client_doc=(
        "``POST /issues/{key}/transitions/{id}/_execute`` → available transitions after move.\n\n"
        "Returns the transitions available for the issue in its new status,\n"
        "parsed as a ``TransitionList``."
    ),
    mcp=Write(
        title="Execute Tracker issue transition",
        doc=(
            "Move a Tracker issue through a workflow transition (change its status).\n\n"
            "Get ``transition_id`` from ``transitions_list``. ``body`` may be empty or carry "
            "issue\nfields to set on transition, e.g. a resolution when closing. Returns the "
            "transitions\navailable from the new status."
        ),
    ),
)
```

The `extra="allow"` openness is a property of the `TransitionExecute` *model* (hand-written),
so the descriptor just names it — nothing special at the op layer.

### surveys (`src/ycli/yandex/forms/surveys/spec.py`)

```python
# ---- #2 surveys_list — offset pagination + drain-to-limit ----
surveys_list = Operation(
    name="list", verb="get", path="surveys",
    params=(Query("offset", default=0), Query("limit", default=100)),
    page=Offset(page_size=100, extract="result"),
    returns=SurveyList, page_model=SurveysResponse,
    client_doc=(
        "``GET /surveys`` → flat :class:`SurveyList`, draining offset pages internally.\n\n"
        "Capped at ``limit`` (``None`` = every form). The API pages by ``offset``/``limit``; "
        "this\nadvances the offset until a short page comes back."
    ),
    mcp=Read(
        title="List Forms surveys",
        doc=(
            "Every form (survey) the caller can see, auto-paginated over the API's offset "
            "pages.\n\nCapped at YCLI_MAX_ITEMS (default 500) unless ``limit`` is given. Each "
            "item's ``id`` is the\nform id you pass to ``surveys_get`` / ``questions_list`` / "
            "``answers_list``."
        ),
    ),
)
```

### questions (`src/ycli/yandex/forms/questions/spec.py`) — ESCAPE HATCH #7

```python
# ---- #7 questions_move — bare position = silent server no-op ----
questions_move = Operation(
    name="move", verb="post",
    path="surveys/{survey_id}/questions/{question_id}/move",
    params=(Path("survey_id"), Path("question_id")),
    body=ModelBody(QuestionMove, by_alias=True), returns=QuestionMoveResult,
    client_doc=(
        "``POST /surveys/{id}/questions/{question_id}/move`` — reposition a question.\n\n"
        "``body`` is a typed :class:`QuestionMove` naming the target page … a bare\n"
        "``position`` is silently ignored by the API (200, nothing moves), so ``QuestionMove``\n"
        "raises unless a page target is also given. … Returns the moved question's id."
    ),
    mcp=Write(
        title="Move Forms question",
        doc=(  # verbatim doc 02 §9 — abbreviated here
            "Reposition a question on the form (target page + position); returns the moved "
            "question's id.\n\n``body.position`` needs a page target to take effect …"
        ),
    ),
    cli=questions_move_command,     # ← CLI visibly defaults --page to 1 (escape hatch)
)
```

**Where the irregular part lives.** The guard "a bare `position` needs a page target" is a
`model_validator(mode="after")` on `QuestionMove` — a hand-written pydantic model. That code is
verbatim as in doc 02 §9; the descriptor never tries to declare it. Because `returns`/`body`
reference the *model class*, the validator rides along for free and `ty` sees it. The CLI's
"visibly default `--page=1`" rescue is a real Typer function referenced by `cli=`:

```python
# forms/questions/_handlers.py — the CLI escape hatch (page-1 default made visible)
def questions_move_command(ctx, survey_id, question_id,
                           page: Annotated[int, typer.Option(help="Target page (1-based).")] = 0,
                           position: Annotated[int, typer.Option(help="0-based index.")] = -1):
    """Move a question; --page defaults to 1 when only --position is given (avoids the no-op)."""
    if position >= 0 and page == 0:
        page = 1                     # visible rescue, not hidden in the model
    body = QuestionMove(page=page or None, position=position if position >= 0 else None)
    app_ctx = AppContext.from_typer_context(ctx)
    Serializer.serialize(app_ctx.forms.questions.move(survey_id, question_id, body),
                         app_ctx.strategy, app_ctx.console)
```

### grids (`src/ycli/yandex/wiki/grids/spec.py`)

```python
# ---- #8 grids_update_cells — structured payload + optimistic-lock revision ----
grids_update_cells = Operation(
    name="update_cells", verb="post", path="grids/{grid_id}/cells",
    params=(Path("grid_id"),),
    body=ModelBody(CellsUpdate), returns=CellsUpdateResult,
    client_doc="``POST /grids/{id}/cells`` — set individual cell values. ``body`` is a ``CellsUpdate``.",
    mcp=Write(
        title="Update Wiki grid cells", idempotent=True,
        doc=(
            "Set the value of individual grid cells (addressed by row id + column slug).\n\n"
            "Repeating the same call sets the same values (idempotent). Returns the updated "
            "cells\nplus the grid's new ``revision``."
        ),
    ),
)
```

`revision` (optimistic lock) is a required field on the `CellsUpdate` model — descriptor names
the model; nothing op-level. The MCP `Field(description=…)` prose the agent sees is on the model.

### attachments (`src/ycli/yandex/wiki/attachments/spec.py`) — ESCAPE HATCH #9

```python
from ._handlers import upload_pipeline, upload_command      # real function objects
# ---- #9 attachments_upload — 3-step pipeline; base64 (MCP) vs raw-bytes (CLI) ----
attachments_upload = Operation(
    name="upload", verb="post", path="pages/{page_id}/attachments",   # path unused by handler
    body=Base64Upload(), returns=AttachedFileList,
    handler=upload_pipeline,        # ← whole public client method is hand-written
    cli=upload_command,             # ← CLI reads bytes off disk (path.read_bytes())
    mcp=Write(
        title="Upload file to Wiki page",
        doc=(
            "Upload one small file and attach it to a wiki page in a single call.\n\n"
            "Runs the whole pipeline end to end: opens an upload session sized to ``data``, "
            "PUTs the\nbytes as a single part, finishes the session, and attaches it to the "
            "page. … Returns the\nnewly-attached files."
        ),
    ),
)
```

The pipeline is *not* one HTTP call, so there is no uplink stub to declare. `handler=upload_pipeline`
points at the exact method from doc 02 §11; the materializer copies it into `client.py` verbatim.
`body=Base64Upload()` tells `emit_mcp` to type the `data` param `Annotated[Base64Bytes, …]`;
`cli=upload_command` supplies the raw-bytes CLI. The base64-vs-raw divergence is expressed as
**two different escape-hatch functions**, which is exactly what it is in reality.

### pages / operations (`src/ycli/yandex/wiki/pages/spec.py`) — ASYNC #10

```python
# poll target — a normal RO op on the operations resource
clone_get = Operation(
    name="clone_get", verb="get", path="operations/clone/{task_id}",
    params=(Path("task_id"),), returns=CloneOperationStatus,
    client_doc=(
        "``GET /operations/clone/{task_id}`` → a page-clone's status (poll this to wait).\n\n"
        "The ``task_id`` is the ``operation.id`` returned by ``PagesClient.clone``. Poll until\n"
        "``is_terminal``; on ``success`` the ``result.page`` names the clone."
    ),
    mcp=Read(title="Get Wiki clone operation status",
             doc="Status of an async page-clone operation; poll until terminal."),
)

# #10 pages_clone — async trigger linked to the poll target above
pages_clone = Operation(
    name="clone", verb="post", path="pages/{page_id}/clone",
    params=(Path("page_id"),), body=ModelBody(PageClone), returns=PageCloneOperation,
    poll=Poll(target=clone_get, id_field="operation.id", done="is_terminal"),
    client_doc="``POST /pages/{id}/clone`` — copy the page to a new address (async trigger). …",
    mcp=Write(
        title="Clone Wiki page",
        doc=(
            "Copy a page to a new address (``POST /pages/{id}/clone`` — asynchronous).\n\n"
            "Cloning is the only way to give content a new slug (slugs are permanent). The "
            "call\nreturns a deferred operation reference — poll ``operations_clone_get`` with "
            "the\nreturned ``operation.id`` until it reaches a terminal status."
        ),
    ),
)
```

`poll=Poll(target=clone_get, …)` is a **live object reference** to the poll op — the linkage
`ty` can follow (rename `clone_get` and the reference breaks at author time). `emit_cli` reads it
to generate the `--wait/--no-wait` command that drives `wait_for(lambda: …clone_get(task_id),
lambda s: s.is_terminal, …)`; `emit_mcp` leaves trigger and poll as two separate tools (agent
self-polls). This is the one place the DSL encodes a cross-op relationship as data — and it's
type-safe because it's a Python reference, not a `"operations_clone_get"` string.

### entities (`src/ycli/yandex/tracker/entities/spec.py`) — GOD-RESOURCE #11 + RAW-DICT #12

```python
# #11 entities_comments_create — god-resource sub-op, grouped
entities_comments_create = Operation(
    name="comments_create", group="comments", verb="post",
    path="entities/{entity_type}/{entity_id}/comments",
    params=(Path("entity_type"), Path("entity_id")),
    body=ModelBody(CommentCreate, by_alias=True), returns=Comment,
    client_doc="``POST …/comments`` — add a comment. Returns the created comment. …",
    mcp=Write(title="Add Tracker entity comment",
              doc="Add a comment to a Tracker entity; returns the created comment."),
)

# #12 entities_set_permissions — raw-dict body (documented ARCH-3 exception)
entities_set_permissions = Operation(
    name="set_permissions", group="permissions", verb="patch",
    path="entities/{entity_type}/{entity_id}/extendedPermissions",
    params=(Path("entity_type"), Path("entity_id")),
    body=RawDict(
        reason=(
            "wire shape nests READ/WRITE/GRANT under grant/revoke verbs; existing "
            "ExtendedPermissionsUpdate/AclInput models describe a different shape. "
            "Allowlisted pending a correctly shaped model."
        ),
    ),
    returns=ExtendedPermissions,
    mcp=Write(
        title="Set Tracker entity permissions", idempotent=True,
        doc=(  # verbatim doc 02 §18, incl. the NOTE about the dict exception
            "Change an entity's access rules; returns the resulting permission set.\n\n"
            "``body`` is the raw API payload; its ``acl`` object accepts only ``grant`` / "
            "``revoke``\nactions … Read the current ACL first with ``entities_permissions_get``.\n\n"
            "NOTE: intentionally ``dict`` (not a typed model) — …"
        ),
    ),
)

entities = Resource(
    domain="tracker", name="entities",
    operations=(entities_comments_create, entities_set_permissions),  # + 31 more sub-ops
)
```

`group=` drives the `# ---- comments ----` / `# ---- permissions ----` banner sections in the
emitted god-resource `client.py`, and the flat `entities_<sub>_<verb>` MCP tool names. `RawDict`
is the *only* op that touches a test allowlist: the materializer emits `body: dict` on the MCP tool
**and** writes/refreshes the `ARCH3_BODY_DICT_ALLOWLIST["yandex/tracker/entities/mcp.py:set_permissions"]`
entry using `reason=` as its text — so the exception is declared in one place and stays in sync
with the test (doc 02 §18; `tests/test_architecture.py:457-463`).

---

## Part 2 — Generated output for the 4 designated ops (diff-checked vs doc 02)

### #1 `issues_get`

**Model** — *not generated*; `spec.py` references the hand-written `Issue` (doc 02 §1 /
`tracker/issues/models.py:14-31`). S5 leaves models exactly as they are. ✅ (design choice, see Part 3)

**`emit_client` output** — byte-identical to doc 02 §1:
```python
@uplink.returns.json()
@uplink.get("issues/{key}")
def get(self, key: uplink.Path) -> Issue:  # ty: ignore[empty-body]
    """``GET /issues/{key}`` → a single ``Issue`` (raises on non-2xx).

    Example:
        >>> client = TrackerClient(oauth_token="…", organization_id="…")  # doctest: +SKIP
        >>> client.issues.get(key="DATAENGINEERING-1").status  # doctest: +SKIP
        'inProgress'
    """
```
The `# ty: ignore[empty-body]` and the doctest come straight from `client_doc`. ✅ **no divergence.**

**`emit_mcp` output** — from `returns=Issue` + `Found(sentinel="key", …)`:
```python
@mcp.tool(name="issues_get", annotations={**RO, "title": "Get Tracker issue"}, tags=TAGS)
def get(key: str, client: TrackerClient = Depends(tracker_client)) -> Issue:
    """A single Tracker issue by key (raises if not found).

    In production the Transport response hook raises ``YandexNotFoundError`` on a 404
    before this guard is reached. This check only fires for a 2xx response that carries
    an empty body (key=None) — an edge case unlikely in practice but defended here for
    safety (e.g. incorrect permissions returning a blank object instead of a 403).
    """
    result = client.issues.get(key)
    return require_found(
        result,
        sentinel=lambda r: r.key is None,
        message=f"issue {key!r} not found (got empty response — check key or permissions)",
    )
```
`Found.sentinel="key"` → `lambda r: r.key is None`; `Found.message` → the f-string. ✅ **matches doc 02 §1 exactly.**

### #2 `surveys_list` — the internal/public pagination split

**`emit_client`** from `page=Offset(page_size=100, extract="result")`, `page_model=SurveysResponse`,
`params=(Query("offset", default=0), Query("limit", default=100))`:
```python
@uplink.returns.json()
@uplink.get("surveys")
def _list_page(
    self,
    offset: uplink.Query = 0,  # ty: ignore[invalid-parameter-default]
    limit: uplink.Query = _PAGE_SIZE,  # ty: ignore[invalid-parameter-default]
) -> SurveysResponse:  # ty: ignore[empty-body]
    """One raw page of surveys at ``offset`` (page size ``limit``); internal — use ``list``."""

def list(self, *, limit: int | None = None) -> SurveyList:
    """``GET /surveys`` → flat :class:`SurveyList`, draining offset pages internally.

    Capped at ``limit`` (``None`` = every form). The API pages by ``offset``/``limit``; this
    advances the offset until a short page comes back.
    """
    strategy = OffsetStrategy(extract=lambda page: page.result, page_size=_PAGE_SIZE)
    surveys = strategy.collect(
        lambda offset: self._list_page(offset=offset, limit=_PAGE_SIZE),
        limit,
    )
    return SurveyList(surveys)
```
`extract="result"` → `lambda page: page.result`; `page_size=100` → the `_PAGE_SIZE` module const
the emitter hoists; `returns=SurveyList` → the `SurveyList(surveys)` wrap. ✅ **matches doc 02 §2**
(incl. the internal `_list_page` stub with its two `ty: ignore` comments and the public `list`).
The real file's `get()` and the module doctest are separate ops in the same `Resource` — omitted here.

> **Minor divergence (cosmetic):** the emitter must reproduce the module-level `_PAGE_SIZE = 100`
> const and the `# doctest: +SKIP` example block inside `list`'s docstring. Both are mechanical
> (a per-resource const declaration + `client_doc`), but they mean the descriptor's `page_size=100`
> and the const are two facts the emitter must keep equal — a small correctness obligation.

**`emit_mcp`** — from `mcp=Read(...)`, a paginated read auto-gets `limit`/`config`:
```python
@mcp.tool(name="surveys_list", annotations={**RO, "title": "List Forms surveys"}, tags=TAGS)
def list_(
    limit: int = 0,
    client: FormsClient = Depends(forms_client),
    config: AppConfig = Depends(app_config),
) -> SurveyList:
    """Every form (survey) the caller can see, auto-paginated over the API's offset pages.

    Capped at YCLI_MAX_ITEMS (default 500) unless ``limit`` is given. Each item's ``id`` is the
    form id you pass to ``surveys_get`` / ``questions_list`` / ``answers_list``.
    """
    cap = resolve_cap(limit, config.max_items)
    return client.surveys.list(limit=cap)
```
✅ **matches doc 02 §2.** The `page=` presence is what tells `emit_mcp` to add the
`limit`/`config`/`resolve_cap` triad (and `emit_cli` the `LimitOption`/`AllOption` + `all_=all_`).

### #4 `issues_create` — the rich-CLI tension

**`emit_mcp`** — from `body=ModelBody(IssueCreate)`, `returns=Issue`, `mcp=Write(...)`:
```python
@mcp.tool(
    name="issues_create", annotations={**WRITE, "title": "Create Tracker issue"}, tags=WRITE_TAGS
)
def create(body: IssueCreate, client: TrackerClient = Depends(tracker_client)) -> Issue:
    """Create a Tracker issue; returns the new issue with its key."""
    return client.issues.create(body.model_dump(exclude_none=True))
```
✅ **matches doc 02 §5 exactly** (`ModelBody(by_alias=False)` → `model_dump(exclude_none=True)`;
`Write(idempotent=False, destructive=False)` → `{**WRITE, …}` + `WRITE_TAGS`).

**CLI** — *not generated*; `cli=issues_create_command` copies the Part-1 handler in verbatim, which
is byte-identical to doc 02 §5's `cli.py:84-112`. ✅ **matches** — but note this is the escape
hatch, i.e. S5 concedes the rich CLI create rather than declaring it (Part 3). The materializer's
only contribution is the `app.command()(issues_create_command)` registration line.

### #9 `attachments_upload` — the hard case

**`emit_client`** — `handler=upload_pipeline` copies the doc 02 §11 method verbatim:
```python
def upload(
    self,
    sessions: UploadSessionsClient,
    page_id: int,
    *,
    file_name: str,
    data: bytes,
) -> AttachedFileList:
    """Run the whole upload pipeline for one file, then attach it to ``page_id``. …"""
    session = sessions.create(UploadSessionCreate(file_name=file_name, file_size=len(data)))
    session_id = session.session_id or ""
    sessions.upload_part(session_id, part_number=1, data=data)
    sessions.finish(session_id=session_id)
    return self.attach(page_id, [session_id])
```
✅ identical — because it *is* the hand-written function; the generator only relocates it.

**`emit_mcp`** — from `body=Base64Upload()`, `returns=AttachedFileList`:
```python
@mcp.tool(
    name="attachments_upload",
    annotations={**WRITE, "title": "Upload file to Wiki page"},
    tags=WRITE_TAGS,
)
def upload(
    page_id: Annotated[int, Field(description="Numeric id of the page to attach the file to.")],
    file_name: Annotated[str, Field(description="Name to give the uploaded file.")],
    data: Annotated[Base64Bytes, Field(description="The file's bytes, base64-encoded.")],
    client: WikiClient = Depends(wiki_client),
) -> AttachedFileList:
    """Upload one small file and attach it to a wiki page in a single call. …"""
    return client.attachments.upload(client.uploadsessions, page_id, file_name=file_name, data=data)
```
⚠️ **Divergence to flag:** the three MCP params (`page_id`/`file_name`/`data`) and their
`Field(description=…)` text are **not** derivable from `Base64Upload()` alone — the real tool takes
scalar params with hand-written descriptions and passes `client.uploadsessions` positionally. So
`Base64Upload` in practice must carry the param list + descriptions (like `ScalarBody`), OR this MCP
body is itself an escape-hatch `mcp=` function. Honest read: **#9 needs escape hatches on *all
three* surfaces** (client `handler=`, CLI `cli=`, and effectively MCP too). The DSL doesn't
*block* it, but the "declarative" content of this op is near zero — it's three hand-written
functions the descriptor merely registers. That's the truthful picture of the hard 15%.

---

## Part 3 — Honest assessment of S5

### Authoring cost (the 12 ops)

Counting non-blank authored lines a human types (descriptor + any escape-hatch functions + the
unchanged prose), against the real hand-written `client.py`+`cli.py`+`mcp.py` for the same ops
(models.py is unchanged under S5, so excluded from both sides):

| Op | Real (client+cli+mcp) | S5 (descriptor + handlers) | Note |
|---|---:|---:|---|
| #1 get | ~28 | ~24 | prose dominates both |
| #2 list (offset) | ~40 | ~22 | split absorbed — real win |
| #3 list (relative) | ~42 | ~24 | + `id_of` lambda |
| #4 create | ~46 | ~44 | CLI is an escape hatch → ~no saving |
| #5 delete (Ack) | ~26 | ~16 | split + Ack absorbed |
| #6 execute | ~30 | ~22 | |
| #7 move | ~48 | ~46 | model validator + CLI handler unchanged |
| #8 update_cells | ~30 | ~20 | |
| #9 upload | ~40 | ~40 | 3 escape hatches → zero saving |
| #10 clone+poll | ~55 | ~40 | CLI `--wait` absorbed; trigger/poll declared |
| #11 entities_comment | ~22 | ~16 | |
| #12 set_permissions | ~30 | ~26 | raw-dict + allowlist |
| **Total** | **~437** | **~340** | **≈ 22% cut, blended** |

That headline is *lower* than it first looks because I'm honest about two things most pitches hide:
1. **Prose is ~45% of authored lines and is irreducible.** The MCP docstring, the CLI help, and
   the client `Example:` doctest are three distinct hand-tuned strings per op that *no* strategy
   generates. They're the same text in the descriptor as in the code. Strip prose out and look at
   **structure only**: real ~230 → S5 ~90, a **~60% structural cut** — that is where the "~60%"
   estimate is right, but it applies to structure, not the whole file.
3. **The escape-hatch ops (#4 CLI, #7, #9) save ≈ nothing** — the handler functions are the same
   lines whether referenced from a descriptor or written in place. On this 12-op pool (deliberately
   escape-hatch-heavy) the blended cut is only ~20-22%; on a resource of mostly plain
   GET/LIST/CREATE ops it would approach the ~60% structural figure. The realistic all-resources
   blended number is **~45-55%**, not 60%.

### Escape-hatch cleanliness — does the long tail ever block?

**No — and this is S5's single strongest property.** The fallback is `handler=<function object>`
(client), `cli=<function>` (CLI), and for the rare MCP-shape, `mcp=<function>`. Because the spec
is Python, an unforeseen op is *always* expressible today: write the method, reference it, done —
zero new generator machinery. And the reference is **type-checked**: `handler=upload_pipeline` is
resolved by `ty`/imports; a rename or typo fails at author time. YAML's equivalent
`handler: "ycli.wiki.attachments._handlers:upload_pipeline"` is an **unchecked string** — a typo
surfaces as a build-time (or worse, runtime) `ImportError`, and refactoring tools won't follow it.
This is the concrete, load-bearing S5-vs-YAML advantage.

The catch: escape hatches are *contagious at the op level*. #9 pulls in a client handler, a CLI
handler, and effectively an MCP handler — at which point the descriptor entry is pure registration
and the "declaration" is fictional. The DSL never blocks generation, but it can degrade to "a
type-safe `add_typer`/`mcp.mount` list" for the hard 15%. That's honest, and it's fine — but it
means S5's declarative benefit is real only on the easy 85%.

### Extensibility (C1 north star) — cost of an unforeseen op-shape #21

Three tiers, cheapest first:
- **Expressible via existing escape hatch (most cases):** cost = writing the Python function +
  `handler=`. **Zero framework change.** This is why S5 scores well on C1 — the tail is never blocked.
- **Worth first-classing (recurring new shape, e.g. a `NextUrl` paginated list):** add one frozen
  dataclass to `dsl.py` + one branch in the relevant emitter. With **B-ir** internals the new IR
  node's type flows through `ty`, so the emitter branch that forgets it won't type-check — a real
  safety net. With **B-tmpl** it's a new Jinja conditional (works, but untyped and gnarlier as
  shapes multiply — doc 05 §1). **Recommend B-ir for S5.**
- **New surface entirely (docs site, TS SDK):** a new emitter over the same descriptors — the
  descriptor is surface-agnostic data. Same leverage YAML+IR would give.

### Invariant fit

- **py.typed:** ✅ emits real committed `.py`; downstream checkers see everything. The *descriptor*
  is also typed Python, so the spec layer itself is `ty`-clean — a genuine plus no other strategy has.
- **100% coverage:** ⚠️ the shared risk (doc 05 §2): the generator must also emit tests, or generated
  code is `# pragma: no cover`-excluded and only `dsl.py`+emitters+handlers are covered. S5-specific
  wrinkle: `spec.py` files are imported Python that `ty` checks but that also count toward
  coverage — pure-data specs have no branches so they're covered by import alone; **handlers need
  real tests** (same as today). Net: no worse than S1/S4, and the spec-is-typed property removes a
  class of "the YAML said `int` but the code wants `str`" bugs before any test runs.
- **ARCH-1..11:** ✅ satisfied by construction — the emitter always produces the quartet +
  registration, so op-parity (ARCH-1), HTTP-confinement (ARCH-2), annotation honesty (ARCH-3, the
  intent is DATA), serialization-confinement (ARCH-4) hold mechanically. ARCH-3's raw-dict allowlist
  is *generated in sync* from `RawDict.reason` — arguably better than today's hand-maintained entry.
- **Reviewable diffs:** ⚠️ **double surface** — a reviewer sees both the `spec.py` diff *and* the
  emitted `.py` diff. Mitigated by a `--check` CI gate (emitted files must match) so reviewers can
  trust "emitted follows from spec" and read only the spec — but that discipline must be enforced,
  or the committed generated files rot.

### The failure mode at 50→200 resources

1. **The descriptor library becomes a second framework.** `dsl.py` grows every time a shape
   recurs; contributors must learn `Operation`/`ModelBody`/`Relative`/`Poll` semantics *and* the
   emitter behavior *and* uplink/FastMCP. At 200 resources that's a lot of implicit knowledge in a
   bespoke DSL only this repo uses.
2. **Import-time coupling / circular-import risk.** Each `spec.py` imports its real models and its
   handlers; the materializer must import all of them to read the specs. `spec.py → models.py`,
   `spec.py → _handlers.py → client/context`, and `handler` objects referencing clients create a
   genuine circular-import surface that a YAML/inert-text spec never has. This is S5's most likely
   *practical* scaling pain.
3. **Escape-hatch creep.** Every irregular op adds a `_handlers.py` function. Past some fraction,
   you maintain a descriptor **and** a handler for the same op — arguably *more* surface than just
   writing the code. The DSL's value is a monotype-decreasing function of how ragged your API is;
   Yandex's API is fairly ragged (doc 02's 20 shapes), so the ragged tail is not small.
4. **Regeneration churn.** A `dsl.py`/emitter change re-emits all 200 resources → a giant diff.
   Great for "review once, apply everywhere"; painful if it lands mixed with a behavior change.

### The ~60%-vs-85% question — validated / challenged

**Challenged, and I think the framing is misattributed.** My rendered examples show the S5
descriptor and an equivalent YAML op-entry are within ~15-20% of each other on *line count* — the
Python has import lines, `Operation(` / `)` punctuation and trailing commas; YAML has block-scalar
`|` indentation and needs a separate schema-validation layer. That syntactic delta is **not** 25
points. So where does the prior "60 vs 85" gap come from? Almost certainly **models**: the ~85%
YAML figure implicitly assumes a schema source (OpenAPI/JSON-Schema) that *also* feeds
datamodel-codegen to generate `models.py` **and** carries the field descriptions that become MCP
schema text (doc 05 §0.3). S5 as scoped here keeps models **hand-written** and referenced by class
— so it never claims the models.py slice, capping it near the ~55-60% structural cut. Two honest
conclusions:

- If the owner is happy hand-writing pydantic models (as the repo does today, with real validators
  like `QuestionMove`'s), **S5 ≈ 55% with full `ty`-checking beats YAML ≈ 85%-on-paper that needs a
  schema-validation layer and can't host a `model_validator`.** The 85% is partly borrowed from
  datamodel-codegen, which S5 could *also* adopt — but then the spec is split-brain (JSON-Schema
  for models + Python for ops), which is uglier than YAML+schema (one format family). **That
  split-brain risk is the real argument against S5, not "Python is less declarative than YAML."**
- The delta that *does* survive is qualitative, not quantitative: type-checked references, IDE
  completion, refactor-safety, and a function-object escape hatch. If the owner weights those over
  raw line-count, ~55% type-safe (S5) is worth more than ~85% stringly-typed (YAML). If the owner
  weights portability-to-a-future-non-Python-consumer and a single inert spec format, YAML wins.

**Bottom line:** S5 is the right pick *iff* (a) models stay hand-written pydantic and the owner
values that, and (b) the team accepts owning a bespoke Python DSL + a `--check` gate for the double
diff surface. Its escape hatch is genuinely best-in-class (a type-checked function object). Its
"~60% reduction" is real for structure but ~45-55% blended once irreducible prose and the ragged
escape-hatch tail are counted honestly — the "85% for YAML" is largely a models-generation claim S5
declines to make.
