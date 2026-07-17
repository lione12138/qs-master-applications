# Discovery and monitoring schedule

GradWindow separates operational work by freshness and trust impact.

## High-frequency monitoring

`.github/workflows/update-data.yml` runs daily. It checks university admissions
entry pages and every published application-window source, refreshes configured
deadline parsers, validates public data, and opens a review pull request. It does
not crawl every programme catalogue.

## Active programme adapters

`.github/workflows/refresh-active-programmes.yml` runs daily but selects no more
than eight adapters whose current candidate state contains application windows
and whose last successful catalogue snapshot is at least seven days old. The
oldest eligible adapters run first, so the work naturally spreads across days.

## Catalogue-only and generic discovery

`.github/workflows/scan-programme-catalogues.yml` runs weekly. It selects no more
than six catalogue-only dedicated adapters whose last successful snapshot is at
least 30 days old. It also runs generic entries whose `discoveryRole` is
`primary`; fallback entries remain tied to dedicated-adapter failures.

All tiers write operational candidates only. Publication still requires an
evidence-locked maintainer approval.

All workflows that can write operational data share the
`gradwindow-data-writes` concurrency group, so scheduled and manual refreshes
cannot update the same partitioned manifests at the same time.
