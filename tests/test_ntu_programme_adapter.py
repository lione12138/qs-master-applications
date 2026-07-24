from gradwindow.programme_adapters.ntu_taiwan import (
    ADMISSIONS_URL,
    CATALOG_URL,
    NTUTaiwanAdapter,
    parse_official_chinese_translations,
)

CATALOGUE = """
<h1>2026/2027 Available Graduate Degree Programs and Application Requirements</h1>
<table><tbody>
  <tr class="js-degreeTr js-showM"><td class="js-college">College of Liberal Arts</td>
    <td class="js-deptName" data-degree="M">Graduate Institute of Linguistics</td>
    <td data-degree="M"><a href="/globaladmission/foreign/requirement/dept.detail/id/demo/degree_key/M/sn/101">Open</a></td></tr>
  <tr class="js-degreeTr js-showM"><td class="js-college">College of Electrical Engineering and Computer Science</td>
    <td class="js-deptName" data-degree="M">Department of Computer Science and Information Engineering</td>
    <td data-degree="M"><a href="/globaladmission/foreign/requirement/dept.detail/id/demo/degree_key/M/sn/202">Open</a></td></tr>
  <tr class="js-degreeTr"><td class="js-college">College of Science</td>
    <td class="js-deptName" data-degree="M">Closed Institute</td><td data-degree="M"><span>-</span></td></tr>
</tbody></table>
"""

ADMISSIONS = """
<h5>2027 February Entry (Graduate programs only)</h5>
<p>Application Period: August 3 (11AM) – September 17, 2026 (4PM)</p>
"""

CHINESE_CATALOGUE = """
<table><tbody>
  <tr class="js-degreeTr"><td class="js-college">文學院</td>
    <td class="js-deptName" data-degree="M">語言學研究所</td>
    <td data-degree="M"><a href="/globaladmission/foreign/requirement/dept.detail/id/demo/degree_key/M/sn/101">查看</a></td></tr>
  <tr class="js-degreeTr"><td class="js-college">電機資訊學院</td>
    <td class="js-deptName" data-degree="M">資訊工程學系</td>
    <td data-degree="M"><a href="/globaladmission/foreign/requirement/dept.detail/id/demo/degree_key/M/sn/202">查看</a></td></tr>
</tbody></table>
"""


def test_ntu_adapter_discovers_available_masters_with_exact_shared_window() -> None:
    pages = {CATALOG_URL: CATALOGUE, ADMISSIONS_URL: ADMISSIONS}
    catalog = NTUTaiwanAdapter(
        minimum_expected_programmes=2
    ).parse_catalog_from_fetcher(pages.__getitem__)

    assert [item.id for item in catalog.programmes] == [
        "ntu-computer-science-information-engineering-master",
        "ntu-international-master-101",
    ]
    window = catalog.programmes[0].windows[0]
    assert (window.opens_at, window.closes_at, window.intake) == (
        "2026-08-03",
        "2026-09-17",
        "February 2027",
    )
    assert window.applicant_categories == ["international-students"]
    assert window.source_url == ADMISSIONS_URL


def test_ntu_adapter_rejects_a_truncated_catalogue() -> None:
    pages = {CATALOG_URL: CATALOGUE, ADMISSIONS_URL: ADMISSIONS}
    try:
        NTUTaiwanAdapter(minimum_expected_programmes=3).parse_catalog_from_fetcher(
            pages.__getitem__
        )
    except ValueError as error:
        assert "expected at least 3" in str(error)
    else:
        raise AssertionError("truncated NTU catalogue was accepted")


def test_ntu_official_chinese_names_are_joined_by_programme_number() -> None:
    assert parse_official_chinese_translations(CATALOGUE, CHINESE_CATALOGUE) == {
        "ntu-computer-science-information-engineering-master": "資訊工程學系",
        "ntu-international-master-101": "語言學研究所",
    }
