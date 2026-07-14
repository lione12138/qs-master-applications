from __future__ import annotations

import pytest

from gradwindow.programme_adapters.manchester import (
    AMBS_APPLICATION_URL,
    CATALOG_URL,
    ManchesterAdapter,
)

CATALOGUE = """
<html><body>
  <a href="../21573/msc-advanced-computer-science/">Advanced Computer Science MSc</a>
  <a href="../08025/msc-aerospace-engineering/">Aerospace Engineering MSc</a>
  <a href="../21876/msc-applied-ai-for-medical-imaging/">Applied AI for Medical Imaging MSc</a>
  <a href="../10867/msc-accounting/">Accounting MSc</a>
  <a href="../09977/pgcert-approved-mental-health-professional-practice/">Approved Mental Health Professional Practice PGCert</a>
</body></html>
"""

STAGED = """
<html><head><title>MSc Advanced Computer Science (2026 entry)</title></head><body>
  <h1>MSc Advanced Computer Science</h1>
  <dl><dt>Department</dt><dd>Department of Computer Science</dd></dl>
  <p>Year of entry: 2026</p>
  <h2>Application and selection</h2>
  <h3>Staged admissions</h3>
  <p>Applications for 2026 entry:</p>
  <p>
    <strong>Stage 1</strong>: Application received by 7 November 2025;
    Decision by 9 January 2026.
    <strong>Stage 2</strong>: Application received by 2 January 2026;
    Decision by 6 March 2026.
    <strong>Stage 3</strong>: Application received by 1 May 2025;
    Decision by 1 June 2026.
  </p>
  <p>Offer conditions must be met by 31 July 2026.</p>
  <h2>Course details</h2><p>Assessment deadline 1 August 2026.</p>
</body></html>
"""

SINGLE = """
<html><body>
  <h1>MSc Aerospace Engineering</h1><p>Year of entry: 2026</p>
  <h2>Application and selection</h2>
  <p>The application deadline for this course is 31 March 2026.</p>
  <p>Offer conditions must be met by 31 July 2026.</p>
  <h2>Course details</h2>
</body></html>
"""

NO_DEADLINE = """
<html><body>
  <h1>MSc Applied AI for Medical Imaging</h1><p>Year of entry: 2026</p>
  <h2>Application and selection</h2>
  <p>Apply online. Applications are considered while places remain available.</p>
  <h2>Course details</h2>
</body></html>
"""

ACCOUNTING = """
<html><body>
  <h1>MSc Accounting</h1><p>Year of entry: 2026</p>
  <dl><dt>School/Faculty</dt><dd>Alliance Manchester Business School</dd></dl>
  <h2>Application and selection</h2><p>Apply online.</p>
  <h2>Course details</h2>
</body></html>
"""

AMBS_DEADLINES = """
<html><body>
  <p>Applications for September 2026 entry will open on 13 October 2025.</p>
  <table>
    <tr><th>Stage</th><th>Application received by:</th><th>Application update by:</th></tr>
    <tr><td>1</td><td>7 December 2025</td><td>20 February 2026</td></tr>
    <tr><td>2</td><td>1 March 2026</td><td>1 May 2026</td></tr>
    <tr><td>3</td><td>3 May 2026</td><td>19 June 2026</td></tr>
    <tr><td>4</td><td>5 July 2026</td><td>31 July 2026</td></tr>
  </table>
</body></html>
"""


def test_manchester_adapter_reads_complete_catalogue_and_safe_deadlines() -> None:
    adapter = ManchesterAdapter(minimum_expected_programmes=4, detail_workers=1)

    def fetcher(url: str) -> str:
        if url == CATALOG_URL:
            return CATALOGUE
        if url == AMBS_APPLICATION_URL:
            return AMBS_DEADLINES
        if "/21573/" in url:
            return STAGED
        if "/08025/" in url:
            return SINGLE
        if "/21876/" in url:
            return NO_DEADLINE
        if "/10867/" in url:
            return ACCOUNTING
        raise AssertionError(url)

    catalog = adapter.parse_catalog_from_fetcher(fetcher)

    assert [programme.name for programme in catalog.programmes] == [
        "MSc Accounting",
        "MSc Advanced Computer Science",
        "MSc Aerospace Engineering",
        "MSc Applied AI for Medical Imaging",
    ]
    accounting = catalog.programmes[0]
    assert accounting.faculty == "Alliance Manchester Business School"
    assert accounting.parse_status == "parsed"
    assert [
        (window.round, window.opens_at, window.closes_at)
        for window in accounting.windows
    ] == [
        ("Stage 1", "2025-10-13", "2025-12-07"),
        ("Stage 2", "2025-10-13", "2026-03-01"),
        ("Stage 3", "2025-10-13", "2026-05-03"),
        ("Stage 4", "2025-10-13", "2026-07-05"),
    ]
    advanced = catalog.programmes[1]
    assert advanced.faculty == "Department of Computer Science"
    assert advanced.parse_status == "incomplete"
    assert [
        (window.round, window.opens_at, window.closes_at, window.intake)
        for window in advanced.windows
    ] == [
        ("Stage 1", None, "2025-11-07", "September 2026"),
        ("Stage 2", None, "2026-01-02", "September 2026"),
    ]
    aerospace = catalog.programmes[2]
    assert [(window.round, window.closes_at) for window in aerospace.windows] == [
        ("Application deadline", "2026-03-31")
    ]
    assert catalog.programmes[3].parse_status == "no-deadline"
    assert catalog.programmes[3].windows == []


def test_manchester_adapter_keeps_temporarily_failed_detail_page() -> None:
    adapter = ManchesterAdapter(minimum_expected_programmes=4, detail_workers=1)

    def fetcher(url: str) -> str:
        if url == CATALOG_URL:
            return CATALOGUE
        raise RuntimeError("temporary block")

    catalog = adapter.parse_catalog_from_fetcher(fetcher)

    assert len(catalog.programmes) == 4
    assert all(
        programme.parse_status == "no-deadline" for programme in catalog.programmes
    )
    assert all(
        "temporary block" in programme.deadline_text for programme in catalog.programmes
    )


def test_manchester_adapter_rejects_implausibly_small_catalogue() -> None:
    adapter = ManchesterAdapter(minimum_expected_programmes=5, detail_workers=1)

    with pytest.raises(ValueError, match="only contained 4 master's programmes"):
        adapter.parse_catalog_from_fetcher(lambda url: CATALOGUE)
