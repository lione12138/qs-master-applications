from __future__ import annotations

import json
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Any


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        if default is not None:
            return default
        raise FileNotFoundError(path)
    payload = _read_plain_json(path)
    if isinstance(payload, dict) and "partitioning" in payload:
        return _read_partitioned_json(path, payload)
    return payload


def write_json(path: Path, payload: Any) -> None:
    if path.exists():
        current = _read_plain_json(path)
        if isinstance(current, dict) and "partitioning" in current:
            _write_partitioned_json(path, payload, current)
            return
    _write_plain_json(path, payload)


def partition_json_file(
    path: Path,
    *,
    collection_key: str,
    group_key: str | None = None,
) -> None:
    """Convert one JSON collection into a manifest backed by university shards."""
    payload = read_json(path)
    if not isinstance(payload, dict) or collection_key not in payload:
        raise ValueError(f"{path} does not contain {collection_key!r}")
    collection = payload[collection_key]
    if isinstance(collection, list) and not group_key:
        raise ValueError("List collections require a group_key")
    if not isinstance(collection, (list, dict)):
        raise ValueError(f"{collection_key!r} must be a list or mapping")
    partition_root = f"{path.stem}/by-university"
    manifest = {
        "meta": dict(payload.get("meta", {})),
        "partitioning": {
            "collectionKey": collection_key,
            "groupKey": group_key,
            "root": partition_root,
            "files": [],
        },
    }
    _write_partitioned_json(path, payload, manifest)


def _read_plain_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _read_partitioned_json(path: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    partitioning = manifest["partitioning"]
    collection_key = partitioning["collectionKey"]
    result = {"meta": dict(manifest.get("meta", {}))}
    combined: list[Any] | dict[str, Any]
    combined = {} if partitioning.get("groupKey") is None else []
    for relative_name in partitioning.get("files", []):
        shard_path = _safe_partition_path(
            path,
            relative_name,
            root=partitioning["root"],
        )
        shard = _read_plain_json(shard_path)
        shard_collection = shard.get(collection_key)
        if isinstance(combined, list) and isinstance(shard_collection, list):
            combined.extend(shard_collection)
        elif isinstance(combined, dict) and isinstance(shard_collection, dict):
            overlap = set(combined).intersection(shard_collection)
            if overlap:
                raise ValueError(
                    f"Duplicate partition keys in {path}: {sorted(overlap)}"
                )
            combined.update(shard_collection)
        else:
            raise ValueError(f"Invalid partition collection in {shard_path}")
    result[collection_key] = combined
    return result


def _write_partitioned_json(
    path: Path,
    payload: Any,
    manifest: dict[str, Any],
) -> None:
    if not isinstance(payload, dict):
        raise ValueError("Partitioned JSON payload must be a mapping")
    partitioning = manifest["partitioning"]
    collection_key = partitioning["collectionKey"]
    group_key = partitioning.get("groupKey")
    collection = payload.get(collection_key)
    grouped = _group_partition_collection(collection, group_key)
    root = partitioning["root"].rstrip("/")
    desired_files: list[str] = []
    used_filenames: set[str] = set()
    for university_id in sorted(grouped):
        filename = _partition_filename(university_id)
        if filename in used_filenames:
            raise ValueError(f"Partition filename collision for {university_id!r}")
        used_filenames.add(filename)
        relative_name = f"{root}/{filename}"
        desired_files.append(relative_name)
        shard_path = _safe_partition_path(path, relative_name, root=root)
        shard_payload = {collection_key: grouped[university_id]}
        if not shard_path.exists() or _read_plain_json(shard_path) != shard_payload:
            _write_plain_json(shard_path, shard_payload)

    old_files = set(partitioning.get("files", []))
    for relative_name in old_files.difference(desired_files):
        _safe_partition_path(path, relative_name, root=root).unlink(missing_ok=True)

    updated_manifest = {
        "meta": dict(payload.get("meta", {})),
        "partitioning": {
            **partitioning,
            "files": desired_files,
        },
    }
    if not path.exists() or _read_plain_json(path) != updated_manifest:
        _write_plain_json(path, updated_manifest)


def _group_partition_collection(
    collection: Any,
    group_key: str | None,
) -> dict[str, Any]:
    if group_key is None:
        if not isinstance(collection, dict):
            raise ValueError("Mapping partitions require a mapping collection")
        return {str(key): {str(key): value} for key, value in collection.items()}
    if not isinstance(collection, list):
        raise ValueError("Grouped partitions require a list collection")
    grouped: dict[str, list[Any]] = {}
    for item in collection:
        if not isinstance(item, dict) or not item.get(group_key):
            raise ValueError(f"Partition item is missing {group_key!r}")
        grouped.setdefault(str(item[group_key]), []).append(item)
    return grouped


def _partition_filename(university_id: str) -> str:
    filename = re.sub(r"[^a-z0-9-]+", "-", university_id.lower()).strip("-")
    if not filename:
        raise ValueError(f"Cannot create partition filename for {university_id!r}")
    return f"{filename}.json"


def _safe_partition_path(
    manifest_path: Path,
    relative_name: str,
    *,
    root: str | None = None,
) -> Path:
    if not isinstance(relative_name, str) or not relative_name:
        raise ValueError("Partition path must be a non-empty string")
    base = manifest_path.parent.resolve()
    candidate = (base / relative_name).resolve()
    if candidate == base or base not in candidate.parents:
        raise ValueError(
            f"Partition path is outside manifest directory: {relative_name}"
        )
    if root is not None:
        partition_root = (base / root).resolve()
        if (
            partition_root == base
            or base not in partition_root.parents
            or partition_root not in candidate.parents
        ):
            raise ValueError(
                f"Partition path is outside partition root: {relative_name}"
            )
    return candidate


def _write_plain_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        _replace_with_retry(temporary_path, path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _replace_with_retry(source: Path, target: Path) -> None:
    for attempt in range(8):
        try:
            os.replace(source, target)
            return
        except PermissionError:
            if attempt == 7:
                raise
            time.sleep(0.05 * (attempt + 1))
