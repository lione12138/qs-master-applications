from __future__ import annotations

import re
from collections.abc import Callable

from bs4 import BeautifulSoup

from .base import BaseProgrammeAdapter, DiscoveredCatalog, DiscoveredProgramme

UNIVERSITY_ID = "california-institute-of-technology-caltech"
CATALOG_URL = "https://catalog.caltech.edu/sitemap.xml"
APPLICATION_URL = "https://gradoffice.caltech.edu/admissions/applyonline"

CATALOG_PREFIX = (
    "https://catalog.caltech.edu/current/information-for-graduate-students/"
    "special-regulations-for-graduate-options/"
)
AEROSPACE_PATH = "aerospace-ae/"
ELECTRICAL_ENGINEERING_PATH = "electrical-engineering-ee/"


class CaltechAdapter(BaseProgrammeAdapter):
    university_id = UNIVERSITY_ID
    catalog_url = CATALOG_URL
    application_url = APPLICATION_URL
    intake = "Fall 2027"
    application_opens_at_basis = "missing"
    replace_pending_candidates = True

    def parse_catalog_from_fetcher(
        self,
        fetcher: Callable[[str], str],
    ) -> DiscoveredCatalog:
        urls = _option_urls(fetcher(self.catalog_url))
        aerospace_url = urls.get(AEROSPACE_PATH)
        electrical_url = urls.get(ELECTRICAL_ENGINEERING_PATH)
        if aerospace_url is None or electrical_url is None:
            raise ValueError(
                "Caltech catalogue did not contain both expected direct-entry "
                "master's option pages"
            )

        aerospace_text = _page_text(fetcher(aerospace_url))
        electrical_text = _page_text(fetcher(electrical_url))
        deadline_policy = _deadline_policy(fetcher(self.application_url))
        programmes = []
        if _is_direct_aerospace(aerospace_text):
            programmes.extend(
                (
                    _programme(
                        programme_id="caltech-aeronautics-ms",
                        name="MS Aeronautics",
                        department="Aerospace",
                        source_url=aerospace_url,
                        deadline_policy=deadline_policy,
                    ),
                    _programme(
                        programme_id="caltech-space-engineering-ms",
                        name="MS Space Engineering",
                        department="Aerospace",
                        source_url=aerospace_url,
                        deadline_policy=deadline_policy,
                    ),
                )
            )
        if _is_direct_electrical_engineering(electrical_text):
            programmes.append(
                _programme(
                    programme_id="caltech-electrical-engineering-ms",
                    name="MS Electrical Engineering",
                    department="Electrical Engineering",
                    source_url=electrical_url,
                    deadline_policy=deadline_policy,
                )
            )
        programmes.sort(key=lambda item: item.id)
        if len(programmes) != 3:
            raise ValueError(
                "Caltech catalogue only verified "
                f"{len(programmes)} direct-entry master's programmes; expected 3"
            )
        return DiscoveredCatalog(application_opens_at=None, programmes=programmes)


def _option_urls(xml: str) -> dict[str, str]:
    soup = BeautifulSoup(xml, "xml")
    urls = {}
    for node in soup.find_all("loc"):
        url = node.get_text(strip=True)
        if not url.startswith(CATALOG_PREFIX):
            continue
        path = url.removeprefix(CATALOG_PREFIX)
        if path:
            urls[path] = url
    return urls


def _page_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    main = soup.find("main") or soup
    return _normalise(main.get_text(" ", strip=True))


def _is_direct_aerospace(text: str) -> bool:
    lower = text.lower().replace("’", "'")
    return all(
        phrase in lower
        for phrase in (
            "eligible to seek admission to work toward the master's degree",
            "master's degree in aeronautics",
            "master's degree in space engineering",
        )
    )


def _is_direct_electrical_engineering(text: str) -> bool:
    lower = text.lower().replace("’", "'")
    return "applicants for the msee" in lower and "m.s.-only program" in lower


def _deadline_policy(html: str) -> str:
    text = _page_text(html)
    match = re.search(
        r"Deadlines vary by program from December 1 to December 15[.]?",
        text,
        re.I,
    )
    if match is None:
        raise ValueError(
            "Caltech application page did not contain the expected deadline policy"
        )
    return match.group(0).rstrip(".")


def _programme(
    *,
    programme_id: str,
    name: str,
    department: str,
    source_url: str,
    deadline_policy: str,
) -> DiscoveredProgramme:
    return DiscoveredProgramme(
        id=programme_id,
        name=name,
        degree_type="MS",
        faculty="Division of Engineering and Applied Science",
        department=department,
        source_url=source_url,
        application_url=APPLICATION_URL,
        windows=[],
        deadline_text=(
            "The current Caltech Catalog verifies this as a direct-entry master's "
            f"programme. The Graduate Studies Office states: {deadline_policy}. "
            "It does not currently publish a cycle year or an exact opening date, "
            "so no exact application window is inferred."
        ),
        parse_status="no-deadline",
        retrieval_method="official-page",
        evidence_quality="official-full-text",
    )


def _normalise(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()
