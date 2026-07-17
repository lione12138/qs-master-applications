from __future__ import annotations

import pytest

from gradwindow.programme_adapters.korea import (
    SCHEDULE_URL,
    KoreaUniversityAdapter,
)

CATALOG_FRAGMENT = """
<div id="all" class="tabcontent">
  <div class="major_wrap">
    <div class="major_box">
      <div class="group"><div class="major_tit">Department of Computer Science and Engineering</div></div>
      <div class="group"><div class="major_sub_tit">Master’s Program</div><ul class="bu_no"><li>Computer Science</li><li>Artificial Intelligence</li></ul></div>
      <div class="group"><div class="major_sub_tit">Doctoral Program</div><ul class="bu_no"><li>Computer Science</li></ul></div>
      <div class="group"><div class="major_sub_tit">College</div><ul class="bu_no"><li>College of Informatics</li></ul></div>
      <div class="group"><a class="major_btn home" href="https://cs.korea.edu/cs/index.do?tracking=1">home</a></div>
    </div>
    <div class="major_box">
      <div class="group"><div class="major_tit">Program in Public Health</div></div>
      <div class="group"><div class="major_sub_tit">Master’s Program</div><ul class="bu_no"><li>Public Health</li></ul></div>
      <div class="group"><div class="major_sub_tit">College</div><ul class="bu_no"><li>College of Medicine</li></ul></div>
    </div>
    <div class="major_box">
      <div class="group"><div class="major_tit">Doctoral Example</div></div>
      <div class="group"><div class="major_sub_tit">Doctoral Program</div><ul class="bu_no"><li>Research</li></ul></div>
      <div class="group"><div class="major_sub_tit">College</div><ul class="bu_no"><li>College of Science</li></ul></div>
    </div>
  </div>
</div>
"""

SCHEDULE_HTML = """
<main>
  <p>This application schedule is for the 2022 Fall Semester.</p>
  <table>
    <tr><th>Online Application</th><td>March 3(Tue) 10:00 - March 13(Fri) 17:00, 2026</td></tr>
  </table>
</main>
"""


def _fetcher(url: str) -> str:
    assert url == SCHEDULE_URL
    return SCHEDULE_HTML


def _adapter(**kwargs) -> KoreaUniversityAdapter:
    kwargs.setdefault("minimum_expected_programmes", 2)
    return KoreaUniversityAdapter(
        department_payload_fetcher=lambda: CATALOG_FRAGMENT,
        **kwargs,
    )


def test_korea_adapter_discovers_seoul_masters_departments() -> None:
    catalog = _adapter(maximum_expected_programmes=3).parse_catalog_from_fetcher(
        _fetcher
    )

    assert {programme.name for programme in catalog.programmes} == {
        "Master's in Computer Science and Engineering",
        "Master's in Public Health",
    }
    assert {programme.faculty for programme in catalog.programmes} == {
        "College of Informatics",
        "College of Medicine",
    }


def test_korea_adapter_preserves_existing_cse_identity_and_official_url() -> None:
    catalog = _adapter().parse_catalog_from_fetcher(_fetcher)
    cse = next(item for item in catalog.programmes if "Computer Science" in item.name)

    assert cse.id == "korea-university-computer-science-master"
    assert cse.source_url == "https://cs.korea.edu/cs/index.do"


def test_korea_adapter_keeps_old_schedule_as_monitoring_evidence() -> None:
    catalog = _adapter().parse_catalog_from_fetcher(_fetcher)

    assert all(programme.windows == [] for programme in catalog.programmes)
    assert all(
        programme.parse_status == "no-deadline" for programme in catalog.programmes
    )
    assert all("March 3" in programme.deadline_text for programme in catalog.programmes)
    assert all(
        "Fall 2026" in programme.deadline_text for programme in catalog.programmes
    )


def test_korea_adapter_rejects_a_truncated_catalogue() -> None:
    with pytest.raises(ValueError, match="only contained 2 Seoul-campus master's"):
        _adapter(minimum_expected_programmes=3).parse_catalog_from_fetcher(_fetcher)
