from __future__ import annotations

import json
from pathlib import Path


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
