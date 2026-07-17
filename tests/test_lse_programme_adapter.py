from __future__ import annotations

import pytest

from gradwindow.programme_adapters.lse import (
    APPLICATIONS_URL,
    CATALOG_URL,
    LSEAdapter,
)
from gradwindow.programme_adapters.lse import (
    _detail as _parse_detail,
)

CATALOG_HTML = """
<html><body><main>
  <h2>MA/MSc A-G</h2>
  <table><tr><th>Programme Code/Title</th></tr><tr><td>
    <a href="https://www.lse.ac.uk/study-at-lse/graduate/msc-data-science">
      G3U1 MSc Data Science
    </a>
  </td><td>Open</td><td>Limited availability</td></tr></table>
  <h2>MA/MSc H-O (including LLM)</h2>
  <table><tr><td><a href="/study-at-lse/graduate/ma-modern-history">
    V4MH MA Modern History
  </a></td><td>Open</td><td>Open</td></tr></table>
  <h2>MA/MSc P-Z (including MPA, MPP)</h2>
  <table><tr><td><a href="/study-at-lse/graduate/mpa-data-science-for-public-policy">
    M1DS MPA Data Science for Public Policy
  </a></td><td>Open</td><td>Open</td></tr></table>
  <h2>Executive Masters Degrees</h2>
  <table><tr><td><a href="/study-at-lse/graduate/msc-finance-part-time">
    N42A MSc Finance (part-time)
  </a></td><td>Open</td><td>Open</td></tr></table>
  <h2>Double Degrees</h2>
  <table>
    <tr><td><a href="/study-at-lse/graduate/lse-pku-double-degree">
      F92A LSE-PKU Double MSc Environmental Policy
    </a></td><td>Closed</td><td>Closed</td></tr>
    <tr><td><a href="/study-at-lse/graduate/lse-bocconi-double-degree">
      L4UU LSE-Bocconi Double Degree in European Public Policy
    </a></td><td>Closed</td><td>Closed</td></tr>
  </table>
</main></body></html>
"""

APPLICATIONS_HTML = """
<html><body><main>
  <p><strong>Applications for entry in 2026/27 will open on 8 October 2025</strong></p>
  <p>Most decisions are made on a rolling basis.</p>
</main></body></html>
"""


def _detail(title: str, department: str, deadline: str) -> str:
    return f"""
    <html><body><main>
      <div class="super-tag super-tag--department">{department}</div>
      <h1>{title}</h1>
      <div><div class="label">Academic year</div><div>2026/27</div></div>
      <div><div class="label">Application deadline</div>
        <div class="text-bold">{deadline}</div></div>
    </main></body></html>
    """


PAGES = {
    CATALOG_URL: CATALOG_HTML,
    APPLICATIONS_URL: APPLICATIONS_HTML,
    "https://www.lse.ac.uk/study-at-lse/graduate/msc-data-science": _detail(
        "MSc Data Science",
        "Department of Statistics",
        "None – rolling admissions. However, please note the funding deadlines",
    ),
    "https://www.lse.ac.uk/study-at-lse/graduate/ma-modern-history": _detail(
        "MA Modern History",
        "Department of International History",
        "None – rolling admissions",
    ),
    "https://www.lse.ac.uk/study-at-lse/graduate/mpa-data-science-for-public-policy": _detail(
        "MPA Data Science for Public Policy",
        "School of Public Policy",
        "Rolling admissions. Early application deadline: 22 January 2026.",
    ),
    "https://www.lse.ac.uk/study-at-lse/graduate/msc-finance-part-time": _detail(
        "MSc Finance (part-time)",
        "Department of Finance",
        "Round 1: 16 January 2026; Round 2: 10 April 2026",
    ),
    "https://www.lse.ac.uk/study-at-lse/graduate/lse-pku-double-degree": _detail(
        "LSE-PKU Double Degree",
        "Department of Geography and Environment",
        "Apply via LSE by 10 March 2026",
    ),
    "https://www.lse.ac.uk/study-at-lse/graduate/lse-bocconi-double-degree": _detail(
        "LSE-Bocconi Double Degree",
        "European Institute",
        'Apply to Bocconi via "My Application" by 5 March 2026',
    ),
}


def _fetcher(url: str) -> str:
    return PAGES[url]


def _adapter() -> LSEAdapter:
    return LSEAdapter(minimum_expected_programmes=6, maximum_expected_programmes=6)


def test_lse_adapter_discovers_all_official_masters_sections() -> None:
    catalog = _adapter().parse_catalog_from_fetcher(_fetcher)

    assert len(catalog.programmes) == 6
    assert len({item.id for item in catalog.programmes}) == 6
    assert catalog.application_opens_at == "2025-10-08"
    assert {item.degree_type for item in catalog.programmes} >= {"MA", "MPA", "MSc"}


def test_lse_adapter_preserves_existing_data_science_identity_and_department() -> None:
    catalog = _adapter().parse_catalog_from_fetcher(_fetcher)
    programme = next(
        item for item in catalog.programmes if item.name == "MSc Data Science"
    )

    assert programme.id == "lse-data-science-msc"
    assert programme.faculty == "London School of Economics and Political Science"
    assert programme.department == "Department of Statistics"
    assert programme.windows == []
    assert programme.parse_status == "no-deadline"


def test_lse_adapter_parses_direct_lse_rounds_with_official_opening() -> None:
    catalog = _adapter().parse_catalog_from_fetcher(_fetcher)
    mpa = next(item for item in catalog.programmes if item.degree_type == "MPA")
    finance = next(
        item for item in catalog.programmes if item.name.endswith("(part-time)")
    )
    pku = next(item for item in catalog.programmes if item.id.startswith("lse-f92a"))

    assert [(item.round, item.opens_at, item.closes_at) for item in mpa.windows] == [
        ("Early application deadline", "2025-10-08", "2026-01-22")
    ]
    assert [(item.round, item.closes_at) for item in finance.windows] == [
        ("Round 1", "2026-01-16"),
        ("Round 2", "2026-04-10"),
    ]
    assert pku.windows[0].closes_at == "2026-03-10"
    assert all(item.parse_status == "parsed" for item in (mpa, finance, pku))


def test_lse_adapter_does_not_invent_partner_application_opening() -> None:
    catalog = _adapter().parse_catalog_from_fetcher(_fetcher)
    bocconi = next(item for item in catalog.programmes if "Bocconi" in item.name)

    assert bocconi.windows == []
    assert bocconi.parse_status == "incomplete"
    assert "5 March 2026" in bocconi.deadline_text


def test_lse_adapter_rejects_missing_official_opening_date() -> None:
    pages = {**PAGES, APPLICATIONS_URL: "<html><body>Rolling admissions</body></html>"}

    with pytest.raises(ValueError, match="exact 2026/27 opening date"):
        _adapter().parse_catalog_from_fetcher(pages.__getitem__)


def test_lse_adapter_keeps_explicitly_nonrunning_programme_as_monitoring() -> None:
    html = _detail(
        "Executive MSc Healthcare Decision-Making",
        "Department of Health Policy",
        "Not accepting applications for 2026 entry",
    ).replace(
        "<div>2026/27</div>",
        "<div>Not accepting applications for 2026 entry</div>",
    )

    parsed = _parse_detail(html, "https://www.lse.ac.uk/study-at-lse/graduate/example")

    assert parsed.deadline == "Not accepting applications for 2026 entry"


def test_lse_adapter_rejects_a_truncated_catalogue() -> None:
    with pytest.raises(ValueError, match="only contained 6 master's programmes"):
        LSEAdapter(
            minimum_expected_programmes=7,
            maximum_expected_programmes=10,
        ).parse_catalog_from_fetcher(_fetcher)
