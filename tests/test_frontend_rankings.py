from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[1]


def test_frontend_joins_application_windows_to_each_selected_ranking() -> None:
    node = shutil.which("node")
    assert node is not None, "Node.js is required for frontend ranking tests"
    module_uri = (ROOT / "ranking-filter.js").resolve().as_uri()
    applications_uri = (ROOT / "data" / "applications.json").resolve().as_uri()
    predictions_uri = (ROOT / "data" / "predictions.json").resolve().as_uri()
    rankings_uri = (ROOT / "data" / "global-rankings.json").resolve().as_uri()
    script = f"""
      import fs from "node:fs";
      import {{ filterRecordsToRanking }} from {json.dumps(module_uri)};
      const load = (url) => JSON.parse(fs.readFileSync(new URL(url), "utf8"));
      const records = [
        ...load({json.dumps(applications_uri)}).applications,
        ...load({json.dumps(predictions_uri)}).predictions,
      ];
      const rankings = load({json.dumps(rankings_uri)}).rankings;
      console.log(JSON.stringify({{
        the: filterRecordsToRanking(records, rankings.the.rows).length,
        arwu: filterRecordsToRanking(records, rankings.arwu.rows).length,
      }}));
    """
    result = subprocess.run(
        [node, "--input-type=module", "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )

    assert json.loads(result.stdout) == {"the": 118, "arwu": 54}
