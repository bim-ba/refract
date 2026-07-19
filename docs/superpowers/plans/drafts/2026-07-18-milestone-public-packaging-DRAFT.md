# Milestone: Public packaging & release (Workstream C-public)

> DRAFT — directional sketch, not a bite-sized TDD plan. Refine via `writing-plans` before execution.

## 1. Goal

Make refract installable and presentable as a real public open-source project — the original ask
that seeded this whole effort (`PROMPT.md`) — without touching generator source. Anyone landing on
the repo should be able to understand it, install it from PyPI, and contribute in under 5 minutes.

## 2. Current gap

| Area | State |
|---|---|
| `README.md` | 16-line stub: one-line pitch + a single `uv run` command. No quickstart, badges, or links. |
| `CLAUDE.md` | Empty template — `<!-- Describe... -->` placeholders unfilled. |
| `ARCHITECTURE.md` | Missing. The hourglass (frontends -> neutral IR -> backends) + 3-layer seam table live only in the internal `docs/superpowers/specs/2026-07-14-...-design.md` (section 4), not public-facing. |
| `CONTRIBUTING.md` / `SECURITY.md` / `CODE_OF_CONDUCT.md` | Missing — no community health files. |
| `CHANGELOG.md` | Missing — no release notes, no version-bump automation. |
| `LICENSE` | **Present** (MIT, 2026 Sava Znatnov) — good, just needs cross-linking from README/pyproject (already referenced in `pyproject.toml`). |
| `.github/` | Only `workflows/ci.yml` (test matrix 3.12/3.13, ruff, ty, pytest w/ 100% coverage gate). No PR/issue templates, no dependabot, no release or PyPI-publish workflow. |
| `pyproject.toml` | Has name/version/classifiers/deps/scripts — but static `version = "0.1.0"` (no tag-driven bump), no `[project.urls]` (homepage/repo/issues/changelog), no `keywords`. |
| Social presence | No repo description/topics/social-preview image confirmed set on GitHub. |

## 3. Scope IN

- Real `README.md`: badges (CI, PyPI once live, license), an actual quickstart (install -> spec -> `generate` -> emitted output), links to ARCHITECTURE/CONTRIBUTING/roadmap.
- `ARCHITECTURE.md`: public distillation of the hourglass + 3-layer table (core / typed-surface / glue) from the internal design spec — the "why" and the seams, not the full spec.
- `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md` (Contributor Covenant baseline).
- Fill in `CLAUDE.md` project overview + conventions (uv/ruff/ty commands, src-layout, coverage gate, examples/ golden-oracle rule).
- `pyproject.toml` polish: `[project.urls]`, `keywords`; keep MIT `LICENSE` as-is.
- `CHANGELOG.md` via Conventional-Commits-driven automation (tool TBD — see open questions), wired into CI.
- CI polish: PR template, issue templates, dependabot.yml; keep existing test matrix as-is (already solid).
- PyPI publish workflow: build via `uv build` / hatchling, publish via trusted publishing (OIDC), triggered off a release tag.
- Social preview / repo description + topics (lightweight, no logo design).

## 4. Scope OUT / defer

- Full docs site (mkdocs-material / Docusaurus + GitHub Pages) — flagged as open question, not committed.
- Logo / branding / marketing copy.
- Multi-language (TS/Rust) install docs — out until those backends exist (Workstream C/D+).
- Deep API reference docs generation (mkdocstrings etc.) — rides on the docs-site decision.

## 5. Key phases (rough order)

1. **README + ARCHITECTURE.md** — the two docs a visitor reads first; ARCHITECTURE.md distills the
   internal design spec's hourglass/seams so the internal doc can stay exhaustive/Russian-process-oriented.
2. **Community health files** — CONTRIBUTING.md (dev setup, ruff/ty/pytest, PR flow, Conventional
   Commits), SECURITY.md, CODE_OF_CONDUCT.md; fill `CLAUDE.md`.
3. **LICENSE confirm + pyproject polish** — LICENSE already present (MIT); add `[project.urls]`/keywords.
4. **CHANGELOG + release automation** — pick a tool, wire it into CI to bump version + generate notes
   + tag on merge to main (gated on Conventional Commits, already this repo's commit convention).
5. **CI polish** — PR/issue templates, dependabot, any missing repo-hygiene files.
6. **PyPI publish workflow** — trusted publishing (OIDC), triggered on release tag from step 4.
7. **Social preview / repo metadata** — description, topics, social-preview image.
8. **Polish pass** — dead-link check, badge verification, dry-run a fresh `uv pip install` from Test PyPI.

## 6. Dependencies

Mostly **independent of the generator/axes work (Workstreams A/B/D)** — can run in parallel with
generator development. Light coupling only: a stable-ish public API surface (CLI flags, spec schema)
makes README quickstart examples less likely to churn, but nothing here blocks or is blocked by axis
work. The one true external gate: PyPI package-name registration is a manual, one-time step outside CI.

## 7. Rough size & effort

| Item | Size |
|---|---|
| README rewrite | S |
| ARCHITECTURE.md | M |
| CONTRIBUTING / SECURITY / CoC | S |
| CLAUDE.md fill-in | S |
| pyproject.toml polish (urls/keywords) | S |
| CHANGELOG + release automation | M |
| CI polish (templates/dependabot) | S |
| PyPI publish workflow | M |
| Social preview/metadata | S |

**Effort note:** bounded, low technical risk — no runtime logic changes, all docs/CI/config. Main
risk is *rework from late decisions* (license already resolved; PyPI name and release-tool choice
should be settled before wiring CI in phases 4/6).

## 8. Open questions

1. **License:** MIT `LICENSE` is already present and referenced in `pyproject.toml` — confirm we keep
   it (vs. reconsider e.g. Apache-2.0 for an explicit patent grant) before it's load-bearing in badges/docs.
2. **PyPI package name:** is `refract` available on PyPI? If taken, need a fallback (`refract-gen`,
   `pyrefract`, ...) — check before wiring the publish workflow, since the name is user-facing forever.
3. **Docs site yes/no:** plain README+ARCHITECTURE.md+`docs/*.md` on GitHub vs. a real docs site
   (mkdocs-material + GH Pages)? Affects whether "Scope OUT" item 1 gets pulled forward.
4. **Release cadence + tool:** continuous release-on-every-merge-to-main vs. manual/batched tags; and
   which automation (`python-semantic-release` vs. `release-please` vs. a plain Conventional-Commits
   changelog generator)? Check what the sibling `ycli` repo (PROMPT.md's stated reference) already uses.
