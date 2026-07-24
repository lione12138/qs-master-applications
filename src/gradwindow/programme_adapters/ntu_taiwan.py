from __future__ import annotations

import re
from datetime import datetime
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from .base import (
    BaseProgrammeAdapter,
    DiscoveredCatalog,
    DiscoveredProgramme,
    DiscoveredWindow,
)

UNIVERSITY_ID = "national-taiwan-university-ntu"
ADMISSIONS_URL = (
    "https://admissions.ntu.edu.tw/apply/degree-students/international-students/"
)
CATALOG_URL = (
    "https://oiasystem.ntu.edu.tw/globaladmission/foreign/requirement/dept.list/"
    "id/hXwLg3Je9mtt/fsemester/1/fdisplay/1?lang=en"
)
CHINESE_CATALOG_URL = CATALOG_URL.replace("lang=en", "lang=zh")
APPLICATION_URL = "https://oiasystem.ntu.edu.tw/globaladmission/foreign"
EXISTING_CS_ID = "ntu-computer-science-information-engineering-master"
_PERIOD_RE = re.compile(
    r"(?P<intake_year>20\d{2})\s+February Entry.*?Application Period:\s*"
    r"(?P<open_month>[A-Z][a-z]+)\s+(?P<open_day>\d{1,2})\s*\([^)]*\)\s*"
    r"[–—-]\s*(?P<close_month>[A-Z][a-z]+)\s+(?P<close_day>\d{1,2}),\s*"
    r"(?P<close_year>20\d{2})",
    re.DOTALL,
)


class NTUTaiwanAdapter(BaseProgrammeAdapter):
    """Discover NTU international master's programmes and shared rounds."""

    university_id = UNIVERSITY_ID
    catalog_url = CATALOG_URL
    application_url = APPLICATION_URL
    intake = "February 2027"
    application_opens_at_basis = "official"
    replace_pending_candidates = True

    def __init__(self, minimum_expected_programmes: int = 55) -> None:
        self.minimum_expected_programmes = minimum_expected_programmes

    def parse_catalog_from_fetcher(self, fetcher) -> DiscoveredCatalog:
        window = _application_window(fetcher(ADMISSIONS_URL))
        programmes = _programmes(fetcher(CATALOG_URL), window)
        if len(programmes) < self.minimum_expected_programmes:
            raise ValueError(
                "NTU's official international directory only contained "
                f"{len(programmes)} available master's programmes; expected at "
                f"least {self.minimum_expected_programmes}"
            )
        return DiscoveredCatalog(
            application_opens_at=window.opens_at,
            programmes=programmes,
        )


def _programmes(html: str, window: DiscoveredWindow) -> list[DiscoveredProgramme]:
    soup = BeautifulSoup(html, "html.parser")
    programmes = []
    for row in soup.select("tr.js-degreeTr"):
        college_node = row.select_one(".js-college")
        name_node = row.select_one('.js-deptName[data-degree="M"]')
        link = row.select_one('td[data-degree="M"] a[href*="degree_key/M"]')
        if college_node is None or name_node is None or link is None:
            continue
        name = _normalise(name_node.get_text(" ", strip=True))
        college = _normalise(college_node.get_text(" ", strip=True))
        source_url = urljoin(CATALOG_URL, str(link.get("href", "")))
        if not _is_official(source_url):
            continue
        sn_match = re.search(r"/sn/(?P<sn>\d+)", source_url)
        if sn_match is None:
            continue
        programme_id = _programme_id(name, sn_match.group("sn"))
        programmes.append(
            DiscoveredProgramme(
                id=programme_id,
                name=f"Master's Programme in {name}",
                degree_type="Master",
                faculty=college,
                department=name,
                source_url=source_url,
                application_url=APPLICATION_URL,
                windows=[window],
                deadline_text=(
                    "NTU's official international admissions page publishes the "
                    f"{window.intake} application period from {window.opens_at} to "
                    f"{window.closes_at}."
                ),
                parse_status="parsed",
                retrieval_method="official-international-degree-directory",
                evidence_quality="official-full-text",
            )
        )
    return sorted(programmes, key=lambda programme: programme.department)


def parse_official_chinese_translations(
    english_html: str, chinese_html: str
) -> dict[str, str]:
    english_names = _master_names_by_sn(english_html)
    chinese_names = _master_names_by_sn(chinese_html)
    return {
        _programme_id(english_name, sn): chinese_names[sn]
        for sn, english_name in english_names.items()
        if sn in chinese_names
    }


def _master_names_by_sn(html: str) -> dict[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    names = {}
    for row in soup.select("tr.js-degreeTr"):
        name_node = row.select_one('.js-deptName[data-degree="M"]')
        link = row.select_one('td[data-degree="M"] a[href*="degree_key/M"]')
        if name_node is None or link is None:
            continue
        match = re.search(r"/sn/(?P<sn>\d+)", str(link.get("href", "")))
        if match:
            names[match.group("sn")] = _normalise(name_node.get_text(" ", strip=True))
    return names


def _programme_id(name: str, sn: str) -> str:
    if name == "Department of Computer Science and Information Engineering":
        return EXISTING_CS_ID
    return f"ntu-international-master-{sn}"


def _application_window(html: str) -> DiscoveredWindow:
    text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
    match = _PERIOD_RE.search(text)
    if match is None:
        raise ValueError("NTU did not publish the expected February application period")
    closes_at = datetime.strptime(
        f"{match.group('close_month')} {match.group('close_day')} "
        f"{match.group('close_year')}",
        "%B %d %Y",
    ).date()
    opens_at = datetime.strptime(
        f"{match.group('open_month')} {match.group('open_day')} {closes_at.year}",
        "%B %d %Y",
    ).date()
    if opens_at > closes_at:
        opens_at = opens_at.replace(year=opens_at.year - 1)
    return DiscoveredWindow(
        round="International application round",
        opens_at=opens_at.isoformat(),
        closes_at=closes_at.isoformat(),
        intake=f"February {match.group('intake_year')}",
        applicant_categories=["international-students"],
        source_url=ADMISSIONS_URL,
    )


def _is_official(value: str) -> bool:
    host = (urlparse(value).hostname or "").lower()
    return host == "ntu.edu.tw" or host.endswith(".ntu.edu.tw")


def _normalise(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()
