from __future__ import annotations

from gradwindow.io import read_json
from gradwindow.paths import APPLICATIONS_PATH, PROGRAMS_PATH

MIT_ID = "massachusetts-institute-of-technology-mit"


def test_mit_exact_programme_windows_are_published() -> None:
    programs = [
        item
        for item in read_json(PROGRAMS_PATH)["programs"]
        if item["universityId"] == MIT_ID
    ]
    applications = [
        item
        for item in read_json(APPLICATIONS_PATH)["applications"]
        if item["universityId"] == MIT_ID
    ]

    assert len(programs) >= 20
    assert len(applications) >= 20
    assert any(
        item["scopeId"] == "mit-aeronautics-and-astronautics-masters"
        and item["opensAt"] == "2026-09-01"
        and item["closesAt"] == "2026-12-01"
        for item in applications
    )
    assert not any(
        item["scopeId"] == "mit-sloan-mba-program-masters" for item in applications
    )
