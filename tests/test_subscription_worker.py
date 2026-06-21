from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess


def test_subscription_core_normalizes_and_signs_without_exposing_email() -> None:
    node = shutil.which("node")
    assert node is not None, "Node.js is required for subscription worker tests"
    module_uri = (
        Path(__file__).parents[1] / "subscriptions" / "core.js"
    ).resolve().as_uri()
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
        Path(__file__).parents[1] / "subscriptions" / "worker.js"
    ).resolve().as_uri()
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
