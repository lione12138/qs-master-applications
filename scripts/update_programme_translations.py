from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from gradwindow.io import read_json, write_json
from gradwindow.programme_adapters.ntu_taiwan import (
    CATALOG_URL as NTU_ENGLISH_CATALOG_URL,
)
from gradwindow.programme_adapters.ntu_taiwan import (
    CHINESE_CATALOG_URL as NTU_CHINESE_CATALOG_URL,
)
from gradwindow.programme_adapters.ntu_taiwan import (
    EXISTING_CS_ID as NTU_EXISTING_CS_ID,
)
from gradwindow.programme_adapters.ntu_taiwan import (
    parse_official_chinese_translations,
)

DATA_DIR = ROOT / "data"
TRANSLATIONS_PATH = DATA_DIR / "programme-translations.json"
DEFAULT_MODEL = "deepseek-v4-flash"
DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MAX_ATTEMPTS = 3
MAX_ERROR_BODY_LENGTH = 800
RETRYABLE_STATUS_CODES = {408, 409, 425, 429, 500, 502, 503, 504}


class TranslationAPIError(RuntimeError):
    """A sanitized, actionable DeepSeek request failure."""


class TranslationResponseError(ValueError):
    """A DeepSeek response that cannot safely update the translation cache."""


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


def fetch_official_translations(
    catalog: dict[str, dict[str, str]],
) -> dict[str, str]:
    target_ids = {
        scope_id
        for scope_id in catalog
        if scope_id == NTU_EXISTING_CS_ID
        or scope_id.startswith("ntu-international-master-")
    }
    if not target_ids:
        return {}
    with httpx.Client(follow_redirects=True, timeout=60) as client:
        english_response = client.get(NTU_ENGLISH_CATALOG_URL)
        english_response.raise_for_status()
        chinese_response = client.get(NTU_CHINESE_CATALOG_URL)
        chinese_response.raise_for_status()
    translations = parse_official_chinese_translations(
        english_response.text, chinese_response.text
    )
    return {
        scope_id: value
        for scope_id, value in translations.items()
        if scope_id in target_ids
    }


def strip_json_fence(text: str) -> str:
    cleaned = text.strip()
    match = re.search(r"```(?:json)?\s*(.*?)\s*```", cleaned, flags=re.S)
    if match:
        return match.group(1).strip()
    return cleaned


def _request_payload(
    *,
    model: str,
    system: str,
    user: dict[str, Any],
    compatibility_mode: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
        ],
        "stream": False,
        "temperature": 0.2,
        "max_tokens": 6000,
    }
    if not compatibility_mode:
        payload.update(
            {
                "thinking": {"type": "disabled"},
                "response_format": {"type": "json_object"},
            }
        )
    return payload


def _sanitized_error_body(response: httpx.Response, api_key: str) -> str:
    try:
        body = response.text
    except Exception:  # pragma: no cover - defensive for unusual transports
        body = ""
    if api_key:
        body = body.replace(api_key, "[redacted]")
    body = re.sub(r"(?i)bearer\s+[^\s,;\"']+", "Bearer [redacted]", body)
    return " ".join(body.split())[:MAX_ERROR_BODY_LENGTH]


def _retry_delay(response: httpx.Response | None, attempt: int) -> float:
    if response is not None:
        retry_after = response.headers.get("Retry-After", "").strip()
        try:
            return min(max(float(retry_after), 0.0), 30.0)
        except ValueError:
            pass
    return min(2 ** (attempt - 1), 8)


def _post_translation_request(
    *,
    api_key: str,
    base_url: str,
    payload: dict[str, Any],
    timeout: float,
    max_attempts: int,
) -> httpx.Response:
    endpoint = f"{base_url.rstrip('/')}/chat/completions"
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            response = httpx.post(
                endpoint,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=timeout,
            )
        except httpx.RequestError as exc:
            last_error = exc
            if attempt == max_attempts:
                break
            time.sleep(_retry_delay(None, attempt))
            continue

        if response.status_code in RETRYABLE_STATUS_CODES:
            if attempt == max_attempts:
                body = _sanitized_error_body(response, api_key)
                detail = f"; body={body}" if body else ""
                raise TranslationAPIError(
                    "DeepSeek request exhausted "
                    f"{max_attempts} attempt(s): HTTP {response.status_code}{detail}"
                )
            time.sleep(_retry_delay(response, attempt))
            continue
        return response

    error_type = type(last_error).__name__ if last_error else "RequestError"
    raise TranslationAPIError(
        "DeepSeek request exhausted "
        f"{max_attempts} attempt(s): {error_type}. "
        "Check network access and DEEPSEEK_BASE_URL."
    ) from last_error


def _completion_response(
    *,
    api_key: str,
    base_url: str,
    model: str,
    system: str,
    user: dict[str, Any],
    timeout: float,
    max_attempts: int,
) -> httpx.Response:
    response = _post_translation_request(
        api_key=api_key,
        base_url=base_url,
        payload=_request_payload(
            model=model,
            system=system,
            user=user,
            compatibility_mode=False,
        ),
        timeout=timeout,
        max_attempts=max_attempts,
    )
    if response.status_code == 400:
        print(
            "DeepSeek may have rejected optional thinking/JSON-output parameters; "
            "retrying this batch in compatibility mode.",
            file=sys.stderr,
        )
        response = _post_translation_request(
            api_key=api_key,
            base_url=base_url,
            payload=_request_payload(
                model=model,
                system=system,
                user=user,
                compatibility_mode=True,
            ),
            timeout=timeout,
            max_attempts=max_attempts,
        )

    if response.is_error:
        body = _sanitized_error_body(response, api_key)
        detail = f"; body={body}" if body else ""
        fallback = (
            " after compatibility fallback" if response.status_code == 400 else ""
        )
        raise TranslationAPIError(
            f"DeepSeek returned HTTP {response.status_code}{fallback}{detail}"
        )
    return response


def translate_batch(
    rows: list[dict[str, str]],
    *,
    api_key: str,
    base_url: str,
    model: str,
    timeout: float,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
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
    response = _completion_response(
        api_key=api_key,
        base_url=base_url,
        model=model,
        system=system,
        user=user,
        timeout=timeout,
        max_attempts=max_attempts,
    )
    try:
        content = response.json()["choices"][0]["message"]["content"]
        if not isinstance(content, str):
            raise TypeError("completion content is not text")
        parsed = json.loads(strip_json_fence(content))
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise TranslationResponseError(
            "DeepSeek returned an invalid completion payload; no checkpoint was written."
        ) from exc
    if not isinstance(parsed, dict):
        raise TranslationResponseError(
            "DeepSeek returned JSON that was not an object; no checkpoint was written."
        )

    expected_ids = {row["id"] for row in rows}
    translated = {
        scope_id: value
        for scope_id, value in parsed.items()
        if scope_id in expected_ids
        and isinstance(value, dict)
        and isinstance(value.get("zh"), str)
        and value["zh"].strip()
    }
    missing_ids = sorted(expected_ids - translated.keys())
    if missing_ids:
        preview = ", ".join(missing_ids[:5])
        suffix = "..." if len(missing_ids) > 5 else ""
        raise TranslationResponseError(
            "DeepSeek omitted or returned invalid translations for "
            f"{len(missing_ids)} item(s): {preview}{suffix}. "
            "No checkpoint was written for this batch."
        )
    return translated


def update_translations(
    *,
    limit: int = 0,
    batch_size: int = 20,
    dry_run: bool = False,
    force: bool = False,
    include_manual: bool = False,
    model: str | None = None,
    base_url: str | None = None,
    timeout: float = 60.0,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    api_key: str | None = None,
) -> int:
    if batch_size < 1:
        raise ValueError("batch_size must be at least 1")
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")

    model = model or os.environ.get("DEEPSEEK_MODEL") or DEFAULT_MODEL
    base_url = base_url or os.environ.get("DEEPSEEK_BASE_URL") or DEFAULT_BASE_URL
    payload = load_translation_payload()
    translations = payload.setdefault("translations", {})
    catalog = build_scope_catalog()

    if not dry_run:
        missing_catalog = {
            scope_id: item
            for scope_id, item in catalog.items()
            if needs_translation(scope_id, translations, False, False)
        }
        official_translations = fetch_official_translations(missing_catalog)
        official_count = 0
        for scope_id, value in official_translations.items():
            if not needs_translation(scope_id, translations, False, False):
                continue
            translations[scope_id] = {
                "zh": value,
                "source": "official",
                "sourceUrl": NTU_CHINESE_CATALOG_URL,
                "updatedAt": date.today().isoformat(),
            }
            official_count += 1
        if official_count:
            meta = payload.setdefault("meta", {})
            providers = meta.setdefault("providers", [])
            if "official" not in providers:
                providers.append("official")
            meta["updatedAt"] = date.today().isoformat()
            write_json(TRANSLATIONS_PATH, payload)
            print(f"Imported and checkpointed {official_count} official translations.")
    else:
        official_count = 0

    pending = [
        item
        for scope_id, item in catalog.items()
        if needs_translation(scope_id, translations, force, include_manual)
    ]
    if limit:
        pending = pending[:limit]

    if dry_run:
        print(
            json.dumps(
                {"pending": len(pending), "items": pending},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    if not pending:
        print("No missing programme translations.")
        return official_count

    api_key = api_key or os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise SystemExit("Set DEEPSEEK_API_KEY before running this script.")

    translated_count = official_count
    for start in range(0, len(pending), batch_size):
        batch = pending[start : start + batch_size]
        translated = translate_batch(
            batch,
            api_key=api_key,
            base_url=base_url,
            model=model,
            timeout=timeout,
            max_attempts=max_attempts,
        )
        for scope_id, value in translated.items():
            aliases = value.get("aliasesZh", [])
            if not isinstance(aliases, list):
                aliases = []
            translations[scope_id] = {
                "zh": value["zh"].strip(),
                "aliasesZh": [
                    alias.strip()
                    for alias in aliases
                    if isinstance(alias, str) and alias.strip()
                ],
                "source": "deepseek",
                "model": model,
                "updatedAt": date.today().isoformat(),
            }
        translated_count += len(translated)
        payload.setdefault("meta", {})["updatedAt"] = date.today().isoformat()
        write_json(TRANSLATIONS_PATH, payload)
        print(
            f"Translated and checkpointed "
            f"{min(start + len(batch), len(pending))}/{len(pending)}"
        )

    print(f"Wrote {TRANSLATIONS_PATH.relative_to(ROOT)}")
    return translated_count


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
        default=os.environ.get("DEEPSEEK_MODEL") or DEFAULT_MODEL,
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("DEEPSEEK_BASE_URL") or DEFAULT_BASE_URL,
    )
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--max-attempts", type=int, default=DEFAULT_MAX_ATTEMPTS)
    args = parser.parse_args()
    try:
        update_translations(
            limit=args.limit,
            batch_size=args.batch_size,
            dry_run=args.dry_run,
            force=args.force,
            include_manual=args.include_manual,
            model=args.model,
            base_url=args.base_url,
            timeout=args.timeout,
            max_attempts=args.max_attempts,
        )
    except (TranslationAPIError, TranslationResponseError, ValueError) as exc:
        raise SystemExit(f"Programme translation update failed: {exc}") from exc


if __name__ == "__main__":
    main()
