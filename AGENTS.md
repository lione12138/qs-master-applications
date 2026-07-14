# AGENTS.md

Instructions for AI coding agents working on GradWindow.

## Project purpose

GradWindow is a transparent graduate application-window tracker for QS top-200
universities. The site publishes official, reviewable application windows and
separates them from generated predictions and unreviewed candidates.

Correctness matters more than volume. Never turn a weak scrape result into a
published deadline.

## Repository map

- `src/gradwindow/` — Python package and data pipeline.
  - `cli.py` exposes all maintenance commands.
  - `validation.py`, `models.py`, `schemas.py` define data contracts.
  - `predictions.py`, `coverage.py`, `readme.py`, `site.py` generate derived
    artifacts.
  - `programme_adapters/` contains dedicated and generic programme discovery
    adapters.
  - `generic_seed_discovery.py` and `generic_discovery_batch.py` audit and run
    generic programme discovery.
- `web/` — static frontend source (`index.html`, `app.js`, `styles.css`,
  `i18n.js`, `ranking-filter.js`, `window-grouping.js`, etc.).
- `site/` — generated deployable site. Do not hand-edit it; regenerate with
  `build-site`.
- `data/` — public and generated datasets.
- `data/ops/` — operational state, discovery reports, review queues, and
  candidate records.
- `data/evidence/` — evidence snapshots used to validate/publicly explain data.
- `tests/` — pytest coverage for the Python pipeline and frontend invariants.
- `.github/workflows/` — CI, data refresh, GitHub Pages, and notification jobs.

## Data model and trust boundaries

Published data:

- `data/universities.json` — canonical university records. QS/THE/ARWU ranking
  views should share this same university table; do not create separate school
  databases per ranking.
- `data/programs.json` — curated programme metadata.
- `data/programme-groups.json` — display/grouping metadata.
- `data/applications.json` — curated exact application windows.
- `data/predictions.json` — generated non-official next-cycle estimates. Do not
  edit by hand.
- `data/programme-translations.json` — translated programme names. Prefer the
  translation script/API workflow instead of ad-hoc manual bulk edits.

Operational data:

- `data/ops/window-candidates.json` — exact-window candidates awaiting review.
- `data/ops/programme-candidates.json` — new programme candidates awaiting
  review.
- `data/ops/generic-programme-discovery.json` — configured generic discovery
  seed pages.
- `data/ops/reports/*.json` — generated audit/report outputs.
- `data/ops/*-state.json` — generated monitoring/discovery state.

The large programme and window candidate collections, plus programme catalogue
state, use small JSON manifests backed by per-university files under matching
`by-university/` directories. Always access these manifests through
`gradwindow.io.read_json` and `write_json`; do not parse the manifest files
directly or hand-edit shards. A single-school refresh should change only that
school's shard and the small manifest when the partition list changes.

Do not publish an application window unless all of these are known and official:

- university
- programme, programme group, or explicit scope
- intake
- applicant category
- application round, if applicable
- exact opening date
- exact closing date
- official application URL
- official source URL
- verification date

Month-only wording such as “September”, “mid-September”, or “opens in fall” is
not an exact date. Keep it as policy/guidance or a review candidate; do not
coerce it into an ISO date.

Third-party pages may help discovery, but official university pages are the only
authority for published dates.

## Local setup

Python:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

Frontend tooling:

```powershell
npm ci
```

If the package is not installed in the active shell, run CLI commands with:

```powershell
$env:PYTHONPATH='src'
python -m gradwindow.cli <command>
```

After editable install, `gradwindow <command>` is also valid.

## Core commands

Validate public data:

```powershell
gradwindow validate
```

Build deployable site:

```powershell
gradwindow build-site
```

Run full Python tests:

```powershell
pytest
```

Run lint and format checks:

```powershell
ruff check .
ruff format --check .
npm run lint
npm run format:check
```

Generate predictions, coverage, schemas, and README/site artifacts:

```powershell
gradwindow predictions
gradwindow coverage
gradwindow export-schemas
gradwindow readme
gradwindow build-site
```

Daily-style pipeline:

```powershell
gradwindow pipeline --skip-build
```

## Common workflows

### Add or correct an exact application window

1. Verify the official source page manually.
2. Add a pending record to `data/ops/window-candidates.json`, or use an adapter
   that writes a candidate.
3. Run validation/tests.
4. Promote only after review:

```powershell
gradwindow approve-window <candidate-id> --reviewer <name>
```

Never let a parser write directly to `data/applications.json`.

### Discover new programmes with the generic crawler

1. Add or update an entry in `data/ops/generic-programme-discovery.json`.
2. Audit seed quality:

```powershell
gradwindow discover-generic-seeds
```

3. Run the configured batch:

```powershell
gradwindow discover-generic-batch --replace-existing
```

4. Review `data/ops/reports/generic-programme-discovery-report.json`.

Useful classification buckets:

- `readyToApprove` — exact windows with official opening dates.
- `needsOpeningReview` — closing dates found, opening dates inferred.
- `needsOpeningDate` — closing dates found, opening dates missing.
- `deadlineUnavailableMonitor` — programme discovered but no exact deadline.
- `comingSoonMonitor` — official page says applications/details will open later.
- `needsAdapter` — generic crawler could not safely interpret the page.

Generic discovery creates candidates only. It does not publish new programmes by
itself.

If a school blocks automated access, mark the config with
`accessStatus: "blocked"` and an `accessReason` rather than leaving the batch in
a permanent error state.

Blocked schools can opt into the assisted official-domain fallback with
`assistedDiscovery.enabled`. It uses Serper as the primary official-domain
search provider and Brave as an optional independent-index fallback. High
priority entries can merge both providers. Optional Cloudflare Browser
Rendering handles blocked page retrieval, and DeepSeek performs bounded
structured extraction. Search snippets may create programme-only candidates,
but exact dates require official full text and deterministic evidence checks.
See `docs/assisted-discovery.md`.

### Add a dedicated programme adapter

Dedicated adapters live in `src/gradwindow/programme_adapters/`. Existing
examples include `birmingham.py`, `bristol.py`, `mit.py`, `cuhk.py`, `polyu.py`,
`cambridge.py`, `edinburgh.py`, `glasgow.py`, `imperial.py`, `hku.py`, `hkust.py`,
`melbourne.py`, `monash.py`, `manchester.py`, `nus.py`, `oxford.py`, `sydney.py`,
and `uq.py`.

Register each dedicated adapter exactly once in
`programme_adapters/registry.py`; the CLI and manual Actions workflow derive
their supported keys from that registry. Do not add another hard-coded school
list to a workflow. If an enabled generic entry overlaps a dedicated adapter,
set `discoveryRole: "fallback"`: the daily pipeline runs it only when the
dedicated adapter fails.

#### Definition of done

Treat a school adapter as three explicit phases. Report the completed phase
accurately; do not call a catalogue-only integration a finished school adapter.

1. **Catalogue discovery** — the official source produces a plausibly complete,
   deduplicated set of master's programmes with official programme and
   application URLs.
2. **Window discovery** — official programme-, faculty-, or school-level sources
   are systematically checked for exact application opening and closing dates.
   If the university does not publish exact dates, record that limitation and
   place the programmes in the appropriate monitor/review bucket.
3. **Integration** — candidates and state are generated, translations are
   queued when needed, validation/build checks pass, and the change is pushed
   with green CI.

Phase 1 may still be useful, but describe it as "catalogue discovery complete;
application-window discovery pending." A programme count with zero exact
windows is not a completed deadline adapter unless the official sources have
been checked and the no-deadline policy is documented.

#### Efficient investigation order

Use the cheapest deterministic source first. Escalate only when the preceding
step cannot provide the required data:

1. Check existing generic discovery configuration, university records, and
   similar adapters.
2. Fetch the official HTML directly and inspect links, forms, embedded JSON,
   JSON-LD, sitemaps, RSS feeds, downloadable CSV/JSON, and PDFs.
3. Inspect only the relevant first-party JavaScript bundle for named API calls
   or public data endpoints. Prefer a stable public JSON/API endpoint over
   browser automation.
4. Use Browser/Playwright only when the data genuinely requires client-side
   execution or an authenticated/interactive flow.
5. Use assisted search/LLM extraction only as a bounded fallback for discovery;
   exact dates still require official full text and deterministic checks.

When a central catalogue lacks deadlines, group its programme detail URLs by
domain/faculty and test one representative page per group. Implement shared
faculty/domain rules before considering per-programme logic.

Apply a stop-loss: if one approach produces no new evidence after roughly ten
minutes, record the blocker and change strategy instead of repeatedly retrying
the same page or tool.

#### Implementation sequence

1. Define the expected catalogue count, deadline source, and completion phase
   before writing code.
2. Build a small fixture containing two or three representative official
   records and write focused parser tests.
3. Implement parsing into `DiscoveredCatalog`, `DiscoveredProgramme`, and
   `DiscoveredWindow`.
4. Run focused tests and a `--dry-run`; inspect counts, a few sample records,
   duplicate IDs, missing URLs, and window evidence.
5. Only after the dry run is credible, write operational candidate/state files.
   Do not generate thousands of JSON lines merely to debug the parser.
6. Ensure the adapter only creates candidates unless an explicit approval
   command promotes them.
7. Keep unrelated cleanup or report improvements in a separate commit so they
   cannot delay or obscure the adapter change.
8. Run `ruff check .`, `ruff format --check .`, focused tests, full `pytest`,
   `gradwindow validate`, frontend lint/format checks when relevant, and a site
   build to a temporary output directory when the public site should not change.

Keep repository searches scoped. Prefer commands such as:

```powershell
rg "search term" src tests .github web
```

Do not run broad recursive searches from the repository root when `site/`,
`data/evidence/`, virtual environments, caches, or generated operational JSON
could be traversed. Add explicit paths or exclusions.

Before pushing, fetch and rebase onto the latest remote `main`, because scheduled
monitoring workflows may have advanced it. If HTTPS connections reset, retry
Git operations with `-c http.version=HTTP/1.1` before changing remotes or using
more invasive workarounds.

Discovery also revisits programmes already present in `data/programs.json`.
Official new intake cycles and official date changes become pending records in
`data/ops/window-candidates.json`. Do not add a second, adapter-specific update
path for known programmes.

An exact-looking configured default is still inferred. Batch promotion requires
`opensAtBasis: "official"`; do not weaken this guard to make an adapter's output
approve successfully.

Prefer a generic seed when the official catalogue is simple and stable. Use a
dedicated adapter when deadlines are encoded in unusual JSON, PDFs, dynamic
pages, school-level rules, or applicant-specific rules.

### Translate new programme names

The GitHub Actions data workflow uses `DEEPSEEK_API_KEY` for translation during
scheduled/manual refreshes. Locally, run:

```powershell
python scripts/update_programme_translations.py
```

Do not assume English-only candidate names are final UI copy if translation
coverage is expected.

### Frontend changes

Edit the source files under `web/`, not `site/`:

- `web/index.html`
- `web/app.js`
- `web/styles.css`
- `web/i18n.js`
- supporting modules such as `web/window-grouping.js`,
  `web/ranking-filter.js`, `web/state.js`, `web/review.js`, `web/roadmap.js`

Then run:

```powershell
npm run lint
npm run format:check
gradwindow build-site
```

Keep mobile and desktop layouts aligned. When optimizing cards/lists, preserve
source links, data status, applicant category, intake, opening date, closing
date, add-to-calendar, and review/manual-check cues unless the task explicitly
changes that hierarchy.

## CI and deployment

Main checks:

- `.github/workflows/tests.yml`
  - Python ruff lint/format
  - JS ESLint/Prettier
  - pytest on Python 3.10 and 3.12
  - site build
- `.github/workflows/update-data.yml`
  - on push to relevant data/source files: predictions, validation, coverage
  - on schedule/manual dispatch: daily pipeline, translations, data review PR
- Cloudflare Workers/Pages deployment runs `gradwindow build-site` via Wrangler.

When CI fails, reproduce the exact failing command locally first. Common quick
fixes:

- `ruff check . --fix` for import ordering or lint autofixes.
- `ruff format .` for formatting.
- `gradwindow predictions` when generated predictions are stale.
- `gradwindow export-schemas` after model/schema changes.
- `gradwindow build-site` after frontend/data publication changes.

## Engineering rules for agents

- Start every task with `git status --short --branch`.
- Preserve unrelated user changes. Do not reset or discard files unless the
  user explicitly asks.
- Keep generated timestamp-only changes out of commits unless they are expected
  outputs of the task.
- Use `rg` for search.
- Use `apply_patch` for file edits.
- Add or update tests for behavioural changes.
- Do not hand-edit `site/`, `data/predictions.json`, or `docs/schemas/`.
- Do not treat successful parsing as sufficient for publication; review status
  and trust boundaries still apply.
- Use concrete dates in user-facing explanations and data notes.
- Do not fabricate admissions dates, source URLs, translations, or applicant
  categories.
- When network access is blocked by a university, record the limitation and
  move the school to a monitor/blocked workflow instead of adding guessed data.

## Git notes

This repository is often edited from Codex on Windows. The `.git` directory may
be readable but not writable from the agent process. If staging or committing
fails with permission errors, finish the code/data work, report verification
results, and give the user explicit `git add`, `git commit`, and `git push`
commands.

Use small, descriptive commits. Good examples:

- `support sitemap generic programme discovery`
- `classify blocked generic programme seeds`
- `add MIT programme discovery adapter`
- `fix mobile exception views`
