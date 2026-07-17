from __future__ import annotations

import json
from urllib.parse import parse_qs, urlparse, urlsplit, urlunsplit

from bs4 import BeautifulSoup

from ..http_client import DEFAULT_USER_AGENT, fetch_page
from .base import BaseProgrammeAdapter, DiscoveredCatalog, DiscoveredProgramme

UNIVERSITY_ID = "the-university-of-amsterdam"
CATALOG_URL = (
    "https://www.uva.nl/en/education/master-s/master-s-programmes/"
    "masters-programmes.html"
)
APPLY_URL = (
    "https://www.uva.nl/en/education/admissions/masters/"
    "applying-for-a-degree-programme.html"
)
APPLICATION_URL = APPLY_URL
EXISTING_COMPUTER_SCIENCE_ID = "uva-vu-computer-science-msc"
EXISTING_COMPUTER_SCIENCE_SOURCE_ID = "0fb7d08e-7f53-4959-b5e8-26a1c87ff755"
EXISTING_COMPUTER_SCIENCE_APPLICATION_URL = (
    "https://vu.nl/en/education/more-about/apply-for-a-masters-programme"
)

_FACULTIES = {
    "faculty-of-social-and-behavioural-sciences": (
        "Faculty of Social and Behavioural Sciences"
    ),
    "faculty-of-humanities": "Faculty of Humanities",
    "economics-and-business": "Economics and Business",
    "faculty-of-science": "Faculty of Science",
    "amsterdam-law-school": "Amsterdam Law School",
    "faculty-of-medicine": "Faculty of Medicine",
    "faculty-of-dentistry": "Faculty of Dentistry",
}


class UvAAdapter(BaseProgrammeAdapter):
    """Discover English-taught master's programmes from UvA's official list API."""

    university_id = UNIVERSITY_ID
    catalog_url = CATALOG_URL
    application_url = APPLICATION_URL
    intake = "Varies by programme"
    application_opens_at_basis = "missing"
    replace_pending_candidates = True

    def __init__(
        self,
        minimum_expected_programmes: int = 195,
        maximum_expected_programmes: int = 210,
        api_payload_fetcher=None,
    ) -> None:
        self.minimum_expected_programmes = minimum_expected_programmes
        self.maximum_expected_programmes = maximum_expected_programmes
        self.api_payload_fetcher = api_payload_fetcher or _fetch_api_payload

    def parse_catalog_from_fetcher(self, fetcher) -> DiscoveredCatalog:
        api_url = _catalogue_api_url(fetcher(CATALOG_URL))
        _verify_deadline_policy(fetcher(APPLY_URL))
        programmes = _catalogue_programmes(self.api_payload_fetcher(api_url))
        if len(programmes) < self.minimum_expected_programmes:
            raise ValueError(
                "UvA's official catalogue only contained "
                f"{len(programmes)} English-taught master's programmes; expected at "
                f"least {self.minimum_expected_programmes}"
            )
        if len(programmes) > self.maximum_expected_programmes:
            raise ValueError(
                "UvA's official catalogue unexpectedly contained "
                f"{len(programmes)} English-taught master's programmes; expected at "
                f"most {self.maximum_expected_programmes}"
            )
        if len({programme.id for programme in programmes}) != len(programmes):
            raise ValueError("UvA catalogue generated duplicate programme IDs")
        return DiscoveredCatalog(
            application_opens_at=None,
            programmes=sorted(programmes, key=lambda item: item.id),
        )


def _catalogue_api_url(html: str) -> str:
    root = BeautifulSoup(html, "html.parser").select_one("#root[data-urljson]")
    if root is None:
        raise ValueError("UvA master's page lacked its catalogue API URL")
    url = _normalise(root["data-urljson"])
    if not _is_official_api_url(url):
        raise ValueError(
            f"UvA master's page linked a non-official catalogue API: {url}"
        )
    return url


def _verify_deadline_policy(html: str) -> None:
    text = _normalise(
        BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
    ).lower()
    expected = (
        "every programme at the university of amsterdam has its own entry "
        "requirements, application procedure and deadlines"
    )
    if expected not in text:
        raise ValueError(
            "UvA application page lacked its programme-specific deadline policy"
        )


def _catalogue_programmes(value: str) -> list[DiscoveredProgramme]:
    try:
        payload = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError("UvA catalogue API payload is invalid") from exc
    items = payload.get("items") if isinstance(payload, dict) else None
    if (
        not isinstance(items, list)
        or _normalise(payload.get("title")) != "All our Master's programmes"
    ):
        raise ValueError("UvA catalogue API payload lacked master's programme items")
    programmes = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("UvA catalogue API contained an invalid item")
        languages = item.get("programmeLanguage") or []
        programme_types = item.get("programmeType") or []
        if "english" not in languages or "minor" in programme_types:
            continue
        identifier = _normalise(item.get("id"))
        title = _normalise(item.get("title"))
        source_url = _canonical_programme_url(_normalise(item.get("url")))
        faculty_keys = item.get("faculty") or []
        if not identifier or not title or len(faculty_keys) != 1:
            raise ValueError("UvA catalogue API contained an incomplete master's item")
        faculty_key = _normalise(faculty_keys[0])
        if faculty_key not in _FACULTIES:
            raise ValueError(
                f"UvA catalogue contained an unknown faculty: {faculty_key}"
            )
        is_existing_cs = identifier == EXISTING_COMPUTER_SCIENCE_SOURCE_ID
        programmes.append(
            DiscoveredProgramme(
                id=(
                    EXISTING_COMPUTER_SCIENCE_ID
                    if is_existing_cs
                    else f"uva-master-{identifier}"
                ),
                name="MSc Computer Science" if is_existing_cs else title,
                degree_type=_degree_type(item.get("studytitle") or []),
                faculty=_FACULTIES[faculty_key],
                department=title,
                source_url=source_url,
                application_url=(
                    EXISTING_COMPUTER_SCIENCE_APPLICATION_URL
                    if is_existing_cs
                    else APPLICATION_URL
                ),
                windows=[],
                deadline_text=(
                    "UvA's official master's catalogue confirms this English-taught "
                    "programme. UvA's central application guidance states that entry "
                    "requirements, procedures, and deadlines are programme-specific; "
                    "the catalogue does not publish an exact application opening date."
                ),
                parse_status="no-deadline",
                retrieval_method="official-masters-list-json-api",
                evidence_quality="official-full-text",
            )
        )
    return programmes


def _degree_type(values: list[object]) -> str:
    value = _normalise(values[0] if values else "").lower()
    return {
        "msc": "MSc",
        "ma": "MA",
        "research-ma": "MA",
        "llm": "LLM",
        "jd": "JD",
    }.get(value, "Master")


def _canonical_programme_url(value: str) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "www.uva.nl"
        or not parsed.path.startswith("/en/")
        or not parsed.path.lower().endswith(".html")
        or (
            "/programmes/" not in parsed.path.lower()
            and "master" not in parsed.path.lower()
        )
    ):
        raise ValueError(f"UvA catalogue contained an invalid programme URL: {value}")
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def _fetch_api_payload(url: str) -> str:
    if not _is_official_api_url(url):
        raise ValueError(f"Refusing to fetch a non-official UvA API: {url}")
    page = fetch_page(
        url,
        user_agent=DEFAULT_USER_AGENT,
        timeout=60,
        max_bytes=6_000_000,
        attempts=3,
        accept="application/json",
    )
    if page.truncated:
        raise ValueError("UvA catalogue API response exceeded the download limit")
    return page.body


def _is_official_api_url(value: str) -> bool:
    parsed = urlparse(value)
    query = parse_qs(parsed.query)
    return (
        parsed.scheme == "https"
        and parsed.hostname == "www.uva.nl"
        and parsed.path == "/_restapi/list-json"
        and bool(query.get("uuid"))
        and bool(query.get("mount"))
    )


def _normalise(value: object) -> str:
    return " ".join(str(value or "").replace("\xa0", " ").split())
