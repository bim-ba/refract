# Skills System Reference

This document is the canonical reference for the `.claude/skills/` system. Every developer and AI agent working in this repository should read this before creating, modifying, or using a skill.

---

## Table of Contents

1. [Purpose](#1-purpose)
2. [Directory Structure](#2-directory-structure)
3. [SKILL.md Required Sections](#3-skillmd-required-sections)
4. [Rules Files Conventions](#4-rules-files-conventions)
5. [Templates Conventions](#5-templates-conventions)
6. [references/index/ vs references/ (generated content)](#6-referencesindex-vs-references-generated-content)
7. [Language Standard](#7-language-standard)
8. [How Skills Are Referenced from AGENTS.md](#8-how-skills-are-referenced-from-agentsmd)
9. [Quality Bar](#9-quality-bar)

---

## 1. Purpose

### What a skill is

A skill is a self-contained knowledge package for a specific domain task. It bundles everything an AI agent needs to execute that task correctly: the workflow steps, the conventions to follow, the templates to use, and the navigation guides for external systems. A skill does not contain general programming knowledge — it contains only what is specific to this team, this codebase, and this task type.

### Why the skill system exists

Agents have a limited context window and no persistent memory between sessions. Loading the entire codebase context on every task is wasteful and degrades output quality. The skill system solves this by letting an agent load exactly the context relevant to the current task — nothing more, nothing less. Each skill is designed to be the complete and sufficient context for one category of work.

### When to use a skill

Load the relevant skill before any domain-specific task where conventions, templates, or API patterns matter. Examples:

- Before documenting a backend domain — load `documentation-backend`
- Before creating or updating an issue tracker entry — load the relevant tracker skill
- Before creating or editing a wiki page — load the relevant wiki skill
- Before writing meeting notes from an SRT transcript — load `documenting-meetings`
- Before building or editing a presentation deck — load the relevant presentation skill
- Before writing or reviewing `docs/` for a service repository — load the relevant documentation skill

### When NOT to use a skill

Do not load a skill for:

- Generic programming tasks (writing a utility function, refactoring logic)
- One-off scripts without structured output requirements
- Analysis tasks that do not produce a defined artifact
- Tasks where no skill in the registry matches the domain

If no skill matches, proceed without one and note this as a gap for future skill creation.

---

## Skill naming convention

Skill directory names are lowercase-kebab and follow one of two shapes by category:

- **Workflow skills** (the skill performs an action) → `<gerund-verb>-<object>`.
  Verb families: `using-` (operate a tool/service), `documenting-` (produce docs),
  `reviewing-` (review/audit), `researching-` (research/fact-check),
  `creating-`/`writing-` (author an artifact).
  Examples: `using-playwright`, `documenting-meetings`, `reviewing-agent-instructions`,
  `researching-rigorously`, `creating-drift-logs`, `reviewing-drift-logs`.
- **Rulebook skills** (a reference body of domain rules, not an action) → `<domain>-<aspect>`.
  Example: `clickhouse-query-best-practices`.

Exception: a skill meant to be invoked as an explicit slash command may keep a short
imperative name (e.g. `setup` → `/setup`).

---

## Skill structure (self-contained)

Prefer self-contained skills. `SKILL.md` is a thin router — when to use it, the
workflow/rules summary, and pointers — while heavier material lives in on-demand
subdirectories so it is loaded only when needed (token-efficient) and the skill is
portable:

- `rules/NN-*.md` — atomic rules, one concern per file.
- `templates/` — copyable artifact templates.
- `references/` — deep reference material loaded on demand.
- `examples/` — worked before/after examples.
- `scripts/` — executable helpers.

Every `rules/`/`examples/`/`templates/` file linked from `SKILL.md` must exist
(no broken internal links).

---

## 2. Directory Structure

Every skill follows this exact layout:

```text
.claude/skills/{skill-name}/
├── SKILL.md                          # Entry point — always read first
├── rules/                            # Numbered convention files
│   ├── 01-{topic}.md
│   └── 02-{topic}.md
├── templates/                        # Output templates
│   └── {template-name}/              # Use subdirs when a template has multiple files
├── references/
│   ├── index/                        # Navigation guides: what exists, where to find it
│   │   └── {source}.md
│   ├── {content-file}.md             # Flat generated files (e.g. domain-index.md)
│   └── {content-dir}/               # Generated directories (e.g. index/ navigation guides)
│       └── {name}.md
└── scripts/                          # Optional: automation scripts
```

### Component explanations

**`SKILL.md`** — Entry point. An agent MUST read this file before using the skill. It contains the complete workflow and a map to all other files in the skill. Do not skip directly to rules or templates — `SKILL.md` tells you which files are relevant for the current task and in what order.

**`rules/`** — Numbered convention files (01-, 02-, …). Each file is a self-contained rule set for one topic area. The number prefix controls reading order when context matters. Read only the rule files relevant to the current task — you do not need to read all of them. Each rule file is independently understandable without requiring the others.

**`templates/`** — Output templates. Use a named subdirectory when a template spans multiple related files (for example, `domain-passport/` with 7 section files). Single-file templates can sit directly in `templates/` as flat files. A template must be usable without reading anything else first — it is self-contained.

**`references/index/`** — Navigation artifacts only. These files help the agent find information in external systems: repositories, wikis, API documentation directories. They answer the question "where is X?" Examples: a map of all backend services (`backend.md`), an API documentation directory guide (`docs.md`), a team role list.

**`references/` (generated content)** — AI-generated and maintained content. Files that the agent creates and updates over time live directly under `references/`, not in a further `artifacts/` subdirectory. Examples: domain passports generated from code analysis, wiki structural maps, queue state snapshots. The `references/index/` subdirectory is the only reserved name under `references/`; everything else is generated content.

**`scripts/`** — Optional automation scripts used by the skill. Not all skills require this directory.

> **index/ vs generated content:** `references/index/` is a map — it tells the agent WHERE things are. Everything else in `references/` is a shelf — it holds what the agent has BUILT. If you would delete a file and regenerate it from scratch by running the workflow again, it goes in `references/` (not `references/index/`).

---

## 3. SKILL.md Required Sections

Skills fall into two categories, declared in `category:` frontmatter. The required SKILL.md sections differ per category — forcing a rulebook skill into the workflow template adds empty sections (no "Post-checks" without a procedure; no "Artifact Map" without produced output) and a workflow skill without "Pre-checks/Post-checks" is genuinely incomplete.

### `category: workflow` — drives a multi-step procedure

| Section | What it must contain |
|---|---|
| **Purpose** | What this skill enables; when to use it; when NOT to use it |
| **Pre-checks** | What to verify before starting: files that must exist, context to load, auth that must be configured |
| **Workflow** | Numbered steps with explicit decision points and branching. No ambiguity about what to do when. |
| **Post-checks** | How to verify output quality; what "done" looks like; acceptance criteria |
| **Guardrails** | What NOT to do; common mistakes; anti-patterns; things that seem reasonable but are not |
| **Artifact Map** | What files this skill produces, where they go, naming conventions |
| **References Guide** | How to use `references/index/` for this skill; which source to consult first for a given question |

**Purpose** must include a negative case ("when NOT to use it"). **Pre-checks** must be executable, not aspirational — `"Verify API_TOKEN is set"`, not `"Ensure auth is configured"`. **Workflow** must handle the main path plus the most common branches (create vs. update, exists vs. not). **Post-checks** must include at least one verifiable criterion. **Guardrails** document hard-won knowledge about what goes wrong — essential for API skills with side effects. **Artifact Map** is a table (artifact name, output path pattern, naming convention). **References Guide** maps questions → which `references/index/` file to read first.

### `category: rulebook` — encodes conventions, type mappings, idiomatic patterns

| Section | What it must contain |
|---|---|
| **When to use** | Concrete trigger conditions — "writing or reviewing `models/**/*.yml`" — that an agent scanning the registry can match unambiguously |
| **When NOT to use** | Negative cases — adjacent domains this skill does not cover, alternative skills to load instead |
| **Rules** (or domain analogue) | The encoded conventions — typed rules, mappings, required sections, etc. Domain-specific naming is fine (e.g., "Type definitions", "DB type mapping", "Per-layer matrix") |
| **Examples / Canonical patterns** | Before/after pairs, complete working examples, idiomatic snippets the agent can adapt |
| **Anti-patterns** | Concrete mistakes seen in practice — wrong usage, side effects, things that look right but aren't |

Rulebook skills omit Pre-checks/Post-checks/Workflow/Artifact Map (no procedure to verify, nothing produced) — they are loaded as context for whatever procedure the agent is already executing.

---

## 4. Rules Files Conventions

- One rule file per topic area — do not mix concerns in a single file
- Named with a two-digit numeric prefix: `01-`, `02-`, `03-`, … — controls reading order for context
- Each rule file is self-contained: reading it requires no cross-reference to other rule files
- Content written in English; example values (field names, entity names, sample data) may appear in the team's language only when clearly labeled as examples
- Rule files answer four questions: what is required, what is forbidden, what are the edge cases, and how to handle them

### Naming pattern

```text
rules/
├── 01-agent-behavior.md        # How the agent should behave overall
├── 02-artifact-conventions.md  # Output naming, structure, update rules
└── 03-documentation-depth.md   # What level of detail is required
```

The number prefix does not imply that all files must be read in order every time. It provides a default reading order and makes the relative priority of rules visible at a glance.

---

## 5. Templates Conventions

- Templates contain English structural elements: section names, field labels, and instructional comments
- Example content within templates may be in the team's language only when it is clearly wrapped in an `<!-- EXAMPLE -->` HTML comment or explicitly labeled as an example value
- Templates that produce multi-file output live in a named subdirectory (e.g., `templates/domain-passport/`)
- Single-file templates sit directly in `templates/` as flat files
- A template must be usable without reading anything else first — it is self-contained
- Do not include implementation-specific defaults in templates; use placeholder values instead

### Template subdirectory pattern

Use a subdirectory when the output artifact is a folder, not a single file:

```text
templates/
├── domain-passport/        # Multi-file template (subdirectory)
│   ├── 01-overview.md
│   ├── 02-entities.md
│   └── 03-integrations.md
└── domain-index-entry.md   # Single-file template (flat)
```

### Instructional comments

Use HTML comments to embed instructions inside a template that are visible to the agent but not rendered in the final output:

```markdown
<!-- INSTRUCTION: Write 2-3 sentences describing the business purpose. Focus on what question this domain answers, not how it is implemented. -->

## Business Purpose

<!-- EXAMPLE: "The Parcels domain tracks shipment lifecycle from label creation through delivery confirmation. It is the primary source for all logistics KPIs." -->
```

---

## 6. references/index/ vs references/ (generated content)

This distinction is fundamental. Mixing these two categories breaks navigation and causes agents to overwrite navigation guides with generated content or vice versa.

### references/index/ contains

Navigation guides — content that helps an agent find things in external systems:

- Maps of external repositories (what services exist, where the code lives, directory layout)
- Navigation guides for API documentation directories
- Team and role reference lists
- Queue and board reference lists for issue trackers

`references/index/` is the only reserved subdirectory name under `references/`. Files in `index/` are written by humans or carefully curated, not overwritten by agent workflows.

**Examples from existing skills:**

| File | What it is |
|---|---|
| `documentation-backend/references/index/backend.md` | Map of all services under `backend/`, their project names, and directory structure |
| `documentation-backend/references/index/nuget.md` | Map of all packages under `backend/nuget/` |
| `documentation-backend/references/index/wiki.md` | Navigation guide for wiki pages relevant to the data team |

### references/ (everything else) contains

AI-generated and maintained content — outputs the agent creates or updates over time. These files sit directly under `references/`, not in a further subdirectory:

- Domain passports generated from code analysis
- Wiki structural maps generated by the agent after traversing the wiki API
- Queue state snapshots (list of open issues, current sprint state)
- Meeting summaries and research notes
- Any content the agent creates as a deliverable

**Examples from existing skills:**

| File | What it is |
|---|---|
| `docs/passports/<domain>/` | Domain passport authored by documentation-backend (lives in the platform `docs/` tree, not the skill) |
| `documentation-backend/references/domain-index.md` | Registry of all documented domains with their passport paths |
| `wiki/references/wiki-map.md` | Structural map of a wiki space |

### Decision rule

If you would delete the file and regenerate it from scratch by running the workflow again, it goes in `references/` (not `references/index/`). If you would lose navigation ability without it and it cannot be regenerated from a workflow, it is an index file.

---

## 7. Language Standard

| Location | Language rule |
|---|---|
| `SKILL.md` — all sections | English only |
| `rules/` — all rule files | English only |
| `references/index/` — all index files | English only |
| `templates/` — structural elements (section names, field labels, instructional comments) | English only |
| `templates/` — example content inside `<!-- EXAMPLE -->` blocks | Team language acceptable |
| Output artifacts (domain passports, meeting notes, wiki pages) | Language of the team |
| `references/` — generated content (non-index) | Language of the team |

### Rationale and enforcement

Skill infrastructure (SKILL.md, rules, index files) is English because it is read and generated by AI agents. Output artifacts (passports, notes, wiki pages) are in the team's language because they are read by the team. When reviewing a skill, scan the entire `SKILL.md` and all `rules/` files for non-English prose — if any appears outside clearly labeled example blocks, the skill fails the language standard.

---

## 8. How Skills Are Referenced from AGENTS.md

`AGENTS.md` contains a Skills Registry table. This table is the primary discovery mechanism — agents scan it to decide which skill to load for the current task.

### Registry format

```markdown
## Skills Registry

All skills live under `.claude/skills/`. Read a skill's `SKILL.md` before using it — this is mandatory, not optional.

| Skill | Path | Purpose | When to load |
|---|---|---|---|
| `documentation-backend` | `.claude/skills/documentation-backend/` | Document backend domains | Before documenting or reading any backend domain |
| `issue-tracker`         | `.claude/skills/issue-tracker/`         | Manage issue tracker entries | Before any issue tracker API call |
```

### Loading sequence

1. Scan the Skills Registry table in `AGENTS.md` to identify which skill matches the current task
2. Navigate to the skill directory
3. Read `SKILL.md` — this is mandatory; do not skip directly to rules or templates
4. Follow the workflow in `SKILL.md`, which tells you which rules and index files to read for the current task

### Adding a new skill to the registry

When a new skill is created, add a row to the Skills Registry table in `AGENTS.md`. The row must include: skill name (matching the directory name), path, one-sentence purpose, and a concrete "when to load" trigger condition. The trigger must be specific enough that an agent scanning the registry can determine unambiguously whether the condition applies.

---

## 9. Quality Bar

### A skill is production-ready when all of the following are true

- All 7 `SKILL.md` sections are present and non-trivial (no placeholder text, no empty sections)
- All files referenced in `SKILL.md` actually exist at the stated paths
- `templates/` contains a template for every output type the skill produces
- `references/index/` contains an index file for every external source the skill needs to navigate
- No broken internal links (every `rules/XX-*.md` mentioned in `SKILL.md` exists)
- No non-English text in `SKILL.md` or `rules/` files, except in clearly labeled example blocks
- An agent can run the skill from a cold start (no prior context from a previous session) and produce correct output

### A skill is a draft (not ready for production) if any of the above is missing

Mark draft skills explicitly at the top of their `SKILL.md`:

```markdown
> **Status: DRAFT** — Missing: [list what is incomplete]. Do not use in production tasks.
```

When reviewing a skill, walk the production-ready criteria above as a checklist — each bullet is a `pass/fail` gate. Skills that fail any gate must either be fixed or marked DRAFT.
