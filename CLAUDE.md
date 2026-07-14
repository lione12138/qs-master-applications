# CLAUDE.md

Claude-specific working notes for this repository.

Read `AGENTS.md` first. It is the project-wide source of truth for data trust,
publication rules, commands, and repository layout. This file adds Claude/Claude
Code operating guidance so future sessions do not rediscover the same project
constraints.

## Default operating mode

- Be conservative with admissions data. A parser or crawler result is not a
  publishable fact until it passes the review workflow described in `AGENTS.md`.
- Prefer small, reviewable diffs. This project has large JSON files, so broad
  rewrites are expensive and hard to audit.
- Start with `git status --short --branch`.
- Stage explicit files only. Do not use `git add .` unless the user explicitly
  asks for it and the worktree has been inspected.
- If `.git` writes fail on Windows, finish the implementation and give the user
  exact `git add`, `git commit`, and `git push` commands.
- Use concrete dates when discussing admissions windows, CI runs, or deployment
  state. Avoid relative wording like “today” without the actual date.

## Fast orientation

Important files and folders:

- `AGENTS.md` — project-wide AI instructions.
- `CONTRIBUTING.md` — human contribution and trust rules.
- `src/gradwindow/cli.py` — command entrypoint.
- `src/gradwindow/programme_adapters/` — dedicated and generic programme
  discovery adapters.
- `data/applications.json` — curated official application windows.
- `data/programs.json` — curated programmes.
- `data/ops/programme-candidates.json` — discovered programme candidates.
- `data/ops/window-candidates.json` — discovered exact-window candidates.
- `data/ops/generic-programme-discovery.json` — generic discovery seed config.
- `data/ops/reports/` — generated reports used to decide next work.
- Root JS/CSS/HTML files — frontend source.

The candidate and programme-catalog state JSON files are partition manifests.
Their records live under matching `by-university/` directories. Read and write
them through `gradwindow.io` so commands continue to see the legacy aggregate
shape while Git changes remain scoped to one university.
- `site/` — generated site output; do not edit directly.

## Command shortcuts

If the package is not installed in the current shell:

```powershell
$env:PYTHONPATH='src'
python -m gradwindow.cli <command>
```

Preferred checks before handoff:

```powershell
python -m ruff check .
python -m pytest -q
$env:PYTHONPATH='src'; python -m gradwindow.cli validate
$env:PYTHONPATH='src'; python -m gradwindow.cli build-site
git diff --check
```

For frontend work, also run:

```powershell
npm run lint
npm run format:check
```

For docs-only changes, `git diff --check` is usually enough unless the docs
change command examples or generated outputs.

## Admissions-data rules to enforce

Do not directly publish from discovery:

- Generic discovery and dedicated adapters should create candidates.
- Promotion into `data/applications.json` should happen through
  `approve-window` or `approve-programmes` after review.
- `data/predictions.json`, `site/`, and `docs/schemas/` are generated. Do not
  hand-edit them.

Do not infer exact dates from vague text:

- “Applications open in September” is not an ISO date.
- “Usually closes in May” is not a deadline.
- “Coming soon” belongs in monitor/review output, not the official table.

Official source hierarchy:

1. Official university admissions/programme pages.
2. Official PDFs from university domains.
3. Official structured JSON used by the university site.
4. Third-party sites only for discovery hints, never final data.

## Generic programme discovery workflow

Use this when a school has a reasonably discoverable official course catalogue.

```powershell
$env:PYTHONPATH='src'; python -m gradwindow.cli discover-generic-seeds
$env:PYTHONPATH='src'; python -m gradwindow.cli discover-generic-batch --replace-existing
```

Then inspect:

- `data/ops/reports/generic-seed-discovery-report.json`
- `data/ops/reports/generic-programme-discovery-report.json`
- `data/ops/programme-candidates.json`
- `data/ops/programme-catalog-state.json`

Classify outcomes pragmatically:

- `readyToApprove` — likely review-and-promote.
- `needsOpeningReview` or `needsOpeningDate` — do not publish yet.
- `deadlineUnavailableMonitor` — catalogue is useful, deadline is not exact.
- `comingSoonMonitor` — revisit later.
- `needsAdapter` — write or improve a dedicated adapter.
- `accessStatus: "blocked"` — use when official catalogue access returns 403 or
  equivalent access controls.

## Dedicated adapter workflow

The detailed, mandatory workflow and definition of done are in the
`Add a dedicated programme adapter` section of `AGENTS.md`. In particular, keep
catalogue discovery, application-window discovery, and final integration as
separate completion phases. Never describe phase 1 as a finished school adapter.

Use a dedicated adapter when:

- the catalogue is dynamic or hidden behind official JSON;
- deadlines are in PDFs;
- deadlines are school-level but programme pages are separate;
- applicant categories or rounds require custom parsing;
- generic discovery repeatedly produces sparse or misleading candidates.

Implementation checklist:

1. Try direct official HTML/API/sitemap/PDF inspection before browser or LLM
   fallbacks.
2. Add fixture-based focused tests before generating operational JSON.
3. Add or update an adapter under `src/gradwindow/programme_adapters/` and run a
   dry run before writing candidates.
4. Ensure adapter output remains candidate/review-oriented and exact windows
   have deterministic official evidence.
5. Run ruff, pytest, validate, and build-site; then fetch/rebase before pushing.

## Frontend workflow

Edit source files under `web/`, then rebuild `site/`.

Common files:

- `web/app.js`
- `web/styles.css`
- `web/i18n.js`
- `web/window-grouping.js`
- `web/ranking-filter.js`
- `web/index.html`

The QS/THE/ARWU ranking selectors should display different ranking attributes
from the same canonical university dataset. Do not split them into separate
school databases.

For compact-card or mobile-density changes, preserve the functional hierarchy:

- university/programme
- ranking
- intake
- applicant category
- opening and closing dates
- source status and source link
- add-to-calendar/favorite/manual-check affordances

## Generated-file hygiene

Many commands update timestamps or generated reports. Before handoff:

```powershell
git diff --stat
git diff -- data/coverage.json
git diff -- data/predictions.json
```

If a generated timestamp changed but is unrelated to the task, restore that
timestamp or explain why it must be committed.

Avoid committing `site/` unless the user wants deployable output committed or
the repository convention for the current task requires it.

## CI triage

When GitHub Actions fail:

1. Identify the workflow: `Tests`, `Update application windows`, Pages, or
   Cloudflare/Workers.
2. Read the failing command and reproduce locally.
3. Fix the smallest actual cause.
4. Rerun the relevant local checks.

Common failure fixes:

- Ruff import order: `python -m ruff check . --fix`
- Formatting: `python -m ruff format .`
- Generated predictions stale: `gradwindow predictions`
- Schema changes: `gradwindow export-schemas`
- Site/build entrypoint issues: `gradwindow build-site`

## Handoff format

End with:

- what changed;
- which files changed;
- checks run and results;
- anything intentionally left as candidate/review/monitor rather than
  published;
- exact commit commands if the agent could not commit.

Keep handoffs short and factual.
