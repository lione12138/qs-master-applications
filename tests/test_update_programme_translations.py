from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import httpx
import pytest


def load_module():
    path = Path(__file__).parents[1] / "scripts" / "update_programme_translations.py"
    spec = importlib.util.spec_from_file_location("update_programme_translations", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def completion_response(
    status_code: int,
    *,
    content: str | None = None,
    error: str = "",
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    request = httpx.Request("POST", "https://api.deepseek.com/chat/completions")
    if content is not None:
        payload = {"choices": [{"message": {"content": content}}]}
    else:
        payload = {"error": {"message": error}}
    return httpx.Response(
        status_code,
        json=payload,
        headers=headers,
        request=request,
    )


def sample_rows() -> list[dict[str, str]]:
    return [
        {
            "id": "example-msc",
            "english": "Example MSc",
            "scopeType": "programme",
            "university": "Example University",
            "country": "Exampleland",
            "description": "",
        }
    ]


def test_translate_batch_retries_http_400_without_optional_parameters(
    monkeypatch,
) -> None:
    module = load_module()
    request_payloads = []
    responses = [
        completion_response(400, error="unsupported field: thinking"),
        completion_response(
            200,
            content=json.dumps(
                {"example-msc": {"zh": "示例理学硕士", "aliasesZh": []}},
                ensure_ascii=False,
            ),
        ),
    ]

    def fake_post(_url, *, headers, json, timeout):
        assert headers["Authorization"] == "Bearer test-key"
        assert timeout == 10
        request_payloads.append(json)
        return responses.pop(0)

    monkeypatch.setattr(module.httpx, "post", fake_post)

    translated = module.translate_batch(
        sample_rows(),
        api_key="test-key",
        base_url="https://api.deepseek.com",
        model="deepseek-v4-flash",
        timeout=10,
    )

    assert translated["example-msc"]["zh"] == "示例理学硕士"
    assert request_payloads[0]["thinking"] == {"type": "disabled"}
    assert request_payloads[0]["response_format"] == {"type": "json_object"}
    assert "thinking" not in request_payloads[1]
    assert "response_format" not in request_payloads[1]


def test_translate_batch_retries_transient_http_errors(monkeypatch) -> None:
    module = load_module()
    responses = [
        completion_response(
            429,
            error="rate limited",
            headers={"Retry-After": "0"},
        ),
        completion_response(
            200,
            content=json.dumps(
                {"example-msc": {"zh": "示例理学硕士", "aliasesZh": []}},
                ensure_ascii=False,
            ),
        ),
    ]
    delays = []

    monkeypatch.setattr(
        module.httpx,
        "post",
        lambda *_args, **_kwargs: responses.pop(0),
    )
    monkeypatch.setattr(module.time, "sleep", delays.append)

    translated = module.translate_batch(
        sample_rows(),
        api_key="test-key",
        base_url="https://api.deepseek.com",
        model="deepseek-v4-flash",
        timeout=10,
    )

    assert translated["example-msc"]["zh"] == "示例理学硕士"
    assert delays == [0.0]


def test_api_error_diagnostic_redacts_api_key(monkeypatch) -> None:
    module = load_module()
    secret = "very-secret-key"
    monkeypatch.setattr(
        module.httpx,
        "post",
        lambda *_args, **_kwargs: completion_response(
            400,
            error=f"invalid request with Bearer {secret}",
        ),
    )

    with pytest.raises(module.TranslationAPIError) as exc_info:
        module.translate_batch(
            sample_rows(),
            api_key=secret,
            base_url="https://api.deepseek.com",
            model="deepseek-v4-flash",
            timeout=10,
        )

    message = str(exc_info.value)
    assert secret not in message
    assert "[redacted]" in message
    assert "HTTP 400 after compatibility fallback" in message


def test_successful_batches_are_checkpointed_before_later_failure(
    monkeypatch,
    tmp_path,
) -> None:
    module = load_module()
    translation_path = tmp_path / "programme-translations.json"
    monkeypatch.setattr(module, "TRANSLATIONS_PATH", translation_path)
    monkeypatch.setattr(
        module,
        "build_scope_catalog",
        lambda: {
            scope_id: {
                "id": scope_id,
                "english": scope_id,
                "scopeType": "programme",
                "university": "Example University",
                "country": "Exampleland",
                "description": "",
            }
            for scope_id in ["programme-a", "programme-b", "programme-c"]
        },
    )
    calls = 0

    def fake_translate(rows, **_kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise module.TranslationAPIError("second batch failed")
        return {row["id"]: {"zh": f"中文 {row['id']}", "aliasesZh": []} for row in rows}

    monkeypatch.setattr(module, "translate_batch", fake_translate)

    with pytest.raises(module.TranslationAPIError, match="second batch failed"):
        module.update_translations(
            batch_size=2,
            api_key="test-key",
            model="deepseek-v4-flash",
        )

    saved = json.loads(translation_path.read_text(encoding="utf-8"))
    assert set(saved["translations"]) == {"programme-a", "programme-b"}
    assert not list(tmp_path.glob(".programme-translations.json.*.tmp"))


def test_empty_ci_variables_fall_back_to_script_defaults(monkeypatch, tmp_path) -> None:
    module = load_module()
    monkeypatch.setenv("DEEPSEEK_MODEL", "")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "")
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(
        module,
        "TRANSLATIONS_PATH",
        tmp_path / "data" / "programme-translations.json",
    )
    monkeypatch.setattr(
        module,
        "build_scope_catalog",
        lambda: {"example-msc": sample_rows()[0]},
    )
    request_options = {}

    def fake_translate(rows, **kwargs):
        request_options.update(kwargs)
        return {
            rows[0]["id"]: {"zh": "示例理学硕士", "aliasesZh": []},
        }

    monkeypatch.setattr(module, "translate_batch", fake_translate)

    translated = module.update_translations(api_key="test-key")

    assert translated == 1
    assert request_options["model"] == module.DEFAULT_MODEL
    assert request_options["base_url"] == module.DEFAULT_BASE_URL


def test_incomplete_batch_is_rejected_without_checkpoint(monkeypatch) -> None:
    module = load_module()
    monkeypatch.setattr(
        module.httpx,
        "post",
        lambda *_args, **_kwargs: completion_response(200, content="{}"),
    )

    with pytest.raises(module.TranslationResponseError, match="1 item"):
        module.translate_batch(
            sample_rows(),
            api_key="test-key",
            base_url="https://api.deepseek.com",
            model="deepseek-v4-flash",
            timeout=10,
        )


def test_official_translations_are_saved_without_an_api_key(
    monkeypatch, tmp_path
) -> None:
    module = load_module()
    translation_path = tmp_path / "programme-translations.json"
    monkeypatch.setattr(module, "TRANSLATIONS_PATH", translation_path)
    monkeypatch.setattr(
        module,
        "build_scope_catalog",
        lambda: {
            "ntu-international-master-101": {
                "id": "ntu-international-master-101",
                "english": "Master's Programme in Graduate Institute of Linguistics",
                "scopeType": "programme",
                "university": "National Taiwan University",
                "country": "Taiwan",
                "description": "",
            }
        },
    )
    monkeypatch.setattr(
        module,
        "fetch_official_translations",
        lambda _catalog: {"ntu-international-master-101": "語言學研究所"},
    )

    translated = module.update_translations(api_key=None)

    assert translated == 1
    saved = json.loads(translation_path.read_text(encoding="utf-8"))
    assert saved["translations"]["ntu-international-master-101"] == {
        "zh": "語言學研究所",
        "source": "official",
        "sourceUrl": module.NTU_CHINESE_CATALOG_URL,
        "updatedAt": module.date.today().isoformat(),
    }
