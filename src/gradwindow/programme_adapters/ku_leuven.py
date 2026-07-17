from __future__ import annotations

import json
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

from ..http_client import DEFAULT_USER_AGENT
from .base import BaseProgrammeAdapter, DiscoveredCatalog, DiscoveredProgramme

UNIVERSITY_ID = "ku-leuven"
CATALOG_URL = "https://www.kuleuven.be/programmes/"
HOW_TO_APPLY_URL = (
    "https://www.kuleuven.be/english/study/apply/application-instructions/"
    "apply-to-kuleuven"
)
APPLICATION_URL = HOW_TO_APPLY_URL
API_HOST = "onderwijsaanbod.kuleuven.be"
EXISTING_STATISTICS_ID = "ku-leuven-statistics-data-science-master"
EXISTING_STATISTICS_SOURCE_ID = "50550147"


class KULeuvenAdapter(BaseProgrammeAdapter):
    """Discover English-taught master's programmes from KU Leuven's guide API."""

    university_id = UNIVERSITY_ID
    catalog_url = CATALOG_URL
    application_url = APPLICATION_URL
    intake = "2026/27; varies by programme"
    application_opens_at_basis = "missing"
    replace_pending_candidates = True

    def __init__(
        self,
        minimum_expected_programmes: int = 95,
        maximum_expected_programmes: int = 110,
        minimum_catalog_year: int = 2026,
        api_payload_fetcher=None,
    ) -> None:
        self.minimum_expected_programmes = minimum_expected_programmes
        self.maximum_expected_programmes = maximum_expected_programmes
        self.minimum_catalog_year = minimum_catalog_year
        self.api_payload_fetcher = api_payload_fetcher or _fetch_api_payload

    def parse_catalog_from_fetcher(self, fetcher) -> DiscoveredCatalog:
        year, index = _catalog_config(fetcher(CATALOG_URL))
        if year < self.minimum_catalog_year:
            raise ValueError(
                f"KU Leuven's programme guide is for {year}; expected "
                f"{self.minimum_catalog_year} or later"
            )
        _verify_deadline_policy(fetcher(HOW_TO_APPLY_URL))
        programmes = _catalogue_programmes(
            self.api_payload_fetcher(year, index), catalog_year=year
        )
        if len(programmes) < self.minimum_expected_programmes:
            raise ValueError(
                "KU Leuven's official programme guide only contained "
                f"{len(programmes)} English-taught master's programmes; expected at "
                f"least {self.minimum_expected_programmes}"
            )
        if len(programmes) > self.maximum_expected_programmes:
            raise ValueError(
                "KU Leuven's official programme guide unexpectedly contained "
                f"{len(programmes)} English-taught master's programmes; expected at "
                f"most {self.maximum_expected_programmes}"
            )
        if len({programme.id for programme in programmes}) != len(programmes):
            raise ValueError("KU Leuven programme guide generated duplicate IDs")
        return DiscoveredCatalog(
            application_opens_at=None,
            programmes=sorted(programmes, key=lambda item: item.id),
        )


def _catalog_config(html: str) -> tuple[int, str]:
    component = BeautifulSoup(html, "html.parser").select_one(
        "#app home-search[esindex]"
    )
    if component is None:
        raise ValueError("KU Leuven programme guide lacked its search configuration")
    try:
        year = int(str(component.get(":year", component.get("year", ""))))
    except ValueError as exc:
        raise ValueError("KU Leuven programme guide had an invalid year") from exc
    index = _normalise(component["esindex"])
    if index != "pg":
        raise ValueError(f"KU Leuven programme guide had an invalid index: {index}")
    return year, index


def _verify_deadline_policy(html: str) -> None:
    text = _normalise(
        BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
    ).lower()
    if (
        "every programme at ku leuven has its own entry requirements, application procedure and deadlines"
        not in text
        or "application window tool" not in text
    ):
        raise ValueError(
            "KU Leuven application page lacked its programme-specific deadline policy"
        )


def _catalogue_programmes(
    value: str, *, catalog_year: int
) -> list[DiscoveredProgramme]:
    try:
        payload = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError("KU Leuven programme-guide API payload is invalid") from exc
    hits_wrapper = payload.get("hits") if isinstance(payload, dict) else None
    hits = hits_wrapper.get("hits") if isinstance(hits_wrapper, dict) else None
    total = hits_wrapper.get("total") if isinstance(hits_wrapper, dict) else None
    total_value = total.get("value") if isinstance(total, dict) else None
    if not isinstance(hits, list) or not isinstance(total_value, int):
        raise ValueError("KU Leuven programme-guide API payload lacked search hits")
    if total_value != len(hits):
        raise ValueError(
            f"KU Leuven programme-guide API returned {len(hits)} of {total_value} records"
        )
    programmes = []
    for hit in hits:
        source = hit.get("_source") if isinstance(hit, dict) else None
        if not isinstance(source, dict):
            raise ValueError("KU Leuven programme-guide API contained an invalid hit")
        identifier = _normalise(source.get("id"))
        degree = _normalise(source.get("enQualificationDegreeLevel"))
        if (
            not identifier.isdigit()
            or source.get("qualificationOriginalLangu") != "EN"
            or degree not in {"Master's", "Advanced Master's"}
        ):
            raise ValueError(
                "KU Leuven programme-guide API contained an invalid master's record"
            )
        title = _english_title(source)
        faculty = _primary_faculty(source)
        source_url = f"https://{API_HOST}/opleidingen/e/CQ_{identifier}"
        is_existing_statistics = identifier == EXISTING_STATISTICS_SOURCE_ID
        programmes.append(
            DiscoveredProgramme(
                id=(
                    EXISTING_STATISTICS_ID
                    if is_existing_statistics
                    else f"ku-leuven-master-{identifier}"
                ),
                name=(
                    "Master of Statistics and Data Science"
                    if is_existing_statistics
                    else title
                ),
                degree_type=(
                    "Advanced Master" if degree.startswith("Advanced") else "Master"
                ),
                faculty=faculty,
                department=title,
                source_url=source_url,
                application_url=APPLICATION_URL,
                windows=[],
                deadline_text=(
                    f"KU Leuven's official {catalog_year}-{catalog_year + 1} programme "
                    "guide confirms this English-taught master's programme. Its official "
                    "application instructions state that deadlines are programme-specific, "
                    "and no exact application opening date is published in the catalogue."
                ),
                parse_status="no-deadline",
                retrieval_method="official-programme-guide-search-api",
                evidence_quality="official-full-text",
            )
        )
    return programmes


def _english_title(source: dict) -> str:
    for language in source.get("qualificationLanguageSet", []):
        for title in language.get("qualificationTitleSet", []):
            if title.get("qualificationLangu") == "EN" and _normalise(
                title.get("description")
            ):
                return _normalise(title["description"])
    raise ValueError("KU Leuven master's record lacked an English title")


def _primary_faculty(source: dict) -> str:
    for programme in source.get("programSet", []):
        for organisation in programme.get("organizationSet", []):
            if (
                organisation.get("organizationType") == "8F"
                and organisation.get("alsoOfferedBy", "False") == "False"
                and _normalise(organisation.get("enOrganization"))
            ):
                return _normalise(organisation["enOrganization"])
    raise ValueError("KU Leuven master's record lacked a primary faculty")


def _fetch_api_payload(year: int, index: str) -> str:
    if index != "pg" or year < 2020 or year > 2100:
        raise ValueError("Refusing to query an invalid KU Leuven programme index")
    url = f"https://{API_HOST}/api/{index}{year}/_search"
    if not _is_official_api_url(url):
        raise ValueError(f"Refusing to query a non-official KU Leuven API: {url}")
    query = {
        "size": 200,
        "_source": [
            "id",
            "qualificationOriginalLangu",
            "enQualificationDegreeLevel",
            "qualificationLanguageSet.qualificationTitleSet",
            "programSet.organizationSet",
        ],
        "query": {
            "bool": {
                "filter": [
                    {
                        "terms": {
                            "enQualificationDegreeLevel.keyword": [
                                "Master's",
                                "Advanced Master's",
                            ]
                        }
                    },
                    {"term": {"qualificationOriginalLangu.keyword": "EN"}},
                    {
                        "term": {
                            "programSet.organizationSet.organizationId.keyword": "50000050"
                        }
                    },
                ]
            }
        },
        "sort": [{"id.keyword": "asc"}],
    }
    request = Request(
        url,
        data=json.dumps(query).encode("utf-8"),
        headers={
            "User-Agent": DEFAULT_USER_AGENT,
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest",
        },
        method="POST",
    )
    with urlopen(request, timeout=45) as response:
        raw = response.read(2_000_001)
    if len(raw) > 2_000_000:
        raise ValueError("KU Leuven programme-guide API response exceeded the limit")
    return raw.decode("utf-8")


def _is_official_api_url(value: str) -> bool:
    parsed = urlparse(value)
    return (
        parsed.scheme == "https"
        and parsed.hostname == API_HOST
        and parsed.path.startswith("/api/pg")
        and parsed.path.endswith("/_search")
    )


def _normalise(value: object) -> str:
    return " ".join(str(value or "").replace("\xa0", " ").split())
