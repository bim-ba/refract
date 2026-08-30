# refract

A spec-driven code generator. Describe one API operation as YAML, and refract emits the code a hand-written client would need for it: a typed Pydantic model, an `httpx` request builder, a Typer CLI command, and a FastMCP tool — plus a test for each. [`ycli`](https://github.com/bim-ba/ycli), a Yandex 360 client, is the first consumer and the accuracy bar: refract's output is checked byte-for-byte against ycli's real, hand-written files.

**Input** — one operation in a `resource.yaml` ([`examples/ycli-tracker/tracker/priorities/resource.yaml`](examples/ycli-tracker/tracker/priorities/resource.yaml)):

```yaml
- name: create
  method: POST
  path: priorities/
  operationId: priorities_create
  body: {strategy: TypedModel, model: PriorityCreate, dump: "by_alias=True, exclude_none=True"}
  responses:
    200: {model: Priority}
  mcp:
    name: priorities_create
    safety: WRITE
    title: "Create Tracker priority"
  cli:
    name: create
    documentation: "Create a priority from a key, localized name, and optional order/description."
```

**Output** — the generated client method ([`examples/ycli-tracker/out/tracker/priorities/client.py`](examples/ycli-tracker/out/tracker/priorities/client.py)):

```python
def create(self, body: PriorityCreate) -> Priority:
    """Create a priority from a typed ``PriorityCreate`` body. Returns the new ``Priority``.

    Example:
        >>> client = TrackerClient(oauth_token="…", organization_id="…")  # doctest: +SKIP
        >>> client.priorities.create(
        ...     PriorityCreate(key="one", name=LocalizedName(ru="Низкий"), order=60)
        ... ).key  # doctest: +SKIP
        'one'
    """
    return self._session.send(_requests.create(body))
```

The same `create` block also produced this operation's request builder, MCP tool, CLI command, and test — one spec entry, one `mcp:` line and one `cli:` line, instead of four files to keep in sync by hand.

## Status

**Alpha — walking skeleton.** One target language (Python), one proving ground (the `examples/ycli-tracker` corpus: two Tracker resources, `priorities` and `me`). Not published, not used by ycli yet.

What exists:

- A `resource.yaml` + `client.yaml` spec loader and a typed intermediate representation (IR).
- Python emitters for models, the request builder, the client, the CLI, the FastMCP server, and tests.
- The `--check` drift gate (`refract generate --check`) — renders in memory and fails if the checked-in output has gone stale.
- The golden-oracle example (`examples/ycli-tracker`) that the emitted code is diffed against.

What doesn't, yet — despite being described in [`docs/design.md`](docs/design.md):

- OpenAPI 3.1 emission or import — no `openapi.py` exists in the tree.
- Any language besides Python — the emitter registry resolves backends by name (`refract.emitters.<name>.backend`), and only `python` is implemented.
- Most of the pagination, body-encoding, and error-model strategies the design document lists as `[roadmap]`.

## Quick start

```bash
uv sync
uv run refract generate --check
```

`--check` defaults to the `examples/ycli-tracker` spec and compares the render against `examples/ycli-tracker/out/`. Point it elsewhere with `--specs` and `--out`; add `--write` to render for real instead of just checking.

## Spec

A resource lives at `<domain>/<resource>/resource.yaml`, next to a `client.yaml` that holds the shared base URL and auth. Inside a `resource.yaml`:

- **`models:`** — the resource's Pydantic models: plain field lists, a `root_list` wrapping another model, or a request body like `PriorityCreate`. A field can be `ref<Model>` to reuse another model in the same file.
- **`operations:`** — one entry per HTTP call: `method` + `path`, `params` (path/query, typed), `body` (a strategy such as `TypedModel`, naming which model to send), and `responses` (status code to model).
- **`mcp:`** and **`cli:`** — the same operation's MCP tool and CLI command, named and documented right next to the HTTP shape they wrap, instead of living in separate files.
- **`tests:`** — fixtures (a stubbed HTTP response, a `call`, and `asserts`) that the emitter turns into a real test alongside the generated code.

Neither `resource.yaml` example in the repo yet uses `oneOf`/discriminated unions — the `priorities` resource is deliberately the simple case. See [`docs/design.md`](docs/design.md) for the full type system and the registries (pagination, auth, async, errors) beyond what's implemented today.

## Layout

```text
src/refract/
├── cli.py                  # `refract` Typer entry point (generate --write / --check)
├── generation.py           # the driver: resolve a backend, render each resource + its glue
├── spec/                   # resource.yaml / client.yaml loading and validation
├── ir/                     # the typed intermediate representation (auth, client, model, types)
├── runtime/                # what generated code imports at run time (auth, base, request, session)
└── emitters/
    ├── ports.py             # the LanguageBackend / EmitContext seam
    ├── registry.py          # @backend("python") registration, lazy-imported by name
    └── python/              # the one implemented backend
        ├── backend.py, naming.py, types.py, views.py, format.py, doc_comments.py
        ├── resolve/         # spec → per-surface render data
        ├── surfaces/        # per-surface renderers (models, requests, client, cli, mcp, tests, …)
        └── templates/       # the Jinja templates each surface renders

examples/ycli-tracker/      # the golden-oracle spec + its checked-in `out/` (Tracker priorities, me)
docs/design.md              # the full design: registries, roadmap, everything past [v1]
```

## Development

```bash
uv sync
uv run ruff check --fix && uv run ruff format
uv run ty check
uv run pytest
```

`pytest` runs with `--cov-fail-under=100`: the suite is a 100%-coverage gate, not a target. Slow tests that import and run emitted code are tagged `behavioral` and excluded by default (`-m 'not behavioral'` in `pyproject.toml`); run them explicitly with `uv run pytest -m behavioral`.

## License

[MIT](LICENSE) © 2026 Sava Znatnov
