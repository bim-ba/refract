# ycli codebase anatomy + a diverse operation pool

Research artifact for designing a per-resource code generator. All code quoted verbatim with
`path:line-range` citations, read-only (no files modified). Repo root: `/home/sava/dev/dev/ycli`.

---

## PART A — Anatomy: invariant skeleton vs. per-operation variation

### A.1 The "quartet" — one resource, four files

Every resource lives at `src/ycli/yandex/<domain>/<resource>/{client.py,cli.py,mcp.py,models.py}`.
Domains: `tracker` (33 resources), `wiki` (10), `forms` (10), plus a tiny `status` domain
(auth probe / whoami wrapper, not counted).

```
src/ycli/yandex/tracker/issues/{client.py,cli.py,mcp.py,models.py}
src/ycli/yandex/wiki/pages/{client.py,cli.py,mcp.py,models.py}
src/ycli/yandex/forms/surveys/{client.py,cli.py,mcp.py,models.py}
```

### A.2 Cross-cutting machinery (`src/ycli/yandex/*.py`)

| File | Owns |
|---|---|
| `base.py` | `BaseYandex` (uplink.Consumer; required-`session` DI ctor + `base_url` ClassVar) and `DomainClient` (shared 5-arg ctor for the 3 domain composition roots: builds one `Transport.session`, then calls the subclass's `_wire`) |
| `models.py` | `APIModel` (pydantic base, `extra="ignore"`, `populate_by_name=True`); `Ack` (typed no-body-write ack + 6 factory classmethods: `deleted/published/unpublished/linked/unlinked/removed/cleared`); `require_found` (turns a lenient all-`None` 404 into `ValueError`); `KeyStr`/`IdStr`/`DisplayStr`/`DisplayNameStr` (`BeforeValidator`-based ref-flattening annotations) |
| `pagination.py` | 4 pure `PaginationStrategy` subclasses (below) + `resolve_cap(limit, max_items, all_=False)` |
| `polling.py` | `poll(fetch, is_done, attempts=30, backoff=default_backoff, sleep=time.sleep, on_attempt=None)` + `default_backoff` (0.5·2ⁿ capped 60s) |
| `errors.py` | `YandexError` hierarchy: `YandexAuthError`(401/403) / `YandexNotFoundError`(404) / `YandexRateLimitError`(429) / `YandexServerError`(5xx) / `YandexClientError`(other 4xx) / `YandexTimeoutError` (client-side poll timeout, no HTTP status) |
| `transport.py` | `Transport.session(*, oauth_token, organization_id, timeout_seconds, retries, base=None)` — builds one authed `requests.Session`: `Authorization: OAuth <token>` + `X-Org-Id` header, a response hook mapping non-2xx → typed error, a `urllib3.Retry` adapter (GET/HEAD/OPTIONS only, backoff on 429/5xx) |
| `mcp.py` | `RO`/`WRITE`/`WRITE_IDEMPOTENT`/`DESTRUCTIVE` annotation dicts + `WRITE_TAG="write"`; `CachedProvider[T]`; `make_cached_client(client_cls)` (returns a `@cache`d zero-arg provider); `app_config()` (`@cache`d `AppConfig()`) |
| `factory.py` | `ClientFactory.build(client_cls, credentials, config)` — the one place that maps `Credentials`+`AppConfig` → a domain client's raw ctor args (env-free) |

**Pagination strategies (pagination.py) — pick one per LIST operation:**

| Strategy | Cursor mechanic | Used by |
|---|---|---|
| `CursorStrategy` | envelope's own `next_cursor`/`next` field | Wiki descendants, grids, attachments |
| `NextUrlStrategy` | HATEOAS — full next-page URL in the envelope | (declared; not exercised by a live resource in this pass) |
| `OffsetStrategy` | integer `offset` advanced by `page_size`; short page = done | Forms `/surveys` |
| `RelativeCursorStrategy` | next cursor = **last item's own id** (not an envelope field) | Tracker comments, entity history/comments, changelog, worklog, users, boards |

`TrackerResource._drain_relative` (`tracker/base.py:19-40`) wraps `RelativeCursorStrategy` with the
`min(max_page_size, limit)` first-page clamp shared by all 7 Tracker relative-cursor drains.

### A.3 Per-domain base + dependencies (`<domain>/base.py`, `<domain>/dependencies.py`)

- `<Domain>Resource(BaseYandex)` — sets only `base_url: ClassVar[str]` (e.g.
  `TrackerResource` → `https://api.tracker.yandex.net/v3`, `WikiResource` →
  `https://api.wiki.yandex.net/v1`, `FormsResource` → `https://api.forms.yandex.net/v1`).
  Tracker's also carries `_drain_relative` (the only domain with relative-cursor resources).
- `<domain>/dependencies.py` — re-exports `RO`/`WRITE`/`WRITE_IDEMPOTENT`/`DESTRUCTIVE`/`app_config`
  from the shared `ycli.yandex.mcp`, plus domain-local `TAGS = {"tracker"}` /
  `WRITE_TAGS = TAGS | {WRITE_TAG}` and `<domain>_client = make_cached_client(<Domain>Client)`.
  Every resource's `mcp.py` imports its `Depends(<domain>_client)` factory from here — never
  constructs a client itself.

### A.4 Domain composition root (`<domain>/client.py`)

```python
class TrackerClient(DomainClient):
    def _wire(self, transport: requests.Session) -> None:
        self.me = MeClient(session=transport)
        self.issues = IssuesClient(session=transport)
        ...  # one line per resource, 33 lines for tracker
```
Registration is a flat attribute assignment per resource client, all sharing the ONE
`requests.Session` the base `DomainClient.__init__` built. (`tracker/client.py:52-84`)

### A.5 Registration chain (3 tiers, CLI and MCP mirror each other)

```
resource client  → domain client.py:  self.<resource> = <Resource>Client(session=transport)
resource cli.py  → domain cli.py:     app.add_typer(<resource>_app)
domain cli.py    → root cli/app.py:   app.add_typer(<domain>_app)

resource mcp.py  → domain mcp.py:     mcp.mount(<resource>_mcp)
domain mcp.py    → root mcp/server.py: mcp.mount(<domain>_mcp, namespace="<domain>")
```
Root files: `src/ycli/cli/app.py:64-69`, `src/ycli/mcp/server.py:30-33`.

### A.6 What is INVARIANT across every operation

- **client.py**: no `from __future__ import annotations` (uplink reads annotations eagerly);
  `@uplink.returns.json()` + `@uplink.json` (if body) + `@uplink.<verb>("path/{param}")` stack;
  path params are `uplink.Path`, query params `uplink.Query` (optionally aliased,
  `uplink.Query("perPage")`), body is a single `uplink.Body`; every public method has a
  doctest-style `Example:` docstring with `# doctest: +SKIP`; a raw/no-JSON write (204, or a
  200 the caller must not trust the body of) is wrapped: an **internal** `_verb` uplink method
  returning `requests.Response`, plus a **public** hand-written wrapper method that calls it and
  returns `None` or a synthesized `Ack`.
- **mcp.py**: `mcp = FastMCP("<domain>-<resource>")`; every tool is
  `@mcp.tool(name="<resource>_<op>", annotations={**RO|WRITE|WRITE_IDEMPOTENT|DESTRUCTIVE, "title": "..."}, tags=TAGS|WRITE_TAGS)`;
  every function takes `client: <Domain>Client = Depends(<domain>_client)` as the last
  parameter; reads return a model directly, writes take a typed pydantic body parameter
  (or occasionally a raw `dict` — see §B.18) and call `body.model_dump(exclude_none=True)`
  (often `by_alias=True` too) before handing it to the client.
- **cli.py**: `app = typer.Typer(name="<resource>", help="...", no_args_is_help=True)`;
  every command takes `ctx: typer.Context` first, resolves `AppContext.from_typer_context(ctx)`,
  and ends with `Serializer.serialize(result, app_ctx.strategy, app_ctx.console)` (ARCH-4 — the
  only place output rendering happens); list commands additionally take `limit: LimitOption = 0`
  and `all_: AllOption = False` and call `resolve_cap(limit, app_ctx.config.max_items, all_=all_)`.
- **models.py**: every model subclasses `APIModel`; every field is optional
  (`| None = None` / `= Field(default=None, ...)`) because the API's "lenient parse" contract
  means a 404 or filtered response can omit any field; list responses are either a bare
  `RootModel[list[X]]` (`IssueList`, `CommentList`, ...) or an internal per-page envelope model
  consumed only inside `client.py` and never exposed publicly; write bodies are separate
  `*Create`/`*Update` models (never the read model), each field carrying a human
  `Field(description=...)` (this text becomes the MCP JSON-schema description an agent sees).
- **DI**: never `from_env`; the client's own `__init__` takes `session: requests.Session`
  (or, at the domain root, `oauth_token`/`organization_id`/`timeout_seconds`/`retries`) as
  explicit constructor args; env is read exactly once, at a composition root
  (`AppContext`/`Credentials()`+`AppConfig()` for CLI, the cached `dependencies.py` provider
  for MCP).

### A.7 What VARIES per operation

| Axis | Where it shows up |
|---|---|
| HTTP verb + path template | the `@uplink.<verb>("...")` decorator string |
| Path / query / body params | the method signature's `uplink.Path`/`uplink.Query`/`uplink.Body` args |
| Return model | the method's return type annotation |
| Pagination strategy | which `PaginationStrategy` subclass (or none) the public wrapper method picks |
| MCP annotation class + tags | `RO` / `WRITE` / `WRITE_IDEMPOTENT` / `DESTRUCTIVE`, `TAGS` vs `WRITE_TAGS` |
| Docstring / CLI help | hand-tuned prose — the single largest "creative" surface per operation |
| Model fields | per-resource, obviously |

---

## PART B — 20 genuinely diverse operations

Each entry: shape → client.py → mcp.py → cli.py (where relevant) → models. All quoted verbatim.

### 1. Simple GET-by-id — `tracker issues_get`

Path param → model, no query/body.

```python
# src/ycli/yandex/tracker/issues/client.py:17-26
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

```python
# src/ycli/yandex/tracker/issues/mcp.py:28-42
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

Model: `Issue(APIModel)` — `tracker/issues/models.py:14-31` (all-optional fields, `KeyStr`/`DisplayStr` ref-flattening).

---

### 2. LIST offset/page pagination + drain-to-limit — `forms surveys_list`

```python
# src/ycli/yandex/forms/surveys/client.py:24-49
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

```python
# src/ycli/yandex/forms/surveys/mcp.py:30-42
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

CLI drives the same `resolve_cap` with the extra `--all` flag:
```python
# src/ycli/yandex/forms/surveys/cli.py:51-60
@app.command("list")
def list_(ctx: typer.Context, limit: LimitOption = 0, all_: AllOption = False) -> None:
    """List all forms (auto-paginated over offset pages; --all for everything)."""
    app_ctx = AppContext.from_typer_context(ctx)
    cap = resolve_cap(limit, app_ctx.config.max_items, all_=all_)
    Serializer.serialize(app_ctx.forms.surveys.list(limit=cap), app_ctx.strategy, app_ctx.console)
```

Models: `Survey`, `SurveysResponse` (internal per-page envelope `{links, result}`), `SurveyList = RootModel[list[Survey]]` — `forms/surveys/models.py:12-60`.

---

### 3. LIST cursor pagination — `wiki pages_descendants`

```python
# src/ycli/yandex/wiki/pages/client.py:59-97
@uplink.returns.json()
@uplink.get("pages/descendants")
def _descendants_page(
    self,
    slug: uplink.Query,
    page_size: uplink.Query = 100,  # ty: ignore[invalid-parameter-default]
    cursor: uplink.Query = None,  # ty: ignore[invalid-parameter-default]
    actuality: uplink.Query = None,  # ty: ignore[invalid-parameter-default]
) -> DescendantsResponse:  # ty: ignore[empty-body]
    """One raw page of ``{id, slug}`` refs + ``next_cursor``. Internal; callers use ``descendants``."""

def descendants(
    self, slug: str, *, limit: int | None = None, actuality: str | None = None
) -> PageRefList:
    """All descendant refs under ``slug``, draining ``next_cursor`` internally.

    Capped at ``limit``.
    """
    return CursorStrategy.collect_wrapped(
        lambda cursor: self._descendants_page(
            slug=slug, page_size=100, cursor=cursor, actuality=actuality
        ),
        extract=lambda page: page.results,
        next_of=lambda page: page.next_cursor,
        wrap=PageRefList,
        limit=limit,
    )
```

```python
# src/ycli/yandex/wiki/pages/mcp.py:47-59
@mcp.tool(
    name="pages_descendants", annotations={**RO, "title": "List Wiki page descendants"}, tags=TAGS
)
def descendants(
    slug: str,
    limit: int = 0,
    client: WikiClient = Depends(wiki_client),
    config: AppConfig = Depends(app_config),
) -> PageRefList:
    """All descendant refs under SLUG, auto-paginated. Capped at YCLI_MAX_ITEMS (default 500)
    unless ``limit`` is given; narrow by SLUG for large trees."""
    cap = resolve_cap(limit, config.max_items)
    return client.pages.descendants(slug=slug, limit=cap)
```

Models: `PageRef`, `DescendantsResponse` (internal envelope `{results, next_cursor}`), `PageRefList = RootModel[list[PageRef]]` — `wiki/pages/models.py:59-97`.

---

### 4. LIST relative-cursor drain — `tracker comments_list`

```python
# src/ycli/yandex/tracker/comments/client.py:16-46
@uplink.returns.json()
@uplink.get("issues/{key}/comments")
def _page(
    self,
    key: uplink.Path,
    per_page: uplink.Query("perPage") = 100,  # ty: ignore[invalid-type-form]
    comment_id: uplink.Query("id") = None,  # ty: ignore[invalid-type-form]
) -> CommentList:  # ty: ignore[empty-body]
    """One raw ``/issues/{key}/comments`` page (a bare JSON array); callers use ``list``."""

def list(self, key: str, *, limit: int | None = None) -> CommentList:
    """All comments on an issue, draining the ``id=<last comment id>`` relative cursor.

    ``GET /issues/{key}/comments`` returns one page at a time (50 comments by default);
    each next page repeats with ``id=<id of the last comment seen>`` until a page comes
    back empty. Capped at ``limit`` (``None`` = every comment).
    """
    comments = self._drain_relative(
        extract=lambda page: page.root,
        id_of=lambda comment: str(comment.id) if comment.id is not None else None,
        fetch_page=lambda cursor, per_page: self._page(
            key, per_page=per_page, comment_id=cursor
        ),
        limit=limit,
    )
    return CommentList(comments)
```

```python
# src/ycli/yandex/tracker/comments/mcp.py:28-46
@mcp.tool(
    name="comments_list", annotations={**RO, "title": "List Tracker issue comments"}, tags=TAGS
)
def list_(
    key: str,
    limit: Annotated[
        int,
        Field(description="Max comments to return; 0 means the YCLI_MAX_ITEMS cap (default 500)."),
    ] = 0,
    client: TrackerClient = Depends(tracker_client),
    config: AppConfig = Depends(app_config),
) -> CommentList:
    """All comments on a Tracker issue, auto-paginated via the relative id-cursor.

    Capped at YCLI_MAX_ITEMS (default 500) unless ``limit`` is given, so very long threads
    are truncated at the cap rather than fetched forever.
    """
    cap = resolve_cap(limit, config.max_items)
    return client.comments.list(key, limit=cap)
```

Model: `Comment` / `CommentList` — `tracker/comments/models.py:13-33`.

---

### 5. CREATE with a rich nested body — `tracker issues_create`

```python
# src/ycli/yandex/tracker/issues/client.py:56-68
@uplink.returns.json()
@uplink.json
@uplink.post("issues/")
def create(self, body: uplink.Body) -> Issue:  # ty: ignore[empty-body]
    """``POST /issues/`` — create from a ready body. Returns the created ``Issue``.

    Example:
        >>> client = TrackerClient(oauth_token="…", organization_id="…")  # doctest: +SKIP
        >>> client.issues.create(
        ...     {"queue": "DATAENGINEERING", "summary": "New", "type": {"key": "improvement"}}
        ... ).key  # doctest: +SKIP
        'DATAENGINEERING-200'
    """
```

```python
# src/ycli/yandex/tracker/issues/mcp.py:106-111
@mcp.tool(
    name="issues_create", annotations={**WRITE, "title": "Create Tracker issue"}, tags=WRITE_TAGS
)
def create(body: IssueCreate, client: TrackerClient = Depends(tracker_client)) -> Issue:
    """Create a Tracker issue; returns the new issue with its key."""
    return client.issues.create(body.model_dump(exclude_none=True))
```

```python
# src/ycli/yandex/tracker/issues/cli.py:84-112  (rich flag-to-body construction)
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

Model: `IssueCreate(APIModel)`, `model_config = ConfigDict(extra="allow")` (custom queue-local
fields escape hatch) — `tracker/issues/models.py:43-71`.

---

### 6. Partial UPDATE / PATCH — `tracker issues_update`

```python
# src/ycli/yandex/tracker/issues/client.py:70-82
@uplink.returns.json()
@uplink.json
@uplink.patch("issues/{key}")
def update(self, key: uplink.Path, body: uplink.Body) -> Issue:  # ty: ignore[empty-body]
    """``PATCH /issues/{key}`` — update fields. Returns the updated ``Issue``."""
```

```python
# src/ycli/yandex/tracker/issues/mcp.py:114-124
@mcp.tool(
    name="issues_update",
    annotations={**WRITE_IDEMPOTENT, "title": "Update Tracker issue"},
    tags=WRITE_TAGS,
)
def update(key: str, body: IssueUpdate, client: TrackerClient = Depends(tracker_client)) -> Issue:
    """Update fields of a Tracker issue; only the keys present in ``body`` are changed.

    Status is NOT changed here — use ``transitions_execute``. Returns the updated issue.
    """
    return client.issues.update(key, body.model_dump(exclude_none=True))
```

Model: `IssueUpdate(APIModel)`, all fields optional, `extra="allow"` — `tracker/issues/models.py:74-101`.

---

### 7. DELETE returning an Ack (bodyless write) — `tracker comments_delete`

```python
# src/ycli/yandex/tracker/comments/client.py:74-85
@uplink.delete("issues/{key}/comments/{comment_id}")
def _delete(self, key: uplink.Path, comment_id: uplink.Path) -> requests.Response:  # ty: ignore[empty-body]
    """``DELETE /issues/{key}/comments/{comment_id}`` (204, no body; internal)."""

def delete(self, key: str, comment_id: str) -> None:
    """Delete a comment (``DELETE …/comments/{id}`` → 204). Raises on non-2xx."""
    self._delete(key, comment_id)
```

```python
# src/ycli/yandex/tracker/comments/mcp.py:74-85
@mcp.tool(
    name="comments_delete",
    annotations={**DESTRUCTIVE, "title": "Delete Tracker issue comment"},
    tags=WRITE_TAGS,
)
def delete(key: str, comment_id: str, client: TrackerClient = Depends(tracker_client)) -> Ack:
    """Permanently delete one comment from a Tracker issue (irreversible).

    Get ``comment_id`` from ``comments_list``. Returns an acknowledgement on success.
    """
    client.comments.delete(key, comment_id)
    return Ack.deleted("comment", comment_id, on=key)
```

Note the internal/public split pattern: `_delete` (uplink, raw `requests.Response`) vs. public
`delete` (returns `None`, callers wrap it into `Ack.deleted(...)`).

---

### 8. ACTION / transition — `tracker transitions_execute`

```python
# src/ycli/yandex/tracker/transitions/client.py:26-42
@uplink.returns.json()
@uplink.json
@uplink.post("issues/{key}/transitions/{transition_id}/_execute")
def execute(
    self, key: uplink.Path, transition_id: uplink.Path, body: uplink.Body
) -> TransitionList:  # ty: ignore[empty-body]
    """``POST /issues/{key}/transitions/{id}/_execute`` → available transitions after move.

    Returns the transitions available for the issue in its new status,
    parsed as a ``TransitionList``.
    """
```

```python
# src/ycli/yandex/tracker/transitions/mcp.py:23-40
@mcp.tool(
    name="transitions_execute",
    annotations={**WRITE, "title": "Execute Tracker issue transition"},
    tags=WRITE_TAGS,
)
def execute(
    key: str,
    transition_id: str,
    body: TransitionExecute,
    client: TrackerClient = Depends(tracker_client),
) -> TransitionList:
    """Move a Tracker issue through a workflow transition (change its status).

    Get ``transition_id`` from ``transitions_list``. ``body`` may be empty or carry issue
    fields to set on transition, e.g. a resolution when closing. Returns the transitions
    available from the new status.
    """
    return client.transitions.execute(key, transition_id, body.model_dump(exclude_none=True))
```

Model: `TransitionExecute(APIModel)`, `extra="allow"` — `tracker/transitions/models.py:52-69`
(open-ended: any issue field can ride along, e.g. a resolution when closing).

---

### 9. Explicit-position move with page semantics — `forms questions_move`

The most defensively-validated op in the codebase: a bare `position` is a **silent server no-op**
(200, nothing moves), so the model raises client-side rather than let that footgun through.

```python
# src/ycli/yandex/forms/questions/client.py:127-152
@uplink.returns.json()
@uplink.json
@uplink.post("surveys/{survey_id}/questions/{question_id}/move")
def _move(
    self, survey_id: uplink.Path, question_id: uplink.Path, body: uplink.Body
) -> QuestionMoveResult:  # ty: ignore[empty-body]
    """Raw ``POST …/questions/{id}/move`` from a ready dict; internal — callers use ``move``."""

def move(self, survey_id: str, question_id: str, body: QuestionMove) -> QuestionMoveResult:
    """``POST /surveys/{id}/questions/{question_id}/move`` — reposition a question.

    ``body`` is a typed :class:`~ycli.yandex.forms.questions.models.QuestionMove` naming the
    target page (``page`` / ``page_id`` / ``create_page``) and ``position``; a bare
    ``position`` is silently ignored by the API (200, nothing moves), so ``QuestionMove``
    raises unless a page target is also given. Display-condition consistency is validated
    server-side. Returns the moved question's id.
    """
    return self._move(survey_id, question_id, body.model_dump(by_alias=True, exclude_none=True))
```

```python
# src/ycli/yandex/forms/questions/mcp.py:131-151
@mcp.tool(
    name="questions_move", annotations={**WRITE, "title": "Move Forms question"}, tags=WRITE_TAGS
)
def move(
    survey_id: Annotated[str, Field(description="Form id (hex ObjectId) the question belongs to.")],
    question_id: Annotated[str, Field(description="Question id (integer) to reposition.")],
    body: Annotated[
        QuestionMove,
        Field(description="Target placement: page / page_id / create_page and position."),
    ],
    client: FormsClient = Depends(forms_client),
) -> QuestionMoveResult:
    """Reposition a question on the form (target page + position); returns the moved question's id.

    ``body.position`` needs a page target to take effect — the underlying API silently ignores
    a bare position (200, nothing moves) — so ``QuestionMove`` raises a validation error if
    ``position`` is set with no ``page`` / ``page_id`` / ``question`` / ``create_page`` target;
    pass one explicitly (e.g. ``page=1``). Display-condition consistency is validated
    server-side — moving a question above one its conditions depend on is rejected.
    """
    return client.questions.move(survey_id, question_id, body)
```

Model with a `model_validator(mode="after")` guard:
```python
# src/ycli/yandex/forms/questions/models.py:548-597
class QuestionMove(APIModel):
    question: int | str | None = Field(default=None, ...)
    page: int | None = Field(default=None, ...)
    page_id: int | None = Field(default=None, ...)
    create_page: bool | None = Field(default=None, ...)
    position: int | None = Field(default=None, ...)

    @model_validator(mode="after")
    def _require_target_for_position(self) -> QuestionMove:
        no_target = (
            self.page is None
            and self.page_id is None
            and self.question is None
            and not self.create_page
        )
        if self.position is not None and no_target:
            raise ValueError(
                "question move needs a target: pass page / page_id / question / create_page "
                "(a bare position is a silent no-op live)"
            )
        return self
```
The CLI visibly defaults `--page` to 1 when only `--position` is given, rather than hiding the
same rescue inside the model (`forms/questions/cli.py:295-314`).

---

### 10. Structured-cell-payload update — `wiki grids_update_cells`

```python
# src/ycli/yandex/wiki/grids/client.py:198-214
@uplink.returns.json()
@uplink.json
@uplink.post("grids/{grid_id}/cells")
def update_cells(self, grid_id: uplink.Path, body: uplink.Body) -> CellsUpdateResult:  # ty: ignore[empty-body]
    """``POST /grids/{id}/cells`` — set individual cell values. ``body`` is a ``CellsUpdate``."""
```

```python
# src/ycli/yandex/wiki/grids/mcp.py:313-343
@mcp.tool(
    name="grids_update_cells",
    annotations={**WRITE_IDEMPOTENT, "title": "Update Wiki grid cells"},
    tags=WRITE_TAGS,
)
def update_cells(
    grid_id: GridIdParam,
    body: Annotated[
        CellsUpdate,
        Field(
            description="``cells`` (each: ``row_id`` + ``column_slug`` + ``value``) + the "
            "current ``revision``."
        ),
    ],
    client: WikiClient = Depends(wiki_client),
) -> CellsUpdateResult:
    """Set the value of individual grid cells (addressed by row id + column slug).

    Repeating the same call sets the same values (idempotent). Returns the updated cells
    plus the grid's new ``revision``.
    """
    return client.grids.update_cells(grid_id, body=body.model_dump(exclude_none=True))
```

Models — note the **optimistic-locking `revision` field on every write**, a grids-only pattern:
```python
# src/ycli/yandex/wiki/grids/models.py:567-591
class UpdateCellSchema(APIModel):
    row_id: int = Field(description="Numeric id of the row whose cell is updated.")
    column_slug: str = Field(description="Slug of the cell's column.")
    value: Any = Field(default=None, description="New cell value (scalar, list, or user ref).")

class CellsUpdate(APIModel):
    revision: str = Field(description="Current grid revision (optimistic lock).")
    cells: list[UpdateCellSchema] = Field(description="The cells to update.")
```

---

### 11. File upload pipeline — `wiki attachments_upload`

Not literal HTTP multipart — Wiki uses a 3-step upload-session pipeline (create → PUT bytes →
finish) then attaches. The client composes the whole pipeline; MCP exposes it as one call taking
base64 bytes (agents cannot stream multipart).

```python
# src/ycli/yandex/wiki/attachments/client.py:137-164
def upload(
    self,
    sessions: UploadSessionsClient,
    page_id: int,
    *,
    file_name: str,
    data: bytes,
) -> AttachedFileList:
    """Run the whole upload pipeline for one file, then attach it to ``page_id``.

    Drives the four steps end to end against the injected ``sessions`` client: open a
    session sized to ``data``, PUT the bytes as a single octet-stream part, finish the
    session, then ``attach`` the finished session to the page. Small-file path — the bytes
    go up as one ``part_number=1`` part (chunk large files with ``upload_part`` directly).
    Returns the flat list of newly-attached files.
    """
    session = sessions.create(UploadSessionCreate(file_name=file_name, file_size=len(data)))
    session_id = session.session_id or ""
    sessions.upload_part(session_id, part_number=1, data=data)
    sessions.finish(session_id=session_id)
    return self.attach(page_id, [session_id])
```

```python
# src/ycli/yandex/wiki/attachments/mcp.py:73-95
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

CLI reads local bytes off disk (`wiki/attachments/cli.py:97-114`, `path.read_bytes()`), where MCP
must take `pydantic.Base64Bytes` — the one place CLI/MCP body-construction genuinely diverges
(binary vs. base64-JSON), unlike every other operation where they share the same typed model.

Model: `AttachedFile` / `AttachedFileList` — `wiki/attachments/models.py:77-131`.

---

### 12. Async op with polling — `wiki pages_clone` + `wiki operations_clone_get`

Trigger returns a deferred operation id; a *separate read-only resource* (`operations`) is polled.

```python
# src/ycli/yandex/wiki/pages/client.py:235-249  (trigger)
@uplink.returns.json()
@uplink.json
@uplink.post("pages/{page_id}/clone")
def clone(self, page_id: uplink.Path, body: uplink.Body) -> PageCloneOperation:  # ty: ignore[empty-body]
    """``POST /pages/{id}/clone`` — copy the page to a new address (async trigger).

    Returns a :class:`PageCloneOperation`; poll its ``operation.id`` via
    ``OperationsClient.clone_get`` until terminal. ``body`` is a dumped :class:`PageClone`
    (``{target, title?, subscribe_me}``).
    """
```

```python
# src/ycli/yandex/wiki/operations/client.py:23-35  (poll target)
@uplink.returns.json()
@uplink.get("operations/clone/{task_id}")
def clone_get(self, task_id: uplink.Path) -> CloneOperationStatus:  # ty: ignore[empty-body]
    """``GET /operations/clone/{task_id}`` → a page-clone's status (poll this to wait).

    The ``task_id`` is the ``operation.id`` returned by ``PagesClient.clone``. Poll until
    ``is_terminal``; on ``success`` the ``result.page`` names the clone.
    """
```

MCP exposes both as separate tools (trigger is `WRITE`, the status read is `RO`) — an agent
polls itself by re-calling `operations_clone_get`:
```python
# src/ycli/yandex/wiki/pages/mcp.py:227-248
@mcp.tool(name="pages_clone", annotations={**WRITE, "title": "Clone Wiki page"}, tags=WRITE_TAGS)
def clone(
    page_id: Annotated[int, Field(description="Numeric id of the page to copy.")],
    body: Annotated[PageClone, Field(description="Clone spec: required ``target`` ...")],
    client: WikiClient = Depends(wiki_client),
) -> PageCloneOperation:
    """Copy a page to a new address (``POST /pages/{id}/clone`` — asynchronous).

    Cloning is the only way to give content a new slug (slugs are permanent). The call
    returns a deferred operation reference — poll ``operations_clone_get`` with the
    returned ``operation.id`` until it reaches a terminal status.
    """
    return client.pages.clone(page_id=page_id, body=body.model_dump(exclude_none=True))
```

The CLI, unlike MCP, blocks and polls itself via `wait_for` (shared with bulk-change, §13):
```python
# src/ycli/yandex/wiki/pages/cli.py:172-201
@app.command()
def clone(
    ctx: typer.Context, page_id: PageIdArg,
    target: Annotated[str, typer.Option("--target", help="Destination slug for the copy.")],
    title: Annotated[str, typer.Option(help="Title of the copy, if renaming.")] = "",
    subscribe_me: Annotated[bool, typer.Option("--subscribe-me", ...)] = False,
    wait: Annotated[bool, typer.Option("--wait/--no-wait", ...)] = True,
) -> None:
    """Copy a page to a new address (POST /pages/{id}/clone; async). --wait polls to completion."""
    app_ctx = AppContext.from_typer_context(ctx)
    body = PageClone(target=target, title=title or None, subscribe_me=subscribe_me).model_dump(
        exclude_none=True
    )
    operation = app_ctx.wiki.pages.clone(page_id=page_id, body=body)
    if wait and operation.operation is not None and operation.operation.id is not None:
        task_id = operation.operation.id
        status = wait_for(
            lambda: app_ctx.wiki.operations.clone_get(task_id),
            lambda state: state.is_terminal,
            message="Waiting for page clone…",
            console=app_ctx.stderr_console,
        )
        Serializer.serialize(status, app_ctx.strategy, app_ctx.console)
    else:
        Serializer.serialize(operation, app_ctx.strategy, app_ctx.console)
```

`wait_for` (`src/ycli/cli/progress.py:45-74`) wraps `ycli.yandex.polling.poll` with a stderr
spinner — the shared CLI `--wait` idiom used by every async trigger (bulk-change, page clone,
grid clone).

---

### 13. Bulk op — `tracker bulk_update`

```python
# src/ycli/yandex/tracker/bulk/client.py:19-31
@uplink.returns.json()
@uplink.json
@uplink.post("bulkchange/_update")
def update(self, body: uplink.Body) -> BulkChange:  # ty: ignore[empty-body]
    """``POST /bulkchange/_update`` — mass-edit issues. Returns the started ``BulkChange``."""
```

```python
# src/ycli/yandex/tracker/bulk/mcp.py:73-84
@mcp.tool(
    name="bulk_update",
    annotations={**WRITE_IDEMPOTENT, "title": "Bulk-update Tracker issues"},
    tags=WRITE_TAGS,
)
def update(body: BulkUpdate, client: TrackerClient = Depends(tracker_client)) -> BulkChange:
    """Start an async bulk field update over many Tracker issues; returns the operation.

    Poll the returned operation id with ``bulk_get`` and inspect failures with
    ``bulk_issues_list``.
    """
    return client.bulk.update(body.model_dump(by_alias=True, exclude_none=True))
```

Model — `is_terminal` property drives the poll's `is_done`:
```python
# src/ycli/yandex/tracker/bulk/models.py:26-83 (excerpt)
TERMINAL_STATUSES = frozenset({"COMPLETE", "FAILED"})

class BulkChange(APIModel):
    id: str | None = Field(default=None, ...)
    status: str | None = Field(default=None, ...)
    total_issues: int | None = Field(default=None, alias="totalIssues", ...)
    total_completed_issues: int | None = Field(default=None, alias="totalCompletedIssues", ...)

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_STATUSES
```

CLI's `_finish` helper (`tracker/bulk/cli.py:60-75`) is the same `wait_for` idiom as §12.

---

### 14. POST search with a query language — `tracker issues_search` (TQL)

```python
# src/ycli/yandex/tracker/issues/client.py:28-42
@uplink.returns.json()
@uplink.json
@uplink.post("issues/_search")
def search(self, body: uplink.Body) -> IssueList:  # ty: ignore[empty-body]
    """``POST /issues/_search`` → list of issues.

    ``body`` is ``{"filter": …}`` or ``{"query": …}``.
    """
```

```python
# src/ycli/yandex/tracker/issues/mcp.py:69-74
@mcp.tool(
    name="issues_search", annotations={**RO, "title": "Search Tracker issues (TQL)"}, tags=TAGS
)
def search(query: str, client: TrackerClient = Depends(tracker_client)) -> IssueList:
    """Issues matching a TQL query string."""
    return client.issues.search(body={"query": query})
```

Note: this same `search` client method is reused for the structured `issues_list` MCP tool too
(`body={"filter": {...}}` instead of `body={"query": ...}}`) — one client method, two MCP tools
with different semantics (`issues/mcp.py:45-66`).

---

### 15. Count endpoint — `tracker issues_count`

Bare-int return type (no model at all).

```python
# src/ycli/yandex/tracker/issues/client.py:44-54
@uplink.returns.json()
@uplink.json
@uplink.post("issues/_count")
def count(self, body: uplink.Body) -> int:  # ty: ignore[empty-body]
    """``POST /issues/_count`` → a bare integer count."""
```

```python
# src/ycli/yandex/tracker/issues/mcp.py:77-90
@mcp.tool(name="issues_count", annotations={**RO, "title": "Count Tracker issues"}, tags=TAGS)
def count(
    query: str = "",
    queue: str = "",
    status: str = "",
    client: TrackerClient = Depends(tracker_client),
) -> int:
    """Count of issues matching a TQL query or filters.

    Pass ``query`` for a TQL query string (takes precedence over filters), or pass
    ``queue``/``status`` to filter by those fields.  With no arguments the API counts
    every issue in the org.
    """
    return client.issues.count(body=count_body(query=query, queue=queue, status=status))
```
`count_body` (`tracker/utils.py`, not reproduced) is a shared helper resolving the
query-vs-filter precedence, reused identically by the CLI `count` command.

---

### 16. Path + query + body all at once — `tracker entities_search`

```python
# src/ycli/yandex/tracker/entities/client.py:108-146
@uplink.returns.json()
@uplink.json
@uplink.post("entities/{entity_type}/_search")
def _search(
    self,
    entity_type: uplink.Path,
    body: uplink.Body,
    fields: uplink.Query = None,  # ty: ignore[invalid-parameter-default]
    per_page: uplink.Query("perPage") = None,  # ty: ignore[invalid-type-form]
    page: uplink.Query = None,  # ty: ignore[invalid-parameter-default]
) -> EntitySearchResponse:  # ty: ignore[empty-body]
    """One raw ``{hits, pages, values}`` page (internal; callers use :meth:`search`)."""

def search(
    self,
    entity_type: str,
    body: dict | None = None,
    *,
    fields: str | None = None,
    per_page: int | None = None,
    page: int | None = None,
) -> EntityList:
    """``POST /entities/{entity_type}/_search`` → flat :class:`EntityList` of ``values``.

    ``body`` carries ``input`` (substring), ``filter`` (field→value), ``orderBy``,
    ``orderAsc`` and ``rootOnly``. ``fields`` selects extra ``fields`` keys in the results;
    ``per_page``/``page`` page the server-side listing.
    """
    response = self._search(
        entity_type, body or {}, fields=fields, per_page=per_page, page=page
    )
    return EntityList(response.values)
```

```python
# src/ycli/yandex/tracker/entities/mcp.py:83-106
@mcp.tool(name="entities_search", annotations={**RO, "title": "Search Tracker entities"}, tags=TAGS)
def search(
    entity_type: TypeArg,
    input_text: Annotated[str, Field(description="Substring to match in the entity name.")] = "",
    order_by: Annotated[str, Field(description="Field key to sort the results by.")] = "",
    fields: Annotated[str, Field(description="Comma-separated extra fields to include.")] = "",
    client: TrackerClient = Depends(tracker_client),
) -> EntityList:
    """Entities of a given type matching a name substring, sorted server-side.

    Returns a flat list of entities. Pass ``input_text`` to match part of the name and
    ``order_by`` (e.g. ``entityStatus``) to sort. For richer filtering (by author, status,
    followers, …) use the CLI ``tracker entities search --filter`` which accepts an arbitrary
    filter object.
    """
    body: dict[str, str] = {}
    if input_text:
        body["input"] = input_text
    if order_by:
        body["orderBy"] = order_by
    return client.entities.search(entity_type, body, fields=fields or None)
```

---

### 17. God-resource sub-op — `tracker entities_comments_create`

`entities` is the "unified projects / portfolios / goals" god-resource: one client class
(`tracker/entities/client.py`, 626 lines) fronting the entity itself PLUS its comments,
checklists, links, attachments, permissions and bulk-change — all keyed by a leading
`entity_type` (`project`/`portfolio`/`goal`) path segment every sub-op repeats. Unlike a normal
resource (whose whole file is one noun), a god-resource's client.py is organized into `# ----
comments ----` / `# ---- checklists ----` / `# ---- links ----` / `# ---- attachments ----`
banner-commented sections, each mirroring the CRUD shape of a *would-be* standalone resource.

```python
# src/ycli/yandex/tracker/entities/client.py:342-357
@uplink.returns.json()
@uplink.json
@uplink.post("entities/{entity_type}/{entity_id}/comments")
def comments_create(
    self, entity_type: uplink.Path, entity_id: uplink.Path, body: uplink.Body
) -> Comment:  # ty: ignore[empty-body]
    """``POST …/comments`` — add a comment. Returns the created comment.

    Example:
        >>> client = TrackerClient(oauth_token="…", organization_id="…")  # doctest: +SKIP
        >>> client.entities.comments_create(
        ...     "project", "655f", {"text": "Готово"}
        ... ).id  # doctest: +SKIP
        22
    """
```

```python
# src/ycli/yandex/tracker/entities/mcp.py:391-405
@mcp.tool(
    name="entities_comments_create",
    annotations={**WRITE, "title": "Add Tracker entity comment"},
    tags=WRITE_TAGS,
)
def comments_create(
    entity_type: TypeArg,
    entity_id: IdArg,
    body: CommentCreate,
    client: TrackerClient = Depends(tracker_client),
) -> Comment:
    """Add a comment to a Tracker entity; returns the created comment."""
    return client.entities.comments_create(
        entity_type, entity_id, body.model_dump(by_alias=True, exclude_none=True)
    )
```
Generator implication: the god-resource is NOT one operation-per-noun; the MCP tool namespace
flattens `<resource>_<subresource>_<verb>` (`entities_comments_create`,
`entities_checklists_edit_item`, `entities_attachments_attach`, ...) — 33 tools from a single
client class, each still following the standard per-operation shape.

---

### 18. "Set permissions" nested-body op left as a raw dict — `tracker entities_set_permissions`

The one deliberate escape from "every write takes a typed model" — documented as an explicit,
test-allowlisted exception rather than silently doing the wrong thing.

```python
# src/ycli/yandex/tracker/entities/client.py:195-212
@uplink.returns.json()
@uplink.json
@uplink.patch("entities/{entity_type}/{entity_id}/extendedPermissions")
def set_permissions(
    self, entity_type: uplink.Path, entity_id: uplink.Path, body: uplink.Body
) -> ExtendedPermissions:  # ty: ignore[empty-body]
    """``PATCH …/extendedPermissions`` — set access settings. Returns the new settings.

    The ``acl`` object accepts only ``grant`` / ``revoke`` actions, each mapping an access
    level (``READ``/``WRITE``/``GRANT``) to users/groups/roles.
    """
```

```python
# src/ycli/yandex/tracker/entities/mcp.py:334-358
@mcp.tool(
    name="entities_set_permissions",
    annotations={**WRITE_IDEMPOTENT, "title": "Set Tracker entity permissions"},
    tags=WRITE_TAGS,
)
def set_permissions(
    entity_type: TypeArg,
    entity_id: IdArg,
    body: dict,
    client: TrackerClient = Depends(tracker_client),
) -> ExtendedPermissions:
    """Change an entity's access rules; returns the resulting permission set.

    ``body`` is the raw API payload; its ``acl`` object accepts only ``grant`` / ``revoke``
    actions, each mapping an access level (``READ``/``WRITE``/``GRANT``) to users/groups/roles,
    e.g. ``{"acl": {"grant": {"READ": {"users": ["8000000000000002"]}}}}``. Read the current
    ACL first with ``entities_permissions_get``.

    NOTE: intentionally ``dict`` (not a typed model) — the wire shape nests READ/WRITE/GRANT
    under ``grant``/``revoke`` verbs (see ``references/yandex-360/tracker/ru/api-ref/entities/
    patch-access.md``); the existing ``ExtendedPermissionsUpdate``/``AclInput`` models describe
    a different (direct READ/WRITE/GRANT) shape and would misrepresent this endpoint's real
    body. Allowlisted in ``tests/test_architecture.py`` pending a correctly shaped model.
    """
    return client.entities.set_permissions(entity_type, entity_id, body)
```
Generator implication: a codegen'd default should be "always a typed model"; this op is the
documented, allowlisted exception a generator must be able to special-case rather than force.

---

### 19. POST-not-PATCH quirk — `wiki pages_update`

```python
# src/ycli/yandex/wiki/pages/client.py:191-201
@uplink.returns.json()
@uplink.json
@uplink.post("pages/{page_id}")
def update(self, page_id: uplink.Path, body: uplink.Body) -> PageDetails:  # ty: ignore[empty-body]
    """``POST /pages/{id}`` — update (POST not PATCH; PATCH returns 405)."""
```

```python
# src/ycli/yandex/wiki/pages/mcp.py:152-176
@mcp.tool(
    name="pages_update",
    annotations={**WRITE_IDEMPOTENT, "title": "Update Wiki page"},
    tags=WRITE_TAGS,
)
def update(
    page_id: Annotated[int, Field(description="Numeric id of the page to update.")],
    content: Annotated[str, Field(description="New page body in YFM markdown (full replace).")],
    title: Annotated[str | None, Field(description="New title (unchanged when omitted).")] = None,
    client: WikiClient = Depends(wiki_client),
) -> PageDetails:
    """Replace a wiki page's body (and optionally its title) by numeric id.

    This REPLACES the whole body — to add to an existing page use ``pages_append_content``
    instead. The Wiki API updates via POST, not PATCH (PATCH returns 405); the SDK already
    handles that quirk. Repeating the same call yields the same page state (idempotent).
    """
    body: dict[str, str] = {"content": content}
    if title is not None:
        body["title"] = title
    return client.pages.update(page_id=page_id, body=body)
```
Note this tool does NOT take a typed body model — `content`/`title` are plain scalar params and
the dict is hand-assembled inline (contrast with §5/§6/§8/§9/§10/§13 which all take a typed
Pydantic body). Despite being POST on the wire, the MCP annotation is still `WRITE_IDEMPOTENT`
(full-replace semantics, not create-semantics) — annotation follows REST *semantics*, not verb.

---

### 20. No-args "me"/whoami read — `tracker me_get`

```python
# src/ycli/yandex/tracker/me/client.py:9-15
class MeClient(TrackerResource):
    """Declarative HTTP for ``/myself``."""

    @uplink.returns.json()
    @uplink.get("myself")
    def get(self) -> Me:  # ty: ignore[empty-body]
        """``GET /myself`` → the authenticated ``Me`` (a safe auth probe)."""
```

```python
# src/ycli/yandex/tracker/me/mcp.py:11-22
mcp = FastMCP("tracker-me")

@mcp.tool(name="me_get", annotations={**RO, "title": "Get current Tracker user"}, tags=TAGS)
def get(client: TrackerClient = Depends(tracker_client)) -> Me:
    """The authenticated Yandex Tracker user (a safe auth probe)."""
    result = client.me.get()
    return require_found(
        result,
        sentinel=lambda r: r.login is None,
        message="auth probe failed — empty user (check YANDEX_ID_OAUTH_TOKEN)",
    )
```

Model — the smallest resource in the codebase, 4 flat scalar fields:
```python
# src/ycli/yandex/tracker/me/models.py:8-14
class Me(APIModel):
    """The authenticated Tracker user (``GET /v3/myself``) — a safe auth probe."""

    uid: int | None = None
    login: str | None = None
    display: str | None = None
    email: str | None = None
```
Wiki has the identical shape one level deeper (`wiki/me/client.py`, `GET /users/me` →
`Me(username, home_cluster, identity, org)`), each domain's `me_get` reusing the same
`require_found(..., sentinel=lambda r: r.<distinguishing-field> is None, ...)` idiom with a
domain-specific sentinel field (`key`/`id`/`login`/`username`) and near-identical wording.

---

## Summary table — the 20 ops and which axis each demonstrates

| # | Op | Axis demonstrated |
|---|---|---|
| 1 | `tracker issues_get` | simple GET-by-id |
| 2 | `forms surveys_list` | offset/page pagination + drain-to-limit |
| 3 | `wiki pages_descendants` | envelope-cursor pagination |
| 4 | `tracker comments_list` | relative (last-item-id) cursor drain |
| 5 | `tracker issues_create` | CREATE, rich nested body |
| 6 | `tracker issues_update` | partial UPDATE / PATCH |
| 7 | `tracker comments_delete` | DELETE → synthesized `Ack` |
| 8 | `tracker transitions_execute` | ACTION / state transition |
| 9 | `forms questions_move` | explicit-position move, client-side guard against a server no-op |
| 10 | `wiki grids_update_cells` | structured cell payload, optimistic-lock `revision` |
| 11 | `wiki attachments_upload` | multi-step upload pipeline, base64 vs. raw-bytes CLI/MCP divergence |
| 12 | `wiki pages_clone` + `operations_clone_get` | async trigger + separate poll-target resource |
| 13 | `tracker bulk_update` | bulk op, async, CLI `--wait` |
| 14 | `tracker issues_search` | POST search, query-language body |
| 15 | `tracker issues_count` | bare-scalar return (no model) |
| 16 | `tracker entities_search` | path + query + body simultaneously |
| 17 | `tracker entities_comments_create` | god-resource sub-op (`<resource>_<sub>_<verb>` MCP naming) |
| 18 | `tracker entities_set_permissions` | raw-`dict` body, documented architecture exception |
| 19 | `wiki pages_update` | POST-not-PATCH quirk; untyped inline dict body |
| 20 | `tracker me_get` | no-args whoami / auth probe |
