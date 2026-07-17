from __future__ import annotations

import pytest

from gradwindow.programme_adapters.lmu import (
    APPLICATIONS_URL,
    CATALOG_URL,
    LMUAdapter,
)

CATALOG_HTML = """
<main>
  <h1>International degree programs</h1>
  <h2>English-taught master's degree programs</h2>
  <div class="link-list__container"><ul>
    <li><a href="https://www.genzentrum.uni-muenchen.de/study-program/master/index.html">Biochemistry</a></li>
    <li><a href="https://www.statistik.uni-muenchen.de/studium/master/index.html">Statistics and Data Science</a></li>
  </ul></div>
  <h2>Double degree programs</h2>
  <div class="link-list__container"><ul>
    <li><a href="https://www.som.lmu.de/en/studies/triple-degree/">Management - International Triple Degree</a></li>
    <li><a href="https://www.som.lmu.de/en/studies/triple-degree/">Master of Science in Management - International triple degree</a></li>
  </ul></div>
  <h2>Erasmus Mundus</h2>
  <div class="text-module__text"><ul>
    <li>Master's Program in Materials Science Exploring Large Scale Facilities (<a href="https://www.mamaself.eu">MaMaSELF</a>) Contact: <a href="mailto:test@lmu.de">Coordinator</a></li>
  </ul></div>
</main>
"""

APPLICATIONS_HTML = """
<main>
  <dd class="definition-list__description">
    For the <b>Master's programs Biochemistry, Epidemiology (WS), Quantitative Economics (WS) and Statistics &amp; Data Science</b>
    please use the <a href="https://lmu.gomovein.com">online portal MoveIN</a>.
    The portal is open from 15 May 2026 until 15 July 2026.
  </dd>
</main>
"""


def _fetcher(url: str) -> str:
    if url == CATALOG_URL:
        return CATALOG_HTML
    if url == APPLICATIONS_URL:
        return APPLICATIONS_HTML
    raise AssertionError(url)


def _adapter(**kwargs) -> LMUAdapter:
    kwargs.setdefault("minimum_expected_programmes", 4)
    kwargs.setdefault("maximum_expected_programmes", 5)
    return LMUAdapter(**kwargs)


def test_lmu_adapter_discovers_all_three_international_master_categories() -> None:
    catalog = _adapter().parse_catalog_from_fetcher(_fetcher)

    assert len(catalog.programmes) == 4
    assert {item.name for item in catalog.programmes} == {
        "Biochemistry",
        "MSc Statistics and Data Science",
        "Management - International Triple Degree",
        "Master's Program in Materials Science Exploring Large Scale Facilities",
    }
    assert {item.department for item in catalog.programmes} == {
        "English-taught master's degree programs",
        "Double degree programs",
        "Erasmus Mundus",
    }


def test_lmu_adapter_preserves_existing_statistics_identity() -> None:
    catalog = _adapter().parse_catalog_from_fetcher(_fetcher)
    statistics = next(item for item in catalog.programmes if "Statistics" in item.name)

    assert statistics.id == "lmu-statistics-data-science-msc"
    assert statistics.name == "MSc Statistics and Data Science"
    assert (
        statistics.application_url
        == "https://www.stat.lmu.de/en/studies/interested-master/"
    )


def test_lmu_adapter_maps_only_exact_movein_programmes_to_window() -> None:
    catalog = _adapter().parse_catalog_from_fetcher(_fetcher)
    by_name = {item.name: item for item in catalog.programmes}

    for name in ("Biochemistry", "MSc Statistics and Data Science"):
        assert len(by_name[name].windows) == 1
        window = by_name[name].windows[0]
        assert window.opens_at == "2026-05-15"
        assert window.closes_at == "2026-07-15"
        assert window.intake == "Winter semester 2026/27"
        assert window.applicant_categories == ["international-students"]
        assert window.source_url == APPLICATIONS_URL
    assert by_name["Management - International Triple Degree"].windows == []


def test_lmu_adapter_rejects_a_missing_official_opening_date() -> None:
    def fetcher(url: str) -> str:
        html = _fetcher(url)
        if url == APPLICATIONS_URL:
            return html.replace("15 May 2026", "mid-May 2026")
        return html

    with pytest.raises(ValueError, match="exact MoveIN opening and closing dates"):
        _adapter().parse_catalog_from_fetcher(fetcher)


def test_lmu_adapter_rejects_a_truncated_catalogue() -> None:
    with pytest.raises(ValueError, match="only contained 4 international master's"):
        _adapter(minimum_expected_programmes=5).parse_catalog_from_fetcher(_fetcher)
