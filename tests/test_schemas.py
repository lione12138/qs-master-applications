from __future__ import annotations

import json

from gradwindow.schemas import export_schemas


def test_export_schemas_uses_public_aliases(tmp_path) -> None:
    written = export_schemas(tmp_path)
    assert len(written) == 7
    application = json.loads(
        (tmp_path / "application-window.schema.json").read_text(
            encoding="utf-8"
        )
    )
    assert "universityId" in application["properties"]
    assert "intakeDetails" in application["properties"]
