from __future__ import annotations

from gradwindow.programme_adapters.static_catalog import (
    StaticCatalogAdapter,
    StaticCatalogConfig,
)

CONFIG = StaticCatalogConfig(
    university_id="university-of-edinburgh",
    school_prefix="edinburgh",
    catalog_url="https://study.ed.ac.uk/programmes/postgraduate-taught-a-z",
    link_path_contains="/programmes/postgraduate-taught/",
    minimum_expected_programmes=1,
    default_application_url="https://study.ed.ac.uk/postgraduate/applying",
    default_intake="September 2026",
)

CATALOG_HTML = """
<html><body>
  <a href="/programmes/postgraduate-taught/913-advanced-chemical-engineering">
    Advanced Chemical Engineering MSc
  </a>
  <a href="/programmes/postgraduate-taught/478-acoustics-and-music-technology">
    Acoustics and Music Technology MSc
  </a>
</body></html>
"""

DETAIL_HTML = """
<html><body>
  <h3>When to apply</h3>
  <p>Programme start date Application deadline 14 September 2026 30 August 2026</p>
</body></html>
"""


def test_static_catalog_adapter_extracts_programmes_and_incomplete_deadline() -> None:
    def fetcher(url: str) -> str:
        return DETAIL_HTML if "913-advanced" in url else CATALOG_HTML

    catalog = StaticCatalogAdapter(CONFIG, detail_workers=1).parse_catalog_from_fetcher(
        fetcher
    )

    assert [item.id for item in catalog.programmes] == [
        "edinburgh-acoustics-and-music-technology-msc",
        "edinburgh-advanced-chemical-engineering-msc",
    ]
    advanced = next(item for item in catalog.programmes if "advanced" in item.id)
    assert advanced.parse_status == "incomplete"
    assert advanced.windows[0].opens_at is None
    assert advanced.windows[0].closes_at == "2026-08-30"
    assert "Application deadline" in advanced.deadline_text
