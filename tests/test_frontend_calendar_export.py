from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

MODULE_URI = (
    (Path(__file__).parents[1] / "web" / "calendar-export.js").resolve().as_uri()
)

RECORD = {
    "id": "test-data-science-msc-fall-2026",
    "school": "Test University",
    "program": "Data Science MSc",
    "closesAt": "2026-06-30",
    "applicationUrl": "https://apply.example.edu",
    "sourceUrl": "https://example.edu/deadlines",
    "dataStatus": "official",
}


def run_node(script: str) -> dict:
    node = shutil.which("node")
    assert node is not None, "Node.js is required for calendar export tests"
    result = subprocess.run(
        [node, "--input-type=module", "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def test_frontend_google_calendar_url_official_and_estimate() -> None:
    script = """
      const { googleCalendarUrl } = await import(__MODULE__);
      const record = __RECORD__;
      const officialUrl = new URL(googleCalendarUrl(record));
      const yearEnd = new URL(
        googleCalendarUrl({ ...record, closesAt: "2026-12-31" }),
      );
      const predicted = new URL(
        googleCalendarUrl({ ...record, dataStatus: "predicted" }),
      );
      console.log(JSON.stringify({
        origin: officialUrl.origin + officialUrl.pathname,
        action: officialUrl.searchParams.get("action"),
        text: officialUrl.searchParams.get("text"),
        dates: officialUrl.searchParams.get("dates"),
        details: officialUrl.searchParams.get("details"),
        yearEndDates: yearEnd.searchParams.get("dates"),
        predictedText: predicted.searchParams.get("text"),
        predictedWarned: predicted.searchParams
          .get("details")
          .startsWith("Unofficial calendar-date estimate."),
      }));
    """.replace("__MODULE__", json.dumps(MODULE_URI)).replace(
        "__RECORD__", json.dumps(RECORD)
    )
    assert run_node(script) == {
        "origin": "https://calendar.google.com/calendar/render",
        "action": "TEMPLATE",
        "text": "Test University Data Science MSc application deadline",
        "dates": "20260630/20260701",
        "details": (
            "Application: https://apply.example.edu\n"
            "Source: https://example.edu/deadlines"
        ),
        "yearEndDates": "20261231/20270101",
        "predictedText": (
            "[ESTIMATE] Test University Data Science MSc application deadline"
        ),
        "predictedWarned": True,
    }


def test_frontend_outlook_calendar_url_is_all_day_event() -> None:
    script = """
      const { outlookCalendarUrl } = await import(__MODULE__);
      const url = new URL(outlookCalendarUrl(__RECORD__));
      console.log(JSON.stringify({
        origin: url.origin + url.pathname,
        startdt: url.searchParams.get("startdt"),
        enddt: url.searchParams.get("enddt"),
        allday: url.searchParams.get("allday"),
        subject: url.searchParams.get("subject"),
      }));
    """.replace("__MODULE__", json.dumps(MODULE_URI)).replace(
        "__RECORD__", json.dumps(RECORD)
    )
    assert run_node(script) == {
        "origin": "https://outlook.live.com/calendar/0/deeplink/compose",
        "startdt": "2026-06-30T00:00:00Z",
        "enddt": "2026-07-01T00:00:00Z",
        "allday": "true",
        "subject": "Test University Data Science MSc application deadline",
    }


def test_frontend_ics_body_escapes_and_spans_deadline_day() -> None:
    script = """
      const { icsFileBody } = await import(__MODULE__);
      const record = { ...__RECORD__, school: "Test University, Downtown" };
      const body = icsFileBody(record, new Date("2026-06-15T12:34:56Z"));
      const lines = body.split("\\r\\n");
      console.log(JSON.stringify({
        first: lines[0],
        last: lines[lines.length - 1],
        uid: lines.find((line) => line.startsWith("UID:")),
        dtstamp: lines.find((line) => line.startsWith("DTSTAMP:")),
        dtstart: lines.find((line) => line.startsWith("DTSTART")),
        dtend: lines.find((line) => line.startsWith("DTEND")),
        summary: lines.find((line) => line.startsWith("SUMMARY:")),
      }));
    """.replace("__MODULE__", json.dumps(MODULE_URI)).replace(
        "__RECORD__", json.dumps(RECORD)
    )
    assert run_node(script) == {
        "first": "BEGIN:VCALENDAR",
        "last": "END:VCALENDAR",
        "uid": "UID:test-data-science-msc-fall-2026@gradwindow",
        "dtstamp": "DTSTAMP:20260615T123456Z",
        "dtstart": "DTSTART;VALUE=DATE:20260630",
        "dtend": "DTEND;VALUE=DATE:20260701",
        "summary": (
            "SUMMARY:Test University\\, Downtown Data Science MSc application deadline"
        ),
    }
