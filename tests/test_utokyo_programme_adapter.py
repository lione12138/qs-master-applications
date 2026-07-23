from __future__ import annotations

import pytest

from gradwindow.predictions import official_cycle_key
from gradwindow.programme_adapters.utokyo import (
    CATALOG_URL,
    IST_ADMISSIONS_URL,
    IST_APPLICATION_URL,
    IST_GUIDE_URL,
    UTokyoAdapter,
)
from gradwindow.programme_windows import known_programme_window_candidates

ENGINEERING_URL = "https://www.u-tokyo.ac.jp/en/academics/grad_engineering.html"
PHARMACEUTICAL_URL = "https://www.u-tokyo.ac.jp/en/academics/grad_pharmaceutical.html"
IST_URL = "https://www.u-tokyo.ac.jp/en/academics/grad_ist.html"

INDEX_HTML = f"""
<html><body>
  <a href="/en/academics/grad_engineering.html">Graduate School of Engineering</a>
  <a href="{PHARMACEUTICAL_URL}">Graduate School of Pharmaceutical Sciences</a>
  <a href="/en/academics/grad_ist.html">
    Graduate School of Information Science and Technology
  </a>
</body></html>
"""

ENGINEERING_HTML = """
<html><body><main>
  <h1>Graduate School of Engineering</h1>
  <h2>2. Departments</h2>
  <h3>Department of Civil Engineering</h3>
  <h3>Department of Systems Innovation</h3>
  <h2>3. Websites</h2>
  <h3>Graduate School of Engineering</h3>
</main></body></html>
"""

PHARMACEUTICAL_HTML = """
<html><body><main>
  <h1>Graduate School of Pharmaceutical Sciences</h1>
  <h2>2. Departments</h2>
  <h3>Department of Pharmaceutical Sciences (Master's program and Doctoral program)</h3>
  <h3>Department of Pharmacy (Doctoral Program)</h3>
  <h2>3. Website</h2>
</main></body></html>
"""

IST_HTML = """
<html><body><main>
  <h1>Graduate School of Information Science and Technology</h1>
  <h2>2. Departments</h2>
  <h3>Department of Computer Science</h3>
  <h3>Department of Creative Informatics</h3>
  <h2>3. Websites</h2>
</main></body></html>
"""

IST_ADMISSIONS_HTML = """
<html><body>
  <p>The application periods for AY2027 entrance examinations (conducted in AY2026)
  for Master's and Doctoral programs are as follows.</p>
  <h3>Summer Examinations</h3>
  <p>Application Period Applications are accepted from Friday, May 29, until
  14:00 on Thursday, June 4, 2026 (JST).</p>
  <h3>Winter Examinations</h3>
  <p>Application Period Applications are accepted from Wednesday, November 11,
  until 14:00 on Tuesday, November 17, 2026 (JST).</p>
  <a href="/edu/entra/2027_ag_m_e.pdf">Master's Program</a>
</body></html>
"""

IST_GUIDE_TEXT = """
AY2027 Admission Guide: Master's Program
Examinations Conducted in AY2026
Summer Entrance Examinations will be held in each department: Computer Science;
Creative Informatics.
Winter Entrance Examinations will be held in the Department of Creative Informatics.
The entrance dates for successful applicants for the Summer Entrance Examinations
and for the Winter Entrance Examinations are in April 2027 and October 2027 respectively.
"""


def _fetcher(url: str) -> str:
    pages = {
        CATALOG_URL: INDEX_HTML,
        ENGINEERING_URL: ENGINEERING_HTML,
        PHARMACEUTICAL_URL: PHARMACEUTICAL_HTML,
        IST_URL: IST_HTML,
        IST_ADMISSIONS_URL: IST_ADMISSIONS_HTML,
        IST_GUIDE_URL: IST_GUIDE_TEXT,
    }
    return pages[url]


def _adapter(*, target_intake_year: int = 2027) -> UTokyoAdapter:
    return UTokyoAdapter(
        minimum_expected_school_pages=3,
        minimum_expected_programmes=5,
        target_intake_year=target_intake_year,
    )


def test_utokyo_adapter_discovers_master_eligible_units() -> None:
    catalog = _adapter().parse_catalog_from_fetcher(_fetcher)

    assert len(catalog.programmes) == 5
    assert len({programme.id for programme in catalog.programmes}) == 5
    assert all(programme.degree_type == "Master" for programme in catalog.programmes)
    assert not any(
        "Department of Pharmacy" in item.department for item in catalog.programmes
    )
    assert {item.name for item in catalog.programmes} >= {
        "Master's in Civil Engineering",
        "Master's in Pharmaceutical Sciences",
    }


def test_utokyo_adapter_preserves_existing_computer_science_identity() -> None:
    catalog = _adapter().parse_catalog_from_fetcher(_fetcher)
    programme = next(
        item
        for item in catalog.programmes
        if item.id == "utokyo-computer-science-master"
    )

    assert programme.name == "Master's Program in Computer Science"
    assert programme.faculty == "Graduate School of Information Science and Technology"
    assert programme.application_url == IST_APPLICATION_URL


def test_utokyo_adapter_parses_both_exact_ay2027_ist_windows() -> None:
    catalog = _adapter().parse_catalog_from_fetcher(_fetcher)
    creative_informatics = next(
        item for item in catalog.programmes if "Creative Informatics" in item.name
    )

    assert [
        (
            window.round,
            window.opens_at,
            window.closes_at,
            window.intake,
            window.source_url,
        )
        for window in creative_informatics.windows
    ] == [
        (
            "Summer entrance examination",
            "2026-05-29",
            "2026-06-04",
            "Spring (April) 2027",
            IST_ADMISSIONS_URL,
        ),
        (
            "Winter entrance examination",
            "2026-11-11",
            "2026-11-17",
            "Fall (October) 2027",
            IST_ADMISSIONS_URL,
        ),
    ]
    assert creative_informatics.parse_status == "parsed"


def test_utokyo_adapter_keeps_decentralised_schools_in_monitoring() -> None:
    catalog = _adapter().parse_catalog_from_fetcher(_fetcher)
    civil_engineering = next(
        item
        for item in catalog.programmes
        if item.name == "Master's in Civil Engineering"
    )

    assert civil_engineering.windows == []
    assert civil_engineering.parse_status == "no-deadline"
    assert "decentralised" in civil_engineering.deadline_text


def test_utokyo_known_cs_reuses_published_summer_and_excludes_winter() -> None:
    adapter = _adapter()
    catalog = adapter.parse_catalog_from_fetcher(_fetcher)
    programme = next(
        item
        for item in catalog.programmes
        if item.id == "utokyo-computer-science-master"
    )
    existing = {
        "id": "utokyo-computer-science-masters-ay2027-summer",
        "universityId": "the-university-of-tokyo",
        "scopeType": "programme",
        "scopeId": programme.id,
        "intake": "Academic Year 2027",
        "intakeDetails": {
            "label": "Academic Year 2027",
            "cycleYear": 2027,
            "academicYearEnd": None,
            "term": "spring",
            "startMonth": 4,
        },
        "round": "Summer entrance examination",
        "applicantCategories": ["all"],
        "opensAt": "2026-05-29",
        "closesAt": "2026-06-04",
        "applicationUrl": IST_APPLICATION_URL,
        "sourceUrl": IST_ADMISSIONS_URL,
        "verifiedAt": "2026-04-24",
        "evidence": "Official admissions page.",
    }

    candidates = known_programme_window_candidates(
        adapter,
        programme,
        {"id": programme.id, "applicationUrl": IST_APPLICATION_URL},
        None,
        {official_cycle_key(existing): existing},
        {existing["id"]},
        "2026-07-17T00:00:00+00:00",
    )

    assert candidates == []


def test_utokyo_adapter_filters_stale_ist_cycle() -> None:
    catalog = _adapter(target_intake_year=2028).parse_catalog_from_fetcher(_fetcher)

    assert all(programme.windows == [] for programme in catalog.programmes)
    assert all(
        programme.parse_status == "no-deadline" for programme in catalog.programmes
    )


def test_utokyo_adapter_rejects_a_truncated_catalogue() -> None:
    with pytest.raises(ValueError, match="only contained 5 master's programmes"):
        UTokyoAdapter(
            minimum_expected_school_pages=3,
            minimum_expected_programmes=6,
        ).parse_catalog_from_fetcher(_fetcher)
