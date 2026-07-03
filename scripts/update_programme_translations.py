from __future__ import annotations

import argparse
import json
import os
import re
from datetime import date
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
TRANSLATIONS_PATH = DATA_DIR / "programme-translations.json"
DEFAULT_MODEL = "deepseek-v4-flash"
DEFAULT_BASE_URL = "https://api.deepseek.com"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def load_translation_payload() -> dict[str, Any]:
    if TRANSLATIONS_PATH.exists():
        return read_json(TRANSLATIONS_PATH)
    return {
        "meta": {
            "description": "Chinese programme and programme-group labels used by GradWindow.",
            "updatedAt": date.today().isoformat(),
            "defaultLanguage": "zh",
            "providers": ["manual", "deepseek", "rule"],
        },
        "translations": {},
    }


def build_scope_catalog() -> dict[str, dict[str, str]]:
    universities = {
        item["id"]: item
        for item in read_json(DATA_DIR / "universities.json")["universities"]
    }
    programs = {
        item["id"]: item for item in read_json(DATA_DIR / "programs.json")["programs"]
    }
    groups = {
        item["id"]: item
        for item in read_json(DATA_DIR / "programme-groups.json")["groups"]
    }
    applications = read_json(DATA_DIR / "applications.json")["applications"]
    predictions = read_json(DATA_DIR / "predictions.json")["predictions"]

    catalog: dict[str, dict[str, str]] = {}
    for record in [*applications, *predictions]:
        scope_id = record["scopeId"]
        university = universities.get(record["universityId"], {})
        if record["scopeType"] == "programme":
            source = programs.get(scope_id, {})
            english = source.get("name") or record.get("program") or scope_id
            description = source.get("faculty", "")
            scope_type = "programme"
        elif record["scopeType"] == "programme-group":
            source = groups.get(scope_id, {})
            english = source.get("name") or record.get("program") or scope_id
            description = source.get("description", "")
            scope_type = "programme-group"
        else:
            english = (
                record.get("program") or "Institution-wide master's application window"
            )
            description = "University-level graduate admissions scope."
            scope_type = "institution"
        catalog[scope_id] = {
            "id": scope_id,
            "english": english,
            "scopeType": scope_type,
            "university": university.get("school", record.get("school", "")),
            "country": university.get("country", record.get("country", "")),
            "description": description,
        }
    return dict(sorted(catalog.items()))


def needs_translation(
    scope_id: str,
    existing: dict[str, Any],
    force: bool,
    include_manual: bool,
) -> bool:
    current = existing.get(scope_id)
    if not current:
        return True
    if isinstance(current, str):
        return force
    if current.get("source") == "manual" and not include_manual:
        return False
    return force or not current.get("zh")


def strip_json_fence(text: str) -> str:
    cleaned = text.strip()
    match = re.search(r"```(?:json)?\s*(.*?)\s*```", cleaned, flags=re.S)
    if match:
        return match.group(1).strip()
    return cleaned


def translate_batch(
    rows: list[dict[str, str]],
    *,
    api_key: str,
    base_url: str,
    model: str,
    timeout: float,
) -> dict[str, dict[str, Any]]:
    system = (
        "You translate university master's admissions programme/scope labels "
        "into concise Simplified Chinese for a Chinese GradWindow UI. "
        "Use common Chinese admissions terminology. Keep proper nouns concise. "
        "Do not invent dates or requirements. Return JSON only."
    )
    user = {
        "task": "Translate each item into Simplified Chinese.",
        "output_schema": {
            "scope-id": {
                "zh": "Chinese display label",
                "aliasesZh": ["optional Chinese search aliases"],
            }
        },
        "rules": [
            "Use natural Chinese names students would search for.",
            "Keep degree type meaning when important, e.g. MSc = 理学硕士, MPhil = 哲学硕士.",
            "For admissions windows or programme groups, translate the scope, not the whole page.",
            "Return every input id exactly once.",
        ],
        "items": rows,
    }
    response = httpx.post(
        f"{base_url.rstrip('/')}/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
            ],
            "stream": False,
            "thinking": {"type": "disabled"},
            "temperature": 0.2,
            "max_tokens": 6000,
            "response_format": {"type": "json_object"},
        },
        timeout=timeout,
    )
    response.raise_for_status()
    content = response.json()["choices"][0]["message"]["content"]
    parsed = json.loads(strip_json_fence(content))
    return {
        scope_id: value
        for scope_id, value in parsed.items()
        if isinstance(value, dict) and value.get("zh")
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Update cached Chinese programme translations with DeepSeek."
    )
    parser.add_argument(
        "--limit", type=int, default=0, help="Maximum scopes to translate"
    )
    parser.add_argument("--batch-size", type=int, default=20)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--force", action="store_true", help="Re-translate generated entries"
    )
    parser.add_argument(
        "--include-manual",
        action="store_true",
        help="Allow manual entries to be re-translated when --force is used",
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("DEEPSEEK_MODEL", DEFAULT_MODEL),
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("DEEPSEEK_BASE_URL", DEFAULT_BASE_URL),
    )
    parser.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args()

    payload = load_translation_payload()
    translations = payload.setdefault("translations", {})
    catalog = build_scope_catalog()
    pending = [
        item
        for scope_id, item in catalog.items()
        if needs_translation(scope_id, translations, args.force, args.include_manual)
    ]
    if args.limit:
        pending = pending[: args.limit]

    if args.dry_run:
        print(
            json.dumps(
                {"pending": len(pending), "items": pending},
                ensure_ascii=False,
                indent=2,
            )
        )
        return
    if not pending:
        print("No missing programme translations.")
        return

    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise SystemExit("Set DEEPSEEK_API_KEY before running this script.")

    for start in range(0, len(pending), args.batch_size):
        batch = pending[start : start + args.batch_size]
        translated = translate_batch(
            batch,
            api_key=api_key,
            base_url=args.base_url,
            model=args.model,
            timeout=args.timeout,
        )
        for scope_id, value in translated.items():
            translations[scope_id] = {
                "zh": value["zh"].strip(),
                "aliasesZh": [
                    alias.strip()
                    for alias in value.get("aliasesZh", [])
                    if isinstance(alias, str) and alias.strip()
                ],
                "source": "deepseek",
                "model": args.model,
                "updatedAt": date.today().isoformat(),
            }
        print(f"Translated {min(start + len(batch), len(pending))}/{len(pending)}")

    payload.setdefault("meta", {})["updatedAt"] = date.today().isoformat()
    write_json(TRANSLATIONS_PATH, payload)
    print(f"Wrote {TRANSLATIONS_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
