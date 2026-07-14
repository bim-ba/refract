# Bake-off entry: YAML-authored generator (S1 template-direct + S4 typed-IR)

**Strategies covered:** S1 (YAML → Jinja templates → committed quartet) **and** S4 (YAML → typed
IR → per-layer emitters). *Same YAML authoring surface; different internals.* Everything below is
grounded in the verbatim real code in `02-codebase-anatomy-and-op-pool.md` (re-read from source
during this pass — the quoted blocks in Part 2 are what the current tree actually contains).

Reference decisions inherited from `05-strategy-design-space.md`: committed source (not runtime),
`datamodel-code-generator` owns the `models.py` slice, and the escape hatch is a first-class
part of the schema, not an afterthought.

---

## 0. The shared authoring surface (S1 == S4 here)

**One YAML file per resource.** Directory encodes domain+resource; the filename is the resource:

```
specs/tracker/issues.yaml      specs/forms/surveys.yaml      specs/wiki/attachments.yaml
specs/tracker/comments.yaml    specs/forms/questions.yaml    specs/wiki/grids.yaml
specs/tracker/entities.yaml    specs/wiki/pages.yaml         specs/wiki/operations.yaml
```

A resource file is a header + an `operations:` list:

```yaml
domain: tracker
resource: issues
client_class: IssuesClient          # TrackerResource subclass name
mcp_server: tracker-issues          # FastMCP("tracker-issues")
operations:
  - name: get
    ...
```

`models.py` is **NOT** authored in this YAML. Per the settled research (05 §0.3) models come from
`datamodel-code-generator` (field skeletons from the vendored JSON-Schema/OpenAPI) plus
hand-authored validators. The op-spec only *references* model class names (`returns: Issue`,
`body.model: IssueCreate`). This keeps the YAML about *operations*, and puts the one place that
genuinely needs Python (a `@model_validator`, op #7) where Python belongs.

### 0.1 The spec schema is itself a pydantic model (the validation layer)

Both S1 and S4 parse each YAML file into this typed spec model **before** any codegen. A malformed
spec fails loudly at author time with a pydantic error, not with a broken emit. This is the
"real YAML schema-validation layer" the mandate asks for:

```python
# generator/spec.py — the schema the YAML is validated against (abridged)
from enum import StrEnum
from typing import Literal, Any
from pydantic import BaseModel, Field, model_validator

class ParamIn(StrEnum):
    path = "path"; query = "query"

class Param(BaseModel):
    name: str
    in_: ParamIn = Field(alias="in")
    type: str = "str"                       # rendered verbatim into the annotation
    alias: str | None = None                # uplink.Query("perPage")
    default: Any = ...                       # ... = no default (required positional)
    description: str | None = None          # -> Field(description=...) on the MCP surface

class Pagination(BaseModel):
    strategy: Literal["none", "offset", "cursor", "relative_cursor", "next_url"]
    page_size: int = 100
    extract: str                            # "page.result" | "page.results" | "page.root"
    next_of: str | None = None              # cursor: "page.next_cursor"
    id_of: str | None = None                # relative_cursor: "comment.id"
    wrap: str                               # SurveyList / CommentList / PageRefList
    public_name: str = "list"
    internal_name: str = "_list_page"

class Body(BaseModel):
    mode: Literal["none", "typed_model", "assemble", "raw_dict", "handler"] = "none"
    model: str | None = None
    dump: Literal["exclude_none", "by_alias_exclude_none", "plain"] = "exclude_none"
    split: bool = False                     # emit internal _verb + public wrapper
    allowlisted: bool = False               # raw_dict ARCH-3 exception -> test allowlist entry

class Ack(BaseModel):                        # bodyless-write return
    factory: Literal["deleted","published","unpublished","linked","unlinked","removed","cleared"]
    args: list[str]                          # ['"comment"', "comment_id"]; kwargs: on=/from_=
    kwargs: dict[str, str] = {}

class Guard(BaseModel):                       # require_found sentinel for get-style reads
    sentinel: str                            # "r.key is None"
    message: str

class Mcp(BaseModel):
    annotation: Literal["RO", "WRITE", "WRITE_IDEMPOTENT", "DESTRUCTIVE"]
    title: str
    docstring: str                           # hand-tuned prose — the one truly creative field
    name: str | None = None                  # default: <resource>_<op>
    guard: Guard | None = None
    body_dump: str | None = None             # override where MCP (not client) does the dump

class Poll(BaseModel):                         # async trigger -> poll-target linkage (op #10)
    target_client: str                       # "operations"
    target_method: str                       # "clone_get"
    terminal: str                            # "state.is_terminal"

class Operation(BaseModel):
    name: str                                # client method name
    verb: Literal["get","post","patch","delete","put"] | None = None
    path: str | None = None
    params: list[Param] = []
    body: Body = Body()
    returns: str                             # model name | "int" | "Ack" | "bytes"
    pagination: Pagination | None = None
    ack: Ack | None = None
    mcp: Mcp | None = None                    # None => not exposed over MCP (binary download)
    cli: "Cli | None" = None
    client_doc: str                          # client.py docstring incl. the Example block
    handler: str | None = None               # "module:fn" escape hatch — long tail
    poll: Poll | None = None

    @model_validator(mode="after")
    def _coherent(self) -> "Operation":
        if self.pagination and self.body.mode != "none":
            raise ValueError(f"{self.name}: a paginated list cannot also take a body")
        if self.handler is None and self.verb is None:
            raise ValueError(f"{self.name}: needs a verb+path or a handler")
        return self

class ResourceSpec(BaseModel):
    domain: str
    resource: str
    client_class: str
    mcp_server: str
    operations: list[Operation]
```

**Where S1 and S4 diverge (invisible to the author):**

- **S1** parses YAML → `ResourceSpec`, then hands the validated model straight to **Jinja
  templates** (`client.py.jinja`, `cli.py.jinja`, `mcp.py.jinja`). Each template is one big file
  with `{% if op.pagination %}…{% elif op.body.mode == "raw_dict" %}…{% elif op.handler %}…`
  branch ladders.
- **S4** parses YAML → `ResourceSpec`, then **lowers** it into a richer typed IR whose nodes are
  *per-shape* (`SimpleRead`, `PaginatedList`, `BodylessWrite`, `TypedBodyWrite`, `RawDictWrite`,
  `AsyncTrigger`, `HandlerOp`, `ScalarReturn`). Per-layer **emitter** classes dispatch on node
  *type* (a `match node:` / visitor), not on a growing `if`-ladder. The IR is the extension point.

`ResourceSpec` is a shallow, close-to-YAML shape; the S4 IR is a deeper, resolved shape. S1 skips
the lowering step and pays for it later in template complexity (see Part 3 / §S1-vs-S4).

---

## Part 1 — Authored spec for all 12 ops

Each block is the *complete* YAML a human writes. Prose (`docstring`, `client_doc`, `cli.help`) is
copied verbatim from today's code — under codegen it moves from Python into the spec unchanged, so
it is genuinely per-op, not boilerplate (see Part 3 authoring cost).

### Op 1 — `tracker issues_get` (trivial GET-by-id) — file `specs/tracker/issues.yaml`

```yaml
- name: get
  verb: get
  path: issues/{key}
  params:
    - {name: key, in: path, type: uplink.Path}
  returns: Issue
  client_doc: |
    ``GET /issues/{key}`` → a single ``Issue`` (raises on non-2xx).

    Example:
        >>> client = TrackerClient(oauth_token="…", organization_id="…")  # doctest: +SKIP
        >>> client.issues.get(key="DATAENGINEERING-1").status  # doctest: +SKIP
        'inProgress'
  mcp:
    annotation: RO
    title: Get Tracker issue
    guard:
      sentinel: "r.key is None"
      message: "issue {key!r} not found (got empty response — check key or permissions)"
    docstring: |
      A single Tracker issue by key (raises if not found).

      In production the Transport response hook raises ``YandexNotFoundError`` on a 404
      before this guard is reached. This check only fires for a 2xx response that carries
      an empty body (key=None) — an edge case unlikely in practice but defended here for
      safety (e.g. incorrect permissions returning a blank object instead of a 403).
  cli:
    help: "Print a single issue (full model) for KEY."
    args: [{name: key, type: KeyArg}]
```

### Op 2 — `forms surveys_list` (offset pagination + drain-to-limit) — `specs/forms/surveys.yaml`

The `pagination:` block *implies* the internal `_list_page` + public `list` split; no need to
declare two methods.

```yaml
- name: list
  verb: get
  path: surveys
  params:
    - {name: offset, in: query, type: uplink.Query, default: 0}
    - {name: limit,  in: query, type: uplink.Query, default: _PAGE_SIZE}
  returns: SurveyList
  pagination:
    strategy: offset
    page_size: 100                 # emits `_PAGE_SIZE = 100` module constant
    extract: page.result
    wrap: SurveyList
    public_name: list
    internal_name: _list_page
  client_doc: |
    One raw page of surveys at ``offset`` (page size ``limit``); internal — use ``list``.
  mcp:
    annotation: RO
    title: List Forms surveys
    paginated: true                # emits limit:int=0 + config + resolve_cap
    docstring: |
      Every form (survey) the caller can see, auto-paginated over the API's offset pages.

      Capped at YCLI_MAX_ITEMS (default 500) unless ``limit`` is given. Each item's ``id`` is the
      form id you pass to ``surveys_get`` / ``questions_list`` / ``answers_list``.
  cli:
    help: "List all forms (auto-paginated over offset pages; --all for everything)."
    paginated: true                # emits limit/all_ options + resolve_cap(..., all_=all_)
```

### Op 3 — `tracker comments_list` (relative-cursor drain) — `specs/tracker/comments.yaml`

Only the knobs change vs op 2: `strategy: relative_cursor`, `id_of:`, and the aliased `perPage`/`id`
query params. The emitter routes this through `TrackerResource._drain_relative`.

```yaml
- name: list
  verb: get
  path: issues/{key}/comments
  params:
    - {name: key,        in: path,  type: uplink.Path}
    - {name: per_page,   in: query, type: uplink.Query, alias: perPage, default: 100}
    - {name: comment_id, in: query, type: uplink.Query, alias: id,      default: null}
  returns: CommentList
  pagination:
    strategy: relative_cursor
    extract: page.root
    id_of: "str(comment.id) if comment.id is not None else None"
    wrap: CommentList
    public_name: list
    internal_name: _page
  client_doc: |
    One raw ``/issues/{key}/comments`` page (a bare JSON array); callers use ``list``.
  mcp:
    annotation: RO
    title: List Tracker issue comments
    paginated: true
    limit_field_desc: "Max comments to return; 0 means the YCLI_MAX_ITEMS cap (default 500)."
    docstring: |
      All comments on a Tracker issue, auto-paginated via the relative id-cursor.

      Capped at YCLI_MAX_ITEMS (default 500) unless ``limit`` is given, so very long threads
      are truncated at the cap rather than fetched forever.
```

### Op 4 — `tracker issues_create` (typed body + rich CLI flag→body mapping)

The MCP surface is trivially declarative (`body.mode: typed_model`). The rich CLI is expressed as a
**declarative option→body map** — `wrap: key_object` reproduces the `{"key": …}` wrapping, and
`fields_escape` reproduces the `body |= parse_fields(field)` tail (see Part 2 for the exact emit).

```yaml
- name: create
  verb: post
  path: issues/
  body: {mode: typed_model, model: IssueCreate, dump: exclude_none}
  returns: Issue
  client_doc: |
    ``POST /issues/`` — create from a ready body. Returns the created ``Issue``.

    Example:
        >>> client = TrackerClient(oauth_token="…", organization_id="…")  # doctest: +SKIP
        >>> client.issues.create(
        ...     {"queue": "DATAENGINEERING", "summary": "New", "type": {"key": "improvement"}}
        ... ).key  # doctest: +SKIP
        'DATAENGINEERING-200'
  mcp:
    annotation: WRITE
    title: Create Tracker issue
    docstring: "Create a Tracker issue; returns the new issue with its key."
  cli:
    help: 'Create an issue (POST /issues/). type/priority wrap to {"key": …}; queue/parent stay bare.'
    options:
      - {name: queue,    required: true, help: "Target queue key.",                 to: queue}
      - {name: summary,  required: true, help: "Issue summary (title).",            to: summary}
      - {name: type_,    flag: "--type", help: "Issue type key, e.g. task.",  wrap: key_object, to: type}
      - {name: priority, help: "Priority key, e.g. normal.",                 wrap: key_object, to: priority}
      - {name: parent,   help: "Parent issue key.",                                 to: parent}
      - {name: description, help: 'Markdown body — pass "$(cat file.md)".',         to: description}
      - {name: tag,      flag: "--tag", repeatable: true, help: "Tag (repeatable).", to: tags}
      - {name: field,    flag: ["--field", "-F"], fields_escape: true,
         help: "Extra field key=value (JSON-coerced; repeatable)."}
```

### Op 5 — `tracker comments_delete` (bodyless write → `Ack`; internal/public split)

`verb: delete` + no body + `ack:` ⇒ emitter produces the internal `_delete` (raw
`requests.Response`) and the public `delete` returning `None`; the MCP tool calls it and returns the
`Ack.deleted(...)` factory.

```yaml
- name: delete
  verb: delete
  path: issues/{key}/comments/{comment_id}
  params:
    - {name: key,        in: path, type: uplink.Path}
    - {name: comment_id, in: path, type: uplink.Path}
  returns: "None"
  raw_response: true               # internal _delete -> requests.Response, public returns None
  client_doc: |
    ``DELETE /issues/{key}/comments/{comment_id}`` (204, no body; internal).
  mcp:
    annotation: DESTRUCTIVE
    title: Delete Tracker issue comment
    ack: {factory: deleted, args: ['"comment"', comment_id], kwargs: {on: key}}
    docstring: |
      Permanently delete one comment from a Tracker issue (irreversible).

      Get ``comment_id`` from ``comments_list``. Returns an acknowledgement on success.
```

### Op 6 — `tracker transitions_execute` (action; open-ended `extra=allow` body)

Identical shape to a create, with two path params. `extra=allow` lives in the model
(`TransitionExecute`), so nothing extra is needed in the op spec.

```yaml
- name: execute
  verb: post
  path: issues/{key}/transitions/{transition_id}/_execute
  params:
    - {name: key,           in: path, type: uplink.Path}
    - {name: transition_id, in: path, type: uplink.Path}
  body: {mode: typed_model, model: TransitionExecute, dump: exclude_none}
  returns: TransitionList
  client_doc: |
    ``POST /issues/{key}/transitions/{id}/_execute`` → available transitions after move.

    Returns the transitions available for the issue in its new status,
    parsed as a ``TransitionList``.
  mcp:
    annotation: WRITE
    title: Execute Tracker issue transition
    docstring: |
      Move a Tracker issue through a workflow transition (change its status).

      Get ``transition_id`` from ``transitions_list``. ``body`` may be empty or carry issue
      fields to set on transition, e.g. a resolution when closing. Returns the transitions
      available from the new status.
```

### Op 7 — `forms questions_move` (ESCAPE HATCH: validator guard + CLI page=1 rescue)

The op spec is ordinary (typed-body write with an internal/public split, `dump:
by_alias_exclude_none`). The **irregular part** is two hand-written pieces the generator only
*references*:

1. The `model_validator` guard → lives in the hand-authored `QuestionMove` model (datamodel-codegen
   emits the fields; the validator sits in a `# region hand-authored` block the generator preserves).
2. The CLI's visible `--page 1` rescue → a `cli.handler` pointing at a hand-written command body.

```yaml
- name: move
  verb: post
  path: surveys/{survey_id}/questions/{question_id}/move
  params:
    - {name: survey_id,   in: path, type: uplink.Path}
    - {name: question_id, in: path, type: uplink.Path}
  body: {mode: typed_model, model: QuestionMove, dump: by_alias_exclude_none, split: true}
  returns: QuestionMoveResult
  client_doc: |
    ``POST /surveys/{id}/questions/{question_id}/move`` — reposition a question.
    ``body`` is a typed :class:`QuestionMove` naming the target page …
  mcp:
    annotation: WRITE
    title: Move Forms question
    passthrough_model: true        # MCP passes the typed model straight to client.move (no dump)
    params_desc:
      survey_id: "Form id (hex ObjectId) the question belongs to."
      question_id: "Question id (integer) to reposition."
      body: "Target placement: page / page_id / create_page and position."
    docstring: |
      Reposition a question on the form (target page + position); returns the moved question's id.

      ``body.position`` needs a page target to take effect — the underlying API silently ignores
      a bare position (200, nothing moves) — so ``QuestionMove`` raises a validation error if
      ``position`` is set with no ``page`` / ``page_id`` / ``question`` / ``create_page`` target;
      pass one explicitly (e.g. ``page=1``). Display-condition consistency is validated
      server-side — moving a question above one its conditions depend on is rejected.
  cli:
    handler: ycli.yandex.forms.questions.cli_handlers:move_command   # <-- the page=1 rescue
```

The escape-hatch model region (hand-authored, imported by the generated client — verbatim from
`forms/questions/models.py:585-598`):

```python
# forms/questions/models.py  — region preserved by the generator, never synthesized
@model_validator(mode="after")
def _require_target_for_position(self) -> QuestionMove:
    no_target = (
        self.page is None and self.page_id is None
        and self.question is None and not self.create_page
    )
    if self.position is not None and no_target:
        raise ValueError(
            "question move needs a target: pass page / page_id / question / create_page "
            "(a bare position is a silent no-op live)"
        )
    return self
```

### Op 8 — `wiki grids_update_cells` (structured cell payload + optimistic-lock `revision`)

Fully declarative. The `revision` optimistic lock is just a required field on the `CellsUpdate`
model — no generator support needed; it is *data in a model*.

```yaml
- name: update_cells
  verb: post
  path: grids/{grid_id}/cells
  params:
    - {name: grid_id, in: path, type: uplink.Path}
  body: {mode: typed_model, model: CellsUpdate, dump: exclude_none}
  returns: CellsUpdateResult
  client_doc: |
    ``POST /grids/{id}/cells`` — set individual cell values. ``body`` is a ``CellsUpdate``.
  mcp:
    annotation: WRITE_IDEMPOTENT
    title: Update Wiki grid cells
    params_desc:
      grid_id: GridIdParam       # reuse the shared Annotated type alias by name
      body: "``cells`` (each: ``row_id`` + ``column_slug`` + ``value``) + the current ``revision``."
    docstring: |
      Set the value of individual grid cells (addressed by row id + column slug).

      Repeating the same call sets the same values (idempotent). Returns the updated cells
      plus the grid's new ``revision``.
```

### Op 9 — `wiki attachments_upload` (ESCAPE HATCH: pipeline + base64/raw divergence)

The client method is pure orchestration business logic (create→upload_part→finish→attach) — the
generator does **not** synthesize it. It is a `handler:`. The generator's job shrinks to wiring the
two surfaces around the hand-written method, with the *one* CLI/MCP divergence declared explicitly
(`param: data` is `Base64Bytes` on MCP, `file_path → read_bytes()` on CLI).

```yaml
- name: upload
  handler: ycli.yandex.wiki.attachments.pipeline:upload   # client method is hand-written
  returns: AttachedFileList
  # no verb/path: this op makes 4 HTTP calls via the injected sessions client — not one request
  mcp:
    annotation: WRITE
    title: Upload file to Wiki page
    params:
      - {name: page_id,   type: int,          desc: "Numeric id of the page to attach the file to."}
      - {name: file_name, type: str,          desc: "Name to give the uploaded file."}
      - {name: data,      type: Base64Bytes,  desc: "The file's bytes, base64-encoded."}
    call: "client.attachments.upload(client.uploadsessions, page_id, file_name=file_name, data=data)"
    docstring: |
      Upload one small file and attach it to a wiki page in a single call.

      Runs the whole pipeline end to end: opens an upload session sized to ``data``, PUTs the
      bytes as a single part, finishes the session, and attaches it to the page. Small-file
      path — for large files drive ``uploadsessions_create`` / ``uploadsessions_upload_part``
      (chunked) / ``uploadsessions_finish`` + ``attachments_attach`` yourself. Returns the
      newly-attached files.
  cli:
    help: "Upload a local file and attach it to a page in one step (create→upload→finish→attach)."
    args:
      - {name: page_id,   type: "int (metavar PAGE_ID)", help: "Numeric page id."}
      - {name: file_path, type: "str (metavar FILE_PATH)", help: "Path to the local file to upload + attach."}
    body_from_disk: {file_name: "path.name", data: "path.read_bytes()"}   # raw-bytes path
    call: "client.attachments.upload(client.uploadsessions, page_id, file_name=path.name, data=path.read_bytes())"
```

The hand-written pipeline (verbatim from `wiki/attachments/client.py:137-164`) lives in
`attachments/pipeline.py` and is *imported* into the generated client class as the `upload` method
(the generator emits `upload = pipeline.upload` binding, or copies the file next to it). The
generator authored **zero** lines of the orchestration.

### Op 10 — `wiki pages_clone` + `operations_clone_get` (async trigger + poll target)

Two ops in two resource files, linked by `poll:`. The trigger is a normal typed-body write plus a
`poll:` block; the poll target is a trivial GET. The `poll:` block drives the CLI `--wait` codegen.

```yaml
# specs/wiki/pages.yaml
- name: clone
  verb: post
  path: pages/{page_id}/clone
  params:
    - {name: page_id, in: path, type: uplink.Path}
  body: {mode: typed_model, model: PageClone, dump: exclude_none}
  returns: PageCloneOperation
  poll: {target_client: operations, target_method: clone_get, terminal: "state.is_terminal"}
  client_doc: |
    ``POST /pages/{id}/clone`` — copy the page to a new address (async trigger).
    Returns a :class:`PageCloneOperation`; poll its ``operation.id`` via
    ``OperationsClient.clone_get`` until terminal. ``body`` is a dumped :class:`PageClone`.
  mcp:
    annotation: WRITE
    title: Clone Wiki page
    docstring: |
      Copy a page to a new address (``POST /pages/{id}/clone`` — asynchronous).

      Cloning is the only way to give content a new slug (slugs are permanent). The call
      returns a deferred operation reference — poll ``operations_clone_get`` with the
      returned ``operation.id`` until it reaches a terminal status.
  cli:
    wait: true                     # emits --wait/--no-wait + wait_for(...) loop over poll target
    help: "Copy a page to a new address (POST /pages/{id}/clone; async). --wait polls to completion."

# specs/wiki/operations.yaml
- name: clone_get
  verb: get
  path: operations/clone/{task_id}
  params:
    - {name: task_id, in: path, type: uplink.Path}
  returns: CloneOperationStatus
  client_doc: |
    ``GET /operations/clone/{task_id}`` → a page-clone's status (poll this to wait).
    Poll until ``is_terminal``; on ``success`` the ``result.page`` names the clone.
  mcp:
    annotation: RO
    title: Get Wiki page-clone operation status
    docstring: "Status of a page-clone operation by task id — poll until terminal."
```

### Op 11 — `tracker entities_comments_create` (god-resource sub-op)

The god-resource is one resource file whose op names carry the sub-noun (`comments_create`,
`checklists_edit_item`, …). `mcp.name` defaults to `<resource>_<op>` → `entities_comments_create`
for free. An optional `section: comments` groups the banner comments (`# ---- comments ----`) in the
emitted client.py.

```yaml
domain: tracker
resource: entities
client_class: EntitiesClient
mcp_server: tracker-entities
operations:
  # ... entity CRUD, then:
  - name: comments_create
    section: comments
    verb: post
    path: entities/{entity_type}/{entity_id}/comments
    params:
      - {name: entity_type, in: path, type: uplink.Path}
      - {name: entity_id,   in: path, type: uplink.Path}
    body: {mode: typed_model, model: CommentCreate, dump: by_alias_exclude_none}
    returns: Comment
    client_doc: |
      ``POST …/comments`` — add a comment. Returns the created comment.

      Example:
          >>> client.entities.comments_create(
          ...     "project", "655f", {"text": "Готово"}
          ... ).id  # doctest: +SKIP
          22
    mcp:
      # name auto-derives: entities_comments_create
      annotation: WRITE
      title: Add Tracker entity comment
      params_desc: {entity_type: TypeArg, entity_id: IdArg}   # reuse shared Annotated aliases
      docstring: "Add a comment to a Tracker entity; returns the created comment."
```

### Op 12 — `tracker entities_set_permissions` (ESCAPE HATCH: raw-dict, allowlisted)

A single flag (`body.mode: raw_dict, allowlisted: true`) makes the MCP surface take `body: dict`
instead of a typed model **and** emits the allowlist entry into `tests/test_architecture.py`. The
documented rationale rides in the `mcp.docstring` (it must be present, so the exception stays
self-documenting).

```yaml
- name: set_permissions
  section: permissions
  verb: patch
  path: entities/{entity_type}/{entity_id}/extendedPermissions
  params:
    - {name: entity_type, in: path, type: uplink.Path}
    - {name: entity_id,   in: path, type: uplink.Path}
  body: {mode: raw_dict, allowlisted: true}
  returns: ExtendedPermissions
  client_doc: |
    ``PATCH …/extendedPermissions`` — set access settings. Returns the new settings.
    The ``acl`` object accepts only ``grant`` / ``revoke`` actions …
  mcp:
    annotation: WRITE_IDEMPOTENT
    title: Set Tracker entity permissions
    params_desc: {entity_type: TypeArg, entity_id: IdArg}
    docstring: |
      Change an entity's access rules; returns the resulting permission set.

      ``body`` is the raw API payload; its ``acl`` object accepts only ``grant`` / ``revoke``
      actions, each mapping an access level (``READ``/``WRITE``/``GRANT``) to users/groups/roles,
      e.g. ``{"acl": {"grant": {"READ": {"users": ["8000000000000002"]}}}}``. Read the current
      ACL first with ``entities_permissions_get``.

      NOTE: intentionally ``dict`` (not a typed model) — the wire shape nests READ/WRITE/GRANT
      under ``grant``/``revoke`` verbs; the existing models describe a different (direct
      READ/WRITE/GRANT) shape and would misrepresent this endpoint's real body. Allowlisted in
      ``tests/test_architecture.py`` pending a correctly shaped model.
```

---

## Part 2 — Generated output for the 4 designated ops (diff-checked)

The generated blocks below are what the emitters produce; each is diff-checked against the verbatim
source read this pass. **The `# ty: ignore[...]` comments are derived deterministically** from the
param shapes, per a fixed rule the emitter applies:

| Condition | comment appended |
|---|---|
| any uplink body-less stub | `empty-body` |
| a `uplink.Query("alias")` typed param | `invalid-type-form` |
| a `uplink.Query`/`Path` param carrying a default | `invalid-parameter-default` |

Multiple conditions merge into one `# ty: ignore[a, b]`.

### Op 1 — `issues_get`

**client.py** (generated) vs `tracker/issues/client.py:17-26`:

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
✅ **Exact match.** The `@uplink.returns.json()` + `@uplink.get(path)` stack, the `uplink.Path`
signature, the return annotation, the `# ty: ignore[empty-body]`, and the docstring (carried from
`client_doc`) all reproduce.

**mcp.py** (generated) vs `tracker/issues/mcp.py:28-42`:

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
✅ **Exact match.** `annotation: RO` → `{**RO, "title": ...}`, `tags=TAGS` (RO ⇒ non-write tag set),
the `mcp.guard` block → the `require_found(...)` call with the exact sentinel + f-string message.
The path param `key` becomes the MCP param `key: str`; `client=Depends(tracker_client)` is invariant
wiring the emitter always appends.

**models.py** — *not* emitted from this op spec. `Issue` comes from datamodel-codegen (the
all-optional `KeyStr`/`DisplayStr` fields) + a hand tweak for the ref-flattening annotations. The op
spec only names it (`returns: Issue`). **This is the honest boundary: the YAML op-generator does not
own models.py.**

### Op 2 — `surveys_list` (the internal/public pagination split)

**client.py** (generated) vs `forms/surveys/client.py:18-49`. From the *single* `pagination:` block
the emitter produces the module constant, the internal `_list_page` uplink stub, and the public
`list` wrapper:

```python
_PAGE_SIZE = 100


class SurveysClient(FormsResource):
    """Declarative HTTP for ``/surveys`` (offset-paged list envelope + single get)."""

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
✅ **Structural + code match.** `strategy: offset` → `OffsetStrategy(extract=lambda page: page.result,
page_size=_PAGE_SIZE)`; `wrap: SurveyList` → `return SurveyList(surveys)`. The `# ty: ignore`
comments derive from the rule table (both query params carry defaults → `invalid-parameter-default`;
the stub → `empty-body`).

⚠️ **One divergence to flag honestly.** The real `list` docstring omits its `Example:` block above
(doc 02 trimmed it, but the live source at `client.py:39-43` *has* one). The generator only
reproduces prose that is present in `client_doc`. **Consequence: every hand-tuned docstring — public
*and* internal — must be authored verbatim into the spec.** For `surveys_list` that is two
docstrings (the `_list_page` one-liner and the multi-line public `list` with its Example). If the
author omits the public Example, the diff will not match the tree. This is a real authoring-fidelity
tax, not a generator bug (see Part 3).

**mcp.py** (generated) vs `forms/surveys/mcp.py:30-42`:

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
✅ **Exact match.** `mcp.paginated: true` is the switch that injects `limit: int = 0`, the extra
`config: AppConfig = Depends(app_config)` param, the `cap = resolve_cap(limit, config.max_items)`
line, and the `list_` name (Python-keyword-collision rename the emitter applies to `list`/`import`).

### Op 4 — `issues_create` (the rich-CLI-flag tension)

**mcp.py** (generated) vs `tracker/issues/mcp.py:106-111`:

```python
@mcp.tool(
    name="issues_create", annotations={**WRITE, "title": "Create Tracker issue"}, tags=WRITE_TAGS
)
def create(body: IssueCreate, client: TrackerClient = Depends(tracker_client)) -> Issue:
    """Create a Tracker issue; returns the new issue with its key."""
    return client.issues.create(body.model_dump(exclude_none=True))
```
✅ **Exact match.** `annotation: WRITE` ⇒ `{**WRITE, ...}` + `tags=WRITE_TAGS`; `body.mode:
typed_model, dump: exclude_none` ⇒ the `body: IssueCreate` param and `body.model_dump(exclude_none
=True)`.

**cli.py** (generated) vs `tracker/issues/cli.py:84-112`. The declarative `cli.options` map lowers to
the exact hand-written body assembly. Required options seed the initial dict; optional options become
`if x:` guards; `wrap: key_object` → `{"key": x}`; `fields_escape` → the `parse_fields` tail:

```python
@app.command()
def create(
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
✅ **Exact match** — including the `body |= parse_fields(field)` line and the ARCH-4
`Serializer.serialize(...)` tail (invariant, always emitted). `FieldOpt` is a module-level shared
alias the emitter references by name (declared once per file from a `cli.aliases` header, not shown).

**Honest note:** the `cli.options` DSL here is *expressive enough for this op* but it is a small
language of its own (`wrap`, `fields_escape`, `required`, `repeatable`, `to`). It reproduces
`issues_create`/`issues_update` cleanly, but see Part 3 — the moment a CLI needs conditional logic
the DSL cannot express (e.g. op #7's page=1 rescue), it must drop to `cli.handler`. That boundary is
where the "declarative CLI" thesis is weakest.

### Op 9 — `attachments_upload` (what the escape hatch produces)

The generator emits **only the two surfaces**; the client `upload` method is the hand-written
`handler:`. Generated **mcp.py** vs `wiki/attachments/mcp.py:73-95`:

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
    """Upload one small file and attach it to a wiki page in a single call.

    Runs the whole pipeline end to end: opens an upload session sized to ``data``, PUTs the
    bytes as a single part, finishes the session, and attaches it to the page. Small-file
    path — for large files drive ``uploadsessions_create`` / ``uploadsessions_upload_part``
    (chunked) / ``uploadsessions_finish`` + ``attachments_attach`` yourself. Returns the
    newly-attached files.
    """
    return client.attachments.upload(client.uploadsessions, page_id, file_name=file_name, data=data)
```
✅ **Exact match.** The `mcp.params` list (each with `type` + `desc`) → the `Annotated[T,
Field(description=...)]` params; `mcp.call` → the delegating return line. The `Base64Bytes` import is
added because a param uses it (import-tracking is a mechanical emitter concern).

Generated **cli.py** vs `wiki/attachments/cli.py:97-114`:

```python
@app.command()
def upload(
    ctx: typer.Context,
    page_id: Annotated[int, typer.Argument(metavar="PAGE_ID", help="Numeric page id.")],
    file_path: Annotated[
        str, typer.Argument(metavar="FILE_PATH", help="Path to the local file to upload + attach.")
    ],
) -> None:
    """Upload a local file and attach it to a page in one step (create→upload→finish→attach)."""
    app_ctx = AppContext.from_typer_context(ctx)
    path = Path(file_path)
    result = app_ctx.wiki.attachments.upload(
        app_ctx.wiki.uploadsessions,
        page_id,
        file_name=path.name,
        data=path.read_bytes(),
    )
    Serializer.serialize(result, app_ctx.strategy, app_ctx.console)
```
✅ **Match** — the `cli.body_from_disk` directive produces the `path = Path(file_path)` +
`file_name=path.name, data=path.read_bytes()` divergence (raw bytes), vs MCP's `Base64Bytes`. This
is the one op where CLI and MCP genuinely differ, and the spec expresses the difference as two small
declarative hints rather than one shared body model.

The **client** `upload` method is **not shown as generated** because it isn't — it is
`wiki/attachments/client.py:137-164` verbatim, hand-written, imported via `handler:`. ✅ The
generator reproduced 0 of its 28 lines and wired both surfaces around it correctly. **This is the
escape hatch working as designed: the long tail did not block generation of the surfaces.**

---

## Part 3 — Honest assessment

### 3.1 Authoring cost for the 12 ops

Rough authored-YAML line counts (prose included, since it moves verbatim into the spec):

| Op | Authored YAML lines | of which irreducible prose (docstrings/help) |
|---|---:|---:|
| 1 issues_get | ~28 | ~18 |
| 2 surveys_list | ~26 | ~12 |
| 3 comments_list | ~28 | ~13 |
| 4 issues_create | ~30 | ~9 (+ CLI option map ~10 structural) |
| 5 comments_delete | ~18 | ~7 |
| 6 transitions_execute | ~24 | ~15 |
| 7 questions_move | ~26 YAML + ~13 hand Python (validator) + ~12 hand Python (cli handler) | ~18 |
| 8 grids_update_cells | ~20 | ~9 |
| 9 attachments_upload | ~24 YAML + ~28 hand Python (pipeline, already exists) | ~16 |
| 10 pages_clone (+clone_get) | ~34 | ~20 |
| 11 entities_comments_create | ~22 | ~7 |
| 12 entities_set_permissions | ~24 | ~18 |

**Headline: ~330–360 authored YAML lines for all 12 ops, plus ~53 lines of hand-written Python
across the 2 escape-hatch handlers (#7 validator + cli, #9 pipeline).** That YAML replaces roughly
**1,050–1,150 lines** of committed `client.py`/`cli.py`/`mcp.py` the emitters produce (models.py
excluded — it isn't in scope). So the *structural* boilerplate collapses ~3–3.5×.

**But be honest about the composition:** ~45–55% of the authored YAML is **prose** (the hand-tuned
MCP docstrings, CLI help, and client `Example:` blocks) that is *genuinely per-op and irreducible* —
it must be authored verbatim or the generated tree won't match. The real savings are in the
mechanical surfaces: the uplink decorator stacks, the `Depends(...)` wiring, every `model_dump(...)`
call, the `resolve_cap` plumbing, the internal/public split, the `Ack` factory calls, and the three
registration lines per resource (domain client/cli/mcp) — all of which drop to **zero** authored
lines. For a trivial op like `issues_get`, authoring goes from ~35 Python lines across three files
to ~28 YAML lines in one — not a dramatic win, because the prose dominates. **The easy case does NOT
collapse to near-zero; it collapses to "just the prose."** The dramatic wins are on the
*high-boilerplate* ops (paginated lists, bodyless writes, async triggers) where the structural
scaffolding is large relative to the prose.

### 3.2 Escape-hatch cleanliness (#7 / #9 / #12)

- **#12 set_permissions (raw dict): cleanest.** A single `body.mode: raw_dict, allowlisted: true`
  flag. The generator emits `body: dict`, passes it straight through, *and* auto-emits the
  `tests/test_architecture.py` allowlist entry. Zero hand Python. The self-documenting NOTE rides in
  the required `mcp.docstring`. **This is the escape hatch at its best: a declared exception, not a
  hole.**
- **#9 attachments_upload (pipeline): clean, but the boundary is coarse.** `handler:` cleanly
  offloads the whole client method — the generator wires both surfaces around 28 lines of
  hand-written orchestration it never touches. The base64/raw divergence is two small declarative
  hints. The one wart: the op has **no `verb`/`path`** (it's 4 HTTP calls), so the spec model needs
  the `handler ⇒ verb optional` special-case (already in the `_coherent` validator). That's honest —
  a pipeline is *not* an HTTP method, and pretending otherwise would be the lie.
- **#7 questions_move (validator + cli rescue): messiest, and this is where honesty matters most.**
  The op spec is ordinary, but the irregular behaviour splits across **two** hand-written locations
  that the generator only *references*: the `@model_validator` (in models.py, a preserved region)
  and the `cli.handler` (a whole hand-written command body). Neither is expressible as data. The
  worry: a `cli.handler` opts the *entire* CLI command out of codegen — including the boilerplate
  (`AppContext.from_typer_context`, the `Serializer.serialize` tail) — so the human re-writes the
  wrapper too, or the generator must offer a "handler body + generated frame" hybrid (a partial
  escape hatch), which is more machinery. **The long tail never *blocks* generation — but #7 shows
  the escape hatch is not always a clean one-liner; sometimes it is "write two Python functions and
  trust the generator to import them."**

**Does the long tail ever block generation? No.** In all three cases the generator produces a valid
tree by delegating. That is the design's core strength and it holds across the pool.

### 3.3 Extensibility — the C1 north star (op-shape #21, unforeseen)

This is where **S1 and S4 diverge sharply.** Take op-shape #21 = a **Server-Sent-Events stream** (a
`GET` that yields an event stream the client must iterate, with a new `StreamStrategy` and an MCP
tool that returns a *summary* of the drained stream) — a shape nothing in the current schema
anticipates.

- **Under S1 (template-direct):** you add a new `{% elif op.stream %}` arm to **each** of
  `client.py.jinja`, `mcp.py.jinja`, and probably `cli.py.jinja`. Each template is already a ladder
  of `{% if pagination %}{% elif raw_response %}{% elif body.mode == "raw_dict" %}{% elif handler
  %}…`; #21 makes it longer. Three risks compound: (a) Jinja has **no type checking** — a typo in
  `op.stream.event_field` fails only at emit time, on that one op; (b) the new arm sits *inside* the
  file that also emits the 85% of normal ops, so a mistake can regress them; (c) there is no compiler
  forcing you to handle #21 in all three templates — miss `cli.py.jinja` and you silently emit a
  resource with no CLI command, caught only by the ARCH-1 parity test *if* you remembered to wire it.
  Cost: **3 template edits, untyped, in shared files, no exhaustiveness guarantee.**
- **Under S4 (typed IR + emitters):** you add one IR node class `SseStream(OperationIR)` (typed
  fields, `ty`-checked), one `lower_sse()` clause in the spec→IR lowering, and one `emit()` method
  per affected emitter. Because emitters dispatch on node *type* via `match node:` (or a visitor),
  Python's checker — and a `case _: assert_never(node)` — **forces** you to handle `SseStream` in
  every emitter that must, or the build fails at *type-check* time, not at emit or (worse) at CI
  parity. The other node types (the 85%) are untouched: their `emit()` clauses don't change. Adding
  a **second consumer** (op-shape stays fixed, you now also want a TS SDK or a docs page) is *one new
  emitter over the existing IR*, zero changes to the 20 existing node types. Cost: **one typed node
  + N localized emitter clauses, checker-enforced exhaustiveness.**

Concretely, the two-legged-OAuth-dance variant of #21 is the same story: S1 threads a new set of
Jinja conditionals through the auth-related sections of `client.py.jinja`; S4 adds an `OAuthFlow` IR
node and the affected emitter clauses, and the `ty` checker lists every emitter that must react.

**Verdict: for the *first handful* of resources S1 wins on time-to-value (no IR to build, templates
are immediately legible). Past ~5 op-shapes — which the 20-op pool already exceeds — the S1
templates become a branch-ladder no type checker guards, and S4's IR earns its keep: it converts
"did I remember to handle this everywhere?" from a runtime/CI question into a compile-time one.** The
05-doc's "S1→S4 is an evolution path" is right: start S1, extract the IR the first time you add an
op-shape and feel the template ladder fight back, or the first time a second surface appears.

### 3.4 Invariant fit (py.typed / coverage / ARCH-1..11 / reviewable diffs)

- **py.typed / ARCH-2 HTTP confinement / ARCH-4 serialization:** clean. Committed `.py` means
  downstream type-checkers see everything; only the client emitter imports `uplink`; the cli emitter
  always ends with `Serializer.serialize(...)`. All satisfied *by construction*.
- **ARCH-3 honest annotations:** the `mcp.annotation` enum *is* the source of truth — the emitter
  stamps the matching `{**RO|WRITE|WRITE_IDEMPOTENT|DESTRUCTIVE}` dict and the `write` tag. This is
  arguably *better* than hand-authoring, where a human can pick the wrong dict. ✅
- **ARCH-1 four-surface parity + ARCH-6 name snapshots:** parity holds by construction (the emitter
  emits all four + registers all three tiers); the snapshot test becomes a **free
  generator-correctness check**. ✅
- **100% coverage gate — the sharp edge.** The generator MUST also emit the per-op tests, or every
  generated op ships uncovered and the `--cov-fail-under=100` gate goes red. This is the single
  biggest cost and it is *not* optional. It is tractable (the test shapes are as regular as the
  code — a get-test, a paginate-drain-test, an ack-test), but the escape-hatch ops (#7 validator, #9
  pipeline) need **hand-written** tests for their hand-written Python, and those tests must be
  authored alongside the handler. So the escape hatch has a coverage tail too: `handler:` code needs
  `handler:` tests.
- **Reviewable diffs:** committed generated source means a PR shows real Python — reviewable. But a
  one-line YAML change can produce a large multi-file diff; reviewers must learn to read the *spec*
  diff as the source of truth and skim the emitted churn. A `--check` CI mode (regenerate, assert
  no-diff) is mandatory to stop hand-edits to generated files drifting.

### 3.5 The failure mode at scale (50 → 200 resources)

- **YAML stringly-typing rot.** `type: uplink.Path`, `id_of: "str(comment.id) if …"`,
  `sentinel: "r.key is None"` are **Python-as-strings** the pydantic spec layer can syntax-check only
  shallowly. At 200 resources the odds that some `extract: page.reslut` typo slips through to emit
  time rise; the schema-validation layer catches *shape* errors, not *semantic* ones inside the
  embedded expressions. (This is the exact weakness S5's Python-descriptor authoring surface removes —
  those expressions become real, checked Python.)
- **Prose duplication.** The near-identical `me_get` docstrings (op #20 family), the repeated
  "Capped at YCLI_MAX_ITEMS (default 500)…" paginated-list boilerplate, the shared "Get X from
  Y_list" phrasings — at scale these want a *snippet/include* mechanism, or the YAML accumulates
  copy-paste prose that drifts. Neither S1 nor S4 solves this for free; it needs a `docstring
  fragments` include feature, which is more schema.
- **The god-resource (`entities`, 33 tools/626 lines).** One resource file with 33 ops, several
  `section:`-grouped, several needing `handler:`/`raw_dict`. This file becomes a 700-line YAML that
  is *itself* hard to review — the pathological case the 05-doc flags. At 200 resources you will have
  a handful of these, and they are where the "concise YAML" promise frays most. Realistic answer:
  regenerate the regular 85% of resources and **leave the god-resource hand-written** (or half-generate
  it), which the escape hatch permits but which dents the "everything is generated" story.
- **Template-ladder rot (S1 specifically).** As covered in 3.3, the S1 templates grow one branch per
  op-shape; by 200 resources you will have accreted enough shapes that `mcp.py.jinja` is a
  hard-to-follow conditional forest. S4 pushes that complexity into typed IR nodes the checker
  guards — the failure mode there is instead "the IR has 25 node types and the lowering step is the
  thing to understand," which is at least *typed* and *localized*.

**Bottom line.** YAML authoring delivers a real ~3× structural-boilerplate cut and an escape hatch
that never blocks generation, at the cost of (a) irreducible verbatim prose that must be re-authored,
(b) embedded-Python-as-strings the schema layer can't fully check, and (c) a mandatory test-emitter
to hold the coverage gate. **S1 is the right *starting* internal (fastest to first value, legible
templates); S4's typed IR is the right *destination* once op-shape variety passes ~5 (which this
codebase already has) or a second output surface appears — and the migration between them is additive,
not a rewrite.** The YAML-vs-Python-descriptor authoring question (S1/S4 vs S5) is orthogonal and
turns on whether you want the embedded expressions type-checked (§3.5's rot) or portable to a
non-Python consumer.
