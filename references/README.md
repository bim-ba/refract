# references/ — vendored external API docs (local research anchor)

Offline, `rg`-able copies of **external** API documentation, kept out of [`docs/`](../docs/) (this
repo's own docs) and [`artifacts/`](../artifacts/) (the distilled research notes). refract is a
*public* generator, so its design is anchored against a deliberately **diverse panel of real APIs** —
technically different, not just business-different — and this tree is where those source docs live for
`rg`/grep during design and implementation.

The distilled per-API technical analysis (pagination / auth / errors / body-encoding / async / unions
across 14 APIs) already lives in [`../artifacts/stress/`](../artifacts/stress/) and
[`../artifacts/16-stress-test-synthesis.md`](../artifacts/16-stress-test-synthesis.md). This folder
holds the raw sources those analyses (and future ones) are grepped from — so re-checking a claim does
not mean re-fetching over the network each time.

## Layout

- **[`yandex-360/`](yandex-360/)** — Yandex 360 + dev-hub service docs (Tracker, Wiki, Forms, Disk,
  ID, ...). Served from `yandex.ru` under the Yandex User Agreement (**not** an open licence), so **not
  committed** — the tree is gitignored and regenerated locally from a reproducible source,
  [`../scripts/fetch_docs.py`](../scripts/fetch_docs.py) (the diplodoc `.md`-sibling method: read a
  service `sitemap.xml`, GET each page's `.md` sibling, write 1:1).

- **`yandex-cloud/`** — the open-source Yandex Cloud docs
  ([`github.com/yandex-cloud/docs`](https://github.com/yandex-cloud/docs), CC BY 4.0). Add on demand as
  a shallow git submodule (kept out of clones/CI so the repo stays lean):

  ```bash
  git submodule add --depth 1 https://github.com/yandex-cloud/docs references/yandex-cloud
  ```

  or fetch selected services with `uv run scripts/fetch_docs.py <svc> --source cloud`.

- **`openapi/`** (add as needed) — vendored OpenAPI / reference docs for the broader diverse panel
  (GitHub, Stripe, OpenAI, Twilio, Notion, Slack, Kubernetes, Elasticsearch, Google, AWS S3). Most of
  these publish a machine-readable OpenAPI document; drop the spec file (or a doc mirror) under
  `openapi/<vendor>/` for local grep. Populated on demand per the axis being built — not all at once.

Everything under `references/` except this `README.md` is gitignored: external corpora are large and
mostly non-redistributable. Fetch what a given design/build step needs; keep it local.
