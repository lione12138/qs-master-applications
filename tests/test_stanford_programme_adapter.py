from __future__ import annotations

from gradwindow.programme_adapters.stanford import StanfordAdapter

CATALOG_HTML = """
<html><body>
  <div id="programs">
    <div class="su-card program"
      data-degree="MS;"
      data-school="School of Engineering;"
      data-name="Computer Science (MS)">
      <div class="links">
        <a aria-label="Program Website for Computer Science (MS)"
           href="https://cs.stanford.edu/admissions/">Program Website</a>
      </div>
      <div class="section-block clearfix">
        <div class="left"><div class="heading">Full-Time Program</div></div>
        <div class="right">
          <table>
            <thead>
              <tr><th>Entry Term</th><th>Application Deadline</th></tr>
            </thead>
            <tbody>
              <tr><th>Autumn 2026-2027</th><td>December 2, 2025</td></tr>
            </tbody>
          </table>
        </div>
      </div>
      <div class="section-block clearfix">
        <div class="left"><div class="heading">Honors Cooperative Program ( ? )</div></div>
        <div class="right">
          <table>
            <thead>
              <tr><th>Entry Term</th><th>Application Deadline</th></tr>
            </thead>
            <tbody>
              <tr><th>Winter 2025-2026</th><td>October 14, 2025</td></tr>
              <tr><th>Spring 2025-2026</th><td>December 2, 2025</td></tr>
              <tr><th>Autumn 2026-2027</th><td>December 2, 2025</td></tr>
            </tbody>
          </table>
        </div>
      </div>
      <div class="section-block clearfix">
        <div class="left"><div class="heading">Testing Requirements</div></div>
        <div class="right">
          <table>
            <thead><tr><th>GRE General Test</th><th>GRE Subject Test</th></tr></thead>
            <tbody><tr><td>Not Considered</td><td>Not Considered</td></tr></tbody>
          </table>
        </div>
      </div>
    </div>
    <div class="su-card program"
      data-degree="PhD;"
      data-school="School of Engineering;"
      data-name="Computer Science (PhD)">
    </div>
  </div>
</body></html>
"""


def test_stanford_adapter_extracts_master_deadline_rows() -> None:
    catalog = StanfordAdapter(minimum_expected_programmes=1).parse_catalog(CATALOG_HTML)

    assert catalog.application_opens_at is None
    assert [item.id for item in catalog.programmes] == ["stanford-computer-science-ms"]
    programme = catalog.programmes[0]
    assert programme.name == "MS Computer Science"
    assert programme.degree_type == "MS"
    assert programme.faculty == "School of Engineering"
    assert (
        programme.source_url
        == "https://applygrad.stanford.edu/portal/explore-programs?cmd=grad-program-list"
    )
    assert programme.application_url == "https://gradadmissions.stanford.edu/apply"
    assert programme.parse_status == "incomplete"
    assert [
        (window.round, window.intake, window.closes_at, window.opens_at)
        for window in programme.windows
    ] == [
        ("Full-Time Program", "Autumn 2026", "2025-12-02", None),
        ("Honors Cooperative Program", "Winter 2026", "2025-10-14", None),
        ("Honors Cooperative Program", "Spring 2026", "2025-12-02", None),
        ("Honors Cooperative Program", "Autumn 2026", "2025-12-02", None),
    ]
