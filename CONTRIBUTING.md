# Contributing

GradWindow prioritizes correctness over the number of displayed deadlines.

## Ways to contribute

- Correct a university homepage or graduate admissions link.
- Add a programme-level application window.
- Add a dedicated parser for a stable official programme page.
- Improve tests, accessibility, documentation, or the static website.

## Local setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pytest
gradwindow build-site
python -m http.server 8000 --directory site
```

## Trust rules

An application window may be published only when all of these are known:

- university
- institution, programme group, or programme scope
- intake
- application round, when applicable
- opening and closing date
- official application URL
- official source URL
- verification date
- structured intake details matching the display label

Do not turn an institution-level page into a single university-wide deadline.
Do not convert “September”, “mid-September”, or an unqualified month/day into
an exact ISO date. Store that information as policy `cycleGuidance` instead.
Do not promote an automatically discovered admissions candidate to `curated`
without opening and reviewing the official page.

`data/predictions.json` is generated. Do not edit it manually. Predictions use
the most recent verified record for the same scope, round, and applicant
category, then shift its intake and dates by one calendar year. They remain
non-official even when historical dates have been stable.

Configured parsers must only create candidates. Direct automated writes to
`data/applications.json` are prohibited because a page layout change can
produce a syntactically valid but semantically incorrect date.

## Exact-window review

1. Add the proposed record to `data/window-candidates.json`.
2. Keep its status as `pending`.
3. Verify the official source, scope, intake, applicant category, and both
   exact dates.
4. Run:

```powershell
gradwindow approve-window candidate-id --reviewer your-name
```

The command validates the complete public dataset before promoting the record
to `data/applications.json`.

Every behavioural change to parsing, validation, monitoring, or publication
must include a test.

Run `gradwindow export-schemas` after changing a Pydantic model. Do not hand
edit files under `docs/schemas/`.
