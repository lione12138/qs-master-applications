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
`assistedDiscovery.enabled`. It uses Brave Search for official URL discovery,
optional Cloudflare Browser Rendering for page retrieval, and DeepSeek for
structured extraction. Search snippets may create programme-only candidates,
but exact dates require official full text and deterministic evidence checks.
See `docs/assisted-discovery.md`.

### Add a dedicated programme adapter

Dedicated adapters live in `src/gradwindow/programme_adapters/`. Existing
examples include `mit.py`, `cuhk.py`, `polyu.py`, `cambridge.py`,
`glasgow.py`, `imperial.py`, `hku.py`, `hkust.py`, `melbourne.py`, `monash.py`,
`oxford.py`, `sydney.py`, and `uq.py`.

Expected pattern:

1. Read official catalogue/admissions pages.
2. Implement parsing into `DiscoveredCatalog`, `DiscoveredProgramme`, and
   `DiscoveredWindow`.
3. Add focused tests under `tests/`.
4. Ensure the adapter only creates candidates unless an explicit approval
   command promotes them.
5. Run `ruff check .`, `pytest`, `gradwindow validate`, and
   `gradwindow build-site`.

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
