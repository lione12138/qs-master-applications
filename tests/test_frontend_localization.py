from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path


def test_frontend_localizes_chinese_record_labels() -> None:
    node = shutil.which("node")
    assert node is not None, "Node.js is required for frontend localization tests"
    module_uri = (Path(__file__).parents[1] / "localization.js").resolve().as_uri()
    script = f"""
      import {{
        countryLabel,
        programmeLabel,
        programmeSearchTerms,
        regionLabel,
        roundLabel,
        schoolLabels,
        setProgrammeTranslations,
      }} from {json.dumps(module_uri)};
      setProgrammeTranslations({{
        translations: {{
          "new-ai-programme": {{
            zh: "人工智能硕士项目",
            aliasesZh: ["AI 硕士"],
          }},
          "ucl-advanced-materials-science-msc": {{
            zh: "高级材料科学硕士项目",
          }},
          "mit-aeronautics-and-astronautics-masters": {{
            zh: "航空航天硕士项目",
          }},
        }},
      }});
      console.log(JSON.stringify({{
        country: countryLabel("United Kingdom", "zh"),
        countryUs: countryLabel("United States", "zh"),
        countryHk: countryLabel("Hong Kong SAR", "zh"),
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
        searchTerms: programmeSearchTerms(
          "new-ai-programme",
          "Artificial Intelligence MSc",
        ),
        round: roundLabel("Visa applicants", "zh"),
        mitProgramme: programmeLabel(
          "mit-aeronautics-and-astronautics-masters",
          "Aeronautics and Astronautics",
          "zh",
        ),
        mitRound: roundLabel("Round 1", "zh"),
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
        "countryUs": "美国",
        "countryHk": "中国香港",
        "region": "欧洲",
        "school": {
            "primary": "伦敦大学学院",
            "secondary": "",
        },
        "programme": "高级材料科学硕士项目",
        "searchTerms": [
            "Artificial Intelligence MSc",
            "人工智能硕士项目",
            "AI 硕士",
            "new-ai-programme",
        ],
        "round": "需要学生签证申请人",
        "mitProgramme": "航空航天硕士项目",
        "mitRound": "第一轮",
    }


def test_frontend_english_mode_does_not_show_chinese_school_alias() -> None:
    node = shutil.which("node")
    assert node is not None, "Node.js is required for frontend localization tests"
    module_uri = (Path(__file__).parents[1] / "localization.js").resolve().as_uri()
    script = f"""
      import {{ schoolLabels }} from {json.dumps(module_uri)};
      console.log(JSON.stringify(schoolLabels({{
        school: "UCL (University College London)",
        schoolZh: "伦敦大学学院",
      }}, "en")));
    """
    result = subprocess.run(
        [node, "--input-type=module", "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(result.stdout) == {
        "primary": "UCL (University College London)",
        "secondary": "",
    }
