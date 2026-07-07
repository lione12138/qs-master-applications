from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from .discovery import same_official_domain
from .http_client import DEFAULT_USER_AGENT, fetch_page
from .io import read_json, write_json
from .paths import (
    GENERIC_PROGRAMME_DISCOVERY_CONFIG_PATH,
    GENERIC_SEED_DISCOVERY_REPORT_PATH,
    UNIVERSITIES_PATH,
)
from .programme_adapters.generic import GenericProgrammeAdapter, GenericProgrammeConfig

SEED_LINK_TERMS = re.compile(
    r"\b("
    r"a-?z|basic list|course finder|find a course|find a programme|"
    r"postgraduate taught|taught postgraduate|postgraduate courses?|"
    r"masters? courses?|master(?:'|’)?s courses?|subjects?|programmes?|programs?"
    r")\b",
    flags=re.IGNORECASE,
)
SEED_REJECT_TERMS = re.compile(
    r"\b("
    r"undergraduate|clearing|cpd|short courses?|research degrees?|phd|doctorate|"
    r"fees?|funding|scholarships?|open days?|meet us|contact|why study|"
    r"student support|teaching and learning|share via|share by"
    r")\b",
    flags=re.IGNORECASE,
)
JS_HEAVY_TERMS = (
    "does not work without javascript",
    "enable javascript",
    "course search does not work without javascript",
)
COMMON_SEED_PATHS = (
    "/study/postgraduate",
    "/study/postgraduate/taught",
    "/study/postgraduate/courses",
    "/study/postgraduate/taught/courses",
    "/study/postgraduate/subjects",
    "/study/masters",
    "/study/masters/courses",
    "/study/masters/courses/list/",
    "/study/masters/courses/list/basic/",
    "/study/courses/postgraduate-taught",
    "/postgraduate/courses/taught",
)


def run_generic_seed_discovery(
    *,
    config_path=GENERIC_PROGRAMME_DISCOVERY_CONFIG_PATH,
    report_path=GENERIC_SEED_DISCOVERY_REPORT_PATH,
    only: set[str] | None = None,
    max_candidate_seeds: int = 12,
    fetcher=None,
) -> dict[str, Any]:
    config = read_json(config_path)
    universities = {
        item["id"]: item
        for item in read_json(UNIVERSITIES_PATH).get("universities", [])
    }
    entries = [
        entry
        for entry in config.get("schools", [])
        if entry.get("enabled", True)
        and (
            only is None
            or entry.get("universityId") in only
            or entry.get("name") in only
        )
    ]
    fetcher = fetcher or _fetch_url
    results = [
        audit_generic_seed_entry(
            entry,
            universities.get(entry["universityId"], {}),
            fetcher=fetcher,
            max_candidate_seeds=max_candidate_seeds,
        )
        for entry in entries
    ]
    summary = _summary(results)
    report = {
        "meta": {
            "updatedAt": datetime.now(timezone.utc).isoformat(),
            "description": (
                "Audit configured generic programme-discovery seed pages and "
                "recommend better official catalogue entry points."
            ),
            "maxCandidateSeeds": max_candidate_seeds,
        },
        "summary": summary,
        "results": results,
    }
    write_json(report_path, report)
    return report


def audit_generic_seed_entry(
    entry: dict[str, Any],
    university: dict[str, Any],
    *,
    fetcher,
    max_candidate_seeds: int = 12,
) -> dict[str, Any]:
    university_id = entry["universityId"]
    current_seed_urls = tuple(entry.get("seedUrls", []))
    seed_sources: dict[str, str] = {
        seed_url: "configured" for seed_url in current_seed_urls
    }
    candidate_urls = list(current_seed_urls)

    configured_evaluations = [
        _evaluate_seed_url(entry, university, seed_url, fetcher, "configured")
        for seed_url in current_seed_urls
    ]
    for evaluation in configured_evaluations:
        for seed_url in evaluation.get("discoveredSeedUrls", []):
            if seed_url not in seed_sources:
                seed_sources[seed_url] = "linked-from-configured"
                candidate_urls.append(seed_url)

    for seed_url in _heuristic_seed_urls(current_seed_urls, university):
        if seed_url not in seed_sources:
            seed_sources[seed_url] = "heuristic"
            candidate_urls.append(seed_url)

    evaluated_by_url = {item["url"]: item for item in configured_evaluations}
    for seed_url in candidate_urls:
        if len(evaluated_by_url) >= max_candidate_seeds + len(current_seed_urls):
            break
        if seed_url in evaluated_by_url:
            continue
        evaluated_by_url[seed_url] = _evaluate_seed_url(
            entry,
            university,
            seed_url,
            fetcher,
            seed_sources.get(seed_url, "candidate"),
        )

    evaluations = sorted(
        evaluated_by_url.values(),
        key=lambda item: (
            item.get("source") != "configured",
            -int(item.get("programmeLinkCount", 0)),
            item["url"],
        ),
    )
    recommendation = _recommend_seed(evaluations, set(current_seed_urls), entry)
    return {
        "name": entry.get("name"),
        "universityId": university_id,
        "currentSeedUrls": list(current_seed_urls),
        "recommendation": recommendation,
        "seedEvaluations": evaluations,
    }


def _evaluate_seed_url(
    entry: dict[str, Any],
    university: dict[str, Any],
    seed_url: str,
    fetcher,
    source: str,
) -> dict[str, Any]:
    official_domains = tuple(
        entry.get("officialDomains") or university.get("officialDomains", [])
    )
    try:
        html = fetcher(seed_url)
    except Exception as exc:
        message = str(exc)
        return {
            "url": seed_url,
            "source": source,
            "status": "error",
            "classification": _error_classification(message),
            "errorType": type(exc).__name__,
            "message": message[:300],
            "programmeLinkCount": 0,
            "programmeSamples": [],
            "discoveredSeedUrls": [],
        }

    soup = BeautifulSoup(html, "html.parser")
    adapter = GenericProgrammeAdapter(
        GenericProgrammeConfig(
            university_id=entry["universityId"],
            school_prefix=entry.get("prefix") or _generic_prefix(entry["universityId"]),
            seed_urls=(seed_url,),
            official_domains=official_domains,
            default_application_url=(
                entry.get("applicationUrl")
                or university.get("admissionsUrl")
                or university.get("homepageUrl")
                or ""
            ),
            default_intake=entry.get("defaultIntake", "September 2026"),
            minimum_expected_programmes=int(entry.get("minimumExpected", 1)),
            max_detail_pages=int(entry.get("maxDetailPages", 25)),
            exclude_url_patterns=tuple(entry.get("excludeUrlPatterns", [])),
        )
    )
    programmes = adapter._candidate_links(seed_url, html)
    discovered_seed_urls = _discover_seed_links(seed_url, html, official_domains)
    text = _normalise_text(soup.get_text(" ", strip=True)).lower()
    classification = (
        "usable"
        if len(programmes) >= int(entry.get("minimumExpected", 1))
        else "js-heavy"
        if any(term in text for term in JS_HEAVY_TERMS)
        else "no-candidates"
    )
    return {
        "url": seed_url,
        "source": source,
        "status": "ok",
        "classification": classification,
        "title": _page_title(soup),
        "htmlLength": len(html),
        "programmeLinkCount": len(programmes),
        "programmeSamples": [
            {
                "id": programme.id,
                "name": programme.name,
                "sourceUrl": programme.source_url,
            }
            for programme in programmes[:8]
        ],
        "discoveredSeedUrls": discovered_seed_urls[:10],
    }


def _discover_seed_links(
    base_url: str,
    html: str,
    official_domains: tuple[str, ...],
) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    urls: list[str] = []
    for link in soup.find_all("a", href=True):
        label = _normalise_text(link.get_text(" ", strip=True))
        href = urljoin(base_url, link["href"]).split("#", 1)[0]
        candidate_text = f"{label} {href}"
        if href.startswith(("mailto:", "tel:")):
            continue
        if not same_official_domain(href, list(official_domains)):
            continue
        if SEED_REJECT_TERMS.search(candidate_text):
            continue
        if not SEED_LINK_TERMS.search(candidate_text):
            continue
        if href not in urls:
            urls.append(href)
    return urls


def _heuristic_seed_urls(
    current_seed_urls: tuple[str, ...],
    university: dict[str, Any],
) -> list[str]:
    urls: list[str] = []
    for seed_url in current_seed_urls:
        if re.search(r"/list/?$", seed_url) and not seed_url.rstrip("/").endswith(
            "/basic"
        ):
            urls.append(seed_url.rstrip("/") + "/basic/")
    homepage_url = university.get("homepageUrl") or ""
    parsed = urlparse(
        homepage_url or (current_seed_urls[0] if current_seed_urls else "")
    )
    if parsed.scheme and parsed.netloc:
        origin = f"{parsed.scheme}://{parsed.netloc}"
        urls.extend(origin + path for path in COMMON_SEED_PATHS)
    return list(dict.fromkeys(urls))


def _recommend_seed(
    evaluations: list[dict[str, Any]],
    current_seed_urls: set[str],
    entry: dict[str, Any],
) -> dict[str, Any]:
    minimum_expected = int(entry.get("minimumExpected", 1))
    usable = [
        item
        for item in evaluations
        if item.get("status") == "ok"
        and int(item.get("programmeLinkCount", 0)) >= minimum_expected
    ]
    current_usable = [item for item in usable if item["url"] in current_seed_urls]
    if current_usable:
        best = max(current_usable, key=lambda item: item["programmeLinkCount"])
        return {
            "action": "keep",
            "category": "usable",
            "seedUrl": best["url"],
            "programmeLinkCount": best["programmeLinkCount"],
            "reason": "Configured seed already exposes programme links.",
        }
    if usable:
        best = max(usable, key=lambda item: item["programmeLinkCount"])
        return {
            "action": "replaceSeed",
            "category": "usable",
            "seedUrl": best["url"],
            "programmeLinkCount": best["programmeLinkCount"],
            "reason": "Candidate seed exposes more official programme links.",
        }
    classifications = {item.get("classification") for item in evaluations}
    if classifications and classifications <= {"blockedByAccess"}:
        return {
            "action": "markBlocked",
            "category": "blockedByAccess",
            "seedUrl": None,
            "programmeLinkCount": 0,
            "reason": "All evaluated seeds are blocked by access controls.",
        }
    best = max(evaluations, key=lambda item: int(item.get("programmeLinkCount", 0)))
    return {
        "action": "manualReview",
        "category": best.get("classification", "no-candidates"),
        "seedUrl": best.get("url"),
        "programmeLinkCount": best.get("programmeLinkCount", 0),
        "reason": "No evaluated seed produced enough programme links.",
    }


def _summary(results: list[dict[str, Any]]) -> dict[str, int]:
    actions = [item["recommendation"]["action"] for item in results]
    categories = [item["recommendation"]["category"] for item in results]
    return {
        "schoolsAudited": len(results),
        "keep": actions.count("keep"),
        "replaceSeed": actions.count("replaceSeed"),
        "manualReview": actions.count("manualReview"),
        "markBlocked": actions.count("markBlocked"),
        "usable": categories.count("usable"),
        "blockedByAccess": categories.count("blockedByAccess"),
        "jsHeavy": categories.count("js-heavy"),
        "noCandidates": categories.count("no-candidates"),
    }


def _error_classification(message: str) -> str:
    lowered = message.lower()
    if "403" in lowered or "forbidden" in lowered:
        return "blockedByAccess"
    if "404" in lowered or "not found" in lowered:
        return "not-found"
    return "fetch-error"


def _fetch_url(url: str) -> str:
    return fetch_page(url, user_agent=DEFAULT_USER_AGENT, timeout=30).body


def _page_title(soup: BeautifulSoup) -> str:
    heading = soup.find("h1")
    if heading is not None:
        title = _normalise_text(heading.get_text(" ", strip=True))
        if title:
            return title
    if soup.title and soup.title.string:
        return _normalise_text(soup.title.string)
    return ""


def _normalise_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _generic_prefix(university_id: str) -> str:
    ignored = {"the", "university", "of", "and", "college", "institute"}
    parts = [part for part in university_id.split("-") if part not in ignored]
    return "-".join(parts[:3]) if parts else university_id.split("-", 1)[0]
