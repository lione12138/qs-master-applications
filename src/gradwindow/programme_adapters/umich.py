from __future__ import annotations

import re
import unicodedata
from urllib.parse import urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup

from .base import BaseProgrammeAdapter, DiscoveredCatalog, DiscoveredProgramme

UNIVERSITY_ID = "university-of-michigan-ann-arbor"
CATALOG_URL = "https://rackham.umich.edu/programs-of-study/"
APPLICATION_URL = "https://rackham.umich.edu/admissions/applying/"
EXISTING_CSE_ID = "michigan-computer-science-engineering-mse"
CATALOG_FETCH_URLS = (
    CATALOG_URL,
    "https://rackham.umich.edu/?p=3775",
    "http://rackham.umich.edu/?p=3775",
    "https://rackham.umich.edu/index.php/programs-of-study/",
    "http://rackham.umich.edu/index.php/programs-of-study/",
)

_MASTER_TOKEN_RE = re.compile(
    r"(?<![A-Za-z])(?:MS/MSE|M\.S\. Online|M\.S\.|MSE|MS|AM|MA|MAT|MDes|MFA|"
    r"MLArch|MPA|MPP|MURP|Master’s)(?![A-Za-z])"
)


class UMichAdapter(BaseProgrammeAdapter):
    """Discover Ann Arbor master's programs from Rackham's official directory."""

    university_id = UNIVERSITY_ID
    catalog_url = CATALOG_URL
    application_url = APPLICATION_URL
    intake = "Latest programme-specific intake"
    application_opens_at_basis = "missing"
    replace_pending_candidates = True

    def __init__(
        self,
        minimum_expected_programmes: int = 82,
        maximum_expected_programmes: int = 92,
    ) -> None:
        self.minimum_expected_programmes = minimum_expected_programmes
        self.maximum_expected_programmes = maximum_expected_programmes

    def parse_catalog_from_fetcher(self, fetcher) -> DiscoveredCatalog:
        programmes = sorted(
            _programmes(_fetch_catalog(fetcher)), key=lambda item: item.id
        )
        if len(programmes) < self.minimum_expected_programmes:
            raise ValueError(
                "Rackham's official directory only contained "
                f"{len(programmes)} Ann Arbor master's programmes; expected at least "
                f"{self.minimum_expected_programmes}"
            )
        if len(programmes) > self.maximum_expected_programmes:
            raise ValueError(
                "Rackham's official directory unexpectedly contained "
                f"{len(programmes)} Ann Arbor master's programmes; expected at most "
                f"{self.maximum_expected_programmes}"
            )
        if len({programme.id for programme in programmes}) != len(programmes):
            raise ValueError("Rackham's official directory generated duplicate IDs")
        return DiscoveredCatalog(application_opens_at=None, programmes=programmes)


def _fetch_catalog(fetcher) -> str:
    last_error = None
    for url in CATALOG_FETCH_URLS:
        try:
            return fetcher(url)
        except Exception as exc:
            last_error = exc
    if last_error is None:
        raise RuntimeError("Rackham catalogue fetch had no configured URL")
    raise last_error


def _programmes(html: str) -> list[DiscoveredProgramme]:
    soup = BeautifulSoup(html, "html.parser")
    programmes = []
    for row in soup.select("table tr"):
        cells = [
            _normalise(cell.get_text(" ", strip=True)) for cell in row.select("td")
        ]
        if len(cells) < 7:
            continue
        name, campus, faculty, degree_types, deadline, application_code = cells[:6]
        if campus != "Ann Arbor" or "Master" not in degree_types:
            continue
        link = row.select_one("td:nth-of-type(7) a[href]")
        if link is None:
            raise ValueError(f"Rackham master's row lacked a program URL: {name}")
        source_url = _canonical_url(urljoin(CATALOG_URL, str(link["href"])))
        degree_type = _master_degree_type(application_code)
        programmes.append(
            DiscoveredProgramme(
                id=(
                    EXISTING_CSE_ID
                    if name == "Computer Science and Engineering"
                    else f"michigan-{_slug(name)}"
                ),
                name=name,
                degree_type=degree_type,
                faculty=faculty,
                department=name,
                source_url=source_url,
                application_url=APPLICATION_URL,
                windows=[],
                deadline_text=_deadline_text(deadline),
                parse_status="no-deadline",
                retrieval_method="official-rackham-programs-of-study-html",
                evidence_quality="official-full-text",
            )
        )
    return programmes


def _master_degree_type(application_code: str) -> str:
    tokens = []
    for match in _MASTER_TOKEN_RE.finditer(application_code):
        token = match.group(0).replace("M.S. Online", "MS Online").replace("M.S.", "MS")
        token = token.replace("Master’s", "Master's")
        expanded = ["MS", "MSE"] if token == "MS/MSE" else [token]
        for value in expanded:
            if value not in tokens:
                tokens.append(value)
    return " / ".join(tokens) if tokens else "Master's"


def _deadline_text(deadline: str) -> str:
    if deadline:
        return (
            "Rackham's official Ann Arbor programs-of-study table lists the "
            f"programme-specific closing guidance '{deadline}', but does not attach "
            "a cycle year or publish an exact application opening date. The yearless "
            "deadline is retained as monitoring evidence and no window is inferred."
        )
    return (
        "Rackham's official Ann Arbor programs-of-study table confirms this master's "
        "programme but publishes no exact application opening and closing date pair."
    )


def _canonical_url(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError(f"Rackham directory contained an invalid URL: {value}")
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def _normalise(value: object) -> str:
    return " ".join(str(value or "").replace("\xa0", " ").split())


def _slug(value: object) -> str:
    ascii_value = (
        unicodedata.normalize("NFKD", _normalise(value))
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    return re.sub(r"[^a-z0-9]+", "-", ascii_value.lower()).strip("-")
