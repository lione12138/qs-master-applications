from __future__ import annotations

import json
from pathlib import Path

from gradwindow.assisted_discovery import AssistedCatalogAdapter
from gradwindow.programme_adapters.base import BaseProgrammeAdapter, ProgrammeAdapter
from gradwindow.programme_adapters.registry import PROGRAMME_ADAPTERS


def test_registry_is_the_complete_unique_source_of_dedicated_adapters() -> None:
    assert len(PROGRAMME_ADAPTERS) == 24
    assert set(PROGRAMME_ADAPTERS) >= {
        "birmingham",
        "bristol",
        "manchester",
        "nus",
        "southampton",
    }
    university_ids = [factory.university_id for factory in PROGRAMME_ADAPTERS.values()]
    assert len(university_ids) == len(set(university_ids))


def test_manual_discovery_workflow_delegates_adapter_validation_to_registry() -> None:
    workflow = Path(".github/workflows/discover-programmes.yml").read_text(
        encoding="utf-8"
    )
    university_input = workflow.split("university:", 1)[1].split("permissions:", 1)[0]

    assert "type: string" in university_input
    assert "options:" not in university_input


def test_every_registered_adapter_satisfies_the_discovery_contract() -> None:
    for name, factory in PROGRAMME_ADAPTERS.items():
        adapter = factory()
        assert isinstance(adapter, ProgrammeAdapter), name
        assert adapter.application_opens_at_basis in {
            "official",
            "missing",
            "inferred-cycle-default",
        }
        assert isinstance(adapter.replace_pending_candidates, bool)


def test_assisted_adapter_uses_the_same_discovery_defaults() -> None:
    assert issubclass(AssistedCatalogAdapter, BaseProgrammeAdapter)


def test_enabled_generic_overlaps_are_explicit_fallbacks() -> None:
    config_path = Path("data/ops/generic-programme-discovery.json")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    dedicated_ids = {factory().university_id for factory in PROGRAMME_ADAPTERS.values()}
    overlaps = [
        school
        for school in config["schools"]
        if school.get("enabled", True) and school["universityId"] in dedicated_ids
    ]

    assert overlaps
    assert all(school.get("discoveryRole") == "fallback" for school in overlaps)
