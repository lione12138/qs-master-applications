from __future__ import annotations

import json
import os
import sys
from datetime import date
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).parents[1]
DATA_DIR = ROOT / "data"
MAX_EVENTS_PER_REQUEST = 20


def read_json(name: str) -> dict:
    return json.loads((DATA_DIR / name).read_text(encoding="utf-8"))


def current_open_events(today: date | None = None) -> list[dict]:
    today = today or date.today()
    universities = {
        item["id"]: item for item in read_json("universities.json")["universities"]
    }
    programs = {
        item["id"]: item["name"] for item in read_json("programs.json")["programs"]
    }
    groups = {
        item["id"]: item["name"]
        for item in read_json("programme-groups.json")["groups"]
    }
    events = []
    for record in read_json("applications.json")["applications"]:
        opens = date.fromisoformat(record["opensAt"])
        closes = date.fromisoformat(record["closesAt"])
        if not opens <= today <= closes:
            continue
        university = universities[record["universityId"]]
        if record["scopeType"] == "programme":
            programme = programs.get(record["scopeId"], record["scopeId"])
        elif record["scopeType"] == "programme-group":
            programme = groups.get(record["scopeId"], record["scopeId"])
        else:
            programme = "Institution-level application window"
        events.append(
            {
                "id": record["id"],
                "school": university["school"],
                "schoolZh": university.get("schoolZh", ""),
                "program": programme,
                "opensAt": record["opensAt"],
                "closesAt": record["closesAt"],
                "applicationUrl": record["applicationUrl"],
                "sourceUrl": record["sourceUrl"],
            }
        )
    return events


def notify(events: list[dict]) -> bool:
    endpoint = os.environ.get("GRADWINDOW_SUBSCRIBE_URL", "").rstrip("/")
    api_key = os.environ.get("GRADWINDOW_NOTIFY_API_KEY", "")
    if not endpoint or not api_key:
        print("Subscriber notification service is not configured; skipping.")
        return False
    if not events:
        print("No official application windows are currently open.")
        return True
    total_sent = 0
    total_failed = 0
    for start in range(0, len(events), MAX_EVENTS_PER_REQUEST):
        batch = events[start : start + MAX_EVENTS_PER_REQUEST]
        request = Request(
            f"{endpoint}/admin/notify",
            data=json.dumps({"events": batch}).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "User-Agent": "GradWindow-GitHub-Actions/1.0",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=45) as response:
                result = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            response_body = exc.read().decode("utf-8", errors="replace")
            print(
                "Notification request failed: "
                f"HTTP {exc.code} {exc.reason}; body={response_body[:1000]}",
                file=sys.stderr,
            )
            raise SystemExit(1) from exc
        except (URLError, TimeoutError) as exc:
            print(
                f"Notification request failed: {type(exc).__name__}: {exc}",
                file=sys.stderr,
            )
            raise SystemExit(1) from exc
        if not result.get("ok"):
            raise SystemExit("Notification service rejected the request.")
        total_sent += result.get("sent", 0)
        total_failed += result.get("failed", 0)
    print(
        f"Processed {len(events)} open official windows; "
        f"sent {total_sent} alerts; "
        f"{total_failed} deliveries failed."
    )
    return True


def main() -> None:
    events = current_open_events()
    if "--dry-run" in sys.argv:
        print(json.dumps({"events": events}, ensure_ascii=False, indent=2))
        return
    notify(events)


if __name__ == "__main__":
    main()
