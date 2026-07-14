from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx
from bs4 import BeautifulSoup

from .discovery import same_official_domain
from .http_client import DEFAULT_USER_AGENT, FetchFailure, fetch_page
from .programme_adapters.base import (
    DiscoveredCatalog,
    DiscoveredProgramme,
    DiscoveredWindow,
)
from .programme_discovery import discover_programmes
from .search_providers import (
    BraveSearcher,  # noqa: F401 - retained as a compatibility re-export
    SearchResult,  # noqa: F401 - retained as a compatibility re-export
    SerperSearcher,  # noqa: F401 - retained as a compatibility re-export
    search_router_from_environment,
)

DEEPSEEK_BASE_URL = "https://api.deepseek.com"
CLOUDFLARE_API_BASE = "https://api.cloudflare.com/client/v4"
DEFAULT_DEEPSEEK_MODEL = "deepseek-v4-flash"
MAX_SEARCH_RESULTS = 12
MAX_DOCUMENT_CHARS = 12_000
MAX_PROMPT_CHARS = 80_000

_DEGREE_RE = re.compile(
    r"\b(MSc|MS|MA|MEng|MEd|MRes|MPhil|MLitt|LLM|MBA|MPH|MPP|MPA|"
    r"Master(?:'s)?(?:\s+of)?)\b",
    flags=re.IGNORECASE,
)
_DATE_PATTERNS = (
    ("%Y-%m-%d", re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")),
    ("%B %d, %Y", re.compile(r"\b([A-Z][a-z]+\s+\d{1,2},\s+20\d{2})\b")),
    ("%d %B %Y", re.compile(r"\b(\d{1,2}\s+[A-Z][a-z]+\s+20\d{2})\b")),
    ("%d %b %Y", re.compile(r"\b(\d{1,2}\s+[A-Z][a-z]{2}\s+20\d{2})\b")),
)
_ALLOWED_APPLICANT_CATEGORIES = {
    "all",
    "domestic-students",
    "international-students",
}
_REJECT_PROGRAMME_RE = re.compile(
    r"\b(PhD|Ph\.D|doctorate|doctoral|bachelor|undergraduate|certificate|"
    r"short course)\b",
    flags=re.IGNORECASE,
)
_NAVIGATION_PROGRAMME_RE = re.compile(
    r"^(master(?:'s)? programmes?|master(?:'s)? programs?|masters? courses?|"
    r"postgraduate(?: taught)? courses?|postgraduate programmes?|"
    r"how to apply|application deadlines?|graduate admissions?)$",
    flags=re.IGNORECASE,
)
_RELEVANT_DOCUMENT_RE = re.compile(
    r"\b(master(?:'s)?|msc|mres|mphil|meng|llm|mba|mph|mpp|mpa|"
    r"postgraduate|graduate|programme|program|course|admission|application|"
    r"deadline|closing date)\b",
    flags=re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class RetrievedDocument:
    id: str
    title: str
    url: str
    content: str
    retrieval_method: str
    evidence_quality: str


@dataclass(frozen=True, slots=True)
class AssistedDiscoveryConfig:
    university_id: str
    university_name: str
    school_prefix: str
    seed_urls: tuple[str, ...]
    official_domains: tuple[str, ...]
    default_application_url: str
    default_intake: str
    minimum_closes_at: str = "2025-07-01"
    max_results: int = MAX_SEARCH_RESULTS
    search_priority: str = "normal"


class AssistedCatalogAdapter:
    application_opens_at_basis = "official"

    def __init__(
        self,
        config: AssistedDiscoveryConfig,
        catalog: DiscoveredCatalog,
    ) -> None:
        self.config = config
        self.university_id = config.university_id
        self.catalog_url = config.seed_urls[0]
        self.intake = config.default_intake
        self._catalog = catalog

    def parse_catalog_from_fetcher(self, _fetcher) -> DiscoveredCatalog:
        return self._catalog


def run_assisted_discovery(
    config: AssistedDiscoveryConfig,
    *,
    candidates_path=None,
    dry_run: bool = False,
    searcher: Callable[[str, int], list[SearchResult]] | None = None,
    page_loader: Callable[[SearchResult], RetrievedDocument] | None = None,
    extractor: Callable[[AssistedDiscoveryConfig, list[RetrievedDocument]], dict]
    | None = None,
) -> dict[str, Any]:
    missing = _missing_credentials()
    if extractor is None and "DEEPSEEK_API_KEY" in missing:
        return _skipped_report(config, missing)

    search_provider = "injected"
    search_usage: dict[str, dict[str, int]] = {}
    search_errors: list[dict[str, str | int]] = []
    search_router = None
    if searcher is None:
        search_router = search_router_from_environment(config.search_priority)
        searcher = search_router.search
        search_provider = search_router.provider_label
    page_loader = (
        page_loader or AssistedPageLoader.from_environment(config.official_domains).load
    )
    extractor = extractor or DeepSeekExtractor.from_environment().extract

    try:
        results = _search_official_sources(config, searcher)
    except Exception as exc:
        report = _error_report(config, "search", exc, dry_run)
        if search_router is not None:
            report.update(
                {
                    "searchProvider": search_router.provider_label,
                    "searchUsage": search_router.usage,
                    "searchErrors": search_router.errors,
                }
            )
        return report
    if search_router is not None:
        search_provider = search_router.provider_label
        search_usage = search_router.usage
        search_errors = search_router.errors
    try:
        retrieved_documents = [page_loader(result) for result in results]
    except Exception as exc:
        return _error_report(config, "retrieval", exc, dry_run)
    if not retrieved_documents:
        return {
            "status": "no-results",
            "universityId": config.university_id,
            "sourceUrl": config.seed_urls[0],
            "searchProvider": search_provider,
            "searchUsage": search_usage,
            "searchErrors": search_errors,
            "searchResults": 0,
            "documents": [],
            "documentsConsidered": 0,
            "documentsSelected": 0,
            "dryRun": dry_run,
        }
    documents = _select_relevant_documents(retrieved_documents)
    if not documents:
        return {
            "status": "no-relevant-documents",
            "universityId": config.university_id,
            "sourceUrl": config.seed_urls[0],
            "searchProvider": search_provider,
            "searchUsage": search_usage,
            "searchErrors": search_errors,
            "searchResults": len(results),
            "documents": _document_report(retrieved_documents),
            "documentsConsidered": len(retrieved_documents),
            "documentsSelected": 0,
            "dryRun": dry_run,
        }

    try:
        payload = extractor(config, documents)
    except Exception as exc:
        return _error_report(config, "extraction", exc, dry_run)
    catalog, validation = _validated_catalog(config, documents, payload)
    if not catalog.programmes:
        return {
            "status": "no-candidates",
            "universityId": config.university_id,
            "sourceUrl": config.seed_urls[0],
            "searchProvider": search_provider,
            "searchUsage": search_usage,
            "searchErrors": search_errors,
            "searchResults": len(results),
            "documents": _document_report(documents),
            "documentsConsidered": len(retrieved_documents),
            "documentsSelected": len(documents),
            "validation": validation,
            "dryRun": dry_run,
        }

    adapter = AssistedCatalogAdapter(config, catalog)
    kwargs: dict[str, Any] = {"dry_run": dry_run}
    if candidates_path is not None:
        kwargs["candidates_path"] = candidates_path
    report = discover_programmes(adapter, **kwargs)
    report.update(
        {
            "assistedDiscovery": True,
            "searchProvider": search_provider,
            "searchUsage": search_usage,
            "searchErrors": search_errors,
            "searchResults": len(results),
            "documents": _document_report(documents),
            "documentsConsidered": len(retrieved_documents),
            "documentsSelected": len(documents),
            "validation": validation,
        }
    )
    return report


class CloudflareBrowserClient:
    def __init__(
        self,
        account_id: str,
        api_token: str,
        *,
        timeout: float = 60,
    ) -> None:
        self.account_id = account_id
        self.api_token = api_token
        self.timeout = timeout

    @classmethod
    def from_environment(cls) -> CloudflareBrowserClient | None:
        account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID")
        api_token = os.environ.get("CLOUDFLARE_BROWSER_API_TOKEN") or os.environ.get(
            "CLOUDFLARE_API_TOKEN"
        )
        if not account_id or not api_token:
            return None
        return cls(account_id, api_token)

    def markdown(self, url: str) -> str:
        response = httpx.post(
            f"{CLOUDFLARE_API_BASE}/accounts/{self.account_id}/"
            "browser-rendering/markdown",
            headers={
                "Authorization": f"Bearer {self.api_token}",
                "Content-Type": "application/json",
            },
            json={"url": url},
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        if not payload.get("success") or not isinstance(payload.get("result"), str):
            errors = payload.get("errors") or []
            raise RuntimeError(f"Cloudflare Browser Rendering failed: {errors}")
        return payload["result"]


class AssistedPageLoader:
    def __init__(
        self,
        official_domains: tuple[str, ...],
        browser: CloudflareBrowserClient | None = None,
    ) -> None:
        self.official_domains = official_domains
        self.browser = browser

    @classmethod
    def from_environment(cls, official_domains: tuple[str, ...]) -> AssistedPageLoader:
        return cls(official_domains, CloudflareBrowserClient.from_environment())

    def load(self, result: SearchResult) -> RetrievedDocument:
        content = ""
        retrieval_method = "search-snippet"
        evidence_quality = "official-search-snippet"
        try:
            page = fetch_page(
                result.url,
                user_agent=DEFAULT_USER_AGENT,
                timeout=25,
                accept="text/html,application/xhtml+xml,text/plain",
            )
            if (
                "text/" in page.content_type or "html" in page.content_type
            ) and same_official_domain(page.final_url, list(self.official_domains)):
                content = BeautifulSoup(page.body, "html.parser").get_text(
                    " ", strip=True
                )
                retrieval_method = "direct-http"
                evidence_quality = "official-fulltext"
        except FetchFailure:
            pass

        if not content and self.browser is not None:
            try:
                content = self.browser.markdown(result.url)
                retrieval_method = "cloudflare-browser-rendering"
                evidence_quality = "official-fulltext"
            except (httpx.HTTPError, RuntimeError):
                pass

        if not content:
            content = " ".join(
                value
                for value in (
                    result.title,
                    result.description,
                    *result.extra_snippets,
                )
                if value
            )
        return RetrievedDocument(
            id="doc-" + hashlib.sha256(result.url.encode("utf-8")).hexdigest()[:12],
            title=result.title,
            url=result.url,
            content=content[:MAX_DOCUMENT_CHARS],
            retrieval_method=retrieval_method,
            evidence_quality=evidence_quality,
        )


class DeepSeekExtractor:
    def __init__(
        self,
        api_key: str,
        *,
        model: str = DEFAULT_DEEPSEEK_MODEL,
        base_url: str = DEEPSEEK_BASE_URL,
        timeout: float = 90,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    @classmethod
    def from_environment(cls) -> DeepSeekExtractor:
        return cls(
            os.environ["DEEPSEEK_API_KEY"],
            model=os.environ.get("DEEPSEEK_MODEL", DEFAULT_DEEPSEEK_MODEL),
            base_url=os.environ.get("DEEPSEEK_BASE_URL", DEEPSEEK_BASE_URL),
        )

    def extract(
        self,
        config: AssistedDiscoveryConfig,
        documents: list[RetrievedDocument],
    ) -> dict:
        prompt = _extraction_prompt(config, documents)
        response = httpx.post(
            f"{self.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You extract graduate admissions facts from supplied "
                            "official-source documents. Return JSON only. Never "
                            "invent a programme, date, URL, intake, or applicant "
                            "category."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                "response_format": {"type": "json_object"},
                "stream": False,
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        return json.loads(_strip_json_fence(content))


def _search_official_sources(
    config: AssistedDiscoveryConfig,
    searcher: Callable[[str, int], list[SearchResult]],
) -> list[SearchResult]:
    intake_years = " ".join(sorted(set(re.findall(r"20\d{2}", config.default_intake))))
    queries = tuple(
        query
        for domain in config.official_domains
        for query in (
            f"site:{domain} masters postgraduate programmes {intake_years}",
            f"site:{domain} masters application opens deadline {intake_years}",
        )
    )
    results: dict[str, SearchResult] = {
        seed_url.split("#", 1)[0]: SearchResult(
            title=f"{config.university_name} official programme catalogue",
            url=seed_url.split("#", 1)[0],
            description="Configured official programme-discovery entry point.",
        )
        for seed_url in config.seed_urls
        if seed_url and same_official_domain(seed_url, list(config.official_domains))
    }
    for query in queries:
        for result in searcher(query[:400], config.max_results):
            if not same_official_domain(result.url, list(config.official_domains)):
                continue
            results.setdefault(result.url.split("#", 1)[0], result)
            if len(results) >= config.max_results:
                break
        if len(results) >= config.max_results:
            break
    return list(results.values())


def _extraction_prompt(
    config: AssistedDiscoveryConfig,
    documents: list[RetrievedDocument],
) -> str:
    document_payload = [
        {
            "id": document.id,
            "url": document.url,
            "title": document.title,
            "evidenceQuality": document.evidence_quality,
            "content": document.content,
        }
        for document in documents
    ]
    prompt = f"""
Extract taught master's programme candidates for {config.university_name}.
Default intake label: {config.default_intake}.

Rules:
- Only use the supplied documents.
- A programme must be a taught master's degree, not a PhD, undergraduate,
  certificate, short course, scholarship, news item, or navigation page.
- sourceDocumentId must exactly match a supplied document id.
- Preserve the official programme name.
- Only extract a window when the exact opening and/or closing date is explicitly
  visible in a document whose evidenceQuality is official-fulltext.
- Never extract a date from official-search-snippet documents.
- Every window requires an exact closing date and a verbatim evidenceQuote from
  the same source document. Use null for an unpublished opening date.
- Return dates as YYYY-MM-DD. Do not convert month-only or approximate wording.
- applicantCategories must contain only all, domestic-students, or
  international-students.
- If a programme is visible but no safe deadline exists, return windows as [].

Return this JSON shape:
{{
  "programmes": [
    {{
      "name": "string",
      "degreeType": "string",
      "faculty": "string",
      "department": "string",
      "sourceDocumentId": "doc-id",
      "applicationUrl": "official URL or empty string",
      "programmeEvidenceQuote": "short verbatim quote",
      "windows": [
        {{
          "intake": "string",
          "round": "string",
          "applicantCategories": ["all"],
          "opensAt": "YYYY-MM-DD or null",
          "closesAt": "YYYY-MM-DD",
          "sourceDocumentId": "doc-id",
          "evidenceQuote": "verbatim quote containing the dates"
        }}
      ]
    }}
  ]
}}

DOCUMENTS:
{json.dumps(document_payload, ensure_ascii=False)}
""".strip()
    return prompt[:MAX_PROMPT_CHARS]


def _validated_catalog(
    config: AssistedDiscoveryConfig,
    documents: list[RetrievedDocument],
    payload: Any,
) -> tuple[DiscoveredCatalog, dict[str, int]]:
    documents_by_id = {document.id: document for document in documents}
    programmes: dict[str, DiscoveredProgramme] = {}
    rejected_programmes = 0
    rejected_windows = 0
    accepted_windows = 0
    raw_programmes = payload.get("programmes", []) if isinstance(payload, dict) else []
    if not isinstance(raw_programmes, list):
        raw_programmes = []

    for item in raw_programmes:
        if not isinstance(item, dict):
            rejected_programmes += 1
            continue
        document = documents_by_id.get(str(item.get("sourceDocumentId", "")))
        name = str(item.get("name", "")).strip()
        degree_type = str(item.get("degreeType") or _degree_type(name))
        if (
            document is None
            or not name
            or not (_DEGREE_RE.search(name) or _DEGREE_RE.search(degree_type))
            or _REJECT_PROGRAMME_RE.search(name)
            or _NAVIGATION_PROGRAMME_RE.search(name)
            or not _text_contains(document.content, name)
        ):
            rejected_programmes += 1
            continue

        windows = []
        excerpts = []
        raw_windows = item.get("windows") or []
        if not isinstance(raw_windows, list):
            raw_windows = []
            rejected_windows += 1
        for raw_window in raw_windows:
            if not isinstance(raw_window, dict):
                rejected_windows += 1
                continue
            window_document = documents_by_id.get(
                str(raw_window.get("sourceDocumentId", ""))
            )
            quote = str(raw_window.get("evidenceQuote", "")).strip()
            opens_at = raw_window.get("opensAt")
            closes_at = raw_window.get("closesAt")
            if not _valid_window(
                raw_window,
                window_document,
                quote,
                opens_at,
                closes_at,
                config.minimum_closes_at,
            ):
                rejected_windows += 1
                continue
            raw_categories = raw_window.get("applicantCategories", [])
            categories = (
                [
                    value
                    for value in raw_categories
                    if isinstance(value, str) and value in _ALLOWED_APPLICANT_CATEGORIES
                ]
                if isinstance(raw_categories, list)
                else []
            ) or ["all"]
            windows.append(
                DiscoveredWindow(
                    round=str(raw_window.get("round") or "Application deadline"),
                    opens_at=opens_at,
                    closes_at=closes_at,
                    applicant_categories=categories,
                    intake=str(raw_window.get("intake") or config.default_intake),
                    source_url=window_document.url,
                )
            )
            excerpts.append(quote)
            accepted_windows += 1

        evidence_quote = str(item.get("programmeEvidenceQuote", "")).strip()
        if evidence_quote and not _text_contains(document.content, evidence_quote):
            evidence_quote = ""
        evidence_quality = (
            "official-fulltext"
            if document.evidence_quality == "official-fulltext"
            else "official-search-snippet"
        )
        programme_id = f"{config.school_prefix}-{_slug(name)}"
        programmes[programme_id] = DiscoveredProgramme(
            id=programme_id,
            name=name,
            degree_type=degree_type,
            faculty=str(item.get("faculty") or ""),
            department=str(item.get("department") or ""),
            source_url=document.url,
            application_url=_official_application_url(
                str(item.get("applicationUrl") or ""), config
            ),
            windows=windows,
            deadline_text=" ".join(excerpts)[:1600]
            or evidence_quote
            or "Programme found through official-domain assisted search.",
            parse_status=(
                "parsed"
                if windows and all(window.opens_at for window in windows)
                else "incomplete"
                if windows
                else "no-deadline"
            ),
            retrieval_method=document.retrieval_method,
            evidence_quality=evidence_quality,
            evidence_document_hash=hashlib.sha256(
                document.content.encode("utf-8")
            ).hexdigest(),
        )

    return (
        DiscoveredCatalog(
            application_opens_at=None,
            programmes=sorted(programmes.values(), key=lambda value: value.id),
        ),
        {
            "modelProgrammes": len(raw_programmes),
            "acceptedProgrammes": len(programmes),
            "rejectedProgrammes": rejected_programmes,
            "acceptedWindows": accepted_windows,
            "rejectedWindows": rejected_windows,
        },
    )


def _valid_window(
    raw_window: dict,
    document: RetrievedDocument | None,
    quote: str,
    opens_at: Any,
    closes_at: Any,
    minimum_closes_at: str,
) -> bool:
    if (
        document is None
        or document.evidence_quality != "official-fulltext"
        or not quote
        or not _text_contains(document.content, quote)
        or not isinstance(closes_at, str)
        or not _is_iso_date(closes_at)
        or closes_at < minimum_closes_at
    ):
        return False
    if opens_at is not None and (
        not isinstance(opens_at, str)
        or not _is_iso_date(opens_at)
        or opens_at > closes_at
    ):
        return False
    quoted_dates = _iso_dates_in_text(quote)
    if closes_at not in quoted_dates:
        return False
    if opens_at is not None and opens_at not in quoted_dates:
        return False
    return isinstance(raw_window.get("applicantCategories", []), list)


def _iso_dates_in_text(text: str) -> set[str]:
    values = set()
    for date_format, pattern in _DATE_PATTERNS:
        for match in pattern.finditer(text):
            try:
                values.add(
                    datetime.strptime(match.group(1), date_format).date().isoformat()
                )
            except ValueError:
                continue
    return values


def _is_iso_date(value: str) -> bool:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date().isoformat() == value
    except ValueError:
        return False


def _text_contains(text: str, excerpt: str) -> bool:
    return _normalise_text(excerpt).casefold() in _normalise_text(text).casefold()


def _normalise_text(value: str) -> str:
    return " ".join(value.split())


def _official_application_url(
    value: str,
    config: AssistedDiscoveryConfig,
) -> str:
    if value and same_official_domain(value, list(config.official_domains)):
        return value
    return config.default_application_url


def _degree_type(name: str) -> str:
    match = _DEGREE_RE.search(name)
    return match.group(1) if match else "Master"


def _slug(value: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", value.lower())).strip("-")


def _strip_json_fence(value: str) -> str:
    stripped = value.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    return stripped


def _missing_credentials() -> list[str]:
    return ["DEEPSEEK_API_KEY"] if not os.environ.get("DEEPSEEK_API_KEY") else []


def _no_search_results(_query: str, _count: int) -> list[SearchResult]:
    return []


def _skipped_report(
    config: AssistedDiscoveryConfig,
    missing: list[str],
) -> dict[str, Any]:
    return {
        "status": "skipped",
        "universityId": config.university_id,
        "sourceUrl": config.seed_urls[0],
        "skipReason": "Missing assisted-discovery credentials: " + ", ".join(missing),
        "missingCredentials": missing,
        "assistedDiscovery": True,
    }


def _error_report(
    config: AssistedDiscoveryConfig,
    stage: str,
    exc: Exception,
    dry_run: bool,
) -> dict[str, Any]:
    message = str(exc)
    if isinstance(exc, httpx.HTTPStatusError):
        response_body = " ".join(exc.response.text.split())[:500]
        if response_body:
            message = f"{message}; responseBody={response_body}"
    return {
        "status": "error",
        "universityId": config.university_id,
        "sourceUrl": config.seed_urls[0],
        "assistedDiscovery": True,
        "stage": stage,
        "errorType": type(exc).__name__,
        "message": message[:900],
        "dryRun": dry_run,
    }


def _select_relevant_documents(
    documents: list[RetrievedDocument],
) -> list[RetrievedDocument]:
    return [
        document
        for document in documents
        if _RELEVANT_DOCUMENT_RE.search(f"{document.title} {document.content}")
    ]


def _document_report(documents: list[RetrievedDocument]) -> list[dict[str, str]]:
    return [
        {
            "id": document.id,
            "url": document.url,
            "retrievalMethod": document.retrieval_method,
            "evidenceQuality": document.evidence_quality,
            "contentHash": hashlib.sha256(document.content.encode("utf-8")).hexdigest(),
        }
        for document in documents
    ]
