from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path


def test_subscription_core_normalizes_and_signs_without_exposing_email() -> None:
    node = shutil.which("node")
    assert node is not None, "Node.js is required for subscription worker tests"
    module_uri = (
        (Path(__file__).parents[1] / "subscriptions" / "core.js").resolve().as_uri()
    )
    script = f"""
      import {{
        bytesToBase64Url,
        decryptEmail,
        encryptEmail,
        normalizeEmail,
        signedUnsubscribeToken,
        verifyUnsubscribeToken,
      }} from {json.dumps(module_uri)};
      const hash = "a".repeat(64);
      const token = await signedUnsubscribeToken(hash, "test-secret");
      const key = bytesToBase64Url(crypto.getRandomValues(new Uint8Array(32)));
      const encrypted = await encryptEmail("user@example.com", key);
      console.log(JSON.stringify({{
        normalized: normalizeEmail("  User@Example.COM "),
        decrypted: await decryptEmail(encrypted.ciphertext, encrypted.iv, key),
        ciphertextContainsEmail: encrypted.ciphertext.includes("@"),
        verified: await verifyUnsubscribeToken(token, "test-secret"),
        rejected: await verifyUnsubscribeToken(token + "x", "test-secret"),
        containsEmail: token.includes("@"),
      }}));
    """
    result = subprocess.run(
        [node, "--input-type=module", "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(result.stdout) == {
        "normalized": "user@example.com",
        "decrypted": "user@example.com",
        "ciphertextContainsEmail": False,
        "verified": "a" * 64,
        "rejected": "",
        "containsEmail": False,
    }


def test_roadmap_preflight_allows_anonymous_visitor_header() -> None:
    node = shutil.which("node")
    assert node is not None, "Node.js is required for subscription worker tests"
    worker_uri = (
        (Path(__file__).parents[1] / "subscriptions" / "worker.js").resolve().as_uri()
    )
    script = f"""
      import worker from {json.dumps(worker_uri)};
      const response = await worker.fetch(
        new Request("https://worker.example/roadmap", {{
          method: "OPTIONS",
          headers: {{ Origin: "https://lione12138.github.io" }},
        }}),
        {{ ALLOWED_ORIGINS: "https://lione12138.github.io" }},
      );
      console.log(JSON.stringify({{
        status: response.status,
        allowHeaders: response.headers.get("Access-Control-Allow-Headers"),
      }}));
    """
    result = subprocess.run(
        [node, "--input-type=module", "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )
    response = json.loads(result.stdout)
    assert response["status"] == 204
    assert "X-GradWindow-Visitor" in response["allowHeaders"]


def test_worker_preflight_allows_comment_reads_and_writes() -> None:
    node = shutil.which("node")
    assert node is not None, "Node.js is required for subscription worker tests"
    worker_uri = (
        (Path(__file__).parents[1] / "subscriptions" / "worker.js").resolve().as_uri()
    )
    script = f"""
      import worker from {json.dumps(worker_uri)};
      const response = await worker.fetch(
        new Request("https://worker.example/universities/ucl/comments", {{
          method: "OPTIONS",
          headers: {{ Origin: "https://gradwindow.com" }},
        }}),
        {{ ALLOWED_ORIGINS: "https://gradwindow.com" }},
      );
      console.log(JSON.stringify({{
        status: response.status,
        methods: response.headers.get("Access-Control-Allow-Methods"),
      }}));
    """
    result = subprocess.run(
        [node, "--input-type=module", "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )
    response = json.loads(result.stdout)
    assert response["status"] == 204
    assert "GET" in response["methods"]
    assert "POST" in response["methods"]
    assert "PATCH" in response["methods"]
    assert "PUT" in response["methods"]


def test_admin_roadmap_stats_require_a_dedicated_secret_and_only_aggregate() -> None:
    node = shutil.which("node")
    assert node is not None, "Node.js is required for subscription worker tests"
    worker_uri = (
        (Path(__file__).parents[1] / "subscriptions" / "worker.js").resolve().as_uri()
    )
    script = f"""
      import worker from {json.dumps(worker_uri)};
      const DB = {{
        prepare(sql) {{
          return {{
            bind() {{ return this; }},
            async first() {{
              if (!sql.includes("AS total_votes")) throw new Error(sql);
              return {{
                total_votes: 4,
                unique_voters: 2,
                first_vote_at: "2026-06-21T13:43:23.358Z",
                last_vote_at: "2026-06-28T14:26:05.510Z",
              }};
            }},
            async all() {{
              if (!sql.includes("GROUP BY p.id")) throw new Error(sql);
              return {{ results: [{{
                id: "wechat-mini-program",
                title_en: "WeChat Mini Program",
                title_zh: "微信小程序",
                source: "owner",
                votes: 2,
                first_vote_at: "2026-06-21T13:43:23.358Z",
                last_vote_at: "2026-06-28T14:26:00.789Z",
              }}] }};
            }},
          }};
        }},
      }};
      const env = {{
        ALLOWED_ORIGINS: "https://gradwindow.com,https://www.gradwindow.com",
        ROADMAP_ADMIN_API_KEY: "roadmap-admin-secret\\n",
        DB,
      }};
      const unauthorized = await worker.fetch(
        new Request("https://worker.example/admin/roadmap/stats", {{
          headers: {{ Origin: "https://gradwindow.com" }},
        }}),
        env,
      );
      const authorized = await worker.fetch(
        new Request("https://worker.example/admin/roadmap/stats", {{
          headers: {{
            Origin: "https://gradwindow.com",
            Authorization: "Bearer roadmap-admin-secret",
          }},
        }}),
        env,
      );
      console.log(JSON.stringify({{
        unauthorizedStatus: unauthorized.status,
        authorizedStatus: authorized.status,
        body: await authorized.json(),
      }}));
    """
    result = subprocess.run(
        [node, "--input-type=module", "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )
    response = json.loads(result.stdout)
    assert response["unauthorizedStatus"] == 401
    assert response["authorizedStatus"] == 200
    assert response["body"] == {
        "summary": {
            "totalVotes": 4,
            "uniqueVoters": 2,
            "firstVoteAt": "2026-06-21T13:43:23.358Z",
            "lastVoteAt": "2026-06-28T14:26:05.510Z",
        },
        "proposals": [
            {
                "id": "wechat-mini-program",
                "title": {"en": "WeChat Mini Program", "zh": "微信小程序"},
                "source": "owner",
                "votes": 2,
                "firstVoteAt": "2026-06-21T13:43:23.358Z",
                "lastVoteAt": "2026-06-28T14:26:00.789Z",
            }
        ],
    }
    assert "visitor_hash" not in json.dumps(response["body"])


def test_worker_configuration_allows_both_canonical_hostnames() -> None:
    config = (
        Path(__file__).parents[1] / "subscriptions" / "wrangler.toml.example"
    ).read_text(encoding="utf-8")

    assert "https://gradwindow.com" in config
    assert "https://www.gradwindow.com" in config


def test_notify_admin_secret_ignores_cli_trailing_newline() -> None:
    worker = (Path(__file__).parents[1] / "subscriptions" / "worker.js").read_text(
        encoding="utf-8"
    )

    assert 'String(env.ADMIN_API_KEY || "").trim()' in worker
