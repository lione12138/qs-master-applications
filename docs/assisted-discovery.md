# Assisted programme discovery

GradWindow can use an assisted fallback when an official university catalogue
returns HTTP 403 to GitHub-hosted runners. This fallback improves discovery
coverage without treating model output as official evidence.

## Retrieval flow

1. Brave Search queries are restricted to the university's configured official
   domains.
2. Each official result is fetched directly. If that fails and Cloudflare
   Browser Rendering is configured, GradWindow requests a rendered Markdown
   copy.
3. DeepSeek extracts programme and application-window candidates as JSON.
4. Deterministic validation checks every URL, programme name, evidence quote,
   and exact date before the normal candidate writer runs.

Search snippets can create a no-deadline programme candidate, but dates from a
snippet are always rejected. A deadline candidate requires full text retrieved
from an official university URL, a verbatim evidence excerpt, and exact dates
that can be independently parsed from that excerpt. All results remain pending
operational candidates; assisted discovery never writes directly to
`data/applications.json`.

## Configuration

Enable the fallback for a school in
`data/ops/generic-programme-discovery.json`:

```json
{
  "accessStatus": "blocked",
  "assistedDiscovery": {
    "enabled": true,
    "maxResults": 12
  }
}
```

Required GitHub Actions secret:

- `DEEPSEEK_API_KEY`

Recommended search secret:

- `BRAVE_SEARCH_API_KEY`

Without Brave Search, the fallback still attempts every configured official
seed URL, but it cannot discover additional indexed pages.

Optional Browser Rendering secrets:

- `CLOUDFLARE_ACCOUNT_ID`
- `CLOUDFLARE_BROWSER_API_TOKEN`

`CLOUDFLARE_API_TOKEN` is also accepted as a fallback token name.

The Cloudflare token needs the `Browser Rendering - Edit` account permission.
Without the optional browser credentials, GradWindow still tries direct access
and preserves official search results as programme-only candidates.

## Commands

Run one configured school:

```powershell
gradwindow discover-assisted --university the-university-of-melbourne --dry-run
```

Run the configured generic batch, including enabled assisted fallbacks:

```powershell
gradwindow discover-generic-batch --replace-existing
```

The scheduled `pipeline` command also runs the generic batch. Missing optional
credentials result in a recorded `skipped` status instead of a failed workflow.
