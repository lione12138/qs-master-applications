from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path


def test_frontend_distinguishes_blocked_crawlers_from_manual_checks() -> None:
    node = shutil.which("node")
    assert node is not None, "Node.js is required for frontend exception tests"
    module_uri = (
        (Path(__file__).parents[1] / "web" / "exception-status.js").resolve().as_uri()
    )
    script = f"""
      import {{ needsManualCheck }} from {json.dumps(module_uri)};
      console.log(JSON.stringify({{
        blockedCrawler: needsManualCheck({{
          admissionsDiscovery: "curated",
          monitor: {{ status: "blocked" }},
          coverage: {{ nextAction: "monitor-and-refresh" }},
          windowPolicy: {{ cycleGuidance: {{ status: "dates-not-exact" }} }}
        }}),
        protectedEntry: needsManualCheck({{
          admissionsDiscovery: "curated",
          coverage: {{ nextAction: "monitor-and-refresh" }},
          windowPolicy: {{ cycleGuidance: {{ status: "official-entry-protected" }} }}
        }}),
        missingRoute: needsManualCheck({{
          admissionsDiscovery: "not-found",
          coverage: {{ nextAction: "locate-official-entry" }}
        }})
      }}));
    """
    result = subprocess.run(
        [node, "--input-type=module", "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(result.stdout) == {
        "blockedCrawler": False,
        "protectedEntry": True,
        "missingRoute": True,
    }
