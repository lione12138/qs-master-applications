from gradwindow.programme_adapters.korea import SCHEDULE_URL, KoreaAdapter

CATALOGUE = """
<div class="major_wrap"><div class="major_box">
  <div class="group"><div class="major_tit">Department of Computer Science and Engineering</div></div>
  <div class="group"><div class="major_sub_tit">Master’s Program</div><ul><li>Computer Science</li></ul></div>
  <div class="group"><div class="major_sub_tit">College</div><ul><li>College of Informatics</li></ul></div>
  <div class="group"><a class="major_btn home" href="https://cs.korea.ac.kr/">Home</a></div>
</div></div>
<div class="major_wrap"><div class="major_box">
  <div class="group"><div class="major_tit">Department of Economics</div></div>
  <div class="group"><div class="major_sub_tit">Master’s Program</div><ul><li>Economics</li></ul></div>
  <div class="group"><div class="major_sub_tit">College</div><ul><li>College of Political Science and Economics</li></ul></div>
</div></div>
"""

SCHEDULE = """
<table><tr><th>Online Application</th>
  <td>March 3(Tue) 10:00 - March 13(Fri) 17:00, 2026</td></tr></table>
"""


def test_korea_adapter_discovers_masters_and_keeps_general_schedule_as_guidance() -> (
    None
):
    adapter = KoreaAdapter(
        minimum_expected_programmes=2,
        catalog_payload_fetcher=lambda: CATALOGUE,
    )
    catalog = adapter.parse_catalog_from_fetcher(
        lambda url: {SCHEDULE_URL: SCHEDULE}[url]
    )

    assert [item.id for item in catalog.programmes] == [
        "korea-university-computer-science-master",
        "korea-university-department-of-economics-master",
    ]
    assert catalog.programmes[0].faculty == "College of Informatics"
    assert all(item.windows == [] for item in catalog.programmes)
    assert all(
        "2026-03-03 to 2026-03-13" in item.deadline_text for item in catalog.programmes
    )


def test_korea_adapter_rejects_a_truncated_catalogue() -> None:
    adapter = KoreaAdapter(
        minimum_expected_programmes=3,
        catalog_payload_fetcher=lambda: CATALOGUE,
    )
    try:
        adapter.parse_catalog_from_fetcher(lambda _url: SCHEDULE)
    except ValueError as error:
        assert "expected at least 3" in str(error)
    else:
        raise AssertionError("truncated Korea catalogue was accepted")
