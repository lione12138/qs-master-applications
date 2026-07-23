from __future__ import annotations

import re
import shutil
import subprocess
import unicodedata
from collections.abc import Callable
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from ..http_client import DEFAULT_USER_AGENT, FetchFailure
from .base import BaseProgrammeAdapter, DiscoveredCatalog, DiscoveredProgramme

UNIVERSITY_ID = "institut-polytechnique-de-paris"
CATALOG_URL = "https://www.ip-paris.fr/en/education/graduate-programs/masters-science"
ADMISSIONS_URL = "https://www.ip-paris.fr/en/education/useful-information/admissions"
APPLICATION_URL = "https://candidatures.polytechnique.fr/"
EXISTING_CS_ID = "ip-paris-computer-science-master"

CatalogFallbackFetcher = Callable[[str], str]


class IPParisAdapter(BaseProgrammeAdapter):
    """Discover national master's programs from IP Paris' central catalogue."""

    university_id = UNIVERSITY_ID
    catalog_url = CATALOG_URL
    application_url = APPLICATION_URL
    intake = "September 2027"
    application_opens_at_basis = "missing"
    replace_pending_candidates = True

    def __init__(
        self,
        minimum_expected_programmes: int = 19,
        maximum_expected_programmes: int = 30,
        catalog_fallback_fetcher: CatalogFallbackFetcher | None = None,
    ) -> None:
        self.minimum_expected_programmes = minimum_expected_programmes
        self.maximum_expected_programmes = maximum_expected_programmes
        self.catalog_fallback_fetcher = catalog_fallback_fetcher or _fetch_with_curl

    def parse_catalog_from_fetcher(self, fetcher) -> DiscoveredCatalog:
        try:
            html = fetcher(CATALOG_URL)
        except FetchFailure:
            html = self.catalog_fallback_fetcher(CATALOG_URL)
        return self.parse_catalog(html)

    def parse_catalog(self, html: str) -> DiscoveredCatalog:
        programmes = sorted(_programmes(html), key=lambda item: item.id)
        if len(programmes) < self.minimum_expected_programmes:
            raise ValueError(
                "IP Paris' official catalogue only contained "
                f"{len(programmes)} master's programmes; expected at least "
                f"{self.minimum_expected_programmes}"
            )
        if len(programmes) > self.maximum_expected_programmes:
            raise ValueError(
                "IP Paris' official catalogue unexpectedly contained "
                f"{len(programmes)} master's programmes; expected at most "
                f"{self.maximum_expected_programmes}"
            )
        if len({item.id for item in programmes}) != len(programmes):
            raise ValueError("IP Paris official catalogue generated duplicate IDs")
        return DiscoveredCatalog(application_opens_at=None, programmes=programmes)


def _programmes(html: str) -> list[DiscoveredProgramme]:
    soup = BeautifulSoup(html, "html.parser")
    programmes = []
    seen_urls = set()
    for link in soup.select("h3.titre-enfant a[href]"):
        label = _normalise(link.get_text(" ", strip=True))
        if not label.endswith(" Program"):
            continue
        source_url = urljoin(CATALOG_URL, str(link.get("href", "")))
        parsed = urlparse(source_url)
        if (
            parsed.scheme != "https"
            or parsed.hostname != "www.ip-paris.fr"
            or "/education/" not in parsed.path
        ):
            raise ValueError(
                f"IP Paris catalogue contained a non-official URL: {source_url}"
            )
        if source_url in seen_urls:
            continue
        field = label.removesuffix(" Program")
        programme_id = f"ip-paris-{_slug(field)}-master"
        if field == "Computer Science":
            programme_id = EXISTING_CS_ID
        programmes.append(
            DiscoveredProgramme(
                id=programme_id,
                name=f"Master in {field}",
                degree_type="Master",
                faculty="Institut Polytechnique de Paris",
                department=field,
                source_url=source_url,
                application_url=APPLICATION_URL,
                windows=[],
                deadline_text=(
                    "IP Paris' official central catalogue confirms this national "
                    "master's program. Its admissions page currently publishes the "
                    "completed 2026/27 IP Paris and Mon Master sessions, but not an "
                    "exact opening and closing date pair for the 2027/28 intake. No "
                    "dates are carried forward or inferred."
                ),
                parse_status="no-deadline",
                retrieval_method="official-central-masters-catalogue-html",
                evidence_quality="official-full-text",
            )
        )
        seen_urls.add(source_url)
    return programmes


def _fetch_with_curl(url: str) -> str:
    executable = shutil.which("curl")
    if executable is None:
        raise ValueError("IP Paris direct access failed and curl is unavailable")
    result = subprocess.run(
        [
            executable,
            "--http1.1",
            "--fail",
            "--silent",
            "--show-error",
            "--location",
            "--max-time",
            "60",
            "--user-agent",
            DEFAULT_USER_AGENT,
            url,
        ],
        capture_output=True,
        check=False,
        timeout=75,
    )
    if result.returncode != 0:
        error = result.stderr.decode("utf-8", errors="replace").strip()
        raise ValueError(f"IP Paris catalogue curl fallback failed: {error}")
    if len(result.stdout) > 1_500_000:
        raise ValueError("IP Paris catalogue exceeded the download limit")
    html = result.stdout.decode("utf-8", errors="replace")
    if 'class="titre-enfant"' not in html:
        raise ValueError("IP Paris catalogue fallback returned an invalid page")
    return html


def _normalise(value: object) -> str:
    return " ".join(str(value or "").replace("\xa0", " ").split())


def _slug(value: object) -> str:
    ascii_value = (
        unicodedata.normalize("NFKD", _normalise(value))
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    return re.sub(r"[^a-z0-9]+", "-", ascii_value.lower()).strip("-")
