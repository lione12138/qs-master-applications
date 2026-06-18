# Data provenance

GradWindow's original curation and annotations are licensed separately from
the software. See [`DATA_LICENSE.md`](../DATA_LICENSE.md) for the applicable
terms, attribution requirements, and third-party exclusions.

## Ranking

- Edition: QS World University Rankings 2027
- Official ranking page: <https://www.topuniversities.com/world-university-rankings>
- Official publication date: 2026-06-18
- Parsed source: QS ranking page endpoint for node `4153156`
- Imported rows: first 200 institution rows
- Tie handling: retain the `rank_display` value published by QS

## Institution identities

Official homepages and domains were resolved through the ROR v2 affiliation
API. Five false-positive affiliation matches were replaced with manually
verified official domains.

## Admissions pages

Admissions links have one of four states:

- `curated`: manually reviewed official link
- `discovered`: high-confidence page found on an official domain
- `low-confidence`: official-domain candidate that still needs review
- `not-found`: official homepage is available, but no general graduate page
  was accepted

No programme deadline is inferred from a university-level page.

## Next-cycle predictions

`predictions.json` is generated only from records already published in
`applications.json`. For each matching scope, round, and applicant category,
the generator selects the most recent verified cycle and shifts the intake,
opening date, and closing date by one calendar year.

Predictions are non-official, remain separate from verified coverage totals,
and link back to the prior-cycle official source. When an official record for
the target cycle is added, that cycle's prediction is removed automatically.

## Evidence snapshots

Checks of published-window sources store a content hash, final URL, response
metadata, and a short deadline-related excerpt under `data/evidence/`. Full
webpages are not retained. These files support later review of what the
monitor observed without treating an automatic observation as verification.
