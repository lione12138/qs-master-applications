from __future__ import annotations

import json

from gradwindow.io import partition_json_file, read_json, write_json


def test_partitioned_list_round_trips_and_only_rewrites_changed_school(
    tmp_path,
) -> None:
    path = tmp_path / "programme-candidates.json"
    original = {
        "meta": {"description": "Candidates"},
        "items": [
            {"id": "new-programme:a", "universityId": "alpha"},
            {"id": "new-programme:b", "universityId": "beta"},
        ],
    }
    path.write_text(json.dumps(original), encoding="utf-8")

    partition_json_file(path, collection_key="items", group_key="universityId")

    manifest = json.loads(path.read_text(encoding="utf-8"))
    assert manifest["partitioning"]["collectionKey"] == "items"
    assert len(manifest["partitioning"]["files"]) == 2
    assert read_json(path) == original

    alpha_path = tmp_path / "programme-candidates/by-university/alpha.json"
    beta_path = tmp_path / "programme-candidates/by-university/beta.json"
    alpha_before = alpha_path.stat().st_mtime_ns
    beta_before = beta_path.stat().st_mtime_ns
    updated = read_json(path)
    updated["items"][0]["reviewReason"] = "Changed"

    write_json(path, updated)

    assert alpha_path.stat().st_mtime_ns > alpha_before
    assert beta_path.stat().st_mtime_ns == beta_before
    assert read_json(path) == updated


def test_partitioned_mapping_round_trips(tmp_path) -> None:
    path = tmp_path / "programme-catalog-state.json"
    original = {
        "meta": {"description": "State"},
        "universities": {
            "alpha": {"itemCount": 2},
            "beta": {"itemCount": 3},
        },
    }
    path.write_text(json.dumps(original), encoding="utf-8")

    partition_json_file(path, collection_key="universities")

    assert read_json(path) == original
    shard = json.loads(
        (tmp_path / "programme-catalog-state/by-university/alpha.json").read_text(
            encoding="utf-8"
        )
    )
    assert shard == {"universities": {"alpha": {"itemCount": 2}}}


def test_partition_manifest_rejects_paths_outside_its_directory(tmp_path) -> None:
    path = tmp_path / "candidates.json"
    path.write_text(
        json.dumps(
            {
                "meta": {"partitioned": True},
                "partitioning": {
                    "collectionKey": "items",
                    "groupKey": "universityId",
                    "root": "candidates/by-university",
                    "files": ["../outside.json"],
                },
            }
        ),
        encoding="utf-8",
    )

    try:
        read_json(path)
    except ValueError as exc:
        assert "outside manifest directory" in str(exc)
    else:
        raise AssertionError("Unsafe partition path was accepted")


def test_partition_manifest_rejects_files_outside_declared_root(tmp_path) -> None:
    path = tmp_path / "candidates.json"
    path.write_text(
        json.dumps(
            {
                "meta": {},
                "partitioning": {
                    "collectionKey": "items",
                    "groupKey": "universityId",
                    "root": "candidates/by-university",
                    "files": ["other.json"],
                },
            }
        ),
        encoding="utf-8",
    )

    try:
        read_json(path)
    except ValueError as exc:
        assert "outside partition root" in str(exc)
    else:
        raise AssertionError("Partition file outside its root was accepted")
