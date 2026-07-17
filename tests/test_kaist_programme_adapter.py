from __future__ import annotations

import json

import pytest

from gradwindow.programme_adapters.kaist import (
    NOTICE_API_URL,
    TIMELINE_URL,
    KAISTAdapter,
)

NOTICE_TABLE = """
<table>
  <tr><th>College</th><th>School/Department/Division</th><th>M.S.</th>
    <th>M.S.-Ph.D.</th><th>Ph.D.</th><th>Contact Info.</th></tr>
  <tr><td rowspan="2">Natural Science</td><td>Physics</td><td></td>
    <td>●</td><td>●</td><td>http://physics.kaist.ac.kr</td></tr>
  <tr><td>Mathematical Sciences</td><td>●</td><td>●</td><td>●</td>
    <td><a href="http://mathsci.kaist.ac.kr">Website</a></td></tr>
  <tr><td>Engineering</td><td>- The Robotics Program</td><td>●</td><td></td>
    <td>●</td><td><a href="https://rp.kaist.ac.kr/">Website</a></td></tr>
  <tr><td>Business (Seoul Campus)</td><td>Finance MBA</td><td>●</td>
    <td></td><td></td><td><a href="https://www.business.kaist.edu">Website</a></td></tr>
</table>
"""

NOTICE_TEXT = """
Online Application Period: August 18, 10:00 A.M. – September 1, 5:00 P.M. 2026 (KST)
Degrees and Programs Offered for Spring 2027 Admission
"""

NOTICE_JSON = json.dumps(
    {
        "data": [
            {
                "pstNo": 2237,
                "pstTtl": "[UPCOMING] Application Guide for Spring 2027 Admission (Aug. 18 – Sep. 1. 2026)",
                "pstCn": NOTICE_TEXT + NOTICE_TABLE,
                "pstTextCn": NOTICE_TEXT,
            }
        ]
    }
)

TIMELINE_HTML = """
<html><body><h2>Application Dates for the 2027 Entries</h2>
<p>Spring 2027 Entry: August 18 – September 1, 2026</p></body></html>
"""


def _adapter() -> KAISTAdapter:
    return KAISTAdapter(
        minimum_expected_programmes=3,
        maximum_expected_programmes=3,
        notice_fetcher=lambda url: NOTICE_JSON if url == NOTICE_API_URL else "",
    )


def test_kaist_adapter_uses_cycle_specific_ms_programmes() -> None:
    catalog = _adapter().parse_catalog_from_fetcher(
        lambda url: TIMELINE_HTML if url == TIMELINE_URL else ""
    )

    assert len(catalog.programmes) == 3
    assert len({item.id for item in catalog.programmes}) == 3
    assert not any(item.name == "Physics" for item in catalog.programmes)
    assert {item.name for item in catalog.programmes} == {
        "Mathematical Sciences",
        "The Robotics Program",
        "Finance MBA",
    }


def test_kaist_adapter_maps_official_shared_window() -> None:
    catalog = _adapter().parse_catalog_from_fetcher(
        lambda url: TIMELINE_HTML if url == TIMELINE_URL else ""
    )

    assert catalog.application_opens_at == "2026-08-18"
    assert all(len(item.windows) == 1 for item in catalog.programmes)
    assert all(item.windows[0].closes_at == "2026-09-01" for item in catalog.programmes)
    assert all(item.windows[0].intake == "Spring 2027" for item in catalog.programmes)


def test_kaist_adapter_preserves_college_and_official_programme_url() -> None:
    catalog = _adapter().parse_catalog_from_fetcher(
        lambda url: TIMELINE_HTML if url == TIMELINE_URL else ""
    )
    robotics = next(item for item in catalog.programmes if "Robotics" in item.name)

    assert robotics.faculty == "Engineering"
    assert robotics.source_url == "https://rp.kaist.ac.kr/"
    assert robotics.degree_type == "Master"
    assert (
        next(item for item in catalog.programmes if "MBA" in item.name).degree_type
        == "MBA"
    )


def test_kaist_adapter_rejects_timeline_disagreement() -> None:
    with pytest.raises(ValueError, match="timeline did not confirm"):
        _adapter().parse_catalog_from_fetcher(lambda _url: "<p>Spring 2027 TBA</p>")


def test_kaist_adapter_rejects_truncated_cycle_programme_table() -> None:
    with pytest.raises(ValueError, match="only contained 3 Spring 2027"):
        KAISTAdapter(
            minimum_expected_programmes=4,
            maximum_expected_programmes=5,
            notice_fetcher=lambda _url: NOTICE_JSON,
        ).parse_catalog_from_fetcher(lambda _url: TIMELINE_HTML)
