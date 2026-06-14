from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess


def test_frontend_upcoming_window_has_thirty_day_boundary() -> None:
    node = shutil.which("node")
    assert node is not None, "Node.js is required for frontend status tests"
    module_uri = (Path(__file__).parents[1] / "status.js").resolve().as_uri()
    script = f"""
      import {{ getApplicationStatus }} from {json.dumps(module_uri)};
      const today = new Date("2026-06-14T00:00:00Z");
      const status = (opensAt, closesAt = "2026-12-31") =>
        getApplicationStatus({{ opensAt, closesAt, dataStatus: "official" }}, today);
      console.log(JSON.stringify({{
        today: status("2026-06-14"),
        within30: status("2026-07-14"),
        after30: status("2026-07-15"),
        snuSpring2027: status("2026-07-06", "2026-07-09"),
        alreadyOpen: status("2026-06-01"),
        closed: status("2026-01-01", "2026-06-13"),
        predictedWithin30: getApplicationStatus({{
          opensAt: "2026-07-01",
          closesAt: "2026-12-01",
          dataStatus: "predicted"
        }}, today),
        predictedFuture: getApplicationStatus({{
          opensAt: "2026-08-01",
          closesAt: "2027-01-01",
          dataStatus: "predicted"
        }}, today)
      }}));
    """
    result = subprocess.run(
        [node, "--input-type=module", "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(result.stdout) == {
        "today": "open",
        "within30": "upcoming",
        "after30": "future",
        "snuSpring2027": "upcoming",
        "alreadyOpen": "open",
        "closed": "closed",
        "predictedWithin30": "upcoming",
        "predictedFuture": "future",
    }
