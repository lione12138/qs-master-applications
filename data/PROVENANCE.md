# Data provenance

## Ranking

- Edition: QS World University Rankings 2026
- Official ranking page: <https://www.topuniversities.com/world-university-rankings>
- Official publication date: 2025-06-19
- Parsed workbook source:
  <https://github.com/olgagaffarova/QS-University-Rankings-2026>
- Imported rows: first 200 institution records
- Tie handling: retain the rank value published by QS

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
