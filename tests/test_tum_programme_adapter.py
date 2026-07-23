from __future__ import annotations

import pytest

from gradwindow.programme_adapters.tum import CATALOG_URL, TUMAdapter, catalog_page_url

FIRST_CATALOG_PAGE = """
<main>
  <p class="in2studyfinder__item-count">3 results found</p>
  <div id="studycourselist-174899">
    <article id="course-559" class="list-teaser">
      <header class="list-teaser__header">
        <p class="roofline">Master of Science (M.Sc.)</p>
        <h3 class="h4">AI in Biomedicine</h3>
      </header>
      <footer class="list-teaser__footer">
        <a href="/en/studies/degree-programs/detail/ai-in-biomedicine-master-of-science-msc#course-559">read more</a>
      </footer>
    </article>
    <article id="course-294" class="list-teaser">
      <header class="list-teaser__header">
        <p class="roofline">Master of Science (M.Sc.)</p>
        <h3 class="h4">Informatics</h3>
      </header>
      <footer class="list-teaser__footer">
        <a href="/en/studies/degree-programs/detail/informatics-master-of-science-msc#course-294">read more</a>
      </footer>
    </article>
  </div>
  <nav aria-label="pagebrowser">
    <a href="/en/studies/degree-programs?tx_solr%5Bpage%5D=2&amp;tx_solr%5Bq%5D=&amp;graduation=Master#studycourselist-174899">2</a>
  </nav>
</main>
"""

SECOND_CATALOG_PAGE = """
<main>
  <div id="studycourselist-174899">
    <article id="course-528" class="list-teaser">
      <header class="list-teaser__header">
        <p class="roofline">Master of Science (M.Sc.)</p>
        <h3 class="h4">AI in Society</h3>
      </header>
      <footer class="list-teaser__footer">
        <a href="/en/studies/degree-programs/detail/ai-in-society#course-528">read more</a>
      </footer>
    </article>
  </div>
</main>
"""


def _detail(
    *,
    name: str,
    deadline: str,
    school: str,
) -> str:
    return f"""
    <main>
      <script type="application/ld+json">
      {{
        "@context": "https://schema.org",
        "@type": ["EducationalOccupationalProgram", "Course"],
        "name": "{name}",
        "educationalCredentialAwarded": "Master of Science (M.Sc.)",
        "applicationDeadline": "{deadline}",
        "potentialAction": {{
          "@type": "ApplyAction",
          "target": {{
            "@type": "EntryPoint",
            "urlTemplate": "https://www.tum.de/en/studies/application/application-info-portal/online-application"
          }}
        }}
      }}
      </script>
      <div class="flex__lg-3">
        <div class="in2studyfinder no-js">
          <div class="ce-textmedia ce-textmedia--aside">
            <h2 class="h5"><a href="https://example.tum.de/">{school}</a></h2>
          </div>
        </div>
      </div>
    </main>
    """


def _pages() -> dict[str, str]:
    return {
        CATALOG_URL: FIRST_CATALOG_PAGE,
        catalog_page_url(2): SECOND_CATALOG_PAGE,
        "https://www.tum.de/en/studies/degree-programs/detail/ai-in-biomedicine-master-of-science-msc": _detail(
            name="AI in Biomedicine",
            deadline=(
                "Winter semester 2026/27: 15.04.2026 – 31.05.2026 "
                "Summer semester 2027: 01.09.2026 – 30.11.2026"
            ),
            school="TUM School of Natural Sciences",
        ),
        "https://www.tum.de/en/studies/degree-programs/detail/informatics-master-of-science-msc": _detail(
            name="Informatics",
            deadline=(
                "Winter semester: 01.02. – 31.05. Summer semester: 01.10. – 30.11."
            ),
            school="TUM School of Computation, Information and Technology",
        ),
        "https://www.tum.de/en/studies/degree-programs/detail/ai-in-society": _detail(
            name="AI in Society",
            deadline="Winter semester: 01.01. –&nbsp;31.05.",
            school="TUM School of Social Sciences and Technology",
        ),
    }


def test_tum_adapter_follows_catalogue_pagination_and_reuses_informatics_id() -> None:
    pages = _pages()
    catalog = TUMAdapter(
        minimum_expected_programmes=3,
        detail_workers=1,
    ).parse_catalog_from_fetcher(lambda url: pages[url])

    assert catalog.application_opens_at is None
    assert [programme.id for programme in catalog.programmes] == [
        "tum-ai-in-biomedicine-master-of-science-msc",
        "tum-ai-in-society",
        "tum-informatics-msc",
    ]
    assert all(programme.degree_type == "MSc" for programme in catalog.programmes)
    assert all(programme.name.startswith("MSc ") for programme in catalog.programmes)


def test_tum_adapter_parses_only_year_specific_exact_windows() -> None:
    pages = _pages()
    catalog = TUMAdapter(
        minimum_expected_programmes=3,
        detail_workers=1,
    ).parse_catalog_from_fetcher(lambda url: pages[url])
    biomedical = catalog.programmes[0]

    assert biomedical.faculty == "TUM School of Natural Sciences"
    assert biomedical.application_url == (
        "https://www.tum.de/en/studies/application/"
        "application-info-portal/online-application"
    )
    assert biomedical.parse_status == "parsed"
    assert [window.intake for window in biomedical.windows] == [
        "Winter semester 2026/27",
        "Summer semester 2027",
    ]
    assert [window.opens_at for window in biomedical.windows] == [
        "2026-04-15",
        "2026-09-01",
    ]
    assert [window.closes_at for window in biomedical.windows] == [
        "2026-05-31",
        "2026-11-30",
    ]
    assert all(
        window.source_url == biomedical.source_url for window in biomedical.windows
    )


def test_tum_adapter_keeps_recurring_yearless_periods_as_monitoring_evidence() -> None:
    pages = _pages()
    catalog = TUMAdapter(
        minimum_expected_programmes=3,
        detail_workers=1,
    ).parse_catalog_from_fetcher(lambda url: pages[url])
    informatics = next(
        programme
        for programme in catalog.programmes
        if programme.id == "tum-informatics-msc"
    )

    assert informatics.faculty == (
        "TUM School of Computation, Information and Technology"
    )
    assert informatics.windows == []
    assert informatics.parse_status == "no-deadline"
    assert "does not publish a cycle year" in informatics.deadline_text
    assert "no application window is inferred" in informatics.deadline_text


def test_tum_adapter_rejects_a_truncated_master_catalogue() -> None:
    pages = _pages()
    with pytest.raises(ValueError, match="only contained 3 master's programmes"):
        TUMAdapter(
            minimum_expected_programmes=4,
            detail_workers=1,
        ).parse_catalog_from_fetcher(lambda url: pages[url])


def test_tum_adapter_uses_the_official_filtered_master_catalogue() -> None:
    assert CATALOG_URL == (
        "https://www.tum.de/en/studies/degree-programs?"
        "tx_solr%5Bq%5D=&graduation=Master"
    )
    assert catalog_page_url(12) == (
        "https://www.tum.de/en/studies/degree-programs?"
        "tx_solr%5Bpage%5D=12&tx_solr%5Bq%5D=&graduation=Master"
    )
