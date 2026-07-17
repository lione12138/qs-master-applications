from __future__ import annotations

import pytest

from gradwindow.programme_adapters.ntu_tw import (
    ADMISSIONS_URL,
    NTUTaiwanAdapter,
)

CATALOG_URL = (
    "https://oiasystem.ntu.edu.tw/globaladmission/foreign/requirement/"
    "dept.list/id/current/fsemester/1/fdisplay/1?lang=en"
)

ADMISSIONS_HTML = f"""
<main>
  <a href="{CATALOG_URL}">2027 February Entry (Graduate programs only)</a>
  <a href="https://oiasystem.ntu.edu.tw/globaladmission/foreign/requirement/dept.list/id/fall?lang=en">2027 September Entry (TBA)</a>
</main>
"""

CATALOG_HTML = """
<main>
  <h1>2026/2027 Available Graduate Degree Programs and Application Requirements</h1>
  <p>First Round：2026-08-03~2026-09-17</p>
  <table>
    <tr><th>College</th><th>Department/Graduate Institute</th><th>First Round</th></tr>
    <tr class="js-degreeTr js-showM js-showD">
      <td class="js-college">College of Electrical Engineering and Computer Science</td>
      <td class="js-deptName" data-degree="B">Department of Computer Science and Information Engineering</td><td data-degree="B">-</td>
      <td class="js-deptName" data-degree="M">Department of Computer Science and Information Engineering</td>
      <td data-degree="M"><a href="/globaladmission/foreign/requirement/dept.detail/id/current/degree_key/M/sn/1"><span class="circle blue"></span></a></td>
      <td class="js-deptName" data-degree="D">Department of Computer Science and Information Engineering</td><td data-degree="D">-</td>
    </tr>
    <tr class="js-degreeTr js-showM">
      <td class="js-college">College of Science</td>
      <td class="js-deptName" data-degree="M">Institute of Astrophysics</td>
      <td data-degree="M"><a href="/globaladmission/foreign/requirement/dept.detail/id/current/degree_key/M/sn/2"><span class="circle gray"></span></a></td>
    </tr>
    <tr class="js-degreeTr js-showD">
      <td class="js-college">College of Medicine</td>
      <td class="js-deptName" data-degree="M">Doctoral-only Example</td><td data-degree="M">-</td>
      <td class="js-deptName" data-degree="D">Doctoral-only Example</td><td data-degree="D"><a href="/doctoral"></a></td>
    </tr>
  </table>
</main>
"""


def _fetcher(url: str) -> str:
    if url == ADMISSIONS_URL:
        return ADMISSIONS_HTML
    if url == CATALOG_URL:
        return CATALOG_HTML
    raise AssertionError(url)


def _adapter(**kwargs) -> NTUTaiwanAdapter:
    kwargs.setdefault("minimum_expected_programmes", 2)
    return NTUTaiwanAdapter(**kwargs)


def test_ntu_adapter_discovers_only_available_masters_programmes() -> None:
    catalog = _adapter(maximum_expected_programmes=3).parse_catalog_from_fetcher(
        _fetcher
    )

    assert {programme.name for programme in catalog.programmes} == {
        "Master's in Computer Science and Information Engineering",
        "Master's in Astrophysics",
    }
    assert all(programme.parse_status == "parsed" for programme in catalog.programmes)


def test_ntu_adapter_preserves_existing_cse_identity() -> None:
    catalog = _adapter().parse_catalog_from_fetcher(_fetcher)
    cse = next(item for item in catalog.programmes if "Computer Science" in item.name)

    assert cse.id == "ntu-computer-science-information-engineering-master"
    assert cse.faculty == "College of Electrical Engineering and Computer Science"
    assert cse.source_url.endswith("/degree_key/M/sn/1")


def test_ntu_adapter_assigns_the_exact_february_2027_window() -> None:
    catalog = _adapter().parse_catalog_from_fetcher(_fetcher)

    assert catalog.application_opens_at == "2026-08-03"
    assert all(len(programme.windows) == 1 for programme in catalog.programmes)
    window = catalog.programmes[0].windows[0]
    assert window.opens_at == "2026-08-03"
    assert window.closes_at == "2026-09-17"
    assert window.intake == "February 2027"
    assert window.applicant_categories == ["international-students"]
    assert window.source_url == CATALOG_URL


def test_ntu_adapter_rejects_a_truncated_catalogue() -> None:
    with pytest.raises(ValueError, match="only contained 2 available master's"):
        _adapter(minimum_expected_programmes=3).parse_catalog_from_fetcher(_fetcher)


def test_ntu_adapter_rejects_a_missing_official_opening_date() -> None:
    def fetcher(url: str) -> str:
        if url == ADMISSIONS_URL:
            return ADMISSIONS_HTML
        return CATALOG_HTML.replace(
            "First Round：2026-08-03~2026-09-17", "First Round: dates TBA"
        )

    with pytest.raises(ValueError, match="exact First Round date range"):
        _adapter().parse_catalog_from_fetcher(fetcher)
