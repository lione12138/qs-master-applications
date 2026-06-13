# Technical architecture

GradWindow is a Python data pipeline that publishes a zero-backend static site.

## Project layout

```text
data/
  universities.json          QS top-200 institution directory
  programs.json              programme directory and inheritance targets
  applications.json          verified scoped application windows
  predictions.json           generated non-official next-cycle estimates
  window-policies.json       reviewed institution granularity policies
  admissions-overrides.json  manually reviewed admissions links
  monitor-state.json         daily availability and content fingerprints
  application-source-state.json
                              checks for published exact-window sources
  review-queue.json          internal findings awaiting review
  window-candidates.json     exact-window proposals awaiting approval
  coverage.json              generated QS top-30 quality metrics
  sources.json               dedicated programme parser configuration
reports/                     daily internal monitoring reports
src/gradwindow/
  cli.py                      command entry point
  validation.py               public data contracts
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
`review-queue.json` and `reports/` are intentionally excluded from the public
site build.

## Commands

```powershell
gradwindow validate
gradwindow monitor
gradwindow monitor-sources
gradwindow update-deadlines --dry-run
gradwindow predictions
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

## Operational limitations

- Many universities publish dates only inside programme catalogues.
- JavaScript-heavy or bot-protected pages may be marked `blocked`.
- A new page fingerprint must appear on two consecutive successful checks.
  The confirmed change is still only a review signal, not proof that a
  deadline changed.
- General-purpose date scraping is deliberately prohibited for publication.
