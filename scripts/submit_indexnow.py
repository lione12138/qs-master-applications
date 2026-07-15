from __future__ import annotations

import argparse
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

INDEXNOW_ENDPOINT = "https://api.indexnow.org/indexnow"
MAX_URLS_PER_REQUEST = 10_000
KEY_PATTERN = re.compile(r"^[A-Za-z0-9-]{8,128}$")


def load_sitemap_urls(path: Path) -> list[str]:
    root = ET.fromstring(path.read_text(encoding="utf-8"))
    urls: list[str] = []
    seen: set[str] = set()
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1] != "loc" or not element.text:
            continue
        url = element.text.strip()
        if url and url not in seen:
            seen.add(url)
            urls.append(url)
    if not urls:
        raise ValueError(f"No URLs found in sitemap: {path}")
    if len(urls) > MAX_URLS_PER_REQUEST:
        raise ValueError(
            f"Sitemap contains {len(urls)} URLs; IndexNow accepts at most "
            f"{MAX_URLS_PER_REQUEST} per request"
        )
    return urls


def load_key(path: Path) -> str:
    key = path.read_text(encoding="utf-8").strip()
    if not KEY_PATTERN.fullmatch(key):
        raise ValueError("IndexNow key must contain 8-128 letters, numbers, or dashes")
    if path.name != f"{key}.txt":
        raise ValueError("IndexNow root key filename must match its content")
    return key


def build_payload(
    urls: list[str],
    *,
    key: str,
    key_filename: str,
) -> dict[str, object]:
    if not urls:
        raise ValueError("At least one URL is required")
    first = urlparse(urls[0])
    if first.scheme not in {"http", "https"} or not first.netloc:
        raise ValueError(f"Invalid URL: {urls[0]}")
    for url in urls:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or parsed.netloc != first.netloc:
            raise ValueError("All IndexNow URLs must use the same host")
    return {
        "host": first.netloc,
        "key": key,
        "keyLocation": f"{first.scheme}://{first.netloc}/{key_filename}",
        "urlList": urls,
    }


def submit_urls(
    payload: dict[str, object],
    *,
    endpoint: str = INDEXNOW_ENDPOINT,
) -> int:
    request = Request(
        endpoint,
        data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": "GradWindow-IndexNow/1.0",
        },
        method="POST",
    )
    with urlopen(request, timeout=45) as response:
        status = response.status
    if status not in {200, 202}:
        raise RuntimeError(f"IndexNow returned HTTP {status}")
    return status


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Submit the built GradWindow sitemap to IndexNow"
    )
    parser.add_argument("--sitemap", type=Path, required=True)
    parser.add_argument("--key-file", type=Path, required=True)
    parser.add_argument("--endpoint", default=INDEXNOW_ENDPOINT)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    urls = load_sitemap_urls(args.sitemap)
    key = load_key(args.key_file)
    payload = build_payload(urls, key=key, key_filename=args.key_file.name)
    if args.dry_run:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    status = submit_urls(payload, endpoint=args.endpoint)
    print(f"IndexNow accepted {len(urls)} URLs with HTTP {status}.")


if __name__ == "__main__":
    main()
