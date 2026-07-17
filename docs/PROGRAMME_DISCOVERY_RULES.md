# Programme discovery rules

GradWindow treats programme discovery as a conservative data pipeline, not as
free-form scraping. The goal is to discover new official master's programmes
quickly while only publishing records that have exact, source-backed application
windows.

## Pipeline

1. Start from the university's official admissions or course-search page.
2. Discover official postgraduate-taught / master's catalogue pages.
3. Extract programme cards or table rows into `DiscoveredProgramme` records.
4. Visit programme detail pages when the catalogue does not publish exact
   opening and closing dates.
5. Parse only exact application windows with both `opensAt` and `closesAt`.
6. Diff adapter observations against both the programme catalogue and existing
   official application cycles.
7. Write new programmes to `data/ops/programme-candidates.json`; write new
   official cycles or changed official dates for known programmes to
   `data/ops/window-candidates.json`.
8. Promote only reviewed candidates with exact, officially sourced windows into:
   - `data/programs.json`
   - `data/applications.json`
   - `data/evidence/*.json`
9. Keep no-deadline, rolling-admission, and incomplete-opening candidates in
   ops data until a human confirms the official interpretation.

## Search rules

Use these rules in order. Stop at the first reliable official source.

### 1. Official-domain constraint

- Accept only URLs on the university's `officialDomains`.
- Reject aggregators, agents, rankings, PDFs mirrored outside the school domain,
  and search-result snippets.
- A linked external application portal is allowed only as `applicationUrl`; the
  date evidence must still come from an official university page unless the
  university explicitly delegates admissions dates to that portal.

### 2. Catalogue-page detection

A page is a strong programme catalogue candidate if it has at least two of:

- URL contains `course`, `programme`, `program`, `degree`, `postgraduate`,
  `graduate`, `masters`, `taught`, or equivalent local-language terms.
- Page title or `h1` contains postgraduate / master's course-search language.
- Repeated cards, rows, or list items link to individual course pages.
- Filter fields include degree level, subject, department, study mode, duration,
  or intake year.
- Pagination or total result count is present.

### 3. Programme-card extraction

For each repeated card/table row:

- Required:
  - programme name
  - source URL
  - degree type, either explicit (`MSc`, `MPhil`, `MRes`, `LLM`, `MBA`, etc.) or
    inferable from the title
- Optional but preferred:
  - department/faculty
  - start date/intake
  - application portal URL
- Generate a stable programme id:
  `{school-prefix}-{normalised-title}-{normalised-degree}`

### 4. Detail-page extraction

Visit the programme detail page when exact dates are not in the catalogue.
Search near headings such as:

- `How to apply`
- `Application deadlines`
- `Application rounds`
- `Admissions timeline`
- `Key dates`
- `Deadlines`

Exact windows require:

- an opening date;
- a closing/deadline date;
- an intake/cycle, either from the page or the course URL/year;
- a clear scope: programme, programme group, applicant category, or round.

### 5. Date parsing

Publish only exact dates. Accept:

- `29 September 2025`
- `September 29, 2025`
- `2025-09-29`
- explicit ranges such as `1 October 2025 to 5 November 2025`
- structured rows with separate open/close cells

Do not publish as official windows:

- `early fall`
- `from January onwards`
- `rolling until full`
- `applications are now closed`
- scholarship-only dates
- visa/CAS processing recommendations unless the page states they are actual
  application deadlines for that applicant category

### 6. Candidate statuses

- `parsed`: exact programme window(s) with opening and closing dates. The
  opening date still carries an independent `opensAtBasis` provenance value.
- `incomplete`: deadline is exact but opening date or applicant scope needs
  review.
- `no-deadline`: programme exists, but no exact application window was found.

Only `parsed` windows whose `opensAtBasis` is exactly `official` may be
promoted. A configured or inferred exact-looking date remains a review
observation and must not cross the publication boundary.

### 7. Promotion rule

First inspect the immutable evidence hash:

```bash
python -m gradwindow.cli programme-candidate-hash <candidate-id>
```

Then approve that exact candidate and evidence version:

```bash
python -m gradwindow.cli approve-programme <candidate-id> \
  --evidence-hash <sha256> \
  --reviewer <reviewer>
```

This promotes only the named pending `new-programme` candidate when its current
content matches the supplied evidence hash, `parseStatus` is `parsed`, and the
opening dates are officially sourced. It creates programme-scoped application
windows, writes an append-only approval audit record, marks a fully promoted
candidate as approved, and regenerates predictions.

Dedicated and generic adapters also revisit programmes that already exist in
`data/programs.json`. A newly observed official intake cycle becomes an
`adapter-new-window` candidate; an official date change for an existing cycle
becomes an `adapter-window-change` candidate. Both use the normal
`approve-window` command and never write directly to `data/applications.json`.

After promotion, run:

```bash
python -m gradwindow.cli monitor-sources
python -m gradwindow.cli validate
python -m gradwindow.cli build-site
```

## When a school still needs an adapter

Write a small university-specific adapter only when the generic search rules
cannot safely identify one of:

- the catalogue pagination/API;
- the programme card fields;
- the detail-page date pattern;
- a repeated department-level application-round pattern.

Adapters should stay thin: fetch catalogue pages, map cards to
`DiscoveredProgramme`, parse exact repeated date patterns, and leave ambiguous
items as candidates.

## Current adapter notes

- HKU uses official `SavedQueryService/Execute` catalogue endpoints and
  programme detail pages. The detail pages publish exact deadline rounds, but
  not exact opening dates, so HKU discoveries remain `incomplete` candidates
  until an official opening date is confirmed.
- Edinburgh publishes programme-level deadlines in the degree finder, but the
  general applying page does not publish an exact taught-postgraduate opening
  date. Those candidates should not be promoted without a confirmed opening
  date.
- King's College London states that applications usually open from mid-October,
  which is not an exact date. Course pages may expose an application-closing
  guidance section, but empty or generic guidance must remain in candidates.
- HKUST's official Program & Course Catalog exposes taught master's programme
  pages and exact 2026/27 Fall deadline rounds by local/non-local applicant
  category. The pages do not publish exact opening dates, so these discoveries
  remain `incomplete` candidates.
- NUS public pages currently return an Incapsula challenge to the automated
  fetcher. Do not add a NUS adapter until a stable official endpoint or export
  can be verified.
- UNSW publishes exact institution-level application closing dates, while
  programme pages point back to those shared dates and do not expose exact
  opening dates. Treat this as a future school-level/shared-window candidate
  source rather than a programme adapter.
- UQ's official sitemap exposes master programme pages. Programme pages publish
  exact closing dates by domestic/international student type and semester, but
  do not publish exact opening dates, so UQ discoveries remain `incomplete`
  candidates.
