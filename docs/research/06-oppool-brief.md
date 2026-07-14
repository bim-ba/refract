# Worked-example op pool — shared brief for the strategy bake-off

Every strategy subagent renders THESE 12 operations (a curated subset of the 20-op pool in
`02-codebase-anatomy-and-op-pool.md`, chosen to span every distinct shape). Use the SAME 12,
in this order, so the outputs compare apples-to-apples. The real current code for each is quoted
verbatim (with `src/…:line` citations) in doc 02 — read it there; do not re-derive.

| # | Op | Real code (doc 02 §) | Axis it stress-tests |
|---|---|---|---|
| 1 | `tracker issues_get` | §1 | trivial GET-by-id — how close to zero authoring does the easy case get? |
| 2 | `forms surveys_list` | §2 | offset pagination + drain-to-limit (internal `_list_page` + public `list`) |
| 3 | `tracker comments_list` | §4 | relative-cursor drain (`_drain_relative`, id-of-last-item cursor) |
| 4 | `tracker issues_create` | §5 | typed nested body (`IssueCreate`, extra=allow) + **rich CLI flag→body mapping** |
| 5 | `tracker comments_delete` | §7 | bodyless write → synthesized `Ack.deleted(...)`; internal `_delete`/public split |
| 6 | `tracker transitions_execute` | §8 | action/transition, open-ended `extra=allow` body |
| 7 | `forms questions_move` | §9 | **escape hatch**: `model_validator` guard (bare-position = silent no-op) + CLI visibly defaults page=1 |
| 8 | `wiki grids_update_cells` | §10 | structured cell payload + optimistic-lock `revision` field |
| 9 | `wiki attachments_upload` | §11 | **escape hatch**: multi-step pipeline; base64 (MCP) vs raw-bytes (CLI) divergence |
| 10 | `wiki pages_clone` + `operations_clone_get` | §12 | async trigger + separate poll-target resource + CLI `--wait` |
| 11 | `tracker entities_comments_create` | §17 | god-resource sub-op; `<resource>_<sub>_<verb>` flat MCP naming |
| 12 | `tracker entities_set_permissions` | §18 | raw-`dict` body (documented ARCH-3 allowlist exception) |

## Output contract (identical for every strategy)

Write to your assigned output file. Structure:

### Part 1 — Authored spec for ALL 12 ops
For each op, show the FULL authored spec a human would write under your strategy (the YAML block,
the Python descriptor, or the OpenAPI fragment). Be complete and realistic — include the
hand-tuned MCP docstring and CLI help as data, the pagination declaration, the body mode, the
annotation class, the return type. For the escape-hatch ops (#7, #9, #12) show EXACTLY how the
strategy expresses the irregular part (a `handler:` reference, a Python function, an allowlist
flag, or — if it can't — say so plainly).

### Part 2 — Generated output for 4 designated ops
Show the generated source your strategy would emit for these 4 (pick the layers that best reveal
differences; you need not show all 4 files for all 4 ops, but show enough to prove it reproduces
the REAL code in doc 02):
  - #1 `issues_get` (models + client + mcp) — the trivial case
  - #2 `surveys_list` (client `_list_page`+`list` + mcp) — the internal/public pagination split
  - #4 `issues_create` (mcp + the CLI command) — the rich-CLI-flag tension
  - #9 `attachments_upload` (whatever the escape hatch produces) — the hard case
Diff-check your generated output against doc 02's verbatim real code and note any divergence.

### Part 3 — Honest assessment of YOUR strategy
- **Authoring cost**: rough authored-lines for the 12 ops; how much is boilerplate vs genuinely per-op.
- **Escape-hatch cleanliness**: how gracefully #7/#9/#12 degrade. Does the long tail ever BLOCK generation?
- **Extensibility (C1 north star)**: what does adding op-shape #21 of an *unforeseen* kind cost —
  a spec field, a template branch, an IR node, a rewrite? Be concrete.
- **Invariant fit**: py.typed / 100% coverage / ARCH-1..11 / reviewable diffs — any friction?
- **The failure mode**: where does this strategy get ugly at scale (50→200 resources)?

## Hard rules for every subagent
- READ-ONLY research; do NOT modify the repo. Everything goes to your scratchpad output file.
- Ground every "generated output" claim in doc 02's real code — the generator's job is to
  REPRODUCE that exact code, so your generated block must match the real quartet (or you must
  flag the divergence as a strategy limitation).
- Do NOT hardcode secrets/tokens/org-ids in any example (use placeholders).
- Be brutally honest in Part 3 — this is a decision aid, not a sales pitch for your strategy.
