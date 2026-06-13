#!/usr/bin/env python3
"""Discover likely graduate admissions pages on verified university domains."""

from __future__ import annotations

import argparse
import concurrent.futures
import html.parser
import json
import re
import ssl
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys_path = str(ROOT / "src")
if sys_path not in sys.path:
    sys.path.insert(0, sys_path)

from gradwindow.discovery import (
    acceptable_page,
    same_official_domain,
    score_candidate,
)

DATA_PATH = ROOT / "data" / "universities.json"
OVERRIDES_PATH = ROOT / "data" / "admissions-overrides.json"
USER_AGENT = "Mozilla/5.0 (compatible; GradWindow/1.0; admissions research)"
TIMEOUT = 15
MAX_BYTES = 1_500_000

COMMON_PATHS = (
    "/graduate-admissions",
    "/admissions/graduate",
    "/graduate/admissions",
    "/postgraduate",
    "/postgraduate-study",
    "/study/postgraduate",
    "/study/masters",
    "/admissions/postgraduate",
    "/masters",
)

class LinkParser(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self.title = ""
        self._href: str | None = None
        self._text: list[str] = []
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "a" and attributes.get("href"):
            self._href = attributes["href"]
            self._text = []
        elif tag == "title":
            self._in_title = True

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text.append(data)
        if self._in_title:
            self.title += data

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._href is not None:
            self.links.append((self._href, " ".join(self._text)))
            self._href = None
            self._text = []
        elif tag == "title":
            self._in_title = False


def load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, payload: dict) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def normalize_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            urllib.parse.quote(urllib.parse.unquote(parsed.path), safe="/:@"),
            urllib.parse.quote(urllib.parse.unquote(parsed.query), safe="=&?/:@,+"),
            "",
        )
    )


def fetch_page(url: str) -> tuple[str, str]:
    url = normalize_url(url)
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
    )
    context = ssl.create_default_context()
    with urllib.request.urlopen(request, timeout=TIMEOUT, context=context) as response:
        content_type = response.headers.get("Content-Type", "")
        if "html" not in content_type.lower():
            return response.geturl(), ""
        charset = response.headers.get_content_charset() or "utf-8"
        return response.geturl(), response.read(MAX_BYTES).decode(charset, errors="replace")


def discover(university: dict) -> dict:
    homepage = university.get("homepageUrl")
    domains = university.get("officialDomains") or []
    if homepage and not domains:
        hostname = urllib.parse.urlparse(homepage).hostname
        if hostname:
            domains = [hostname.lower().removeprefix("www.")]
            university["officialDomains"] = domains
    if not homepage or not domains:
        return {"status": "no-official-domain"}

    candidates: dict[str, dict] = {}
    try:
        final_homepage, homepage_html = fetch_page(homepage)
        parser = LinkParser()
        parser.feed(homepage_html)
        for href, label in parser.links:
            absolute = urllib.parse.urljoin(final_homepage, href).split("#", 1)[0]
            if not absolute.startswith(("http://", "https://")):
                continue
            if not same_official_domain(absolute, domains):
                continue
            score = score_candidate(absolute, label)
            if score >= 8:
                current = candidates.get(absolute)
                if current is None or score > current["score"]:
                    candidates[absolute] = {"url": absolute, "label": label.strip(), "score": score}
    except OSError:
        pass

    parsed_homepage = urllib.parse.urlparse(homepage)
    base = f"{parsed_homepage.scheme or 'https'}://{parsed_homepage.netloc}"
    for path in COMMON_PATHS:
        url = urllib.parse.urljoin(base, path)
        candidates.setdefault(url, {"url": url, "label": "", "score": score_candidate(url, "")})

    ranked = sorted(candidates.values(), key=lambda item: item["score"], reverse=True)[:12]
    checked = []
    for candidate in ranked:
        try:
            final_url, body = fetch_page(candidate["url"])
            if not body or not same_official_domain(final_url, domains):
                continue
            parser = LinkParser()
            parser.feed(body)
            score = score_candidate(final_url, candidate["label"], parser.title)
            if not acceptable_page(final_url, parser.title):
                continue
            checked.append(
                {
                    "url": final_url,
                    "title": re.sub(r"\s+", " ", parser.title).strip(),
                    "score": score,
                }
            )
        except (OSError, ValueError):
            continue

    if not checked:
        return {"status": "not-found"}
    best = max(checked, key=lambda item: item["score"])
    if best["score"] < 12:
        return {"status": "low-confidence", "candidate": best}
    return {
        "status": "discovered",
        "url": best["url"],
        "title": best["title"],
        "score": best["score"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--apply-overrides-only", action="store_true")
    args = parser.parse_args()

    payload = load_json(DATA_PATH)
    overrides = load_json(OVERRIDES_PATH) if OVERRIDES_PATH.exists() else {}
    universities = payload["universities"]
    targets = [
        item
        for item in universities
        if args.refresh
        or item.get("admissionsDiscovery")
        in {"pending", "not-found", "low-confidence", "no-official-domain"}
    ]
    if args.limit:
        targets = targets[: args.limit]

    if not args.apply_overrides_only:
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
            future_map = {executor.submit(discover, item): item for item in targets}
            completed = 0
            for future in concurrent.futures.as_completed(future_map):
                university = future_map[future]
                try:
                    result = future.result()
                except Exception as exc:  # One unusual site must not abort the batch.
                    result = {"status": "error", "message": str(exc)}
                university["admissionsDiscovery"] = result["status"]
                university["admissionsCandidateScore"] = result.get("score") or result.get(
                    "candidate", {}
                ).get("score")
                university["admissionsCandidateTitle"] = result.get("title") or result.get(
                    "candidate", {}
                ).get("title")
                if result.get("url"):
                    university["admissionsUrl"] = result["url"]
                    university["monitorEnabled"] = True
                elif result.get("candidate"):
                    university["admissionsUrl"] = result["candidate"]["url"]
                    university["monitorEnabled"] = False
                else:
                    university["admissionsUrl"] = None
                    university["monitorEnabled"] = False
                completed += 1
                print(
                    f"[{completed}/{len(targets)}] {university['school']}: "
                    f"{university['admissionsDiscovery']}"
                )
                if completed % 10 == 0:
                    write_json(DATA_PATH, payload)

    for university in universities:
        if university["id"] not in overrides:
            continue
        override_url = overrides[university["id"]]
        university["admissionsUrl"] = override_url
        university["admissionsDiscovery"] = "curated" if override_url else "not-found"
        university["admissionsCandidateScore"] = None
        university["admissionsCandidateTitle"] = None
        university["monitorEnabled"] = bool(override_url)

    write_json(DATA_PATH, payload)
    discovered = sum(bool(item.get("admissionsUrl")) for item in universities)
    print(f"Admissions candidates available for {discovered}/{len(universities)} institutions.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
