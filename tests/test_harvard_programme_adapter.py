from __future__ import annotations

from gradwindow.programme_adapters.harvard import HarvardAdapter

FIRST_PAGE_HTML = """
<html><body>
  <a href="/programs?page=1">Page 2</a>
  <div class="views-row">
    <div class="program-title">
      <h3><a href="/program/computational-science-and-engineering">
        Computational Science and Engineering
      </a></h3>
    </div>
    <div class="field field--node-field-area">
      <div class="field-label">Area of Study Within</div>
      <div class="field__item">Engineering and Applied Sciences</div>
    </div>
    <div class="paragraph paragraph--type--degree">
      <div class="field--paragraph-field-degree-type">Master of Engineering (ME)</div>
      <time datetime="2026-12-01T22:00:00Z">Dec 01, 2026 | 05:00 pm</time>
    </div>
    <div class="paragraph paragraph--type--degree">
      <div class="field--paragraph-field-degree-type">Master of Science (SM)</div>
      <time datetime="2026-12-01T22:00:00Z">Dec 01, 2026 | 05:00 pm</time>
    </div>
    <div class="paragraph paragraph--type--degree">
      <div class="field--paragraph-field-degree-type">Doctor of Philosophy (PhD)</div>
      <time datetime="2026-12-15T22:00:00Z">Dec 15, 2026 | 05:00 pm</time>
    </div>
  </div>
</body></html>
"""

SECOND_PAGE_HTML = """
<html><body>
  <div class="views-row">
    <div class="program-title">
      <h3><a href="/program/msmba">MS/MBA</a></h3>
    </div>
    <div class="paragraph paragraph--type--degree">
      <div class="field--paragraph-field-degree-type">Master of Science (SM)</div>
    </div>
  </div>
</body></html>
"""


def test_harvard_adapter_extracts_master_degree_deadlines_across_pages() -> None:
    adapter = HarvardAdapter(minimum_expected_programmes=1)

    def fetcher(url: str) -> str:
        return SECOND_PAGE_HTML if "page=1" in url else FIRST_PAGE_HTML

    catalog = adapter.parse_catalog_from_fetcher(fetcher)

    assert catalog.application_opens_at is None
    assert [item.id for item in catalog.programmes] == [
        "harvard-computational-science-and-engineering-me",
        "harvard-computational-science-and-engineering-sm",
        "harvard-ms-mba-sm",
    ]
    cse_me = catalog.programmes[0]
    assert cse_me.name == "ME Computational Science and Engineering"
    assert cse_me.degree_type == "ME"
    assert cse_me.faculty == "Engineering and Applied Sciences"
    assert (
        cse_me.source_url
        == "https://gsas.harvard.edu/program/computational-science-and-engineering"
    )
    assert cse_me.parse_status == "incomplete"
    assert [
        (window.round, window.intake, window.closes_at, window.opens_at)
        for window in cse_me.windows
    ] == [("Main deadline", "Fall 2027", "2026-12-01", None)]

    msmba = catalog.programmes[-1]
    assert msmba.name == "SM MS/MBA"
    assert msmba.parse_status == "no-deadline"
    assert msmba.windows == []
