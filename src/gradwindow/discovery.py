from __future__ import annotations

import re
import urllib.parse

POSITIVE_PHRASES = {
    "graduate admissions": 18,
    "postgraduate admissions": 18,
    "master admissions": 16,
    "masters admissions": 16,
    "graduate application": 14,
    "postgraduate application": 14,
    "apply for graduate": 12,
    "apply postgraduate": 12,
    "admission": 4,
    "apply": 3,
}

NEGATIVE_PHRASES = {
    "undergraduate": -18,
    "executive education": -12,
    "short course": -8,
    "information session": -8,
    "info event": -8,
    "news": -5,
    "alumni": -5,
}

REJECT_PAGE_TERMS = (
    "/news/",
    "/events/",
    "financial matters",
    "information session",
    "info event",
    "occasional students",
)


def same_official_domain(url: str, official_domains: list[str]) -> bool:
    host = urllib.parse.urlparse(url).hostname or ""
    host = host.lower().removeprefix("www.")
    return any(
        host == domain.lower() or host.endswith(f".{domain.lower()}")
        for domain in official_domains
    )


def score_candidate(url: str, label: str, page_title: str = "") -> int:
    text = urllib.parse.unquote(f"{url} {label} {page_title}").lower()
    score = sum(weight for term, weight in POSITIVE_PHRASES.items() if term in text)
    score += sum(weight for term, weight in NEGATIVE_PHRASES.items() if term in text)
    has_graduate = bool(re.search(r"\bgraduate\b", text))
    has_postgraduate = bool(re.search(r"\bpostgraduate\b", text))
    has_master = bool(re.search(r"\bmasters?\b|\bmaster's\b", text))
    has_advanced_study = has_graduate or has_postgraduate or has_master
    if has_graduate:
        score += 5
    if has_postgraduate:
        score += 6
    if has_master:
        score += 4
    if "admission" in text and has_advanced_study:
        score += 12
    if "apply" in text and has_advanced_study:
        score += 8
    if re.search(r"\bundergraduate\b", text) and not (has_postgraduate or has_master):
        score -= 30
    return score


def acceptable_page(url: str, title: str) -> bool:
    identity = f"{url} {title}".lower()
    if any(term in identity for term in REJECT_PAGE_TERMS):
        return False
    if score_candidate(url, "", title) < 4:
        return False
    final_path = urllib.parse.urlparse(url).path.rstrip("/")
    if not final_path and not re.search(
        r"\bgraduate\b|\bpostgraduate\b|\bmasters?\b", title.lower()
    ):
        return False
    return True
