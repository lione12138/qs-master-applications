from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_equivalent_programme_windows_group_without_merging_distinct_rules() -> None:
    node = shutil.which("node")
    assert node is not None, "Node.js is required for window grouping tests"
    module_uri = (ROOT / "window-grouping.js").resolve().as_uri()
    records = [
        {
            "id": "ucl-a",
            "universityId": "ucl",
            "scopeType": "programme",
            "scopeId": "a",
            "intake": "September 2026",
            "applicantCategories": ["nonvisa"],
            "opensAt": "2025-10-20",
            "closesAt": "2026-08-28",
            "dataStatus": "official",
        },
        {
            "id": "ucl-b",
            "universityId": "ucl",
            "scopeType": "programme",
            "scopeId": "b",
            "intake": "September 2026",
            "applicantCategories": ["nonvisa"],
            "opensAt": "2025-10-20",
            "closesAt": "2026-08-28",
            "dataStatus": "official",
        },
        {
            "id": "ucl-visa",
            "universityId": "ucl",
            "scopeType": "programme",
            "scopeId": "visa",
            "intake": "September 2026",
            "applicantCategories": ["visa"],
            "opensAt": "2025-10-20",
            "closesAt": "2026-08-28",
            "dataStatus": "official",
        },
        {
            "id": "ucl-earlier",
            "universityId": "ucl",
            "scopeType": "programme",
            "scopeId": "earlier",
            "intake": "September 2026",
            "applicantCategories": ["nonvisa"],
            "opensAt": "2025-10-20",
            "closesAt": "2026-06-26",
            "dataStatus": "official",
        },
        {
            "id": "ucl-estimate",
            "universityId": "ucl",
            "scopeType": "programme",
            "scopeId": "estimate",
            "intake": "September 2026",
            "applicantCategories": ["nonvisa"],
            "opensAt": "2025-10-20",
            "closesAt": "2026-08-28",
            "dataStatus": "predicted",
        },
        {
            "id": "ucl-institution",
            "universityId": "ucl",
            "scopeType": "institution",
            "scopeId": "ucl",
            "intake": "September 2026",
            "applicantCategories": ["nonvisa"],
            "opensAt": "2025-10-20",
            "closesAt": "2026-08-28",
            "dataStatus": "official",
        },
    ]
    script = f"""
      import {{ groupEquivalentWindows }} from {json.dumps(module_uri)};
      const groups = groupEquivalentWindows({json.dumps(records)});
      console.log(JSON.stringify(groups.map((group) => ({{
        ids: group.records.map((record) => record.id),
        collapsible: group.collapsible,
      }}))));
    """

    result = subprocess.run(
        [node, "--input-type=module", "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )
    groups = json.loads(result.stdout)

    assert groups[0] == {"ids": ["ucl-a", "ucl-b"], "collapsible": True}
    assert [group["ids"] for group in groups[1:]] == [
        ["ucl-visa"],
        ["ucl-earlier"],
        ["ucl-estimate"],
        ["ucl-institution"],
    ]


def test_university_groups_wrap_equivalent_window_groups() -> None:
    node = shutil.which("node")
    assert node is not None, "Node.js is required for window grouping tests"
    module_uri = (ROOT / "window-grouping.js").resolve().as_uri()
    records = [
        {
            "id": "mit-a",
            "universityId": "mit",
            "scopeType": "programme",
            "scopeId": "a",
            "intake": "September 2027",
            "applicantCategories": ["all"],
            "opensAt": "2026-09-01",
            "closesAt": "2026-12-01",
            "dataStatus": "official",
        },
        {
            "id": "mit-b",
            "universityId": "mit",
            "scopeType": "programme",
            "scopeId": "b",
            "intake": "September 2027",
            "applicantCategories": ["all"],
            "opensAt": "2026-09-15",
            "closesAt": "2026-12-15",
            "dataStatus": "official",
        },
        {
            "id": "ucl-a",
            "universityId": "ucl",
            "scopeType": "programme",
            "scopeId": "a",
            "intake": "September 2026",
            "applicantCategories": ["all"],
            "opensAt": "2025-10-20",
            "closesAt": "2026-08-28",
            "dataStatus": "official",
        },
    ]
    script = f"""
      import {{
        groupEquivalentWindows,
        groupWindowGroupsByUniversity,
      }} from {json.dumps(module_uri)};
      const windowGroups = groupEquivalentWindows({json.dumps(records)});
      const groups = groupWindowGroupsByUniversity(windowGroups);
      console.log(JSON.stringify(groups.map((group) => ({{
        key: group.key,
        ids: group.records.map((record) => record.id),
        windowGroupCount: group.windowGroups.length,
        collapsible: group.collapsible,
      }}))));
    """

    result = subprocess.run(
        [node, "--input-type=module", "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )

    assert json.loads(result.stdout) == [
        {
            "key": "university:mit",
            "ids": ["mit-a", "mit-b"],
            "windowGroupCount": 2,
            "collapsible": True,
        },
        {
            "key": "university:ucl",
            "ids": ["ucl-a"],
            "windowGroupCount": 1,
            "collapsible": False,
        },
    ]
