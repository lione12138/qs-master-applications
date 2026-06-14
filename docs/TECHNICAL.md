# Technical architecture

GradWindow is a Python data pipeline that publishes a zero-backend static site.

## Project layout

```text
data/
  universities.json          QS top-200 institution directory
  programs.json              programme directory and inheritance targets
  programme-groups.json      validated programme-group scope registry
  applicant-categories.json  canonical applicant category registry
  applications.json          verified scoped application windows
  predictions.json           generated non-official next-cycle estimates
  evidence/                  source hashes and short evidence excerpts
  window-policies.json       reviewed institution granularity policies
  admissions-overrides.json  manually reviewed admissions links
  ops/
    monitor-state.json       daily availability and content fingerprints
    application-source-state.json
                              checks for published exact-window sources
    review-queue.json        internal findings awaiting review
    window-candidates.json   exact-window proposals awaiting approval
    reports/                 daily internal monitoring reports
  coverage.json              generated QS top-30 quality metrics
  sources.json               dedicated programme parser configuration
src/gradwindow/
  cli.py                      command entry point
  validation.py               public data contracts
  models.py                   Pydantic v2 domain models
  intakes.py                  structured intake parsing and migration
  http_client.py              retries, throttling, redirects, error taxonomy
  content.py                  main-content extraction and evidence snippets
  monitor.py                  low-frequency official-page monitoring
  deadlines.py                conservative programme date updates
  discovery.py                admissions-page classification rules
  site.py                     deployable static-site builder
scripts/
  discover_admissions.py      maintenance discovery tool
  import_qs_top200.py         ranking import tool
  *.py                        compatibility wrappers
tests/                        offline behavioural and contract tests
site/                         generated deployment artifact
```

## Pipeline

```text
universities.json + admissions overrides
                |
                v
official page monitor ----> monitor-state.json
                |                    |
                v                    v
          review queue/report   source adapters
                                     |
programs + window policies ----------+--> applications.json
                |
                +--> predictions.json (latest verified cycle + one year)
                |
                v
validation -> static site build -> GitHub Pages
```

## Window inheritance

Application periods are not forced into one granularity:

```text
institution default
        |
programme-group override
        |
programme exception
```

The most specific applicable verified record wins. Applicant categories and
intake remain part of the match, so an international deadline cannot silently
replace a domestic or scholarship deadline.

Every dated record keeps both a human label (`intake`) and a structured
`intakeDetails` object. Identity and prediction logic use the structured
cycle year, term, academic-year end, and start month rather than comparing
free text.

`window-policies.json` is the source of truth for granularity. The historical
`datePolicy` value still present on some university directory records is not
used for publication or validation.

## Confidence layers

- `curated`: a maintainer reviewed the official admissions link.
- `discovered`: an official-domain page passed strict classification.
- `low-confidence`: an official-domain candidate needs manual review.
- `not-found`: the official university homepage is known, but no general
  graduate admissions page was accepted.

Records in `applications.json` are official dated windows. Generated records
in `predictions.json` appear in a separate non-official section and never
increase verified coverage metrics.
`data/ops/review-queue.json` and `data/ops/reports/` are intentionally excluded from the public
site build.

## Commands

```powershell
gradwindow validate
gradwindow monitor
gradwindow monitor-sources
gradwindow update-deadlines --dry-run
gradwindow predictions
gradwindow migrate-intakes
gradwindow export-schemas
gradwindow coverage
gradwindow approve-window candidate-id --reviewer maintainer-name
gradwindow build-site
gradwindow pipeline
```

The `pipeline` command performs monitoring, dedicated deadline updates,
prediction regeneration, validation, coverage generation, review reporting,
and site generation. When an official target-cycle record is added, the
matching prediction is removed automatically.

Dedicated parsers never write directly to `applications.json`. A detected
date change becomes a pending item in `window-candidates.json` and must pass
`approve-window` before publication.

`approve-window` performs a full validation against a temporary proposed
applications dataset before writing the approved record. Candidate and review
files are never copied into `site/`.

## Data contracts

Pydantic models validate URLs, dates, enums, unknown fields, and cross-field
rules. Hand-written validation is limited to cross-file relationships such as
programme ownership, official-domain checks, and semantic uniqueness.
Machine-readable contracts are generated under `docs/schemas/`.

## HTTP and evidence

All pipeline fetches use `httpx` with redirect support, explicit timeouts,
per-host throttling, retryable error classification, and exponential backoff.
Fingerprints are computed from the likely main content after removing scripts,
navigation, footers, cookie banners, and other repeated chrome.

Published-window source checks write a compact audit record to `data/evidence/`
containing the final URL, content hash, response metadata, a short
deadline-related excerpt, the matched line, adjacent context, and the selected
main-content region. Full HTML is intentionally not retained.

Monitoring classifies confirmed changes as `deadline`, `application`, or
`generic`. Only deadline-significant changes create GitHub issues; lower
severity changes remain visible in the review queue and daily report.

The static build emits university, country, and deadline-month index pages in
addition to the JavaScript board, plus `sitemap.xml`, `robots.txt`, canonical
links, and OpenGraph metadata.

## Operational limitations

- Many universities publish dates only inside programme catalogues.
- JavaScript-heavy or bot-protected pages may be marked `blocked`.
- A new page fingerprint must appear on two consecutive successful checks.
  The confirmed change is still only a review signal, not proof that a
  deadline changed.
- General-purpose date scraping is deliberately prohibited for publication.
