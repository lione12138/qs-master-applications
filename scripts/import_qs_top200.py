#!/usr/bin/env python3
"""Import the first 200 institutions from the QS 2026 workbook and resolve ROR."""

from __future__ import annotations

import argparse
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = ROOT / "data" / "universities.json"
CACHE_PATH = ROOT / "data" / "ror-cache.json"
ROR_API = "https://api.ror.org/v2/organizations"
USER_AGENT = "GradWindow/1.0 (university admissions research)"

OFFICIAL_SITE_OVERRIDES = {
    "PSL University": {
        "homepage": "https://psl.eu/",
        "domains": ["psl.eu"],
    },
    "Northwestern University": {
        "homepage": "https://www.northwestern.edu/",
        "domains": ["northwestern.edu"],
    },
    "Korea University": {
        "homepage": "https://www.korea.edu/",
        "domains": ["korea.edu"],
    },
    "Purdue University": {
        "homepage": "https://www.purdue.edu/",
        "domains": ["purdue.edu"],
    },
    "Western University": {
        "homepage": "https://www.uwo.ca/",
        "domains": ["uwo.ca"],
    },
}


def slugify(value: str) -> str:
    value = value.lower().replace("&", " and ")
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")


def read_json(path: Path, default: dict) -> dict:
    if not path.exists():
        return default
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, payload: dict) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def resolve_ror(name: str, country: str) -> dict:
    affiliation = urllib.parse.quote(f"{name}, {country}")
    request = urllib.request.Request(
        f"{ROR_API}?affiliation={affiliation}",
        headers={"User-Agent": USER_AGENT},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.load(response)
    if not payload.get("items"):
        return {"matched": False}

    item = payload["items"][0]
    organization = item.get("organization", {})
    websites = [
        link["value"]
        for link in organization.get("links", [])
        if link.get("type") == "website"
    ]
    return {
        "matched": bool(item.get("chosen")),
        "score": item.get("score"),
        "matchingType": item.get("matching_type"),
        "rorId": organization.get("id"),
        "homepage": websites[0] if websites else None,
        "domains": organization.get("domains", []),
        "rorName": next(
            (
                entry["value"]
                for entry in organization.get("names", [])
                if "ror_display" in entry.get("types", [])
            ),
            None,
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("workbook", type=Path)
    parser.add_argument(
        "--skip-ror",
        action="store_true",
        help="Only import ranking rows; do not call the ROR API.",
    )
    args = parser.parse_args()

    frame = pd.read_excel(args.workbook, sheet_name=0, dtype={"Rank": str})
    required = {"Rank", "Name", "Country/Territory", "Region"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Workbook is missing columns: {sorted(missing)}")

    top = frame.head(200)
    cache = read_json(CACHE_PATH, {})
    universities = []

    for position, row in enumerate(top.to_dict("records"), start=1):
        name = str(row["Name"]).strip()
        country = str(row["Country/Territory"]).strip()
        rank = int(re.sub(r"\D", "", str(row["Rank"])))
        cache_key = f"{name}|{country}"

        if args.skip_ror:
            ror = cache.get(cache_key, {"matched": False})
        elif cache_key in cache:
            ror = cache[cache_key]
        else:
            try:
                ror = resolve_ror(name, country)
            except OSError as exc:
                ror = {"matched": False, "error": str(exc)}
            cache[cache_key] = ror
            write_json(CACHE_PATH, cache)
            time.sleep(0.1)

        if name in OFFICIAL_SITE_OVERRIDES:
            ror = {
                **ror,
                **OFFICIAL_SITE_OVERRIDES[name],
                "matched": True,
                "matchingType": "MANUAL OFFICIAL SITE OVERRIDE",
            }

        homepage = ror.get("homepage")
        domains = ror.get("domains", [])
        if homepage and not domains:
            hostname = urllib.parse.urlparse(homepage).hostname
            if hostname:
                domains = [hostname.lower().removeprefix("www.")]

        universities.append(
            {
                "id": slugify(name),
                "qsRank": rank,
                "qsPosition": position,
                "rankDisplay": f"={rank}" if position > 1 and rank == universities[-1]["qsRank"] else str(rank),
                "school": name,
                "schoolZh": "",
                "country": country,
                "region": str(row["Region"]).strip(),
                "homepageUrl": homepage,
                "officialDomains": domains,
                "rorId": ror.get("rorId"),
                "rorMatchScore": ror.get("score"),
                "rorMatched": ror.get("matched", False),
                "admissionsUrl": None,
                "admissionsDiscovery": "pending",
                "datePolicy": "program-specific",
                "monitorEnabled": False,
            }
        )

    payload = {
        "meta": {
            "rankingEdition": "QS World University Rankings 2026",
            "rankingPublishedAt": "2025-06-19",
            "rankingSource": "https://www.topuniversities.com/world-university-rankings",
            "recordCount": len(universities),
            "selectionRule": "First 200 institutions in the published table; ties retain QS rank values.",
            "institutionSource": "QS workbook; official domains resolved through ROR v2.",
        },
        "universities": universities,
    }
    write_json(OUTPUT_PATH, payload)
    write_json(CACHE_PATH, cache)
    print(f"Imported {len(universities)} institutions to {OUTPUT_PATH}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
