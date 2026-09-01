# refract — roadmap & build state

> Resume-here doc. For the design, see `design.md`.
> Status page: https://claude.ai/code/artifact/a5ac6d93-a36e-453a-9168-34cae528ca9e (title "refract: статус"), rendered from `docs/status/refract.status.yaml` with the skill `documenting:publishing-project-status` (bim-ba/ai) - edit the YAML, re-render, republish to the same URL. Research dossier: https://claude.ai/code/artifact/c1bff73d-024d-445f-9932-227f657cb253 (title "refract: досье"), rendered from `docs/status/refract.dossier.yaml` with the same skill.
> Last updated after PR #9 — public repo, milestones A · A.2 · P0 · P1 merged.

## Where we are

**`main` is public and pushed** (`github.com/bim-ba/refract`) — 146 commits, PRs #1–#9 merged:
A (walking skeleton, #1) · P0 debt-zero (#2) · P1 type-foundation (#3) · naming batch A (#4) ·
tooling/config chores (#7, #9). `uv run refract generate --check` → exit 0, **15 files**
(`tracker/me` 6 · `tracker/priorities` 6 · package client · 2 test modules) for the two example
resources. **286 tests** — 278 default green, 8 opt-in `behavioral` green — 100% line+branch
coverage · ruff/ty clean.

Open issues: **#5** (discriminator synthesized twice) · **#6** (path placeholders unchecked against
declared path params) · **#8** (architecture question: SDK as the base, CLI/MCP as mappers).

### Built so far (the `[v1]` subset, driven by what ycli's first two resources need)

| Capability | Where | Proven on |
|---|---|---|
| Neutral spec → pydantic loader (neutral-type lowering, `ref<Model>`) → frozen IR | `loader.py`, `ir/model.py` | me, priorities |
| Python emitters (models/client/cli/mcp/tests) + `ruff_format` post-pass | `emitters/python/*` | me (6 files), priorities (6) |
| Simple GET client; `RootModel` list (no `root:` field) | `client.py`, `models.py` | me.get, priorities.list |
| **Body registry — `TypedModel`** (`_verb`(uplink.Body)+public split, `model_dump(by_alias=True, exclude_none=True)`) | `client.py`, IR `Body` | priorities create/edit |
| Path + query params (`uplink.Path`/`uplink.Query(alias)=default`), PATCH, `?version=` | `client.py` | priorities.edit |
| Models: `Field(description=)` (required+optional), model-ref types (`LocalizedName`) | `models.py` | priorities models |
| MCP: multi-op, safety→annotation+tags (`RO`/`WRITE`/`WRITE_IDEMPOTENT`, `TAGS`/`WRITE_TAGS`), typed-body tools, `require_found` guard, keyword-shadow (`list_`) | `mcp.py` | me, priorities |
| CLI: group + passthrough command, plus **Assembled writes** (flat options → nested body) | `cli.py` | me.get, priorities create/edit |
| Tests: responses-stubbed auto-suite (client/cli/mcp + `require_found` guards) — **multi-op** (iterates every tests-bearing operation) | `tests.py` | me, priorities |
| `refract generate --write/--check` drift gate + **data-presence surface-gating** | `generate.py`, `cli.py` | 15 files |

## Backlog / deferred debt

Everything here is **deferred by design** (YAGNI: added with the resource that first exercises it +
its byte-target golden). Nothing is a bug in current output — the two resources are byte-identical.

### Emitter-generality debt (from the A.2 whole-branch review — the next resource will hit these)
- **A2-2 (top priority):** a **required** field/param with NO explicit default renders `= None`,
  silently making it optional. Sites: `models.py` `_render_field` plain arm; `client.py`
  `_uplink_params`/`_public_method`; `mcp.py` `_signature_parameters`. Fix: gate `= {default}` on
  `field.optional` / `param.optional` (or `default is not None`). Not hit today (every required field
  currently has a `description` → the `Field(...)` arm, which is correct).
- **A2-3:** `client.py` `_BODY_PHRASE[method]` `KeyError`s on a DELETE/PUT body (only POST/PATCH mapped).
  Fix: `.get(method, "a ready body")`.
- **A2-4:** the internal `_verb` docstring is emitter-synthesized prose (no spec knob) — could break
  byte-identity if a future resource's real `_verb` doc is worded differently.
- **A2-5:** free text (`description`/title/doc) is interpolated unescaped — a `"` would break output.
- **A2-1:** the mcp surface-gate's skip arm is vacuously covered (line-cov; both current resources have
  mcp facets). Same class as A.1's F1. Covered when a no-mcp resource arrives.

### Feature debt (deferred forks — see the A.2 plan)
- **`cli.py` write commands** (create/edit): bespoke flat-option→nested-body assembly
  (`LocalizedName.ru/en` → `--name-ru/--name-en`, `x or None`). Not mechanically generatable from the
  model schema → future **`Assembled`-CLI strategy** or a `handler:`. (Deferred from A.2.)
- **ycli's test files are entangled.** `tests/yandex/tracker/priorities/test_client.py` &
  `test_cli.py` cover THREE resources (priorities+issuetypes+linktypes) in one file. refract's natural
  output is per-resource → **Milestone B must reorganize ycli's grouped tests to per-resource** (a real
  migration cost). Riding along in the same deferred batch: F4 (guard-doc as spec data) + F5
  (`loader._response_model` hardcodes `responses[200]` → first-2xx + SpecError for 201/204).

### `[roadmap]` registries not yet built (add as consumers arrive — see `design.md` §6-9)
pagination `Offset/Cursor/RelativeCursor/NextUrl/LinkHeader/…` · async `Operation` (LRO) · errors
`BodyFlag/PartialSuccess` · type-system `oneOf`/discriminated unions + cross-file `ref` + model-level
`handler` · body encodings `FormEncoded/Multipart/Ndjson/Xml` · auth `Signer/TokenProvider/Mtls` ·
OpenAPI emit/import. **v1 non-goals (ratified):** GraphQL, streaming, inbound receivers, interactive
auth bootstrap.

## Next milestones (owner steers)

1. ~~**Push A + A.2** to the public repo (establish github.com/bim-ba/refract).~~ **Done** (PR #1).
2. **A.3 — a fuller-CRUD resource** (e.g. `statuses`/`resolutions`: required fields + delete +
   self-contained per-resource tests). Exercises A2-1..3 with real byte-targets. Stays local, no push
   needed.
3. **Milestone B — wire ycli as the consumer.** ycli grows a `specs/` tree; `refract generate --check`
   runs in ycli CI; hand-written resources are replaced by generated ones resource-by-resource (tracker
   → wiki → forms), 100% suite green throughout; the `entities` god-resource stays hand-written. Proves
   the core thesis (fewer AUTHORED lines). Touches the production repo → separate branch + PR + approval.
   Must reconcile the test-file entanglement (per-resource output) noted above.
