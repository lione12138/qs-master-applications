from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

MODULE_URI = (Path(__file__).parents[1] / "web" / "dom.js").resolve().as_uri()


def run_node(script: str) -> dict:
    node = shutil.which("node")
    assert node is not None, "Node.js is required for frontend dom tests"
    result = subprocess.run(
        [node, "--input-type=module", "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def test_frontend_parse_date_and_acronym() -> None:
    script = """
      import { parseDate, acronym } from __MODULE__;
      console.log(JSON.stringify({
        parsed: parseDate("2026-06-30").toISOString(),
        leapDay: parseDate("2028-02-29").toISOString(),
        hku: acronym("The University of Hong Kong"),
        lse: acronym("London School of Economics and Political Science"),
        empty: acronym(""),
      }));
    """.replace("__MODULE__", json.dumps(MODULE_URI))
    assert run_node(script) == {
        "parsed": "2026-06-30T00:00:00.000Z",
        "leapDay": "2028-02-29T00:00:00.000Z",
        "hku": "uhk",
        "lse": "lseps",
        "empty": "",
    }


def test_frontend_compact_date_range_uses_mobile_numeric_format() -> None:
    script = """
      import { formatCompactDate, formatDateRange } from __MODULE__;
      console.log(JSON.stringify({
        date: formatCompactDate("2026-08-18"),
        range: formatDateRange("2026-08-18", "2026-09-28"),
        missingOpen: formatDateRange("", "2026-09-28"),
      }));
    """.replace("__MODULE__", json.dumps(MODULE_URI))
    assert run_node(script) == {
        "date": "2026.8.18",
        "range": "2026.8.18 - 2026.9.28",
        "missingOpen": "— - 2026.9.28",
    }


def test_frontend_safe_url_blocks_unsafe_protocols() -> None:
    script = """
      globalThis.window = { location: { href: "https://gradwindow.com/" } };
      const { safeUrl } = await import(__MODULE__);
      console.log(JSON.stringify({
        https: safeUrl("https://example.edu/apply"),
        http: safeUrl("http://example.edu/apply"),
        javascript: safeUrl("javascript:alert(1)"),
        data: safeUrl("data:text/html,x"),
        relative: safeUrl("/privacy.html"),
        empty: safeUrl(""),
      }));
    """.replace("__MODULE__", json.dumps(MODULE_URI))
    assert run_node(script) == {
        "https": "https://example.edu/apply",
        "http": "http://example.edu/apply",
        "javascript": "",
        "data": "",
        "relative": "https://gradwindow.com/privacy.html",
        "empty": "https://gradwindow.com/",
    }


def test_frontend_make_link_falls_back_to_span_for_unsafe_urls() -> None:
    script = """
      globalThis.window = { location: { href: "https://gradwindow.com/" } };
      globalThis.document = {
        createElement: (tag) => ({ tagName: tag.toUpperCase() }),
      };
      const { makeLink } = await import(__MODULE__);
      const safe = makeLink("Apply", "https://example.edu/apply", "cls");
      const unsafe = makeLink("Apply", "javascript:alert(1)", "cls");
      console.log(JSON.stringify({
        safeTag: safe.tagName,
        safeRel: safe.rel,
        safeTarget: safe.target,
        safeHref: safe.href,
        unsafeTag: unsafe.tagName,
        unsafeHasHref: "href" in unsafe,
      }));
    """.replace("__MODULE__", json.dumps(MODULE_URI))
    assert run_node(script) == {
        "safeTag": "A",
        "safeRel": "noreferrer",
        "safeTarget": "_blank",
        "safeHref": "https://example.edu/apply",
        "unsafeTag": "SPAN",
        "unsafeHasHref": False,
    }


def test_frontend_visitor_id_is_stable_per_storage_key() -> None:
    script = """
      const store = new Map();
      globalThis.localStorage = {
        getItem: (key) => (store.has(key) ? store.get(key) : null),
        setItem: (key, value) => store.set(key, String(value)),
      };
      const { visitorId } = await import(__MODULE__);
      const first = visitorId("gradwindow:visitor");
      const second = visitorId("gradwindow:visitor");
      const other = visitorId("gradwindow:roadmap-visitor");
      console.log(JSON.stringify({
        stable: first === second,
        nonEmpty: first.length > 0,
        separateKeys: first !== other,
        persisted: store.get("gradwindow:visitor") === first,
      }));
    """.replace("__MODULE__", json.dumps(MODULE_URI))
    assert run_node(script) == {
        "stable": True,
        "nonEmpty": True,
        "separateKeys": True,
        "persisted": True,
    }
