# drift-log

Per-entry record of divergences between what a session actually did and what the codified instructions say. Entries are immutable once committed.

## Shape (this is what the `drifts:*` skills read)

| Fact | Value |
|---|---|
| Root | `.claude/drift-log` |
| Entry shape | **flat** — `open/YYYY-MM-DD-<kebab-slug>.md` |
| Monthly indexes | `applied/INDEX-YYYY-MM.md`, flat under `applied/` |
| Live OPEN index | the `open/` directory listing itself — never a hand-written list |

`open/` holds entries not yet merged into official instructions; `applied/` holds the ones that were. Transition is a `git mv` plus a frontmatter edit, never a delete.

## Process

The triggers, the entry template, the frontmatter schema and the immutability rules live in one place — the `drifts` plugin, not here:

- **`drifts:creating-drift-logs`** — when to log, how to name an entry, `templates/_template.md` (normative for frontmatter).
- **`drifts:reviewing-drift-logs`** — triage, OPEN → APPLIED promotion, staleness, compaction into monthly indexes.

Load the skill rather than copying its rules into this file; a second copy is a second thing to keep true.
