from __future__ import annotations

import concurrent.futures
import re
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import dataclass, replace
from datetime import datetime
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from ..discovery import same_official_domain
from .base import (
    BaseProgrammeAdapter,
    DiscoveredCatalog,
    DiscoveredProgramme,
    DiscoveredWindow,
)

DEGREE_RE = re.compile(
    r"\b(MSc|MS|MA|MEng|MEd|MRes|MPhil|MLitt|LLM|MBA|MPH|MPP|MPA|Master(?:'s)?(?:\s+of)?)\b",
    flags=re.IGNORECASE,
)
DATE_PATTERNS = (
    ("%B %d, %Y", re.compile(r"\b([A-Z][a-z]+\s+\d{1,2},\s+20\d{2})\b")),
    ("%d %B %Y", re.compile(r"\b(\d{1,2}\s+[A-Z][a-z]+\s+20\d{2})\b")),
    ("%d %b %Y", re.compile(r"\b(\d{1,2}\s+[A-Z][a-z]{2}\s+20\d{2})\b")),
)
APPLICATION_TERMS = re.compile(
    r"\b(application|apply|admission|deadline|closing date|due date)\b",
    flags=re.IGNORECASE,
)
APPLICATION_LINK_TERMS = re.compile(
    r"\b(how to apply|apply|application deadlines?|deadlines?)\b",
    flags=re.IGNORECASE,
)
OPEN_TERMS = re.compile(
    r"\b(open|opens|opening|available|portal)\b",
    flags=re.IGNORECASE,
)
APPLICATION_OPEN_TERMS = re.compile(
    r"\b(applications?|admissions?|application portal|portal)\b.{0,80}"
    r"\b(open|opens|opening|available)\b|"
    r"\b(open|opens|opening|available)\b.{0,80}"
    r"\b(applications?|admissions?|application portal|portal)\b",
    flags=re.IGNORECASE,
)
REJECT_TERMS = re.compile(
    r"\b(undergraduate|bachelor|phd|ph\.d|doctorate|doctoral|executive education|"
    r"short course|certificate|apprenticeship)\b",
    flags=re.IGNORECASE,
)
NAVIGATION_TERMS = re.compile(
    r"\b(contact us|fees?|funding|scholarships?|admissions?|how to apply|"
    r"student support|meet us|teaching and learning|entry requirements|"
    r"courses for entry|courses at|course search|find a course|find a programme|"
    r"master(?:'|’)?s courses|"
    r"master(?:'|’)?s programs|"
    r"taught master(?:'|’)?s(?: study)?|why manchester|"
    r"why (?:should i )?study|why study)\b",
    flags=re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class GenericProgrammeConfig:
    university_id: str
    school_prefix: str
    seed_urls: tuple[str, ...]
    official_domains: tuple[str, ...]
    default_application_url: str
    default_intake: str = "September 2026"
    default_application_opens_at: str | None = None
    default_application_closes_at: str | None = None
    default_deadline_evidence: str = ""
    application_opens_at_basis: str = "inferred-cycle-default"
    minimum_closes_at: str = "2025-07-01"
    minimum_expected_programmes: int = 1
    max_detail_pages: int = 25
    follow_application_links: bool = False
    exclude_url_patterns: tuple[str, ...] = ()
    detail_url_replacements: tuple[tuple[str, str], ...] = ()


class GenericProgrammeAdapter(BaseProgrammeAdapter):
    """Generic programme discovery for schools without a bespoke adapter.

    The adapter intentionally favours high precision over recall: it only follows
    official-domain links that look like taught master's programme pages and only
    extracts full calendar dates from application/deadline context.
    """

    def __init__(self, config: GenericProgrammeConfig) -> None:
        self.config = config
        self.university_id = config.university_id
        self.catalog_url = config.seed_urls[0]
        self.application_opens_at_basis = config.application_opens_at_basis
        self.intake = config.default_intake

    def parse_catalog_from_fetcher(self, fetcher) -> DiscoveredCatalog:
        candidates: dict[str, DiscoveredProgramme] = {}
        fetched_seed_pages = []
        for seed_url in self.config.seed_urls:
            html = fetcher(seed_url)
            fetched_seed_pages.append((seed_url, html))
            for programme in self._candidate_links(seed_url, html):
                candidates.setdefault(programme.id, programme)
        for seed_url, html in fetched_seed_pages:
            seed_programme = self._programme_from_detail_page(seed_url, html)
            if seed_programme is not None:
                candidates.setdefault(seed_programme.id, seed_programme)

        programmes = sorted(candidates.values(), key=lambda item: item.id)[
            : self.config.max_detail_pages
        ]

        def parse_one(programme: DiscoveredProgramme) -> DiscoveredProgramme | None:
            try:
                html = fetcher(programme.source_url)
                return self._parse_detail(programme, html, fetcher)
            except Exception:
                return None

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            detailed = [
                programme
                for programme in executor.map(parse_one, programmes)
                if programme is not None
            ]

        if len(detailed) < self.config.minimum_expected_programmes:
            raise ValueError(
                f"Generic crawler for {self.university_id} found {len(detailed)} "
                f"candidate programmes; expected at least "
                f"{self.config.minimum_expected_programmes}"
            )
        return DiscoveredCatalog(
            application_opens_at=self.config.default_application_opens_at,
            programmes=detailed,
        )

    def _candidate_links(
        self,
        base_url: str,
        html: str,
    ) -> list[DiscoveredProgramme]:
        programmes: dict[str, DiscoveredProgramme] = {}
        for href in _sitemap_locations(html):
            self._add_candidate(
                programmes,
                urljoin(base_url, href).split("#", 1)[0],
                "",
            )
        soup = _parse_soup(html)
        for link in soup.find_all("a", href=True):
            text = _normalise_text(link.get_text(" ", strip=True))
            href = urljoin(base_url, link["href"]).split("#", 1)[0]
            self._add_candidate(programmes, href, text)
        return list(programmes.values())

    def _add_candidate(
        self,
        programmes: dict[str, DiscoveredProgramme],
        href: str,
        text: str,
    ) -> None:
        href = self._detail_url(href)
        if self._excluded_url(href):
            return
        if not same_official_domain(href, list(self.config.official_domains)):
            return
        score = _programme_link_score(href, text)
        if score < 8:
            return
        title = _candidate_title(text, href)
        if not title:
            return
        degree_type = _degree_type(title) or "Master"
        programme_id = f"{self.config.school_prefix}-{_slug(title)}"
        programmes[programme_id] = DiscoveredProgramme(
            id=programme_id,
            name=title,
            degree_type=degree_type,
            faculty="",
            department="",
            source_url=href,
            application_url=self.config.default_application_url,
            windows=[],
            deadline_text="Programme found by generic official-site crawler.",
            parse_status="no-deadline",
        )

    def _programme_from_detail_page(
        self,
        url: str,
        html: str,
    ) -> DiscoveredProgramme | None:
        soup = _parse_soup(html)
        title = _page_title(soup)
        if self._excluded_url(url):
            return None
        if title is None or _programme_link_score(url, title) < 8:
            return None
        if not _looks_like_degree_page(url, title):
            return None
        degree_type = _degree_type(title) or "Master"
        return DiscoveredProgramme(
            id=f"{self.config.school_prefix}-{_slug(title)}",
            name=title,
            degree_type=degree_type,
            faculty="",
            department="",
            source_url=url,
            application_url=self.config.default_application_url,
            windows=[],
            deadline_text="Programme found by generic official-site crawler.",
            parse_status="no-deadline",
        )

    def _parse_detail(
        self,
        programme: DiscoveredProgramme,
        html: str,
        fetcher,
    ) -> DiscoveredProgramme:
        soup = BeautifulSoup(html, "html.parser")
        raw_title = _page_title(soup) or programme.name
        title = raw_title
        if not DEGREE_RE.search(raw_title) and DEGREE_RE.search(programme.name):
            title = programme.name
        if NAVIGATION_TERMS.search(title) or not _looks_like_degree_page(
            programme.source_url, title
        ):
            raise ValueError(f"Detail page is not a programme page: {title}")
        degree_type = _degree_type(title) or programme.degree_type
        text_parts = [_normalise_text(soup.get_text(" ", strip=True))]
        if self.config.follow_application_links:
            text_parts.extend(
                _follow_application_link_texts(
                    programme.source_url,
                    soup,
                    fetcher,
                    self.config.official_domains,
                )
            )
        text = " ".join(text_parts)
        windows, excerpt = _parse_application_windows(
            text,
            self.config.default_intake,
            self.config.minimum_closes_at,
        )
        if not windows and self.config.default_application_closes_at:
            windows = [
                DiscoveredWindow(
                    round="Application deadline",
                    closes_at=self.config.default_application_closes_at,
                    intake=self.config.default_intake,
                )
            ]
            excerpt = self.config.default_deadline_evidence
        if not excerpt:
            excerpt = _deadline_status_excerpt(text)
        has_opening_dates = bool(windows) and all(
            window.opens_at or self.config.default_application_opens_at
            for window in windows
        )
        parse_status = (
            "parsed"
            if has_opening_dates
            else "incomplete"
            if windows
            else "no-deadline"
        )
        return replace(
            programme,
            id=f"{self.config.school_prefix}-{_slug(title)}",
            name=title,
            degree_type=degree_type,
            windows=windows,
            deadline_text=excerpt or programme.deadline_text,
            parse_status=parse_status,
        )

    def _excluded_url(self, url: str) -> bool:
        return any(
            re.search(pattern, url) for pattern in self.config.exclude_url_patterns
        )

    def _detail_url(self, url: str) -> str:
        detail_url = url
        for pattern, replacement in self.config.detail_url_replacements:
            detail_url = re.sub(pattern, replacement, detail_url)
        return detail_url


def _programme_link_score(url: str, label: str) -> int:
    text = f"{url} {label}".lower()
    if re.search(r"/(people|staff|faculty|person)/", text):
        return -100
    if REJECT_TERMS.search(text):
        return -100
    if NAVIGATION_TERMS.search(label):
        return -100
    score = 0
    if DEGREE_RE.search(text):
        score += 10
    if re.search(r"\b(postgraduate|graduate|master|masters|msc|meng|llm|mba)\b", text):
        score += 8
    if re.search(r"\b(course|courses|program|programs|degree|study)\b", text):
        score += 4
    if re.search(r"/(course|courses|program|programs|degree|study|graduate)/", text):
        score += 3
    if "admission" in text or "apply" in text:
        score += 2
    return score


def _candidate_title(label: str, url: str) -> str | None:
    label = _normalise_text(label)
    if DEGREE_RE.search(label):
        return label
    path_slug = urlparse(url).path.rstrip("/").split("/")[-1]
    title = _title_from_slug(path_slug)
    if DEGREE_RE.search(title):
        return title
    if re.search(r"\bmaster\b", path_slug, flags=re.IGNORECASE):
        return title
    return None


def _title_from_slug(path_slug: str) -> str:
    path_slug = re.sub(r"\.html?$", "", path_slug)
    path_slug = re.sub(r"(?<=[a-z])0$", "", path_slug)
    replacements = {
        "ai": "AI",
        "ma": "MA",
        "mba": "MBA",
        "med": "MEd",
        "meng": "MEng",
        "mres": "MRes",
        "msc": "MSc",
        "ms": "MS",
        "phd": "PhD",
    }
    words = []
    lowercase_words = {"and", "for", "in", "of", "the", "to", "with"}
    for index, part in enumerate(re.split(r"[-_]+", path_slug)):
        if not part:
            continue
        value = replacements.get(part.lower())
        if value is None and index > 0 and part.lower() in lowercase_words:
            value = part.lower()
        words.append(value or part.capitalize())
    return " ".join(words)


def _parse_soup(markup: str) -> BeautifulSoup:
    return BeautifulSoup(markup, "html.parser")


def _sitemap_locations(markup: str) -> list[str]:
    stripped = markup.lstrip()
    if not (
        stripped.startswith("<?xml")
        or stripped.startswith("<urlset")
        or stripped.startswith("<sitemapindex")
    ):
        return []
    try:
        root = ET.fromstring(markup)
    except ET.ParseError:
        return []
    locations = []
    for element in root.iter():
        if _xml_local_name(element.tag) != "loc":
            continue
        location = _normalise_text(element.text or "")
        if location:
            locations.append(location)
    return locations


def _xml_local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _follow_application_link_texts(
    base_url: str,
    soup: BeautifulSoup,
    fetcher,
    official_domains: tuple[str, ...],
) -> list[str]:
    texts = []
    seen: set[str] = set()
    for link in soup.find_all("a", href=True):
        label = _normalise_text(link.get_text(" ", strip=True))
        href = urljoin(base_url, link["href"]).split("#", 1)[0]
        if href in seen or href == base_url:
            continue
        if not same_official_domain(href, list(official_domains)):
            continue
        if not APPLICATION_LINK_TERMS.search(f"{label} {href}"):
            continue
        seen.add(href)
        try:
            linked_html = fetcher(href)
        except Exception:
            continue
        linked_soup = BeautifulSoup(linked_html, "html.parser")
        texts.append(_normalise_text(linked_soup.get_text(" ", strip=True)))
        if len(texts) >= 3:
            break
    return texts


def _looks_like_degree_page(url: str, title: str) -> bool:
    if DEGREE_RE.search(title):
        return True
    slug = urlparse(url).path.rstrip("/").split("/")[-1]
    return bool(
        re.search(r"\b(master|masters|msc|ms|ma|meng|med|mres|mphil|llm|mba)\b", slug)
    )


def _page_title(soup: BeautifulSoup) -> str | None:
    heading = soup.find("h1")
    if heading is not None:
        title = _normalise_text(heading.get_text(" ", strip=True))
        if title:
            return title
    meta = soup.find("meta", property="og:title")
    if meta and meta.get("content"):
        return _normalise_text(str(meta["content"]).split("|", 1)[0])
    if soup.title and soup.title.string:
        return _normalise_text(soup.title.string.split("|", 1)[0])
    return None


def _parse_application_windows(
    text: str,
    default_intake: str,
    minimum_closes_at: str,
) -> tuple[list[DiscoveredWindow], str]:
    contexts = _application_contexts(text)
    windows: list[DiscoveredWindow] = []
    seen: set[tuple[str, str]] = set()
    excerpt_parts: list[str] = []
    for context in contexts:
        deadline_dates = _dates_in_context(context)
        if not deadline_dates:
            continue
        excerpt_parts.append(context)
        for date_value, source_text, label_text in deadline_dates:
            if date_value < minimum_closes_at:
                continue
            applicant_label = _applicant_round_label_from_prefix(label_text)
            round_label = (
                applicant_label
                or _round_label_near(source_text)
                or "Application deadline"
            )
            applicant_categories = _applicant_categories_for_label(applicant_label)
            key = (round_label, date_value)
            if key in seen:
                continue
            seen.add(key)
            opens_at = _opening_date_in_context(context)
            windows.append(
                DiscoveredWindow(
                    round=round_label,
                    opens_at=opens_at,
                    closes_at=date_value,
                    applicant_categories=applicant_categories,
                    intake=default_intake,
                )
            )
    return windows, " ".join(excerpt_parts)[:1600]


def _application_contexts(text: str) -> list[str]:
    contexts = []
    for match in APPLICATION_TERMS.finditer(text):
        start = max(0, match.start() - 360)
        end = min(len(text), match.end() + 900)
        context = text[start:end]
        if any(date_re.search(context) for _, date_re in DATE_PATTERNS):
            contexts.append(context)
    deduped = list(dict.fromkeys(contexts))
    return deduped[:6]


def _deadline_status_excerpt(text: str) -> str:
    patterns = (
        re.compile(
            r"\b(coming soon|to be confirmed|tba|applications? (?:will )?open soon|"
            r"applications? (?:will )?open|you can still apply|"
            r"applications? for 20\d{2}[/-]\d{2} entry)\b",
            flags=re.IGNORECASE,
        ),
        APPLICATION_TERMS,
    )
    for pattern in patterns:
        match = pattern.search(text)
        if match is not None:
            start = max(0, match.start() - 360)
            end = min(len(text), match.end() + 900)
            return text[start:end][:1600]
    return ""


def _dates_in_context(context: str) -> list[tuple[str, str, str]]:
    dates = []
    for date_format, pattern in DATE_PATTERNS:
        for match in pattern.finditer(context):
            source = match.group(1)
            before_date = context[max(0, match.start() - 180) : match.start()]
            short_prefix = before_date[-90:]
            local_nearby = context[max(0, match.start() - 70) : match.end() + 70]
            nearby = context[max(0, match.start() - 180) : match.end() + 180]
            if not APPLICATION_TERMS.search(nearby):
                continue
            if not re.search(
                r"\b(application deadlines?|deadline|closing date|due date|"
                r"applications? close|apply by|by)\b",
                nearby,
                flags=re.IGNORECASE,
            ):
                continue
            if re.search(
                r"\b(scholarships?|funding|loan|tuition fee discount|course structure|"
                r"year\s+\d+|academic year)\b",
                nearby,
                flags=re.IGNORECASE,
            ):
                continue
            if REJECT_TERMS.search(short_prefix) and not DEGREE_RE.search(short_prefix):
                continue
            if OPEN_TERMS.search(before_date) and not re.search(
                r"\b(deadline|closing|due|by|until)\b",
                before_date,
                flags=re.IGNORECASE,
            ):
                continue
            if OPEN_TERMS.search(local_nearby) and not re.search(
                r"\b(deadline|closing|due|by|until)\b",
                local_nearby,
                flags=re.IGNORECASE,
            ):
                continue
            try:
                parsed = datetime.strptime(source, date_format).date().isoformat()
            except ValueError:
                continue
            dates.append((parsed, nearby, before_date))
    return sorted(dict.fromkeys(dates))


def _opening_date_in_context(context: str) -> str | None:
    for date_format, pattern in DATE_PATTERNS:
        for match in pattern.finditer(context):
            nearby = context[max(0, match.start() - 120) : match.end() + 120]
            if re.search(
                r"\bopen\s+(day|days|event|events|evening|evenings|session|sessions)\b",
                nearby,
                flags=re.IGNORECASE,
            ):
                continue
            if APPLICATION_OPEN_TERMS.search(nearby):
                try:
                    return (
                        datetime.strptime(match.group(1), date_format)
                        .date()
                        .isoformat()
                    )
                except ValueError:
                    continue
    return None


def _round_label_near(text: str) -> str | None:
    category_label = _applicant_round_label_near(text)
    if category_label is not None:
        return category_label
    match = re.search(
        r"\b(round\s+\d+|priority\s+round|final\s+round|main\s+deadline|"
        r"early\s+deadline|regular\s+deadline)\b",
        text,
        flags=re.IGNORECASE,
    )
    if match is None:
        return None
    return _normalise_text(match.group(1)).capitalize()


def _applicant_round_label_near(text: str) -> str | None:
    date_start = len(text)
    for _, pattern in DATE_PATTERNS:
        match = pattern.search(text)
        if match is not None:
            date_start = min(date_start, match.start())
    before_date = text[:date_start]
    labels = [
        (r"\boverseas applicants?\b", "Overseas applicants"),
        (r"\binternational students?\b", "International students"),
        (r"\binternational applicants?\b", "International applicants"),
        (r"\bhome applicants?\b", "Home applicants"),
        (r"\buk students?\b", "UK students"),
    ]
    matches: list[tuple[int, str]] = []
    for pattern, label in labels:
        for match in re.finditer(pattern, before_date, flags=re.IGNORECASE):
            matches.append((match.start(), label))
    if matches:
        return sorted(matches)[-1][1]
    return None


def _applicant_round_label_from_prefix(text: str) -> str | None:
    labels = [
        (r"\boverseas applicants?\b", "Overseas applicants"),
        (r"\binternational students?\b", "International students"),
        (r"\binternational applicants?\b", "International applicants"),
        (r"\bhome applicants?\b", "Home applicants"),
        (r"\buk students?\b", "UK students"),
    ]
    matches: list[tuple[int, str]] = []
    for pattern, label in labels:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            matches.append((match.start(), label))
    if matches:
        return sorted(matches)[-1][1]
    return None


def _applicant_categories_near(text: str) -> list[str]:
    return _applicant_categories_for_label(_applicant_round_label_near(text))


def _applicant_categories_for_label(label: str | None) -> list[str]:
    if label in {
        "Overseas applicants",
        "International students",
        "International applicants",
    }:
        return ["international-students"]
    if label in {"Home applicants", "UK students"}:
        return ["domestic-students"]
    return ["all"]


def _degree_type(title: str) -> str | None:
    match = DEGREE_RE.search(title)
    if match is None:
        return None
    value = match.group(1)
    if value.lower().startswith("master"):
        return "Master"
    return value.upper() if len(value) <= 4 else value


def _slug(value: str) -> str:
    ascii_value = (
        unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    )
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", ascii_value.lower())).strip(
        "-"
    )


def _normalise_text(value: str) -> str:
    return " ".join(str(value).replace("\u00a0", " ").split())
