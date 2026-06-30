from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[1]


def test_extended_rankings_keep_admissions_scope_separate() -> None:
    payload = json.loads(
        (ROOT / "data" / "global-rankings.json").read_text(encoding="utf-8")
    )

    assert payload["meta"]["generatedAt"] == "2026-06-21"
    assert payload["rankings"]["usnews"]["available"] is False

    for ranking_id, expected_count in (("the", 201), ("arwu", 200)):
        ranking = payload["rankings"][ranking_id]
        rows = ranking["rows"]
        assert ranking["rowCount"] == expected_count
        assert len(rows) == expected_count
        assert len({row["id"] for row in rows}) == expected_count
        assert all(row["rankPosition"] <= 200 for row in rows)
        assert any(row["rankingOnly"] for row in rows)
        assert any(not row["rankingOnly"] for row in rows)


ARWU_SHARED_UNIVERSITIES = {
    "University College London": "ucl-university-college-london",
    "University of Munich": "ludwig-maximilians-universit-t-m-nchen",
    "Swiss Federal Institute of Technology Lausanne": (
        "cole-polytechnique-f-d-rale-de-lausanne"
    ),
    "Nanyang Technological University": (
        "nanyang-technological-university-singapore-ntu-singapore"
    ),
    "Moscow State University": "lomonosov-moscow-state-university",
    "Pennsylvania State University, University Park": (
        "pennsylvania-state-university"
    ),
    "Purdue University, West Lafayette": "purdue-university",
    "University of Sao Paulo": "universidade-de-s-o-paulo-usp",
    "University of Barcelona": "university-of-barcelona",
    "University of Montreal": "university-of-montreal",
}


def test_arwu_shared_schools_reuse_canonical_universities() -> None:
    payload = json.loads(
        (ROOT / "data" / "global-rankings.json").read_text(encoding="utf-8")
    )
    rows = payload["rankings"]["arwu"]["rows"]

    for arwu_name, university_id in ARWU_SHARED_UNIVERSITIES.items():
        row = next(
            item
            for item in rows
            if item["school"] in {arwu_name, university_id}
            or item.get("universityId") == university_id
        )
        assert row["universityId"] == university_id, arwu_name
        assert row["rankingOnly"] is False, arwu_name


def test_ranking_importer_maps_shared_arwu_schools_to_canonical_universities(
    tmp_path: Path,
) -> None:
    node = shutil.which("node")
    assert node is not None, "Node.js is required for ranking importer tests"

    the_fixture = tmp_path / "the.html"
    the_fixture.write_text(
        '<script id="__NEXT_DATA__" type="application/json">'
        + json.dumps(
            {
                "props": {
                    "pageProps": {
                        "page": {
                            "rankingsTableConfig": {
                                "rankingsData": {"data": []}
                            }
                        }
                    }
                }
            }
        )
        + "</script>",
        encoding="utf-8",
    )
    arwu_fixture = tmp_path / "arwu.js"
    arwu_rows = [
        {
            "ranking": str(index),
            "univNameEn": school,
            "region": "Fixture country",
        }
        for index, school in enumerate(ARWU_SHARED_UNIVERSITIES, start=1)
    ]
    arwu_fixture.write_text(
        '__NUXT_JSONP__("/rankings/arwu/2025", '
        + json.dumps({"data": [{"filterList": arwu_rows}]})
        + ");",
        encoding="utf-8",
    )
    output = tmp_path / "global-rankings.json"

    subprocess.run(
        [
            node,
            str(ROOT / "scripts" / "import_global_rankings.mjs"),
            "--the-html",
            str(the_fixture),
            "--arwu-payload",
            str(arwu_fixture),
            "--output",
            str(output),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    rows = json.loads(output.read_text(encoding="utf-8"))["rankings"]["arwu"][
        "rows"
    ]
    rows_by_university = {row["universityId"]: row for row in rows}
    for university_id in ARWU_SHARED_UNIVERSITIES.values():
        assert rows_by_university[university_id]["rankingOnly"] is False


def test_extended_ranking_views_reuse_shared_application_windows() -> None:
    app_js = (ROOT / "app.js").read_text(encoding="utf-8")

    assert 'if (state.ranking !== "qs") return [];' not in app_js
    assert "filterRecordsToRanking(state.data, selectedRankingRows())" in app_js
    assert 'state.status = state.ranking === "qs" ? "open" : "unknown";' not in app_js


def test_table_headers_own_application_sorting() -> None:
    app_js = (ROOT / "app.js").read_text(encoding="utf-8")

    assert '{ label: rankColumnLabel(), sort: "rank" }' in app_js
    assert '{ label: t("opens"), sort: "opens" }' in app_js
    assert '{ label: t("deadline"), sort: "deadline" }' in app_js
    assert "table-sort-button" in app_js
