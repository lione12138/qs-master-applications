from __future__ import annotations

import concurrent.futures
import re
from collections.abc import Callable
from urllib.parse import urlsplit
from xml.etree import ElementTree

from bs4 import BeautifulSoup

from .base import BaseProgrammeAdapter, DiscoveredCatalog, DiscoveredProgramme

UNIVERSITY_ID = "the-university-of-new-south-wales"
CATALOG_URL = "https://www.unsw.edu.au/study.sitemap.xml"
APPLICATION_DATES_URL = (
    "https://www.unsw.edu.au/study/how-to-apply/application-deadline-dates"
)
EXISTING_INFORMATION_TECHNOLOGY_ID = "unsw-information-technology-master"

_COURSE_PATH_RE = re.compile(
    r"^/study/postgraduate/(?P<slug>"
    r"(?:master(?:-|$)|agsm-(?:mba|mbax|master)-)[^/]+)$",
    flags=re.IGNORECASE,
)
_MASTER_TITLE_RE = re.compile(r"\b(?:Master|MBA|MBAX)\b", flags=re.IGNORECASE)


class UNSWAdapter(BaseProgrammeAdapter):
    """Discover current UNSW postgraduate master's degree pages."""

    university_id = UNIVERSITY_ID
    catalog_url = CATALOG_URL
    application_url = APPLICATION_DATES_URL
    intake = "Varies by programme"
    application_opens_at_basis = "missing"
    replace_pending_candidates = True

    def __init__(
        self,
        minimum_expected_programmes: int = 115,
        *,
        detail_workers: int = 10,
    ) -> None:
        self.minimum_expected_programmes = minimum_expected_programmes
        self.detail_workers = detail_workers
        self.catalogue_diagnostics = "not inspected"

    def parse_catalog_from_fetcher(
        self,
        fetcher: Callable[[str], str],
    ) -> DiscoveredCatalog:
        course_urls = _course_urls(fetcher(self.catalog_url))

        def parse_one(url: str) -> tuple[str, DiscoveredProgramme] | None:
            try:
                return _programme_from_page(url, fetcher(url))
            except Exception:
                return None

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=self.detail_workers
        ) as executor:
            parsed = list(executor.map(parse_one, course_urls))

        by_code: dict[str, DiscoveredProgramme] = {}
        for item in parsed:
            if item is None:
                continue
            code, programme = item
            previous = by_code.get(code)
            if previous is None or _canonical_score(programme) < _canonical_score(
                previous
            ):
                by_code[code] = programme
        programmes = sorted(by_code.values(), key=lambda item: item.id)
        self.catalogue_diagnostics = (
            f"sitemapCandidates={len(course_urls)}, "
            f"readableMasters={sum(item is not None for item in parsed)}, "
            f"uniqueProgramCodes={len(programmes)}"
        )
        if len(programmes) < self.minimum_expected_programmes:
            raise ValueError(
                "UNSW's official study sitemap only produced "
                f"{len(programmes)} unique master's programmes; expected at "
                f"least {self.minimum_expected_programmes}. "
                f"Diagnostics: {self.catalogue_diagnostics}"
            )
        return DiscoveredCatalog(application_opens_at=None, programmes=programmes)


def _course_urls(xml: str) -> list[str]:
    root = ElementTree.fromstring(xml)
    urls: set[str] = set()
    for node in root.iter():
        if node.tag.rsplit("}", 1)[-1].lower() != "loc":
            continue
        url = str(node.text or "").strip().split("?", 1)[0].rstrip("/")
        parsed = urlsplit(url)
        if parsed.hostname == "www.unsw.edu.au" and _COURSE_PATH_RE.fullmatch(
            parsed.path
        ):
            urls.add(url)
    if not urls:
        raise ValueError("UNSW study sitemap did not contain master's degree pages")
    return sorted(urls)


def _programme_from_page(
    url: str,
    html: str,
) -> tuple[str, DiscoveredProgramme] | None:
    soup = BeautifulSoup(html, "html.parser")
    programme_code = _meta(soup, "degree-program-code")
    degree_type = _meta(soup, "degree-type")
    if not programme_code.isdigit() or degree_type != "Postgraduate":
        return None
    title = _title(soup)
    if title is None:
        return None
    slug = _COURSE_PATH_RE.fullmatch(urlsplit(url).path).group("slug")  # type: ignore[union-attr]
    programme_id = f"unsw-{programme_code}-{slug.lower()}"
    if programme_code == "8543" or slug.lower() == "master-of-information-technology":
        programme_id = EXISTING_INFORMATION_TECHNOLOGY_ID
    return programme_code, DiscoveredProgramme(
        id=programme_id,
        name=title,
        degree_type="MBA" if re.search(r"\bMBA\b", title, re.IGNORECASE) else "Master",
        faculty=_meta(soup, "degree-faculty"),
        department="",
        source_url=url,
        application_url=url,
        windows=[],
        deadline_text=(
            "The official UNSW degree page confirms this postgraduate master's "
            "programme. UNSW states that application closing dates vary by "
            "program and intake and directs applicants to the current closing "
            "dates page. No programme-specific exact opening and closing date "
            "pair is published on this degree page, so no dates are inferred."
        ),
        parse_status="no-deadline",
        retrieval_method="official-sitemap-and-degree-page",
        evidence_quality="official-full-text",
    )


def _title(soup: BeautifulSoup) -> str | None:
    candidates = []
    heading = soup.find("h1")
    if heading is not None:
        candidates.append(_normalise(heading.get_text(" ", strip=True)))
    og_title = soup.find("meta", property="og:title")
    if og_title is not None and og_title.get("content"):
        candidates.append(_normalise(str(og_title["content"])).split("|", 1)[0].strip())
    return next((value for value in candidates if _MASTER_TITLE_RE.search(value)), None)


def _meta(soup: BeautifulSoup, name: str) -> str:
    node = soup.find("meta", attrs={"name": name})
    return _normalise(str(node.get("content", ""))) if node is not None else ""


def _canonical_score(programme: DiscoveredProgramme) -> tuple[int, int, str]:
    return (
        programme.name.count("(") + programme.name.count("/") + 1,
        len(urlsplit(programme.source_url).path),
        programme.source_url,
    )


def _normalise(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\u00a0", " ")).strip()
