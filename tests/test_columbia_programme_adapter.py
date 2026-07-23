from __future__ import annotations

import json
from urllib.error import URLError

import pytest

from gradwindow.programme_adapters import columbia
from gradwindow.programme_adapters.columbia import (
    CATALOG_URL,
    ColumbiaAdapter,
    _decode_query_rows,
    _deduplicate_records,
    _powerbi_descriptor,
    _request_json,
)

PROGRAMME_ROWS = [
    {
        "school": "Graduate School of Arts and Sciences",
        "schoolUrl": "https://www.gsas.columbia.edu/content/prospective-students",
        "title": "Biotechnology",
        "degree": "M.A.",
        "nysedCode": "23017",
        "upi": "493",
        "programmeType": "S",
    },
    {
        "school": "The Fu Foundation School of Engineering and Applied Science",
        "schoolUrl": "https://www.engineering.columbia.edu/academics/programs/masters-programs",
        "title": "Computer Science",
        "degree": "M.S.",
        "nysedCode": "22927",
        "upi": "619",
        "programmeType": "S",
    },
    {
        "school": "School of International and Public Affairs",
        "schoolUrl": "https://www.sipa.columbia.edu/sipa-education/masters-programs",
        "title": "Public Administration",
        "degree": "M.P.A.",
        "nysedCode": "21089",
        "upi": "901",
        "programmeType": "S",
    },
]

VIEW_HTML = r"""
<script>
var clusterAssignmentRecord = {"FixedClusterUri":"https://wabi-us-north-central-b-redirect.analysis.windows.net/"};
var resolvedClusterUri = 'https://wabi-us-north-central-b-redirect.analysis.windows.net/';
var resourceDescriptor = JSON.parse('{\"k\":\"5e90236a-675d-4c0f-ae09-e4b82b922dd3\",\"t\":\"d9968875-549e-4a6e-88c3-2e1b3a6055cb\"}');
</script>
"""


def _fetcher(url: str) -> str:
    assert url == CATALOG_URL
    return VIEW_HTML


def _adapter(*, minimum_expected_programmes: int = 3) -> ColumbiaAdapter:
    return ColumbiaAdapter(
        minimum_expected_programmes=minimum_expected_programmes,
        programme_payload_fetcher=lambda _html: json.dumps(PROGRAMME_ROWS),
    )


def test_columbia_adapter_discovers_registered_masters_programmes() -> None:
    catalog = _adapter().parse_catalog_from_fetcher(_fetcher)

    assert len(catalog.programmes) == 3
    assert {programme.degree_type for programme in catalog.programmes} == {
        "MA",
        "MPA",
        "MS",
    }
    assert len({programme.id for programme in catalog.programmes}) == 3


def test_columbia_adapter_preserves_existing_computer_science_identity() -> None:
    catalog = _adapter().parse_catalog_from_fetcher(_fetcher)
    programme = next(item for item in catalog.programmes if item.degree_type == "MS")

    assert programme.id == "columbia-computer-science-ms"
    assert programme.name == "Computer Science (M.S.)"
    assert programme.faculty.startswith("The Fu Foundation")


def test_columbia_adapter_keeps_catalogue_only_programmes_in_monitoring() -> None:
    catalog = _adapter().parse_catalog_from_fetcher(_fetcher)

    assert all(programme.windows == [] for programme in catalog.programmes)
    assert all(
        programme.parse_status == "no-deadline" for programme in catalog.programmes
    )
    assert all(
        "does not publish an exact opening and closing date pair"
        in programme.deadline_text
        for programme in catalog.programmes
    )


def test_columbia_adapter_rejects_a_truncated_inventory() -> None:
    with pytest.raises(ValueError, match="only contained 3 master's programmes"):
        _adapter(minimum_expected_programmes=4).parse_catalog_from_fetcher(_fetcher)


def test_columbia_powerbi_descriptor_uses_the_public_api_cluster() -> None:
    descriptor = _powerbi_descriptor(VIEW_HTML)

    assert descriptor.resource_key == "5e90236a-675d-4c0f-ae09-e4b82b922dd3"
    assert descriptor.api_cluster_url == (
        "https://wabi-us-north-central-b-api.analysis.windows.net"
    )


def test_columbia_powerbi_request_retries_transient_connection_failures(
    monkeypatch,
) -> None:
    class Response:
        headers = {}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _limit):
            return b'{"models": []}'

    attempts = iter([URLError("tls eof"), URLError("tls eof"), Response()])
    calls = []
    sleeps = []

    def fake_urlopen(*_args, **_kwargs):
        calls.append(1)
        result = next(attempts)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(columbia, "urlopen", fake_urlopen)
    monkeypatch.setattr(columbia, "sleep", sleeps.append, raising=False)

    assert _request_json("https://example.edu/query", headers={}) == {"models": []}
    assert len(calls) == 3
    assert sleeps == [0.5, 1.0]


def test_columbia_adapter_merges_one_dual_programme_listed_by_two_schools() -> None:
    rows = [
        {
            **PROGRAMME_ROWS[0],
            "title": "Dual Degree in Bioethics and Social Work",
            "upi": "341",
        },
        {
            **PROGRAMME_ROWS[0],
            "title": "Dual Degree in Bioethics and Social Work",
            "upi": "341",
            "school": "School of Social Work",
            "schoolUrl": "https://socialwork.columbia.edu/degrees-we-offer",
        },
    ]

    merged = _deduplicate_records(rows)

    assert len(merged) == 1
    assert merged[0]["school"] == (
        "Graduate School of Arts and Sciences / School of Social Work"
    )


def test_columbia_powerbi_decoder_expands_repeated_dictionary_values() -> None:
    data_set = {
        "ValueDicts": {
            "D0": ["Graduate School of Arts and Sciences"],
            "D1": ["Biotechnology", "Statistics"],
        },
        "PH": [
            {
                "DM0": [
                    {
                        "S": [
                            {"N": "G0", "DN": "D0"},
                            {"N": "G1", "DN": "D1"},
                        ],
                        "C": [0, 0],
                    },
                    {"C": [1], "R": 1},
                ]
            }
        ],
    }

    assert _decode_query_rows(data_set) == [
        ["Graduate School of Arts and Sciences", "Biotechnology"],
        ["Graduate School of Arts and Sciences", "Statistics"],
    ]
