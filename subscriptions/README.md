# GradWindow email subscriptions

This Worker provides privacy-preserving, double-opt-in email alerts for newly
opened official application windows.

## Privacy design

- The public site sends email addresses directly to the Worker over HTTPS.
- Email addresses never enter GitHub, static files, analytics, or browser storage.
- D1 stores an AES-GCM encrypted address plus a keyed HMAC lookup value.
- Confirmation tokens are stored only as SHA-256 hashes.
- Unsubscribe URLs contain a keyed signature, not an email address.
- Unsubscribing immediately removes the encrypted email value.
- The database intentionally does not store subscriber IP addresses.
- Resend open and click tracking must remain disabled.

Cloudflare D1 also encrypts data at rest and in transit. Application-level
encryption is retained as an additional control.

## Requirements

- A Cloudflare account with Workers, D1, and Turnstile.
- Node.js 20 or newer and Wrangler.
- A Resend account.
- A domain you own and can verify with Resend. Production sending cannot use a
  shared `github.io` or `workers.dev` hostname.

The Cloudflare and Resend free plans are sufficient for an early-stage site.
Resend's free tier currently limits sending to 100 emails per day.

## Deploy

1. Copy the example:

   ```powershell
   Copy-Item subscriptions/wrangler.toml.example subscriptions/wrangler.toml
   ```

2. Create D1 and put its ID in the copied configuration:

   ```powershell
   npx wrangler d1 create gradwindow-subscribers
   npx wrangler d1 execute gradwindow-subscribers --remote --file subscriptions/schema.sql
   ```

3. Generate secrets locally:

   ```powershell
   python -c "import base64,secrets; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode().rstrip('='))"
   python -c "import secrets; print(secrets.token_urlsafe(48))"
   ```

   Use the first output for `EMAIL_ENCRYPTION_KEY`. Run the second command
   four times for `EMAIL_INDEX_KEY`, `TOKEN_SIGNING_KEY`, `ADMIN_API_KEY`, and
   `ROADMAP_VOTER_HASH_KEY`.

4. Store secrets with Wrangler. Never commit their values:

   ```powershell
   npx wrangler secret put EMAIL_ENCRYPTION_KEY --config subscriptions/wrangler.toml
   npx wrangler secret put EMAIL_INDEX_KEY --config subscriptions/wrangler.toml
   npx wrangler secret put TOKEN_SIGNING_KEY --config subscriptions/wrangler.toml
   npx wrangler secret put ADMIN_API_KEY --config subscriptions/wrangler.toml
   npx wrangler secret put RESEND_API_KEY --config subscriptions/wrangler.toml
   npx wrangler secret put TURNSTILE_SECRET_KEY --config subscriptions/wrangler.toml
   npx wrangler secret put ROADMAP_VOTER_HASH_KEY --config subscriptions/wrangler.toml
   ```

5. Verify a sending subdomain in Resend, update `RESEND_FROM`, then deploy:

   ```powershell
   npx wrangler deploy --config subscriptions/wrangler.toml
   ```

6. Add GitHub repository variables:

   - `GRADWINDOW_SUBSCRIBE_URL`: deployed Worker URL.
   - `GRADWINDOW_TURNSTILE_SITE_KEY`: public Turnstile site key.
   - `GRADWINDOW_ROADMAP_URL`: the same deployed Worker URL, enabling the
     public feature-voting page.

7. Add the GitHub Actions secret `GRADWINDOW_NOTIFY_API_KEY` with the same
   value as Worker `ADMIN_API_KEY`.

The next successful site build publishes the configured form. Run the
`Notify subscribers` workflow manually once for an end-to-end check.

## Feature voting

`/roadmap` serves the public roadmap API. It uses a random browser identifier
stored by the website, then stores only an HMAC hash of that identifier in D1.
The `roadmap_votes` primary key makes one browser identifier eligible for one
vote per proposal. The Worker also hashes the request IP only for short-lived
rate limiting; it never stores a raw IP address.

Run the schema command in step 2 again after pulling this update. It is
idempotent and adds the roadmap tables plus the initial GradWindow proposals.
Owner proposals, status, and progress can be updated in D1 without a new site
deployment, for example:

```powershell
npx wrangler d1 execute gradwindow-subscribers --remote --command "UPDATE roadmap_proposals SET progress = 60, status = 'in_progress' WHERE id = 'application-planner'"
```

Community suggestions are published immediately, intentionally shown in a
collapsed section, and can be hidden by setting `hidden_at` to an ISO timestamp.
Keep `TURNSTILE_SECRET_KEY` configured before enabling public submissions.

## Operational rules

- Never print subscriber rows or decrypted addresses in logs.
- Enable MFA and restrict Cloudflare and Resend account access.
- Back up encryption keys in a password manager.
- Update `privacy.html` with a private operator contact and jurisdiction before
  accepting production subscriptions.
- Review bounce and complaint webhooks before sending at larger volume.
