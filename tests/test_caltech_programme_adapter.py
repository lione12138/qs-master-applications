from __future__ import annotations

from gradwindow.programme_adapters.caltech import (
    APPLICATION_URL,
    CATALOG_URL,
    CaltechAdapter,
)

AEROSPACE_URL = (
    "https://catalog.caltech.edu/current/information-for-graduate-students/"
    "special-regulations-for-graduate-options/aerospace-ae/"
)
ELECTRICAL_ENGINEERING_URL = (
    "https://catalog.caltech.edu/current/information-for-graduate-students/"
    "special-regulations-for-graduate-options/electrical-engineering-ee/"
)

SITEMAP_XML = f"""
<urlset>
  <url><loc>{AEROSPACE_URL}</loc></url>
  <url><loc>{ELECTRICAL_ENGINEERING_URL}</loc></url>
  <url><loc>https://catalog.caltech.edu/current/areas-of-study-and-research/</loc></url>
</urlset>
"""

AEROSPACE_HTML = """
<html><body><main>
  <h1>Aerospace (AE)</h1>
  <h2>Admission</h2>
  <p>Students whose highest qualification is a baccalaureate degree are
  eligible to seek admission to work toward the master's degree.</p>
  <h2>Master's Degree in Aeronautics and Master's Degree in Space Engineering</h2>
  <p>The master's degree program in aeronautics or space engineering is a
  one-year program.</p>
</main></body></html>
"""

ELECTRICAL_ENGINEERING_HTML = """
<html><body><main>
  <h1>Electrical Engineering (EE)</h1>
  <h2>EE Master's Degree</h2>
  <p>The principal criteria for evaluating applicants for the MSEE are the
  excellence of their preparation.</p>
  <p>Students who have been admitted to the M.S.-only program must reapply if
  they are interested in the Ph.D. program.</p>
</main></body></html>
"""

APPLICATION_HTML = """
<html><body><main>
  <h1>Apply Online</h1>
  <p>Check the Application Deadlines for the particular academic program.</p>
  <p>Deadlines vary by program from December 1 to December 15.</p>
</main></body></html>
"""


def _fetcher(url: str) -> str:
    if url == CATALOG_URL:
        return SITEMAP_XML
    if url == AEROSPACE_URL:
        return AEROSPACE_HTML
    if url == ELECTRICAL_ENGINEERING_URL:
        return ELECTRICAL_ENGINEERING_HTML
    if url == APPLICATION_URL:
        return APPLICATION_HTML
    raise AssertionError(url)


def test_caltech_adapter_keeps_only_direct_entry_masters_programmes() -> None:
    catalog = CaltechAdapter().parse_catalog_from_fetcher(_fetcher)

    assert catalog.application_opens_at is None
    assert [programme.id for programme in catalog.programmes] == [
        "caltech-aeronautics-ms",
        "caltech-electrical-engineering-ms",
        "caltech-space-engineering-ms",
    ]
    assert [programme.name for programme in catalog.programmes] == [
        "MS Aeronautics",
        "MS Electrical Engineering",
        "MS Space Engineering",
    ]
    assert all(programme.windows == [] for programme in catalog.programmes)
    assert all(
        programme.parse_status == "no-deadline" for programme in catalog.programmes
    )
    assert all(
        "December 1 to December 15" in programme.deadline_text
        for programme in catalog.programmes
    )


def test_caltech_adapter_rejects_missing_direct_admission_evidence() -> None:
    def fetcher(url: str) -> str:
        if url == ELECTRICAL_ENGINEERING_URL:
            return "<html><body><h1>Electrical Engineering</h1></body></html>"
        return _fetcher(url)

    try:
        CaltechAdapter().parse_catalog_from_fetcher(fetcher)
    except ValueError as exc:
        assert "direct-entry master's programmes" in str(exc)
    else:
        raise AssertionError("Incomplete Caltech catalogue was accepted")
