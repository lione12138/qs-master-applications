from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess


def test_frontend_localizes_chinese_record_labels() -> None:
    node = shutil.which("node")
    assert node is not None, "Node.js is required for frontend localization tests"
    module_uri = (Path(__file__).parents[1] / "localization.js").resolve().as_uri()
    script = f"""
      import {{
        countryLabel,
        programmeLabel,
        regionLabel,
        roundLabel,
        schoolLabels,
      }} from {json.dumps(module_uri)};
      console.log(JSON.stringify({{
        country: countryLabel("United Kingdom", "zh"),
        region: regionLabel("Europe", "zh"),
        school: schoolLabels({{
          school: "UCL (University College London)",
          schoolZh: "伦敦大学学院",
        }}, "zh"),
        programme: programmeLabel(
          "ucl-advanced-materials-science-msc",
          "Advanced Materials Science MSc",
          "zh",
        ),
        round: roundLabel("Visa applicants", "zh"),
      }}));
    """
    result = subprocess.run(
        [node, "--input-type=module", "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(result.stdout) == {
        "country": "英国",
        "region": "欧洲",
        "school": {
            "primary": "伦敦大学学院",
            "secondary": "UCL (University College London)",
        },
        "programme": "高级材料科学理学硕士",
        "round": "需要学生签证申请人",
    }
