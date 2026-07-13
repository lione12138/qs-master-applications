from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path


def test_frontend_groups_equivalent_fall_intakes() -> None:
    node = shutil.which("node")
    assert node is not None, "Node.js is required for frontend intake tests"
    module_uri = (
        (Path(__file__).parents[1] / "web" / "intake-filter.js").resolve().as_uri()
    )
    script = f"""
      import {{ canonicalIntake, intakeLabel }} from {json.dumps(module_uri)};
      const examples = [
        {{ intakeDetails: {{ cycleYear: 2026, term: "fall", startMonth: 9 }} }},
        {{ intakeDetails: {{ cycleYear: 2026, term: "fall", startMonth: 8 }} }},
        {{ intakeDetails: {{ cycleYear: 2026, term: "michaelmas", startMonth: 10 }} }},
        {{ intakeDetails: {{ cycleYear: 2026, term: "other", startMonth: 8 }} }},
      ].map(canonicalIntake);
      const academic = canonicalIntake({{
        intake: "Academic Year 2028",
        intakeDetails: {{
          cycleYear: 2028,
          term: "other",
          startMonth: null,
          academicYearEnd: null
        }}
      }});
      console.log(JSON.stringify({{
        keys: examples.map((item) => item.key),
        en: intakeLabel(examples[0], "en"),
        zh: intakeLabel(examples[0], "zh"),
        academicKey: academic.key,
        academicLabel: intakeLabel(academic, "en"),
      }}));
    """
    result = subprocess.run(
        [node, "--input-type=module", "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(result.stdout) == {
        "keys": ["fall:2026"] * 4,
        "en": "Fall 2026",
        "zh": "2026 秋季",
        "academicKey": "academic:2028",
        "academicLabel": "Academic Year 2028",
    }
