from __future__ import annotations

import hashlib
import re
from datetime import date

from bs4 import BeautifulSoup

NOISE_SELECTOR = ",".join(
    (
        "script",
        "style",
        "noscript",
        "svg",
        "nav",
        "header",
        "footer",
        "aside",
        "[aria-hidden='true']",
        "[class*='cookie' i]",
        "[id*='cookie' i]",
        "[class*='consent' i]",
        "[id*='consent' i]",
        "[class*='breadcrumb' i]",
        "[aria-label*='breadcrumb' i]",
    )
)
DATE_PATTERN = re.compile(
    r"\b\d{1,2}\s+(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|"
    r"may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|"
    r"nov(?:ember)?|dec(?:ember)?)\.?,?\s+20\d{2}\b|"
    r"\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|"
    r"dec(?:ember)?)\.?\s+\d{1,2},?\s+20\d{2}\b|"
    r"\b20\d{2}-\d{2}-\d{2}\b",
    flags=re.IGNORECASE,
)


def extract_main_content(raw_html: str) -> tuple[str, str]:
    soup = BeautifulSoup(raw_html, "html.parser")
    for node in soup.select(NOISE_SELECTOR):
        node.decompose()
    root = soup.find("main")
    selector = "main"
    if root is None:
        root = soup.find("article")
        selector = "article"
    if root is None:
        root = soup.find(attrs={"role": "main"})
        selector = "[role=main]"
    if root is None:
        root = soup.body
        selector = "body"
    if root is None:
        root = soup
        selector = "document"
    lines = [
        re.sub(r"\s+", " ", line).strip()
        for line in root.get_text("\n", strip=True).splitlines()
    ]
    return "\n".join(line for line in lines if line), selector


def extract_main_text(raw_html: str) -> str:
    return extract_main_content(raw_html)[0]


def content_fingerprint(raw_html: str) -> str:
    normalized = re.sub(r"\s+", " ", extract_main_text(raw_html)).strip().lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def evidence_excerpt(
    raw_html: str,
    target_dates: list[str] | None = None,
    max_chars: int = 650,
) -> str:
    lines = extract_main_text(raw_html).splitlines()
    parsed_targets = [date.fromisoformat(value) for value in target_dates or []]
    month_tokens = (
        ("january", "jan"),
        ("february", "feb"),
        ("march", "mar"),
        ("april", "apr"),
        ("may", "may"),
        ("june", "jun"),
        ("july", "jul"),
        ("august", "aug"),
        ("september", "sep", "sept"),
        ("october", "oct"),
        ("november", "nov"),
        ("december", "dec"),
    )
    scored: list[tuple[int, int, bool, bool]] = []
    for index, line in enumerate(lines):
        lowered = line.lower()
        score = 0
        target_match = False
        semantic_match = False
        normalized = re.sub(r"[^a-z0-9]+", " ", lowered)
        for target in parsed_targets:
            tokens = month_tokens[target.month - 1]
            if (
                str(target.year) in normalized
                and re.search(rf"\b0?{target.day}\b", normalized)
                and any(re.search(rf"\b{token}", normalized) for token in tokens)
            ):
                score += 20
                target_match = True
        if DATE_PATTERN.search(line):
            score += 8
        if re.search(r"\bdeadline|deadlines\b", lowered):
            score += 6
            semantic_match = True
        if re.search(r"\bclosed|closing|closes|re-open|reopen\b", lowered):
            score += 5
            semantic_match = True
        if re.search(r"\bopen|opens|opening\b", lowered):
            score += 3
            semantic_match = True
        if re.search(r"\bapplication|applications|admission|admissions\b", lowered):
            score += 1
        if score:
            scored.append((score, index, target_match, semantic_match))

    target_indexes = {
        index for _, index, target, _ in scored if target
    }
    semantic = [
        (score, index)
        for score, index, target, semantic_match in scored
        if not target and semantic_match and score >= 4
    ]
    selected_indexes = set(target_indexes)
    selected_indexes.update(
        index for _, index in sorted(semantic, reverse=True)[:3]
    )
    if not selected_indexes:
        selected_indexes.update(
            index for _, index, _, _ in sorted(scored, reverse=True)[:5]
        )

    selected: list[str] = []
    length = 0
    for index in sorted(selected_indexes):
        line = lines[index]
        addition = len(line) + (1 if selected else 0)
        if selected and length + addition > max_chars:
            break
        selected.append(line[:max_chars] if not selected else line)
        length += addition
    return "\n".join(selected)[:max_chars]


def evidence_context(
    raw_html: str,
    target_dates: list[str] | None = None,
    max_chars: int = 650,
) -> dict[str, str]:
    text, selector = extract_main_content(raw_html)
    lines = text.splitlines()
    excerpt = evidence_excerpt(raw_html, target_dates, max_chars)
    matched = excerpt.splitlines()[0] if excerpt else ""
    try:
        index = lines.index(matched)
    except ValueError:
        index = -1
    return {
        "excerpt": excerpt,
        "contentSelector": selector,
        "matchedTextBefore": lines[index - 1] if index > 0 else "",
        "matchedText": matched,
        "matchedTextAfter": (
            lines[index + 1] if 0 <= index < len(lines) - 1 else ""
        ),
    }


def deadline_signal_text(raw_html: str) -> str:
    lines = extract_main_text(raw_html).splitlines()
    selected = [
        line
        for line in lines
        if DATE_PATTERN.search(line)
        or re.search(
            r"\bdeadline|deadlines|closing|closes|opening|opens\b",
            line,
            flags=re.IGNORECASE,
        )
    ]
    return "\n".join(selected[:20])
