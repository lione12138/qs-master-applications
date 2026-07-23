from __future__ import annotations

import gzip
import json
import re
import unicodedata
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from time import sleep
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from ..http_client import DEFAULT_USER_AGENT
from .base import BaseProgrammeAdapter, DiscoveredCatalog, DiscoveredProgramme

UNIVERSITY_ID = "columbia-university"
PROVOST_CATALOG_URL = (
    "https://provost.columbia.edu/content/academic-programs-columbia-university"
)
CATALOG_URL = (
    "https://app.powerbi.com/view?"
    "r=eyJrIjoiNWU5MDIzNmEtNjc1ZC00YzBmLWFlMDktZTRiODJiOTIyZGQzIiw"
    "idCI6ImQ5OTY4ODc1LTU0OWUtNGE2ZS04OGMzLTJlMWIzYTYwNTVjYiIsImMiOjN9"
)
EXISTING_CS_ID = "columbia-computer-science-ms"

_MASTER_DEGREES = (
    "LL.M.",
    "M.A.",
    "M.Arch.",
    "M.B.A.",
    "M.F.A.",
    "M.H.A.",
    "M.I.A.",
    "M.P.A.",
    "M.P.H.",
    "M.P.S.",
    "M.S.",
)
_DEGREE_TYPES = {
    "LL.M.": "LLM",
    "M.A.": "MA",
    "M.Arch.": "MArch",
    "M.B.A.": "MBA",
    "M.F.A.": "MFA",
    "M.H.A.": "MHA",
    "M.I.A.": "MIA",
    "M.P.A.": "MPA",
    "M.P.H.": "MPH",
    "M.P.S.": "MPS",
    "M.S.": "MS",
}

ProgrammePayloadFetcher = Callable[[str], str]


@dataclass(frozen=True, slots=True)
class PowerBIDescriptor:
    resource_key: str
    api_cluster_url: str


class ColumbiaAdapter(BaseProgrammeAdapter):
    """Discover Columbia master's programmes from its Provost inventory."""

    university_id = UNIVERSITY_ID
    catalog_url = CATALOG_URL
    application_url = PROVOST_CATALOG_URL
    intake = "Varies by programme and school"
    application_opens_at_basis = "missing"
    replace_pending_candidates = True

    def __init__(
        self,
        minimum_expected_programmes: int = 250,
        maximum_expected_programmes: int = 450,
        programme_payload_fetcher: ProgrammePayloadFetcher | None = None,
    ) -> None:
        self.minimum_expected_programmes = minimum_expected_programmes
        self.maximum_expected_programmes = maximum_expected_programmes
        self.programme_payload_fetcher = (
            programme_payload_fetcher or _fetch_programme_payload
        )

    def parse_catalog_from_fetcher(self, fetcher) -> DiscoveredCatalog:
        view_html = fetcher(CATALOG_URL)
        raw_payload = self.programme_payload_fetcher(view_html)
        records = json.loads(raw_payload)
        if not isinstance(records, list):
            raise ValueError("Columbia programme inventory returned an invalid payload")
        records = _deduplicate_records(records)
        programmes = sorted(
            (_programme(record) for record in records), key=lambda item: item.id
        )
        if len(programmes) < self.minimum_expected_programmes:
            raise ValueError(
                "Columbia's official inventory only contained "
                f"{len(programmes)} master's programmes; expected at least "
                f"{self.minimum_expected_programmes}"
            )
        if len(programmes) > self.maximum_expected_programmes:
            raise ValueError(
                "Columbia's official inventory unexpectedly contained "
                f"{len(programmes)} master's programmes; expected at most "
                f"{self.maximum_expected_programmes}"
            )
        ids = [programme.id for programme in programmes]
        if len(ids) != len(set(ids)):
            raise ValueError("Columbia official inventory generated duplicate IDs")
        return DiscoveredCatalog(application_opens_at=None, programmes=programmes)


def _programme(record: object) -> DiscoveredProgramme:
    if not isinstance(record, dict):
        raise ValueError("Columbia programme inventory contained a non-object row")
    title = _normalise(record.get("title"))
    degree = _normalise(record.get("degree"))
    school = _school_name(record.get("school"))
    school_url = _normalise(record.get("schoolUrl"))
    upi = _normalise(record.get("upi"))
    nysed_code = _normalise(record.get("nysedCode"))
    if not all((title, degree, school, school_url)) or not (upi or nysed_code):
        raise ValueError("Columbia programme inventory contained an incomplete row")
    if degree not in _DEGREE_TYPES:
        raise ValueError(f"Columbia inventory returned a non-master degree: {degree}")
    identity = upi or f"nysed-{nysed_code}"
    if not re.fullmatch(r"[A-Za-z0-9.-]+", identity):
        raise ValueError(
            f"Columbia inventory returned an invalid programme identity: {identity}"
        )
    parsed_url = urlparse(school_url)
    hostname = parsed_url.hostname or ""
    if parsed_url.scheme != "https" or not (
        hostname == "columbia.edu" or hostname.endswith(".columbia.edu")
    ):
        raise ValueError(
            f"Columbia inventory returned a non-official URL: {school_url}"
        )

    degree_type = _DEGREE_TYPES[degree]
    programme_id = f"columbia-{identity}-{_slug(title)}-{degree_type.lower()}"
    if (
        title.casefold() == "computer science"
        and degree == "M.S."
        and "engineering" in school.casefold()
    ):
        programme_id = EXISTING_CS_ID

    return DiscoveredProgramme(
        id=programme_id,
        name=f"{title} ({degree})",
        degree_type=degree_type,
        faculty=school,
        department="",
        source_url=PROVOST_CATALOG_URL,
        application_url=school_url,
        windows=[],
        deadline_text=(
            "Columbia's official Provost programme inventory confirms this "
            "registered master's programme and its administering school. The "
            "inventory does not publish an exact opening and closing date pair "
            "for one intake. The school's official admissions route remains "
            "monitored and no dates are inferred."
        ),
        parse_status="no-deadline",
        retrieval_method="official-provost-powerbi-programme-inventory",
        evidence_quality="official-structured-data",
    )


def _deduplicate_records(records: list) -> list[dict]:
    unique: dict[tuple[str, str, str], dict] = {}
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("Columbia programme inventory contained a non-object row")
        identity = _normalise(record.get("upi")) or _normalise(record.get("nysedCode"))
        key = (
            identity,
            _normalise(record.get("title")).casefold(),
            _normalise(record.get("degree")),
        )
        existing = unique.get(key)
        if existing is None:
            unique[key] = dict(record)
            continue
        schools = [
            value
            for value in (
                _school_name(existing.get("school")),
                _school_name(record.get("school")),
            )
            if value
        ]
        existing["school"] = " / ".join(dict.fromkeys(schools))
    return list(unique.values())


def _fetch_programme_payload(view_html: str) -> str:
    descriptor = _powerbi_descriptor(view_html)
    headers = _powerbi_headers(descriptor.resource_key)
    models = _request_json(
        f"{descriptor.api_cluster_url}/public/reports/"
        f"{descriptor.resource_key}/modelsAndExploration?preferReadOnlySession=true",
        headers=headers,
    )
    model_rows = models.get("models", [])
    if len(model_rows) != 1 or not isinstance(model_rows[0].get("id"), int):
        raise ValueError("Columbia Power BI inventory did not expose one model")
    model_id = model_rows[0]["id"]

    schema_payload = _request_json(
        f"{descriptor.api_cluster_url}/public/reports/"
        f"{descriptor.resource_key}/conceptualschema",
        headers=_powerbi_headers(descriptor.resource_key),
    )
    programme_entity, mapping_entity = _inventory_entities(schema_payload)
    query_payload = _query_payload(
        model_id=model_id,
        programme_entity=programme_entity,
        mapping_entity=mapping_entity,
    )
    query_result = _request_json(
        f"{descriptor.api_cluster_url}/public/reports/querydata?synchronous=true",
        headers=_powerbi_headers(descriptor.resource_key, json_content=True),
        payload=query_payload,
    )
    records = _inventory_records(query_result)
    return json.dumps(records, ensure_ascii=False)


def _powerbi_descriptor(html: str) -> PowerBIDescriptor:
    descriptor_match = re.search(
        r"resourceDescriptor\s*=\s*JSON\.parse\('(?P<value>.+?)'\)",
        html,
    )
    cluster_match = re.search(
        r"resolvedClusterUri\s*=\s*'(?P<value>https://[^']+)'",
        html,
    )
    if descriptor_match is None or cluster_match is None:
        raise ValueError("Columbia Power BI view did not expose its public descriptor")
    try:
        descriptor_text = json.loads(f'"{descriptor_match.group("value")}"')
        descriptor = json.loads(descriptor_text)
    except json.JSONDecodeError as exc:
        raise ValueError("Columbia Power BI descriptor was invalid JSON") from exc
    resource_key = descriptor.get("k")
    if not isinstance(resource_key, str) or not re.fullmatch(
        r"[0-9a-fA-F-]{36}", resource_key
    ):
        raise ValueError("Columbia Power BI descriptor lacked a resource key")

    cluster = urlparse(cluster_match.group("value"))
    if cluster.scheme != "https" or not (cluster.hostname or "").endswith(
        ".analysis.windows.net"
    ):
        raise ValueError("Columbia Power BI descriptor used an unexpected cluster")
    labels = (cluster.hostname or "").split(".")
    labels[0] = labels[0].replace("-redirect", "").removeprefix("global-") + "-api"
    return PowerBIDescriptor(
        resource_key=resource_key,
        api_cluster_url=f"https://{'.'.join(labels)}",
    )


def _powerbi_headers(
    resource_key: str, *, json_content: bool = False
) -> dict[str, str]:
    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "identity",
        "ActivityId": str(uuid.uuid4()),
        "RequestId": str(uuid.uuid4()),
        "User-Agent": DEFAULT_USER_AGENT,
        "X-PowerBI-ResourceKey": resource_key,
    }
    if json_content:
        headers["Content-Type"] = "application/json"
    return headers


def _request_json(
    url: str,
    *,
    headers: dict[str, str],
    payload: dict | None = None,
) -> dict:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = Request(url, headers=headers, data=data, method="POST" if data else "GET")
    for attempt in range(3):
        try:
            with urlopen(request, timeout=90) as response:
                raw = response.read(5_000_001)
                content_encoding = response.headers.get("Content-Encoding", "")
            break
        except HTTPError:
            raise
        except (URLError, TimeoutError, ConnectionError):
            if attempt == 2:
                raise
            sleep(0.5 * (2**attempt))
    if len(raw) > 5_000_000:
        raise ValueError("Columbia Power BI response exceeded the download limit")
    if content_encoding == "gzip" or raw.startswith(b"\x1f\x8b"):
        raw = gzip.decompress(raw)
    try:
        result = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Columbia Power BI response was not valid JSON") from exc
    if not isinstance(result, dict):
        raise ValueError("Columbia Power BI response was not an object")
    return result


def _inventory_entities(schema_payload: dict) -> tuple[str, str]:
    schemas = schema_payload.get("schemas", [])
    if len(schemas) != 1:
        raise ValueError("Columbia Power BI inventory exposed an unexpected schema")
    schema = schemas[0].get("schema", {})
    if isinstance(schema, str):
        schema = json.loads(schema)
    entities = schema.get("Entities", []) if isinstance(schema, dict) else []

    programme_entity = _entity_with_properties(
        entities,
        {"Title", "Degree 1", "Administering School", "ExcludeFlag"},
    )
    mapping_entity = _entity_with_properties(
        entities,
        {"Administering School_Full Name", "URL"},
    )
    return programme_entity, mapping_entity


def _entity_with_properties(entities: object, required: set[str]) -> str:
    if not isinstance(entities, list):
        raise ValueError("Columbia Power BI schema lacked entities")
    matches = []
    for entity in entities:
        if not isinstance(entity, dict):
            continue
        properties = {
            item.get("Name")
            for item in entity.get("Properties", [])
            if isinstance(item, dict)
        }
        if required <= properties:
            matches.append(entity.get("Name"))
    if len(matches) != 1 or not isinstance(matches[0], str):
        raise ValueError(
            "Columbia Power BI schema did not identify one required entity"
        )
    return matches[0]


def _query_payload(
    *, model_id: int, programme_entity: str, mapping_entity: str
) -> dict:
    sources = [
        {"Name": "p", "Entity": programme_entity, "Type": 0},
        {"Name": "m", "Entity": mapping_entity, "Type": 0},
    ]
    columns = [
        ("m", "Administering School_Full Name"),
        ("m", "URL"),
        ("p", "Title"),
        ("p", "Degree 1"),
        ("p", "NYSED Inventory Code"),
        ("p", "Unique Program Identifier (UPI)"),
        ("p", "Single/Dual/Joint"),
    ]
    selections = [_column(source, property_name) for source, property_name in columns]
    query = {
        "Version": 2,
        "From": sources,
        "Select": selections,
        "Where": [
            _in_filter("p", "Degree 1", list(_MASTER_DEGREES)),
            _in_filter("p", "Administering School", ["", "TC"], negate=True),
            _in_filter("p", "Single/Dual/Joint", ["J"], negate=True),
            _in_filter("p", "ExcludeFlag", [0], negate=True),
        ],
    }
    command = {
        "SemanticQueryDataShapeCommand": {
            "Query": query,
            "Binding": {
                "Primary": {"Groupings": [{"Projections": list(range(7))}]},
                "DataReduction": {
                    "DataVolume": 6,
                    "Primary": {"Window": {"Count": 500}},
                },
            },
            "ExecutionMetricsKind": 1,
        }
    }
    return {
        "version": "1.0.0",
        "queries": [
            {
                "Query": {"Commands": [command]},
                "ApplicationContext": {"DatasetId": str(model_id)},
            }
        ],
        "cancelQueries": [],
        "modelId": model_id,
    }


def _column(source: str, property_name: str) -> dict:
    return {
        "Column": {
            "Expression": {"SourceRef": {"Source": source}},
            "Property": property_name,
        },
        "Name": f"{source}.{property_name}",
        "NativeReferenceName": property_name,
    }


def _in_filter(
    source: str,
    property_name: str,
    values: list[str | int],
    *,
    negate: bool = False,
) -> dict:
    expression = {
        "In": {
            "Expressions": [
                {
                    "Column": {
                        "Expression": {"SourceRef": {"Source": source}},
                        "Property": property_name,
                    }
                }
            ],
            "Values": [
                [
                    {
                        "Literal": {
                            "Value": repr(value)
                            if isinstance(value, str)
                            else f"{value}L"
                        }
                    }
                ]
                for value in values
            ],
        }
    }
    condition = {"Not": {"Expression": expression}} if negate else expression
    return {"Condition": condition}


def _inventory_records(query_result: dict) -> list[dict[str, str]]:
    try:
        data_set = query_result["results"][0]["result"]["data"]["dsr"]["DS"][0]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError("Columbia Power BI query did not return a data set") from exc
    rows = _decode_query_rows(data_set)
    if len(rows) >= 500:
        raise ValueError("Columbia Power BI programme query reached its row limit")
    records = []
    for row in rows:
        if len(row) != 7:
            raise ValueError("Columbia Power BI programme row had an invalid shape")
        records.append(
            {
                "school": _normalise(row[0]),
                "schoolUrl": _normalise(row[1]),
                "title": _normalise(row[2]),
                "degree": _normalise(row[3]),
                "nysedCode": _normalise(row[4]),
                "upi": _normalise(row[5]),
                "programmeType": _normalise(row[6]),
            }
        )
    return records


def _decode_query_rows(data_set: dict) -> list[list[object]]:
    dictionaries = data_set.get("ValueDicts", {})
    phases = data_set.get("PH", [])
    raw_rows = phases[0].get("DM0", []) if phases else []
    if not raw_rows or not raw_rows[0].get("S"):
        raise ValueError("Columbia Power BI query did not return row metadata")
    specifications = raw_rows[0]["S"]
    names = [item.get("N") for item in specifications]
    dictionary_names = [item.get("DN") for item in specifications]
    if any(not isinstance(name, str) for name in names):
        raise ValueError("Columbia Power BI row metadata was invalid")

    decoded = []
    previous = [None] * len(names)
    for raw_row in raw_rows:
        compressed = iter(raw_row.get("C", []))
        repeat_mask = raw_row.get("R", 0)
        values = []
        for index, name in enumerate(names):
            if repeat_mask & (1 << index):
                value = previous[index]
            elif name in raw_row:
                value = raw_row[name]
            else:
                value = next(compressed, None)
            dictionary_name = dictionary_names[index]
            if dictionary_name and isinstance(value, int):
                try:
                    value = dictionaries[dictionary_name][value]
                except (KeyError, IndexError, TypeError) as exc:
                    raise ValueError(
                        "Columbia Power BI dictionary reference was invalid"
                    ) from exc
            values.append(value)
        previous = values
        decoded.append(values)
    return decoded


def _normalise(value: object) -> str:
    return " ".join(str(value or "").replace("\xa0", " ").split())


def _school_name(value: object) -> str:
    return re.sub(r"^\d+\.\s*", "", _normalise(value))


def _slug(value: object) -> str:
    ascii_value = (
        unicodedata.normalize("NFKD", _normalise(value))
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    return re.sub(r"[^a-z0-9]+", "-", ascii_value.lower()).strip("-")
