# ycli integration (DRAFT sketch - refine later)

> Directional sketch for roadmap.md's "Next milestones" item 3 ("Milestone B - wire ycli as the
> consumer"). NOT a bite-sized TDD plan. Source: docs/roadmap.md, the architecture-redesign design
> spec, examples/ycli-tracker/, and a read-only skim of /home/sava/dev/dev/ycli (accessible).
> Untracked draft; touches a PRODUCTION repo, so this milestone needs its own branch + PR + approval
> before any ycli file is written.

## 1. Goal

Wire ycli up as refract's real consumer: ycli grows a `specs/` tree, `refract generate --check`
runs in ycli's CI, and hand-written tracker/wiki/forms resources are replaced by generated ones
one at a time. This is the proof of the project's core thesis - fewer AUTHORED lines of code for
the same working SDK - on a production codebase, not a curated example.

## 2. Naming note (collision - flag and rename)

roadmap.md's "Milestone B" (this milestone, ycli-as-consumer) is a DIFFERENT "B" from the
design-spec's "Workstream B" (`2026-07-14-refract-architecture-redesign-design.md` section 16 -
the OpenAPI frontend). Same letter, unrelated scope, two different docs. A sibling draft
(`2026-07-18-milestone-deferred-Dplus-backlog-DRAFT.md`) already flags this collision in passing.

Recommendation: drop letter-based milestone names entirely; use content names - "ycli integration"
(this doc) vs "OpenAPI frontend" (Workstream B). Rename at the next roadmap.md edit rather than as
a standalone chore.

## 3. Scope IN

- ycli grows a `specs/` tree (neutral-YAML resource specs, mirroring `examples/ycli-tracker/`
  layout: one `resource.yaml` per resource + a shared `client.yaml` for server/auth).
- `refract generate --check` runs as a CI step in ycli's `.github/workflows/ci.yml` (existing
  pipeline: uv sync -> ruff format/check -> lint-imports -> ty check -> pytest; the new step slots
  in alongside those, gating drift between specs and generated output).
- Hand-written resources are replaced by generated ones resource-by-resource, in order
  tracker -> wiki -> forms, each swap keeping ycli's test suite 100% green.
- The `entities` god-resource (`src/ycli/yandex/tracker/entities/` - 625/735/642/1057 lines across
  client/cli/mcp/models, ~3060 lines total) stays hand-written; not a generation target this
  milestone.
- Reconcile the test-file entanglement: refract emits one test file per resource, but ycli
  currently groups several small tracker resources into one file. Confirmed on disk -
  `tests/yandex/tracker/priorities/test_client.py` and `test_cli.py` hold tests for THREE resources
  (priorities + issuetypes + linktypes); `tests/yandex/tracker/linktypes/` has no test files of its
  own at all (just an empty `__init__.py`), while issuetypes ALSO carries its own separate
  `test_client.py`/`test_cli.py`/`test_mcp.py`/`test_models.py` - so today's suite has both a grouped
  file and per-resource duplicates of the same coverage. This has to be untangled before/while
  migrating priorities, issuetypes, and linktypes.

## 4. Scope OUT / defer

- Regenerating or touching the `entities` god-resource.
- Any non-tracker domain beyond wiki and forms (ycli also has status, and yandex-cloud/other
  references under `references/` that are not live resource domains yet).
- Building new diversity-axis registries speculatively ahead of the resource that needs them (see
  Dependencies below) - rule-of-three still applies inside this milestone.
- OpenAPI frontend work (that is Workstream B / a separate milestone, see section 2).

## 5. Key phases (ordered; each keeps ycli's suite 100% green)

1. Pilot ONE tracker resource end-to-end in ycli: hand-write its `specs/` entry, run
   `refract generate --write`, diff against the current hand-written module, swap it in, suite green.
   This is the walking-skeleton-in-production proof point.
2. Wire `refract generate --check` into ycli's CI (`ci.yml`), as a required step alongside the
   existing format/lint/import-boundary/type/test gates, using the pilot resource as the first
   thing it guards.
3. Migrate the remaining simple tracker resources one by one (e.g. issuetypes, linktypes, statuses,
   resolutions, queues, boards, ... - roughly two dozen small-to-medium resource dirs under
   `src/ycli/yandex/tracker/`), each its own commit/PR-worthy slice.
4. Reconcile the grouped-vs-per-resource test entanglement (priorities+issuetypes+linktypes and any
   other grouped files) - decide regroup-vs-emit-grouped (open question below) and execute it before
   or alongside the resources it touches.
5. Migrate the larger/write-heavy tracker resources (issues, comments, attachments, etc.) once the
   emitter debt items already tracked in roadmap.md (A2-2..A2-5, F2 multi-op tests) are closed by
   the A.3 milestone that precedes this one.
6. Move to the wiki domain (pages, comments, attachments, resources, grids, recovery,
   uploadsessions) - first domain to exercise pagination-shaped params (`expand`/paging args seen in
   `wiki/pages/client.py`, `wiki/attachments/client.py`, `wiki/resources/client.py`,
   `wiki/comments/client.py`) that tracker's me/priorities never needed.
7. Move to the forms domain (surveys, questions, answers, files, images, keysets, filling,
   operations) - first domain to exercise multipart body encoding (`forms/files/client.py` does a
   `multipart/form-data` upload), which is also not built yet.
8. Final sweep: confirm `refract generate --check` is green across all migrated resources, confirm
   the entities god-resource is the only remaining hand-written surface in the migrated domains,
   and update roadmap.md to record the milestone closed.

## 6. Dependencies

Gated on the generator being feature-complete enough for ycli's REAL resources - specifically the
"diversity axes" work already named in the design spec (section 6) and roadmap's backlog, scoped to
exactly what ycli hits, not the full 15-API sweep:

| Axis | ycli needs it for | Built today? |
|---|---|---|
| auth: `MultiHeaderAuth` (OAuth + X-Org-Id) | every Yandex 360 domain | yes (built for me/priorities) |
| body encoding: JSON | most tracker/wiki writes | yes |
| body encoding: multipart | forms/files upload | no - needed before phase 7 |
| pagination (some registry member - Cursor/Offset/LinkHeader/etc, TBD which) | wiki (pages/attachments/resources/comments show paging-shaped params) | no - needed before phase 6 |
| multi-op tests emitter (F2) | any resource with >1 operation | tracked in A.3, precedes this milestone |
| emitter-generality debt A2-2..A2-5 | required-field defaults, DELETE/PUT bodies, doc/text escaping | tracked in A.3, precedes this milestone |

This is the milestone that RETIRES hand-written code for the first time - everything upstream of it
(A.3, the axis work it pulls in) exists to make THIS milestone possible, not as an end in itself.

## 7. Rough size

**M-L.** The generation mechanics per resource are expected to be small once the pilot works; the
real risk is (a) the test-entanglement reconciliation, which touches test files not 1:1 with the
resource being migrated, and (b) this is the first milestone that lands changes in a production repo
under separate owner approval and PR review, which adds process overhead beyond the coding work
itself.

## 8. Open questions

- Which tracker resource to pilot first - priorities (already has a byte-identical golden in
  `examples/ycli-tracker/`) for a near-zero-diff proof, or a fresh one to prove the pipeline on
  something not already validated?
- Test-entanglement reconciliation: regroup ycli's tests to per-resource (matching refract's
  natural output, more files) or add a "grouped tests" emission mode to refract (matching ycli's
  current convention, less migration churn but a new emitter mode)? The disk evidence shows the
  current grouping is already partly redundant with per-resource files (issuetypes has both) -
  regrouping to per-resource may be a net simplification, not just churn.
- Branch/PR cadence in the ycli repo: one big PR per domain (tracker, then wiki, then forms), or
  one PR per resource? Smaller PRs are easier to review/revert but multiply the approval overhead
  this milestone already carries.
- Does the wiki domain's pagination shape turn out to need a NEW registry member, or does an
  existing planned one (Cursor/Offset/LinkHeader) already cover it once inspected closely? Worth a
  quick spike before committing to phase 6's scope.
