from __future__ import annotations

import pytest

import gradwindow.programme_adapters.ucl as ucl_module
from gradwindow.programme_adapters.ucl import CATALOG_URL, UCLAdapter

CATALOG_HTML = """
<html><body>
  <section id="programme-data-content">
    <div class="search-results__result-counter">Showing <strong>4</strong> courses.</div>
    <div class="result-item clearfix">
      <a href="https://www.ucl.ac.uk/prospective-students/graduate/taught-degrees/advanced-audiology-msc">
        Advanced Audiology MSc
      </a>
      <span class="search-results__dept">Faculty of Brain Sciences | Ear Institute</span>
      <span class="search-results__dept">Course summary.</span>
    </div>
    <div class="result-item clearfix">
      <a href="https://www.ucl.ac.uk/prospective-students/graduate/taught-degrees/computer-graphics-vision-and-imaging-msc">
        Computer Graphics, Vision and Imaging MSc
      </a>
      <span class="search-results__dept">Faculty of Engineering Sciences | Computer Science</span>
      <span class="search-results__dept">Course summary.</span>
    </div>
    <div class="result-item clearfix">
      <a href="https://www.ucl.ac.uk/prospective-students/graduate/taught-degrees/education-ma-international">
        Education MA (International)
      </a>
      <span class="search-results__dept">Institute of Education | Education</span>
      <span class="search-results__dept">Course summary.</span>
    </div>
    <div class="result-item clearfix">
      <a href="https://www.ucl.ac.uk/prospective-students/graduate/taught-degrees/implant-dentistry-pg-cert">
        Implant Dentistry PG Cert
      </a>
      <span class="search-results__dept">Faculty of Medical Sciences | Eastman Dental Institute</span>
      <span class="search-results__dept">Course summary.</span>
    </div>
  </section>
</body></html>
"""


def _fetcher(url: str) -> str:
    assert url == CATALOG_URL
    return CATALOG_HTML


def _adapter() -> UCLAdapter:
    return UCLAdapter(minimum_expected_courses=4, minimum_expected_programmes=3)


def test_ucl_adapter_discovers_only_masters_level_courses() -> None:
    catalog = _adapter().parse_catalog_from_fetcher(_fetcher)

    assert len(catalog.programmes) == 3
    assert {item.degree_type for item in catalog.programmes} == {
        "MA (International)",
        "MSc",
    }
    assert not any("PG Cert" in item.name for item in catalog.programmes)
    assert len({item.id for item in catalog.programmes}) == 3


def test_ucl_adapter_parses_faculty_and_department() -> None:
    catalog = _adapter().parse_catalog_from_fetcher(_fetcher)
    audiology = next(item for item in catalog.programmes if "Audiology" in item.name)

    assert audiology.faculty == "Faculty of Brain Sciences"
    assert audiology.department == "Ear Institute"
    assert audiology.source_url == audiology.application_url


def test_ucl_adapter_preserves_existing_programme_identity() -> None:
    catalog = _adapter().parse_catalog_from_fetcher(_fetcher)
    programme = next(
        item for item in catalog.programmes if "Computer Graphics" in item.name
    )

    assert programme.id == "ucl-computer-graphics-vision-imaging-msc"
    assert programme.name == "Computer Graphics, Vision and Imaging MSc"


def test_ucl_adapter_keeps_catalogue_only_programmes_in_monitoring() -> None:
    catalog = _adapter().parse_catalog_from_fetcher(_fetcher)

    assert all(programme.windows == [] for programme in catalog.programmes)
    assert all(
        programme.parse_status == "no-deadline" for programme in catalog.programmes
    )
    assert all(
        "programme-specific" in programme.deadline_text
        for programme in catalog.programmes
    )


def test_ucl_adapter_rejects_a_truncated_course_result() -> None:
    with pytest.raises(ValueError, match="only contained 4 taught courses"):
        UCLAdapter(
            minimum_expected_courses=5,
            minimum_expected_programmes=3,
        ).parse_catalog_from_fetcher(_fetcher)


def test_ucl_adapter_rejects_too_few_masters_programmes() -> None:
    with pytest.raises(ValueError, match="only contained 3 master's programmes"):
        UCLAdapter(
            minimum_expected_courses=4,
            minimum_expected_programmes=4,
        ).parse_catalog_from_fetcher(_fetcher)


def test_ucl_blocked_fallback_uses_browser_request_headers(monkeypatch) -> None:
    captured: list[str] = []

    class Result:
        returncode = 0
        stdout = CATALOG_HTML.encode()
        stderr = b""

    def fake_run(args, **_kwargs):
        captured.extend(args)
        return Result()

    monkeypatch.setattr(ucl_module.shutil, "which", lambda _name: "curl")
    monkeypatch.setattr(ucl_module.subprocess, "run", fake_run)

    assert ucl_module._fetch_with_curl(CATALOG_URL) == CATALOG_HTML
    assert "--referer" in captured
    assert "https://www.ucl.ac.uk/study/prospective-students/graduate" in captured
    assert "--header" in captured
    assert any(value.startswith("Accept-Language:") for value in captured)
    assert any(value.startswith("Mozilla/5.0") for value in captured)
