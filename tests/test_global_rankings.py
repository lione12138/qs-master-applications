from __future__ import annotations

import json
import shutil
import subprocess
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_extended_rankings_keep_admissions_scope_separate() -> None:
    payload = json.loads(
        (ROOT / "data" / "global-rankings.json").read_text(encoding="utf-8")
    )

    date.fromisoformat(payload["meta"]["generatedAt"])
    usnews = payload["rankings"]["usnews"]
    if usnews["available"]:
        assert usnews["rowCount"] == len(usnews["rows"])
        assert usnews["rows"]
    else:
        assert usnews["unavailableReason"]

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
    "Pennsylvania State University, University Park": ("pennsylvania-state-university"),
    "Purdue University, West Lafayette": "purdue-university",
    "University of Sao Paulo": "universidade-de-s-o-paulo-usp",
    "University of Barcelona": "university-of-barcelona",
    "University of Montreal": "university-of-montreal",
}

THE_SHARED_UNIVERSITIES = {
    "LMU Munich": "ludwig-maximilians-universit-t-m-nchen",
    "École Polytechnique Fédérale de Lausanne": (
        "cole-polytechnique-f-d-rale-de-lausanne"
    ),
    "University of Illinois at Urbana-Champaign": (
        "university-of-illinois-at-urbana-champaign"
    ),
    "Paris Sciences et Lettres – PSL Research University Paris": "psl-university",
    "Korea Advanced Institute of Science and Technology (KAIST)": "kaist",
    "UNSW Sydney": "the-university-of-new-south-wales",
    "Purdue University West Lafayette": "purdue-university",
    "Humboldt University of Berlin": "humboldt-universit-t-zu-berlin",
    "Penn State (Main campus)": "pennsylvania-state-university",
    "Free University of Berlin": "freie-universit-t-berlin",
    "University of Bologna": "alma-mater-studiorum-university-of-bologna",
    "University of Barcelona": "university-of-barcelona",
    "Technical University of Berlin": "technische-universit-t-berlin",
    "Karlsruhe Institute of Technology": ("karlsruhe-institute-of-technology-kit"),
    "Trinity College Dublin": ("trinity-college-dublin-the-university-of-dublin"),
    "TU Dresden": "technische-universitat-dresden",
    "King Fahd University of Petroleum and Minerals": (
        "king-fahd-university-of-petroleum-and-minerals"
    ),
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


def test_the_shared_schools_reuse_canonical_universities() -> None:
    payload = json.loads(
        (ROOT / "data" / "global-rankings.json").read_text(encoding="utf-8")
    )
    rows = payload["rankings"]["the"]["rows"]

    for the_name, university_id in THE_SHARED_UNIVERSITIES.items():
        row = next(
            item
            for item in rows
            if item["school"] in {the_name, university_id}
            or item.get("universityId") == university_id
        )
        assert row["universityId"] == university_id, the_name
        assert row["rankingOnly"] is False, the_name


def test_ranking_importer_maps_shared_schools_to_canonical_universities(
    tmp_path: Path,
) -> None:
    node = shutil.which("node")
    assert node is not None, "Node.js is required for ranking importer tests"

    the_fixture = tmp_path / "the.html"
    the_rows = [
        {
            "rank": str(index),
            "name": school,
            "location": "Fixture country",
            "url": f"/fixture/{index}",
        }
        for index, school in enumerate(THE_SHARED_UNIVERSITIES, start=1)
    ]
    the_fixture.write_text(
        '<script id="__NEXT_DATA__" type="application/json">'
        + json.dumps(
            {
                "props": {
                    "pageProps": {
                        "page": {
                            "rankingsTableConfig": {"rankingsData": {"data": the_rows}}
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
    usnews_fixture = tmp_path / "usnews.json"
    usnews_fixture.write_text(
        json.dumps(
            {
                "total_pages": 1,
                "items": [
                    {
                        "name": "University College London",
                        "country_name": "United Kingdom",
                        "url": "https://www.usnews.com/education/best-global-universities/university-college-london-500237",
                        "ranks": [
                            {
                                "value": "9",
                                "is_tied": False,
                                "is_ranked": True,
                                "label": "Best Global Universities",
                            }
                        ],
                    },
                    {
                        "name": "Fixture University",
                        "country_name": "Canada",
                        "url": "https://www.usnews.com/fixture",
                        "ranks": [
                            {
                                "value": "200",
                                "is_tied": True,
                                "is_ranked": True,
                                "label": "Best Global Universities",
                            }
                        ],
                    },
                    {
                        "name": "Outside Top 200",
                        "country_name": "Canada",
                        "url": "https://www.usnews.com/outside",
                        "ranks": [
                            {
                                "value": "201",
                                "is_tied": False,
                                "is_ranked": True,
                                "label": "Best Global Universities",
                            }
                        ],
                    },
                ],
            }
        ),
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
            "--usnews-json",
            str(usnews_fixture),
            "--output",
            str(output),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    rankings = json.loads(output.read_text(encoding="utf-8"))["rankings"]
    arwu_by_university = {row["universityId"]: row for row in rankings["arwu"]["rows"]}
    for university_id in ARWU_SHARED_UNIVERSITIES.values():
        assert arwu_by_university[university_id]["rankingOnly"] is False
    the_by_university = {row["universityId"]: row for row in rankings["the"]["rows"]}
    for university_id in THE_SHARED_UNIVERSITIES.values():
        assert the_by_university[university_id]["rankingOnly"] is False
    usnews = rankings["usnews"]
    assert usnews["available"] is True
    assert usnews["edition"] == "2026-2027"
    assert usnews["rowCount"] == 2
    assert usnews["rows"][0]["universityId"] == "ucl-university-college-london"
    assert usnews["rows"][1]["rankDisplay"] == "=200"


def test_extended_ranking_views_reuse_shared_application_windows() -> None:
    app_js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")

    assert 'if (state.ranking !== "qs") return [];' not in app_js
    assert "selectedRankingCache?.ranking === state.ranking" in app_js
    assert "context.index.universityIds" in app_js
    assert "context.recordsSource !== state.data" in app_js
    assert 'state.status = state.ranking === "qs" ? "open" : "unknown";' not in app_js


def test_table_headers_own_application_sorting() -> None:
    app_js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")

    assert '{ label: rankColumnLabel(), sort: "rank" }' in app_js
    assert '{ label: t("opens"), sort: "opens" }' in app_js
    assert '{ label: t("deadline"), sort: "deadline" }' in app_js
    assert "table-sort-button" in app_js
