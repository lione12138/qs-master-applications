# GradWindow email subscriptions

This Worker provides privacy-preserving, double-opt-in email alerts for newly
opened official application windows. It also backs the public roadmap, school
comments, and the lightweight GradWindow account system.

## Privacy design

- The public site sends email addresses directly to the Worker over HTTPS.
- Email addresses never enter GitHub, static files, analytics, or browser storage.
- D1 stores an AES-GCM encrypted address plus a keyed HMAC lookup value.
- Confirmation tokens are stored only as SHA-256 hashes.
- Unsubscribe URLs contain a keyed signature, not an email address.
- Unsubscribing immediately removes the encrypted email value.
- The database intentionally does not store subscriber IP addresses.
- Resend open and click tracking must remain disabled.
- Accounts use short-lived email login codes and opaque session tokens. The
  Worker stores session hashes, not raw session tokens.
- School comments require a signed-in account. Public comments show the user's
  display name, not their email address.

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
   five times for `EMAIL_INDEX_KEY`, `TOKEN_SIGNING_KEY`, `ADMIN_API_KEY`,
   `ROADMAP_VOTER_HASH_KEY`, and `AUTH_SECRET_KEY`.

4. Store secrets with Wrangler. Never commit their values:

   ```powershell
   npx wrangler secret put EMAIL_ENCRYPTION_KEY --config subscriptions/wrangler.toml
   npx wrangler secret put EMAIL_INDEX_KEY --config subscriptions/wrangler.toml
   npx wrangler secret put TOKEN_SIGNING_KEY --config subscriptions/wrangler.toml
   npx wrangler secret put ADMIN_API_KEY --config subscriptions/wrangler.toml
   npx wrangler secret put RESEND_API_KEY --config subscriptions/wrangler.toml
   npx wrangler secret put TURNSTILE_SECRET_KEY --config subscriptions/wrangler.toml
   npx wrangler secret put ROADMAP_VOTER_HASH_KEY --config subscriptions/wrangler.toml
   npx wrangler secret put AUTH_SECRET_KEY --config subscriptions/wrangler.toml
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

### Roadmap-only quick start

The voting page can be deployed without accounts, a custom domain, or the
email-alert service. You only need Cloudflare Workers, D1, Turnstile, and the
two public GitHub Actions variables below.

1. Install Node.js 20+ and authenticate Wrangler once:

   ```powershell
   npx wrangler login
   ```

2. Copy the Worker configuration and create the database:

   ```powershell
   Copy-Item subscriptions/wrangler.toml.example subscriptions/wrangler.toml
   npx wrangler d1 create gradwindow-subscribers
   ```

   Copy the returned `database_id` into `subscriptions/wrangler.toml`.
   Keep `ALLOWED_ORIGINS` as `https://lione12138.github.io` and
   `PUBLIC_SITE_URL` as `https://lione12138.github.io/qs-master-applications`.

3. Create a Turnstile widget in **Cloudflare Dashboard -> Turnstile**. Use the
   managed widget type and add `lione12138.github.io` as its hostname. Keep the
   site key for GitHub and the secret key for the Worker.

4. Apply the schema and set the two Worker secrets required for public voting:

   ```powershell
   npx wrangler d1 execute gradwindow-subscribers --remote --file subscriptions/schema.sql --config subscriptions/wrangler.toml
   python -c "import secrets; print(secrets.token_urlsafe(48))"
   npx wrangler secret put ROADMAP_VOTER_HASH_KEY --config subscriptions/wrangler.toml
   npx wrangler secret put TURNSTILE_SECRET_KEY --config subscriptions/wrangler.toml
   ```

   Paste the generated random value into the first secret prompt. Paste the
   Turnstile secret key into the second. Do not commit `wrangler.toml` or either
   secret.

5. Deploy the Worker:

   ```powershell
   npx wrangler deploy --config subscriptions/wrangler.toml
   ```

   Wrangler prints a `https://...workers.dev` URL. This is the Worker URL.

6. In **GitHub -> repository Settings -> Secrets and variables -> Actions ->
   Variables**, add:

   - `GRADWINDOW_ROADMAP_URL`: the Worker URL from step 5
   - `GRADWINDOW_TURNSTILE_SITE_KEY`: the public site key from step 3

   Both are repository variables, not GitHub secrets. Push to `main` or run the
   `Tests` workflow manually. The successful build injects both values into the
   GitHub Pages artifact.

7. Check the Worker and then open `roadmap.html` on the live site:

   ```powershell
   Invoke-WebRequest https://YOUR-WORKER.workers.dev/health
   ```

   It should return `ok`. A vote should immediately update its count; a user
   suggestion should appear in the collapsed community section.

The Worker records an HMAC of a browser-local random identifier, not the raw
identifier. A user can evade that by clearing browser storage or switching
browsers, so it is paired with short-lived hashed-IP rate limits. It is a
practical anti-abuse control for an anonymous public roadmap, not identity
verification.

`/roadmap` serves the public roadmap API. It uses a random browser identifier
stored by the website, then stores only an HMAC hash of that identifier in D1.
The `roadmap_votes` primary key makes one browser identifier eligible for one
vote per proposal. The Worker also hashes the request IP only for short-lived
rate limiting; it never stores a raw IP address.

Run the schema command in step 2 again after pulling this update. It is
idempotent and adds the roadmap, account, session, favourite, and comment
tables plus the initial GradWindow proposals.
Owner proposals, status, and progress can be updated in D1 without a new site
deployment, for example:

```powershell
npx wrangler d1 execute gradwindow-subscribers --remote --command "UPDATE roadmap_proposals SET progress = 60, status = 'in_progress' WHERE id = 'account-login-and-favorites'"
```

Community suggestions are published immediately, intentionally shown in a
collapsed section, and can be hidden by setting `hidden_at` to an ISO timestamp.
Keep `TURNSTILE_SECRET_KEY` configured before enabling public submissions.

The unlisted `admin.html` page reads aggregate vote statistics from
`GET /admin/roadmap/stats`. Configure a separate long random key before using
it; the page keeps the key in memory only and never exposes voter hashes:

```powershell
npx wrangler secret put ROADMAP_ADMIN_API_KEY --config subscriptions/wrangler.toml
```

## Accounts and comments

Accounts are passwordless. A user enters an email address, receives a six-digit
code, and the Worker returns an opaque session token after verification. The
static site stores that token in browser local storage and sends it as a Bearer
token to account-only endpoints.

Account endpoints:

- `POST /auth/request`: send an email login code.
- `POST /auth/verify`: verify the code and create a 30-day session.
- `POST /auth/logout`: revoke the current session.
- `GET /me`: return the public profile and synced favourites.
- `PATCH /me`: update display name, language, country/region, and target
  intake.
- `PUT /me/favorites`: replace the signed-in user's favourite item keys.

School comments remain publicly readable, but posting now requires a valid
session. Run the schema command again before deploying this Worker version:

```powershell
npx wrangler d1 execute gradwindow-subscribers --remote --file subscriptions/schema.sql --config subscriptions/wrangler.toml
npx wrangler deploy --config subscriptions/wrangler.toml
```

## Operational rules

- Never print subscriber rows or decrypted addresses in logs.
- Enable MFA and restrict Cloudflare and Resend account access.
- Back up encryption keys in a password manager.
- Update `privacy.html` with a private operator contact and jurisdiction before
  accepting production subscriptions.
- Review bounce and complaint webhooks before sending at larger volume.
