# Test-gen stack validation: schemathesis + hypothesis + faker (retrieved 2026-07-14)

Scope: for ycli's planned spec → IR → emitters generator (uplink client + typer CLI +
fastmcp tools + pydantic models + tests, Python target), determine whether/how
schemathesis, hypothesis, and faker fit the existing offline `responses`-stubbed
`--cov-fail-under=100` gate (`pyproject.toml:74`), and design the test tiers.

All version numbers and API claims below were retrieved live on **2026-07-14** via
context7 (library docs), deepwiki, WebSearch, and WebFetch (PyPI/GitHub) — not from
training data. Current versions found: **schemathesis 4.22.3** (released 2026-07-02),
**hypothesis 6.156.6** (released 2026-07-10), **faker 40.28.1** (released 2026-07-01),
**hypothesis-jsonschema 0.23.1** (released 2024-02-28, stale — see §2).

---

## 1. schemathesis — verdict: **live/contract tier, NOT an offline unit-test generator**

**What it is (CONFIRMED):** property-based *contract* testing driven by an OpenAPI or
GraphQL schema. It generates request cases from the schema and validates the API's
actual responses against that same schema — it does not stub or replace the code
under test, it exercises a real request/response round trip.
Source: `mcp__context7__query-docs` `/schemathesis/schemathesis`, quick-start.md,
retrieved 2026-07-14.

**Does it require something live to hit? CONFIRMED yes — always an HTTP-shaped
target.** Per Schemathesis's own `ARCHITECTURE.md`: *"Cases can reach the API server
through various configurable transports, including live HTTP requests via the
`requests` library, or by directly calling into a mounted WSGI or ASGI application."*
There is no third mode that lets it invoke an arbitrary Python callable (e.g. a hand-
rolled `uplink`-based client method) directly — the target must be one of:
- a live URL (`schemathesis.openapi.from_url(...)`, real network, e.g. via
  `docker compose up -d` in CI per `docs/guides/cicd.md`),
- a local schema file plus a live URL (`from_path(...)` + `case.call(app=app)`),
- an in-process ASGI app (`from_asgi(...)`, FastAPI/Starlette),
- an in-process WSGI app (`from_wsgi(...)`, Flask), or
- a `requests.Session`/test-client object passed to
  `case.call_and_validate(session=...)`.

ycli's generated client is a plain `uplink`-wrapped HTTP client, not a WSGI/ASGI app —
so schemathesis cannot address it directly; it needs either the real Yandex API (a
live external network call, explicitly excluded by ycli's "no live network" test
policy) or a local mock server that itself understands HTTP and the OpenAPI schema
(e.g. a Prism/stub server bound to loopback). Either way it is talking over an actual
transport, not a monkey-patched Python function — this is the offline/live boundary.
Source: same query, `docs/guides/python-apps.md`, `docs/guides/auth.md`, retrieved
2026-07-14.

**Checks it runs (CONFIRMED), default set includes:** `not_a_server_error`,
`status_code_conformance`, `content_type_conformance`, `response_schema_conformance`,
`response_headers_conformance`, `positive_data_acceptance`, `negative_data_rejection`
(requires `--mode negative` or `--mode all`), `use_after_free`,
`ensure_resource_availability`, `missing_required_header`, `ignored_auth`,
`unsupported_method`. Stateful testing via OpenAPI Links is **on by default** in a
standard run (phases: examples → coverage → fuzzing → stateful); if no Links are
defined in the schema, the stateful phase is skipped. Source: `docs/reference/checks.md`,
`docs/guides/stateful-testing.md`, retrieved 2026-07-14.

**Pytest integration (CONFIRMED):**
```python
import schemathesis
schema = schemathesis.openapi.from_url("https://your-api.com/openapi.json")

@schema.parametrize()
def test_api(case):
    case.call_and_validate()
```
`from_path`, `from_asgi`, `from_wsgi` are siblings of `from_url` under the same
`schemathesis.openapi` namespace. Source: `docs/quick-start.md`,
`docs/explanations/pytest.md`, `docs/guides/python-apps.md`, retrieved 2026-07-14.

**Architectural precondition for ycli specifically (finding, not from docs):** the
repo currently has no committed OpenAPI document (`fd -i "openapi|swagger"` in the repo
root returned nothing). Schemathesis needs an OpenAPI/GraphQL schema as its source of
truth — for the generator to use schemathesis at all in *any* tier, it would need to
additionally emit an OpenAPI 3.1 document per domain from the neutral spec/IR (not
just the uplink/typer/fastmcp/pydantic artifacts it emits today). This is a
prerequisite, not a blocker, but it is new generator surface.

**Verdict:** schemathesis is a **separate live/contract test tier**. It cannot live
inside the offline `--cov-fail-under=100` gate because it structurally requires a
reachable HTTP surface (real API, mock server, or in-process ASGI/WSGI app), which
`responses`-stubbed unit tests explicitly avoid, and because its whole value
proposition — catching "the stub says 200 but the real API says 404" class of bugs —
is void if run against the same stub the generator produced.

---

## 2. hypothesis + hypothesis-jsonschema — verdict: **usable offline, with one real caveat**

**hypothesis core (CONFIRMED, current, maintained):** 6.156.6, released 2026-07-10.
Source: WebFetch `https://pypi.org/project/hypothesis/`, retrieved 2026-07-14.

**hypothesis-jsonschema — CONFIRMED stale but not abandoned/broken.**
- Latest PyPI release: **0.23.1, 2024-02-28** — no release in ~2 years as of
  2026-07-14. Source: WebFetch `https://pypi.org/project/hypothesis-jsonschema/`,
  retrieved 2026-07-14.
- GitHub repo (`python-jsonschema/hypothesis-jsonschema`, transferred from the
  original `Zac-HD/hypothesis-jsonschema`) is **not archived**, `pushed_at:
  2025-12-05`, 23 open issues, `updated_at: 2026-07-10` — so it still gets occasional
  commits/community activity even without tagged releases. Source: `gh api
  repos/python-jsonschema/hypothesis-jsonschema`, retrieved 2026-07-14.
- **Draft-support caveat (CONFIRMED, load-bearing):** the package's own docs state
  *"JSONSchema drafts 04, 05, and 07 are fully tested and working."* Source: WebFetch
  PyPI page, retrieved 2026-07-14. Meanwhile **pydantic v2's `model_json_schema()`
  targets JSON Schema Draft 2020-12** (and OpenAPI 3.1.0) by default — confirmed via
  context7 `/pydantic/pydantic`, `docs/concepts/json_schema.md` /
  `docs/migration.md`, retrieved 2026-07-14: *"Changes to JSON schema generation ...
  targeting draft 2020-12."* hypothesis-jsonschema does not document 2020-12 as a
  tested draft. **COULDN'T-VERIFY**: whether `from_schema()` fails outright or merely
  under-supports newer 2020-12-only keywords (e.g. `prefixItems`, certain `$defs`
  patterns) on pydantic-generated schemas — no test was run against a live pydantic
  model in this pass; this needs an empirical smoke test before the generator relies
  on it, not just a docs read.
- **What `from_schema()` does (CONFIRMED):** takes a JSON Schema dict and returns a
  Hypothesis strategy generating valid instances against it, with `custom_formats`,
  `allow_x00`, and `codec` options. Source: WebFetch PyPI description, retrieved
  2026-07-14.

**So: yes, the generator could in principle emit hypothesis strategies from
`Model.model_json_schema()` via `from_schema()` to produce arbitrary-but-valid request
bodies for property tests — but hypothesis-jsonschema is an unmaintained-release
(if not unmaintained-development) dependency with an explicitly narrower JSON Schema
dialect than what pydantic emits.** Treat this as a risk to pin/vendor/test, not a
drop-in.

**CI-stability mechanics (CONFIRMED):**
- `@settings(derandomize=True)` makes a test's random search deterministic — same
  examples every run. Source: context7 `/hypothesisworks/hypothesis`,
  `docs/changelog.rst`, retrieved 2026-07-14.
- `hypothesis.seed(n)` pins the global seed. Source: `docs/reference/api.rst`,
  retrieved 2026-07-14.
- `settings.register_profile(...)` / `settings.load_profile(...)` (commonly from
  `conftest.py`, keyed off an env var or pytest's `--hypothesis-profile`) is the
  documented pattern for a CI profile distinct from a dev profile (e.g.
  `register_profile("ci", max_examples=..., derandomize=True)`). Source:
  `docs/tutorial/settings.rst`, retrieved 2026-07-14.
- `@example(value)` decorator: explicit inputs that **always run, before the random
  search, every single execution**, independent of seed/derandomize state, and do not
  shrink. Source: `docs/tutorial/replaying-failures.rst`, retrieved 2026-07-14. This is
  the mechanism that lets a generator pin specific edge cases (e.g. the one payload
  that must hit a given error-handling branch) so that branch's coverage is
  guaranteed on every run — the random search alone cannot guarantee that.

---

## 3. faker — verdict: **fixture/realism layer, not a search engine; complements, doesn't replace, hypothesis**

**Current (CONFIRMED):** 40.28.1, released 2026-07-01. Source: WebSearch + context7
`/websites/faker_readthedocs_io_en_stable`, retrieved 2026-07-14.

**Determinism (CONFIRMED):** `Faker.seed(0)` (class method, not instance `.seed()`) —
or, under pytest, the `faker` fixture with a session-scoped seed / per-test
`faker.seed_instance(n)` — produces reproducible output. Source: context7 query-docs,
`fakerclass.html`, `pytest-fixtures.rst`, retrieved 2026-07-14.

**Where it fits vs hypothesis:** faker is a *realistic-value generator* (real-looking
names, emails, dates, UUIDs) for **fixtures where the value's realism matters but its
exact content doesn't** — e.g. populating a stubbed 200 response body for a
`responses`-mocked test, or building demo/seed data. hypothesis is an *edge-case
search engine* — it doesn't care whether `"a"` "looks like" an issue key, it cares
about finding the boundary/adversarial value (empty string, unicode, max-length,
`None` where optional) that breaks the code. There is real overlap only at the shallow
end (both can produce "a plausible string"); for anything beyond that they solve
different problems and are not redundant. **Rule of thumb:** use faker when the test
asserts on a *type of value* (e.g. "is a valid email shape") and readability of fixture
data matters to a human reviewer; use hypothesis when the test asserts a *property*
that must hold for all inputs and you want it to actively hunt for counterexamples.
Faker can also be a *strategy source* inside hypothesis via `st.builds`/custom
strategies, but that reintroduces non-determinism unless the faker instance itself is
seeded per hypothesis example — an added complexity most projects avoid by picking one
generator per test.

---

## 4. Coverage-gate compatibility — the decision

| Library | Can live in the 100%-gate (Tier 1, `responses`-stubbed, every commit)? | Why |
|---|---|---|
| **schemathesis** | **No.** | Structurally requires a live URL, mock server, or in-process ASGI/WSGI app — incompatible with `responses`-stubbed, no-live-network unit tests. Also methodologically self-defeating there: it would validate the stub against itself. |
| **hypothesis (+ hypothesis-jsonschema)** | **Conditionally yes**, with mandatory settings. | Property-based search is fine offline (no network), but by default it is *not* deterministic run-to-run and can be slow (default 100 examples/test); both are incompatible with a hard, every-commit `--cov-fail-under=100` gate unless pinned. |
| **faker** | **Yes, trivially**, with `Faker.seed(n)`. | Deterministic once seeded; just a fixture-data generator, no search/flakiness dimension at all. |

**Why "non-deterministic" is a real threat to a 100%-gate, precisely stated:**
`--cov-fail-under=100` measures line/branch coverage of the *whole test run*. Coverage
never goes down from running more examples, but it **can vary run-to-run** if a
specific branch (e.g. an exception path) is only reached by some of the randomly
drawn examples and not others — replacing a deterministic hand-authored assert that
always hits that branch with an un-pinned property search makes that branch's
coverage probabilistic instead of guaranteed. Two runs of the same commit could
legitimately differ in coverage percentage. Separately, hypothesis's shrinking/
example-database behavior means a failure found in one CI run may not reproduce
identically in a fresh, cache-less CI container next run, which reads as CI flake
even when it's a real bug.

**Recommendation for Tier 1 (offline, in the gate):**
1. Keep hand-authored `responses`-stubbed asserts as the primary coverage source per
   ARCH-4/ARCH-3 style conventions — they remain the thing that *guarantees* 100%.
2. Optionally let the generator emit `faker`-seeded fixture bodies (`Faker.seed(0)` at
   module/session scope) to make stub payloads look realistic without adding any
   non-determinism.
3. Optionally *add* narrowly-scoped hypothesis property tests on top (e.g. "any valid
   model round-trips through `model_dump()`/`model_validate()`"), but only with a
   CI settings profile that forces `derandomize=True` (or a fixed `seed()`) and a
   bounded `max_examples`, registered in `conftest.py` and loaded via
   `settings.load_profile("ci")`/env var — and pair every property test that's meant
   to hit a specific branch with an explicit `@example(...)` for that branch, so
   coverage of that line is guaranteed regardless of what the random search finds
   that run. Do not let a property test be the *sole* source of coverage for any
   line — treat it as additive, never load-bearing for the 100% number.
4. Given hypothesis-jsonschema's ~2-year-stale releases and untested-2020-12-dialect
   gap against pydantic's actual output (§2), do not adopt it generator-wide without
   first running an empirical smoke test (`from_schema(Model.model_json_schema())` on
   a real ycli model with `$defs`/`$ref`/`anyOf`) — treat it as unverified until then.

**Recommendation for Tier 2 (opt-in, live/contract):** schemathesis, gated behind a
`@pytest.mark.integration`-style marker (mirroring ycli's existing
`test_integration_markers.py` convention) or a wholly separate `tests/contract/`
suite, run manually or on a nightly schedule against either (a) a local mock server
built from the generator's emitted OpenAPI 3.1 doc, or (b) the real Yandex API with
real credentials in a controlled environment — never inside the default `uv run
pytest` invocation that the 100%-gate enforces. This is the tier that catches
"the stub says 200 but Tracker actually returns 404" class of spec-vs-reality drift
that a `responses`-stubbed test can never catch, because the stub is generated from
the same spec as the code under test.

---

## Confirmed vs couldn't-verify summary

| Claim | Status | Source | Date |
|---|---|---|---|
| schemathesis needs live URL / ASGI / WSGI / session — no arbitrary-callable mode | CONFIRMED | schemathesis `ARCHITECTURE.md` via context7 | 2026-07-14 |
| schemathesis default checks list | CONFIRMED | `docs/reference/checks.md`, `configuration.md` | 2026-07-14 |
| schemathesis stateful testing via OpenAPI Links, on by default | CONFIRMED | `docs/guides/stateful-testing.md` | 2026-07-14 |
| schemathesis current version 4.22.3 (2026-07-02) | CONFIRMED | WebSearch (PyPI/newreleases.io) | 2026-07-14 |
| hypothesis current version 6.156.6 (2026-07-10) | CONFIRMED | WebFetch pypi.org/project/hypothesis | 2026-07-14 |
| hypothesis `@settings(derandomize=True)`, `seed()`, `register_profile`/`load_profile`, `@example` semantics | CONFIRMED | context7 hypothesis docs | 2026-07-14 |
| hypothesis-jsonschema latest release 0.23.1 (2024-02-28), drafts 04/05/07 only | CONFIRMED | WebFetch pypi.org/project/hypothesis-jsonschema | 2026-07-14 |
| hypothesis-jsonschema repo not archived, still receives commits (pushed 2025-12-05) | CONFIRMED | `gh api repos/python-jsonschema/hypothesis-jsonschema` | 2026-07-14 |
| pydantic v2 `model_json_schema()` targets Draft 2020-12 / OpenAPI 3.1.0 | CONFIRMED | context7 pydantic `docs/migration.md`, `docs/concepts/json_schema.md` | 2026-07-14 |
| hypothesis-jsonschema's actual behavior on a real 2020-12 pydantic schema (pass/degrade/fail) | **COULDN'T-VERIFY** — docs don't say; no live smoke test run in this pass | — | 2026-07-14 |
| faker current version 40.28.1 (2026-07-01), `Faker.seed()` determinism | CONFIRMED | context7 faker docs + WebSearch | 2026-07-14 |
| ycli has no committed OpenAPI doc today (prerequisite for any schemathesis use) | CONFIRMED | local repo `fd -i "openapi\|swagger"` → empty | 2026-07-14 |
