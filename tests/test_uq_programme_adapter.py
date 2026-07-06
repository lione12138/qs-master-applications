from __future__ import annotations

from gradwindow.programme_adapters.uq import UQAdapter


SITEMAP_INDEX = """
<sitemapindex>
  <sitemap><loc>https://study.uq.edu.au/sitemap.xml?page=1</loc></sitemap>
</sitemapindex>
"""

SITEMAP_PAGE = """
<urlset>
  <url><loc>https://study.uq.edu.au/study-options/programs/master-information-technology-5581</loc></url>
  <url><loc>https://study.uq.edu.au/study-options/programs/master-information-technology-5581/software-engineering-softwx5581</loc></url>
  <url><loc>https://study.uq.edu.au/study-options/programs/bachelor-arts-2000</loc></url>
</urlset>
"""

DETAIL_HTML = """
<html><body>
  <h1>Master of Information Technology - 2026</h1>
  <section data-student-type="international">
    <h3>Important dates</h3>
    <p>The closing date for this program is:</p>
    <ul>
      <li>To commence study in semester 2 - May 31 of the year of commencement.</li>
      <li>To commence study in semester 1 - November 30 of the previous year.</li>
    </ul>
  </section>
  <section data-student-type="domestic">
    <h3>Important dates</h3>
    <p>The closing date for this program is:</p>
    <ul>
      <li>To commence study in Semester 1 - January 31 of the year of commencement.</li>
      <li>To commence study in Semester 2 - June 30 of the year of commencement.</li>
    </ul>
  </section>
</body></html>
"""


def test_uq_adapter_discovers_master_programmes_from_sitemap() -> None:
    adapter = UQAdapter(minimum_expected_programmes=1, detail_workers=1)

    def fetcher(url: str) -> str:
        if url.endswith("sitemap.xml"):
            return SITEMAP_INDEX
        if "sitemap.xml?page=1" in url:
            return SITEMAP_PAGE
        return DETAIL_HTML

    catalog = adapter.parse_catalog_from_fetcher(fetcher)

    assert catalog.application_opens_at is None
    assert [item.id for item in catalog.programmes] == [
        "uq-information-technology-master-5581"
    ]
    programme = catalog.programmes[0]
    assert programme.name == "Master of Information Technology"
    assert programme.parse_status == "incomplete"
    assert [(w.round, w.closes_at, w.applicant_categories, w.opens_at) for w in programme.windows] == [
        ("Semester 2", "2026-05-31", ["international-students"], None),
        ("Semester 1", "2025-11-30", ["international-students"], None),
        ("Semester 1", "2026-01-31", ["domestic-students"], None),
        ("Semester 2", "2026-06-30", ["domestic-students"], None),
    ]
