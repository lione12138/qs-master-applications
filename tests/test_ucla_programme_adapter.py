from __future__ import annotations

import pytest

from gradwindow.programme_adapters.ucla import CATALOG_URL, UCLAAdapter

PROGRAM_URLS = {
    "Computer Science": "https://grad.ucla.edu/programs/school-of-engineering-and-applied-science/computer-science/",
    "Education": "https://grad.ucla.edu/programs/school-of-education-and-information-studies/education/",
    "African American Studies": "https://grad.ucla.edu/programs/social-sciences/african-american-studies/",
}

CATALOG_HTML = f"""
<main>
  <div class="major-container"><div class="title"><a href="{PROGRAM_URLS["Computer Science"]}">Computer Science</a></div><div class="degree-content"><div class="circle" title="Doctorate offered: Ph.D.">D</div><div class="circle" title="Masters offered: M.S.">M</div></div></div>
  <div class="major-container"><div class="title"><a href="{PROGRAM_URLS["Education"]}">Education</a></div><div class="degree-content"><div class="circle" title="Masters offered: M.Ed. &amp; M.A.">M</div></div></div>
  <div class="major-container"><div class="title"><a href="{PROGRAM_URLS["African American Studies"]}">African American Studies</a></div><div class="degree-content"><div class="circle" title="Masters offered: M.A.">M</div></div></div>
  <div class="major-container"><div class="title"><a href="https://grad.ucla.edu/programs/social-sciences/anthropology/">Anthropology</a></div><div class="degree-content"><div class="circle only-phd" title="Masters offered: (only on PhD-track)">M</div></div></div>
</main>
"""


def _detail(major: str) -> str:
    return f'<a href="https://grad.ucla.edu/requirements/?app=admission&amp;major={major}">Admission Requirements</a>'


REQUIREMENTS_WITH_DEADLINE = """
<main>
  <h3>2026-2027 Admission Requirements for the Graduate Major in Computer Science</h3>
  <table><tr><td><h3>Deadlines to apply</h3></td></tr><tr><td><p>December 15, 2026</p></td></tr></table>
</main>
"""

REQUIREMENTS_EMPTY = """
<main><table><tr><td><h3>Deadlines to apply</h3></td></tr><tr><td><p></p></td></tr></table></main>
"""


def _fetcher(url: str) -> str:
    if url == CATALOG_URL:
        return CATALOG_HTML
    if url == PROGRAM_URLS["Computer Science"]:
        return _detail("0121")
    if url == PROGRAM_URLS["Education"]:
        return _detail("0249")
    if url == PROGRAM_URLS["African American Studies"]:
        return "<main>No central requirements link</main>"
    if url.endswith("major=0121"):
        return REQUIREMENTS_WITH_DEADLINE
    if url.endswith("major=0249"):
        return REQUIREMENTS_EMPTY
    raise AssertionError(url)


def _adapter(**kwargs) -> UCLAAdapter:
    return UCLAAdapter(
        minimum_expected_programmes=3,
        maximum_expected_programmes=4,
        detail_workers=1,
        **kwargs,
    )


def test_ucla_adapter_discovers_only_independently_admitting_masters() -> None:
    catalog = _adapter().parse_catalog_from_fetcher(_fetcher)

    assert len(catalog.programmes) == 3
    assert {item.name for item in catalog.programmes} == {
        "African American Studies",
        "Computer Science",
        "Education",
    }
    assert all(item.name != "Anthropology" for item in catalog.programmes)


def test_ucla_adapter_preserves_existing_computer_science_identity() -> None:
    catalog = _adapter().parse_catalog_from_fetcher(_fetcher)
    programme = next(
        item for item in catalog.programmes if item.name == "Computer Science"
    )

    assert programme.id == "ucla-computer-science-ms"
    assert programme.degree_type == "M.S."


def test_ucla_adapter_records_deadline_guidance_without_inventing_opening() -> None:
    catalog = _adapter().parse_catalog_from_fetcher(_fetcher)
    computer_science = next(
        item for item in catalog.programmes if item.name == "Computer Science"
    )
    education = next(item for item in catalog.programmes if item.name == "Education")

    assert "December 15, 2026" in computer_science.deadline_text
    assert "no exact application opening date" in computer_science.deadline_text
    assert "leaves the deadline field empty" in education.deadline_text
    assert all(item.windows == [] for item in catalog.programmes)
    assert all(item.parse_status == "no-deadline" for item in catalog.programmes)


def test_ucla_adapter_rejects_a_truncated_catalogue() -> None:
    with pytest.raises(ValueError, match="only contained 3 independently-admitting"):
        UCLAAdapter(
            minimum_expected_programmes=4, detail_workers=1
        ).parse_catalog_from_fetcher(_fetcher)
