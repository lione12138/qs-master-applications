# Assisted programme discovery

GradWindow can use an assisted fallback when an official university catalogue
returns HTTP 403 to GitHub-hosted runners. This fallback improves discovery
coverage without treating model output as official evidence.

## Retrieval flow

1. Configured university catalogue and admissions URLs are always included as
   the primary discovery sources.
2. Serper searches the university's configured official domains when an API key
   is available. Brave is retained as an independent-index fallback. Entries
   marked `searchPriority: "high"` merge both providers when both are configured.
3. Each official result is fetched directly. If that fails and Cloudflare
   Browser Rendering is configured, GradWindow requests a rendered Markdown
   copy.
4. DeepSeek extracts programme and application-window candidates as JSON.
5. Deterministic validation checks every URL, programme name, evidence quote,
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
    "maxResults": 12,
    "searchPriority": "high"
  }
}
```

`searchPriority` defaults to `normal`:

- `normal` — use Serper when configured, otherwise Brave. If the selected
  provider fails, try the other configured provider.
- `high` — query and merge both configured providers, deduplicating canonical
  URLs before retrieval.

Required GitHub Actions secret:

- `DEEPSEEK_API_KEY`

Recommended primary search secret:

- `SERPER_SEARCH_API_KEY` (`SERPER_API_KEY` is also accepted locally)

Optional independent-index fallback secret:

- `BRAVE_SEARCH_API_KEY`

Without either search secret, the fallback still attempts every configured
official seed URL, but it cannot discover additional indexed pages.

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

Full `pipeline` runs and the low-frequency catalogue workflow run the generic
batch; scheduled dedicated refreshes run matching fallback entries only after a
dedicated failure. Missing optional
credentials result in a recorded `skipped` status instead of a failed workflow.

## Cost and trust gates

- Normal catalogue discovery does not call a search API when a dedicated or
  generic adapter can read the configured official pages directly.
- Search providers discover URLs only. Third-party domains are discarded and
  search snippets can never provide publishable dates.
- Direct HTTP retrieval is attempted before Browser Rendering.
- DeepSeek receives only the bounded official-domain documents selected by the
  assisted path. Deterministic evidence validation remains authoritative.
