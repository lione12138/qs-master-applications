from __future__ import annotations

import re
from datetime import date, datetime
from urllib.parse import parse_qs, urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup

from .base import (
    BaseProgrammeAdapter,
    DiscoveredCatalog,
    DiscoveredProgramme,
    DiscoveredWindow,
)

UNIVERSITY_ID = "king-fahd-university-of-petroleum-and-minerals"
CATALOG_URL = "https://www.kfupm.edu.sa/study/graduate-programs-ms"
THESIS_CATALOG_URL = "https://www.kfupm.edu.sa/study/master-of-science-thesis-based-phd"
OPERATIONAL_URL = "https://ms.kfupm.edu.sa/"
INTERNATIONAL_APPLY_URL = (
    "https://www.kfupm.edu.sa/study/international-students/"
    "apply-as-an-international-student"
)
EXISTING_DATA_SCIENCE_ID = "kfupm-data-science-analytics-ms"
EXISTING_DATA_SCIENCE_APPLICATION_URL = "https://www.kfupm.edu.sa/study/apply"

_PERIOD_HEADING = "Application Period for Fall 2026 (Third Cycle)"
_PERIOD_RE = re.compile(
    r"(?P<opens>\d{1,2}\s+[A-Za-z]+\s+2026)\s+Opening Online Application\s+"
    r"(?P<closes>\d{1,2}\s+[A-Za-z]+\s+2026)\s+Last Day for submitting "
    r"Online Application",
    re.I,
)


class KFUPMAdapter(BaseProgrammeAdapter):
    """Discover KFUPM project- and thesis-based master's programmes."""

    university_id = UNIVERSITY_ID
    catalog_url = CATALOG_URL
    intake = "Fall 2026"
    application_opens_at_basis = "official"
    replace_pending_candidates = True

    def __init__(
        self,
        minimum_project_programmes: int = 46,
        maximum_project_programmes: int = 52,
        minimum_thesis_programmes: int = 29,
        maximum_thesis_programmes: int = 35,
        minimum_open_programmes: int = 10,
    ) -> None:
        self.minimum_project_programmes = minimum_project_programmes
        self.maximum_project_programmes = maximum_project_programmes
        self.minimum_thesis_programmes = minimum_thesis_programmes
        self.maximum_thesis_programmes = maximum_thesis_programmes
        self.minimum_open_programmes = minimum_open_programmes

    def parse_catalog_from_fetcher(self, fetcher) -> DiscoveredCatalog:
        opens_at, closes_at, open_programmes = _operational_cycle(
            fetcher(OPERATIONAL_URL),
            minimum_open_programmes=self.minimum_open_programmes,
        )
        projects = _project_programmes(
            fetcher(CATALOG_URL),
            open_programmes=open_programmes,
            opens_at=opens_at,
            closes_at=closes_at,
        )
        theses = _thesis_programmes(fetcher(THESIS_CATALOG_URL))
        _check_count(
            "project-based",
            len(projects),
            self.minimum_project_programmes,
            self.maximum_project_programmes,
        )
        _check_count(
            "thesis-based",
            len(theses),
            self.minimum_thesis_programmes,
            self.maximum_thesis_programmes,
        )
        programmes = projects + theses
        if len({programme.id for programme in programmes}) != len(programmes):
            raise ValueError(
                "KFUPM official catalogues generated duplicate programme IDs"
            )
        return DiscoveredCatalog(
            application_opens_at=opens_at,
            programmes=sorted(programmes, key=lambda item: item.id),
        )


def _check_count(label: str, count: int, minimum: int, maximum: int) -> None:
    if count < minimum:
        raise ValueError(
            f"KFUPM official catalogue only contained {count} {label} master's "
            f"programmes; expected at least {minimum}"
        )
    if count > maximum:
        raise ValueError(
            f"KFUPM official catalogue unexpectedly contained {count} {label} "
            f"master's programmes; expected at most {maximum}"
        )


def _operational_cycle(
    html: str, *, minimum_open_programmes: int
) -> tuple[str, str, dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    heading = next(
        (
            item
            for item in soup.select("h4")
            if _normalise(item.get_text(" ", strip=True)) == _PERIOD_HEADING
        ),
        None,
    )
    period = heading.find_next_sibling() if heading is not None else None
    match = _PERIOD_RE.search(
        _normalise(period.get_text(" ", strip=True) if period else "")
    )
    if match is None:
        raise ValueError(
            "KFUPM operational page lacked the exact Fall 2026 third-cycle window"
        )
    opens_at = _parse_date(match.group("opens"))
    closes_at = _parse_date(match.group("closes"))
    if date.fromisoformat(closes_at) <= date.fromisoformat(opens_at):
        raise ValueError(
            "KFUPM operational page published an invalid application period"
        )

    open_programmes = {}
    for item in soup.select("#programs-acc .accordion-item"):
        programme_heading = item.select_one("h2[id]")
        apply_link = next(
            (
                link
                for link in item.select("a[href]")
                if _normalise(link.get_text(" ", strip=True)).lower() == "apply now"
            ),
            None,
        )
        if programme_heading is None or apply_link is None:
            continue
        if "closed" in _normalise(programme_heading.get_text(" ", strip=True)).lower():
            continue
        programme_key = str(programme_heading["id"]).lower()
        application_url = _official_application_url(str(apply_link["href"]))
        open_programmes[programme_key] = application_url
    if len(open_programmes) < minimum_open_programmes:
        raise ValueError(
            "KFUPM operational page contained too few open Fall 2026 programmes"
        )
    return opens_at, closes_at, open_programmes


def _project_programmes(
    html: str,
    *,
    open_programmes: dict[str, str],
    opens_at: str,
    closes_at: str,
) -> list[DiscoveredProgramme]:
    soup = BeautifulSoup(html, "html.parser")
    if (
        _normalise(
            soup.select_one("h1").get_text(" ", strip=True)
            if soup.select_one("h1")
            else ""
        )
        != "Project-Based Master's Degrees"
    ):
        raise ValueError("KFUPM project catalogue lacked its official heading")
    programmes = []
    for heading in soup.select("h5"):
        link = heading.select_one("a[href]")
        if link is None:
            continue
        parsed = urlsplit(urljoin(CATALOG_URL, str(link["href"])))
        if (parsed.hostname or "").lower() != "ms.kfupm.edu.sa" or not parsed.fragment:
            continue
        name = _normalise(heading.get_text(" ", strip=True))
        key = parsed.fragment.lower()
        application_url = open_programmes.get(key)
        has_window = application_url is not None
        programme_key = _key(name)
        programme_id = (
            EXISTING_DATA_SCIENCE_ID
            if programme_key == "master-of-science-in-data-science-and-analytics"
            else f"kfupm-project-{programme_key}"
        )
        if programme_id == EXISTING_DATA_SCIENCE_ID:
            application_url = EXISTING_DATA_SCIENCE_APPLICATION_URL
        programmes.append(
            DiscoveredProgramme(
                id=programme_id,
                name=name,
                degree_type=_degree_type(name),
                faculty="KFUPM",
                department="Project-Based Master's Degrees",
                source_url=CATALOG_URL,
                application_url=application_url or OPERATIONAL_URL,
                windows=(
                    [
                        DiscoveredWindow(
                            round="Fall 2026 third cycle",
                            opens_at=opens_at,
                            closes_at=closes_at,
                            intake="Fall 2026",
                            applicant_categories=["all"],
                            source_url=OPERATIONAL_URL,
                        )
                    ]
                    if has_window
                    else []
                ),
                deadline_text=(
                    "KFUPM's official project-based catalogue lists this programme. "
                    + (
                        "Its operational programme card is not marked closed and "
                        f"links to the Fall 2026 third-cycle application, open "
                        f"{opens_at} through {closes_at}."
                        if has_window
                        else "The Fall 2026 operational page does not identify this "
                        "programme as open with a usable application action; no "
                        "application dates were assigned."
                    )
                ),
                parse_status="parsed" if has_window else "no-deadline",
                retrieval_method="official-project-catalogue-and-operational-html",
                evidence_quality="official-full-text",
            )
        )
    return programmes


def _thesis_programmes(html: str) -> list[DiscoveredProgramme]:
    soup = BeautifulSoup(html, "html.parser")
    title = soup.select_one("h1")
    if title is None or "Thesis-Based Master's Degrees" not in _normalise(
        title.get_text(" ", strip=True)
    ):
        raise ValueError("KFUPM thesis catalogue lacked its official heading")
    programmes = []
    for heading in soup.select("h5"):
        link = heading.select_one("a[href]")
        if link is None:
            continue
        name = _normalise(heading.get_text(" ", strip=True))
        if not name.startswith("Master") or name.startswith("Executive Master"):
            continue
        source_url, program_id = _official_bulletin_url(
            urljoin(THESIS_CATALOG_URL, str(link["href"]))
        )
        if source_url is None:
            continue
        programmes.append(
            DiscoveredProgramme(
                id=f"kfupm-thesis-{program_id}-{_key(name)}",
                name=name,
                degree_type=_degree_type(name),
                faculty="KFUPM",
                department="Thesis-Based Master's Degrees",
                source_url=source_url,
                application_url=INTERNATIONAL_APPLY_URL,
                windows=[],
                deadline_text=(
                    "KFUPM's official thesis-based catalogue and academic bulletin "
                    "list this master's programme. No exact thesis-programme "
                    "application opening and closing dates are published on these "
                    "sources, so it remains in monitoring."
                ),
                parse_status="no-deadline",
                retrieval_method="official-thesis-catalogue-and-bulletin-html",
                evidence_quality="official-full-text",
            )
        )
    return programmes


def _official_application_url(value: str) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or (parsed.hostname or "").lower() != "nabegh.kfupm.edu.sa"
        or re.fullmatch(r"/cycle/\d+/apply", parsed.path) is None
    ):
        raise ValueError(
            f"KFUPM operational page contained an invalid apply URL: {value}"
        )
    return urlunsplit(("https", "nabegh.kfupm.edu.sa", parsed.path, "", ""))


def _official_bulletin_url(value: str) -> tuple[str | None, str | None]:
    parsed = urlsplit(value)
    if (parsed.hostname or "").lower() != "bulletin.kfupm.edu.sa":
        return None, None
    program_ids = parse_qs(parsed.query).get("program_id", [])
    if len(program_ids) != 1 or not program_ids[0].isdigit():
        raise ValueError(f"KFUPM bulletin URL lacked a programme ID: {value}")
    canonical = urlunsplit(
        ("https", "bulletin.kfupm.edu.sa", parsed.path, parsed.query, "")
    )
    return canonical, program_ids[0]


def _degree_type(name: str) -> str:
    lowered = name.lower()
    if "business administration" in lowered:
        return "EMBA" if "executive" in lowered else "MBA"
    if "master of science" in lowered:
        return "MSc"
    if "master of engineering" in lowered:
        return "MEng"
    return "Master"


def _key(value: str) -> str:
    value = value.lower().replace("&", " and ")
    return re.sub(r"[^a-z0-9]+", "-", value).strip("-")


def _parse_date(value: str) -> str:
    for pattern in ("%d %b %Y", "%d %B %Y"):
        try:
            return datetime.strptime(value, pattern).date().isoformat()
        except ValueError:
            continue
    raise ValueError(f"KFUPM page contained an invalid date: {value}")


def _normalise(value: object) -> str:
    return " ".join(str(value or "").replace("\xa0", " ").replace("’", "'").split())
