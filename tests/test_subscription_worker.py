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


def test_notification_worker_sends_one_digest_for_multiple_events() -> None:
    node = shutil.which("node")
    assert node is not None, "Node.js is required for subscription worker tests"
    root = Path(__file__).parents[1]
    worker_uri = (root / "subscriptions" / "worker.js").resolve().as_uri()
    core_uri = (root / "subscriptions" / "core.js").resolve().as_uri()
    script = f"""
      import worker from {json.dumps(worker_uri)};
      import {{ bytesToBase64Url, encryptEmail }} from {json.dumps(core_uri)};

      const encryptionKey = bytesToBase64Url(
        crypto.getRandomValues(new Uint8Array(32)),
      );
      const encrypted = await encryptEmail("user@example.com", encryptionKey);
      const discovered = new Map();
      const deliveries = [];
      const emails = [];
      globalThis.fetch = async (_url, options) => {{
        emails.push(JSON.parse(options.body));
        return new Response("", {{ status: 200 }});
      }};
      const DB = {{
        prepare(sql) {{
          let values = [];
          return {{
            bind(...bound) {{ values = bound; return this; }},
            async run() {{
              if (sql.includes("INTO notification_events")) {{
                for (let index = 0; index < values.length; index += 3) {{
                  if (!discovered.has(values[index])) {{
                    discovered.set(values[index], values[index + 2]);
                  }}
                }}
              }} else if (sql.includes("INTO deliveries")) {{
                for (const eventKey of values.slice(2)) {{
                  deliveries.push({{ eventKey, emailHash: values[0] }});
                }}
              }}
              return {{ success: true }};
            }},
            async all() {{
              if (sql.includes("FROM notification_events")) {{
                return {{
                  results: values.map((eventKey) => ({{
                    event_key: eventKey,
                    discovered_at: discovered.get(eventKey),
                  }})),
                }};
              }}
              if (sql.includes("FROM subscribers")) {{
                return {{ results: [{{
                  email_hash: "hash-1",
                  email_ciphertext: encrypted.ciphertext,
                  email_iv: encrypted.iv,
                  language: "en",
                  confirmed_at: "2026-01-01T00:00:00.000Z",
                }}] }};
              }}
              if (sql.includes("FROM deliveries")) {{
                return {{
                  results: deliveries
                    .filter((item) => item.emailHash === values[0])
                    .map((item) => ({{ event_key: item.eventKey }})),
                }};
              }}
              throw new Error(sql);
            }},
          }};
        }},
      }};
      const event = (id, program) => ({{
        id,
        school: "Example University",
        schoolZh: "示例大学",
        program,
        opensAt: "2026-07-01",
        closesAt: "2026-12-01",
        applicationUrl: "https://example.edu/apply",
        sourceUrl: "https://example.edu/source",
      }});
      const response = await worker.fetch(
        new Request("https://worker.example/admin/notify", {{
          method: "POST",
          headers: {{
            Authorization: "Bearer admin-secret",
            "Content-Type": "application/json",
          }},
          body: JSON.stringify({{
            events: Array.from(
              {{ length: 502 }},
              (_, index) => event(`window-${{index}}`, `MSc ${{index}}`),
            ),
          }}),
        }}),
        {{
          ADMIN_API_KEY: "admin-secret",
          API_BASE_URL: "https://worker.example",
          PUBLIC_SITE_URL: "https://gradwindow.com",
          EMAIL_ENCRYPTION_KEY: encryptionKey,
          TOKEN_SIGNING_KEY: "signing-secret",
          RESEND_API_KEY: "resend-secret",
          RESEND_FROM: "GradWindow <alerts@example.edu>",
          DB,
        }},
      );
      console.log(JSON.stringify({{
        body: await response.json(),
        emailCount: emails.length,
        subject: emails[0]?.subject || "",
        emailText: emails[0]?.text || "",
        deliveryCount: deliveries.length,
      }}));
    """
    result = subprocess.run(
        [node, "--input-type=module", "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )
    response = json.loads(result.stdout)
    assert response["body"] == {"ok": True, "sent": 1, "failed": 0}
    assert response["emailCount"] == 1
    assert response["subject"] == "GradWindow digest: updates from 1 university"
    assert (
        "Example University: 502 programmes, deadline 2026-12-01"
        in response["emailText"]
    )
    assert "MSc 0" not in response["emailText"]
    assert response["deliveryCount"] == 502
