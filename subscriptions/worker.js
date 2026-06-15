import {
  allowedOrigin,
  decryptEmail,
  encryptEmail,
  hmacHex,
  normalizeEmail,
  normalizeLanguage,
  randomToken,
  sha256Hex,
  signedUnsubscribeToken,
  verifyUnsubscribeToken,
} from "./core.js";

const JSON_HEADERS = { "Content-Type": "application/json; charset=utf-8" };
const MAX_EVENTS = 20;
const MAX_SENDS_PER_REQUEST = 80;

function corsHeaders(request, env) {
  const origin = allowedOrigin(
    request.headers.get("Origin"),
    env.ALLOWED_ORIGINS,
  );
  return origin
    ? {
        "Access-Control-Allow-Origin": origin,
        "Access-Control-Allow-Headers": "Content-Type, Authorization",
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        Vary: "Origin",
      }
    : {};
}

function jsonResponse(request, env, body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { ...JSON_HEADERS, ...corsHeaders(request, env) },
  });
}

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

async function verifyTurnstile(token, env) {
  if (!env.TURNSTILE_SECRET_KEY) return true;
  if (!token) return false;
  const response = await fetch(
    "https://challenges.cloudflare.com/turnstile/v0/siteverify",
    {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({
        secret: env.TURNSTILE_SECRET_KEY,
        response: token,
      }),
    },
  );
  const result = await response.json();
  return result.success === true;
}

async function sendEmail(env, { to, subject, html, text, headers = {} }) {
  const response = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.RESEND_API_KEY}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      from: env.RESEND_FROM,
      to: [to],
      subject,
      html,
      text,
      headers,
    }),
  });
  if (!response.ok) throw new Error(`email provider returned ${response.status}`);
}

function confirmationEmail(language, confirmationUrl) {
  if (language === "zh") {
    return {
      subject: "确认订阅 GradWindow 申请开放提醒",
      text: `请点击以下链接确认订阅：${confirmationUrl}\n\n如果不是你提交的邮箱，请忽略本邮件。`,
      html: `<p>请点击下方链接确认订阅 GradWindow 申请开放提醒：</p>
        <p><a href="${escapeHtml(confirmationUrl)}">确认订阅</a></p>
        <p>如果不是你提交的邮箱，请忽略本邮件。</p>`,
    };
  }
  return {
    subject: "Confirm your GradWindow application alerts",
    text: `Confirm your subscription: ${confirmationUrl}\n\nIf you did not request this, ignore this email.`,
    html: `<p>Confirm your GradWindow application-opening alerts:</p>
      <p><a href="${escapeHtml(confirmationUrl)}">Confirm subscription</a></p>
      <p>If you did not request this, ignore this email.</p>`,
  };
}

async function subscribe(request, env) {
  const origin = request.headers.get("Origin");
  if (!allowedOrigin(origin, env.ALLOWED_ORIGINS)) {
    return jsonResponse(request, env, { ok: false }, 403);
  }
  let payload;
  try {
    payload = await request.json();
  } catch {
    return jsonResponse(request, env, { ok: false }, 400);
  }
  if (payload.consent !== true) {
    return jsonResponse(request, env, { ok: false }, 400);
  }
  if (!(await verifyTurnstile(payload.turnstileToken, env))) {
    return jsonResponse(request, env, { ok: false }, 400);
  }
  let email;
  try {
    email = normalizeEmail(payload.email);
  } catch {
    return jsonResponse(request, env, { ok: false }, 400);
  }
  const language = normalizeLanguage(payload.language);
  const emailHash = await hmacHex(env.EMAIL_INDEX_KEY, email);
  const existing = await env.DB.prepare(
    `SELECT status, confirmation_expires_at
     FROM subscribers WHERE email_hash = ?1`,
  ).bind(emailHash).first();
  if (existing?.status === "active") {
    return jsonResponse(request, env, { ok: true });
  }
  const resendCutoff = new Date(Date.now() + 23 * 60 * 60 * 1000);
  if (
    existing?.status === "pending" &&
    existing.confirmation_expires_at &&
    new Date(existing.confirmation_expires_at) > resendCutoff
  ) {
    return jsonResponse(request, env, { ok: true });
  }

  const encrypted = await encryptEmail(email, env.EMAIL_ENCRYPTION_KEY);
  const confirmationToken = randomToken();
  const tokenHash = await sha256Hex(confirmationToken);
  const now = new Date();
  const expires = new Date(now.getTime() + 24 * 60 * 60 * 1000);
  await env.DB.prepare(
    `INSERT INTO subscribers (
       email_hash, email_ciphertext, email_iv, language, status,
       confirmation_token_hash, confirmation_expires_at, created_at,
       confirmed_at, unsubscribed_at
     ) VALUES (?1, ?2, ?3, ?4, 'pending', ?5, ?6, ?7, NULL, NULL)
     ON CONFLICT(email_hash) DO UPDATE SET
       email_ciphertext = excluded.email_ciphertext,
       email_iv = excluded.email_iv,
       language = excluded.language,
       status = 'pending',
       confirmation_token_hash = excluded.confirmation_token_hash,
       confirmation_expires_at = excluded.confirmation_expires_at,
       unsubscribed_at = NULL`,
  ).bind(
    emailHash,
    encrypted.ciphertext,
    encrypted.iv,
    language,
    tokenHash,
    expires.toISOString(),
    now.toISOString(),
  ).run();

  const confirmationUrl =
    `${env.API_BASE_URL.replace(/\/$/, "")}/confirm?token=` +
    encodeURIComponent(confirmationToken);
  await sendEmail(env, {
    to: email,
    ...confirmationEmail(language, confirmationUrl),
  });
  return jsonResponse(request, env, { ok: true });
}

async function confirm(request, env, url) {
  const token = url.searchParams.get("token") || "";
  const tokenHash = await sha256Hex(token);
  const subscriber = await env.DB.prepare(
    `SELECT email_hash FROM subscribers
     WHERE status = 'pending'
       AND confirmation_token_hash = ?1
       AND confirmation_expires_at > ?2`,
  ).bind(tokenHash, new Date().toISOString()).first();
  if (!subscriber) {
    return Response.redirect(
      `${env.PUBLIC_SITE_URL}/?subscription=invalid#subscribe`,
      302,
    );
  }
  await env.DB.prepare(
    `UPDATE subscribers SET
       status = 'active',
       confirmed_at = ?2,
       confirmation_token_hash = NULL,
       confirmation_expires_at = NULL
     WHERE email_hash = ?1`,
  ).bind(subscriber.email_hash, new Date().toISOString()).run();
  return Response.redirect(
    `${env.PUBLIC_SITE_URL}/?subscription=confirmed#subscribe`,
    302,
  );
}

async function unsubscribe(env, url) {
  const emailHash = await verifyUnsubscribeToken(
    url.searchParams.get("token"),
    env.TOKEN_SIGNING_KEY,
  );
  if (emailHash) {
    await env.DB.prepare(
      `UPDATE subscribers SET
         status = 'unsubscribed',
         email_ciphertext = NULL,
         email_iv = NULL,
         confirmation_token_hash = NULL,
         confirmation_expires_at = NULL,
         unsubscribed_at = ?2
       WHERE email_hash = ?1`,
    ).bind(emailHash, new Date().toISOString()).run();
  }
  return new Response(
    `<!doctype html><meta charset="utf-8"><title>GradWindow</title>
     <main style="max-width:640px;margin:80px auto;font:16px/1.7 system-ui;padding:20px">
     <h1>Unsubscribed / 已退订</h1>
     <p>You will no longer receive GradWindow alerts.</p>
     <p>你将不再收到 GradWindow 邮件提醒。</p>
     <p><a href="${escapeHtml(env.PUBLIC_SITE_URL)}">Return to GradWindow</a></p>
     </main>`,
    { headers: { "Content-Type": "text/html; charset=utf-8" } },
  );
}

function alertEmail(language, event, unsubscribeUrl) {
  const school = language === "zh" && event.schoolZh
    ? event.schoolZh
    : event.school;
  const subject = language === "zh"
    ? `${school} 的申请现已开放`
    : `${school} applications are now open`;
  const lines = [
    `${school} — ${event.program}`,
    `${event.opensAt} → ${event.closesAt}`,
    event.applicationUrl,
  ];
  const intro = language === "zh"
    ? "GradWindow 新核验的官网申请窗口现已开放："
    : "A newly verified official application window is now open:";
  return {
    subject,
    text: `${intro}\n\n${lines.join("\n")}\n\nUnsubscribe: ${unsubscribeUrl}`,
    html: `<p>${escapeHtml(intro)}</p>
      <h2>${escapeHtml(school)}</h2>
      <p>${escapeHtml(event.program)}</p>
      <p><strong>${escapeHtml(event.opensAt)}</strong> → <strong>${escapeHtml(event.closesAt)}</strong></p>
      <p><a href="${escapeHtml(event.applicationUrl)}">Open application / 打开申请</a></p>
      <p><a href="${escapeHtml(event.sourceUrl)}">Official source / 官网来源</a></p>
      <hr><p style="font-size:12px"><a href="${escapeHtml(unsubscribeUrl)}">Unsubscribe / 退订</a></p>`,
  };
}

function validEvent(event) {
  return (
    event &&
    typeof event.id === "string" &&
    typeof event.school === "string" &&
    typeof event.program === "string" &&
    /^\d{4}-\d{2}-\d{2}$/.test(event.opensAt || "") &&
    /^\d{4}-\d{2}-\d{2}$/.test(event.closesAt || "") &&
    /^https:\/\//.test(event.applicationUrl || "") &&
    /^https:\/\//.test(event.sourceUrl || "")
  );
}

async function notify(request, env) {
  if (request.headers.get("Authorization") !== `Bearer ${env.ADMIN_API_KEY}`) {
    return jsonResponse(request, env, { ok: false }, 401);
  }
  const payload = await request.json();
  const events = Array.isArray(payload.events) ? payload.events : [];
  if (!events.length || events.length > MAX_EVENTS || !events.every(validEvent)) {
    return jsonResponse(request, env, { ok: false }, 400);
  }

  let sent = 0;
  let failed = 0;
  for (const event of events) {
    const eventKey = `${event.id}:${event.opensAt}`;
    await env.DB.prepare(
      `INSERT OR IGNORE INTO notification_events
       (event_key, payload_json, discovered_at) VALUES (?1, ?2, ?3)`,
    ).bind(eventKey, JSON.stringify(event), new Date().toISOString()).run();
    const storedEvent = await env.DB.prepare(
      "SELECT discovered_at FROM notification_events WHERE event_key = ?1",
    ).bind(eventKey).first();
    const subscribers = await env.DB.prepare(
      `SELECT s.email_hash, s.email_ciphertext, s.email_iv, s.language
       FROM subscribers s
       LEFT JOIN deliveries d
         ON d.email_hash = s.email_hash AND d.event_key = ?1
       WHERE s.status = 'active'
         AND s.confirmed_at <= ?2
         AND d.event_key IS NULL
       LIMIT ?3`,
    ).bind(
      eventKey,
      storedEvent.discovered_at,
      MAX_SENDS_PER_REQUEST - sent,
    ).all();

    for (const subscriber of subscribers.results || []) {
      if (sent >= MAX_SENDS_PER_REQUEST) break;
      try {
        const email = await decryptEmail(
          subscriber.email_ciphertext,
          subscriber.email_iv,
          env.EMAIL_ENCRYPTION_KEY,
        );
        const unsubscribeToken = await signedUnsubscribeToken(
          subscriber.email_hash,
          env.TOKEN_SIGNING_KEY,
        );
        const unsubscribeUrl =
          `${env.API_BASE_URL.replace(/\/$/, "")}/unsubscribe?token=` +
          encodeURIComponent(unsubscribeToken);
        await sendEmail(env, {
          to: email,
          headers: {
            "List-Unsubscribe": `<${unsubscribeUrl}>`,
            "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
          },
          ...alertEmail(subscriber.language, event, unsubscribeUrl),
        });
        await env.DB.prepare(
          `INSERT OR IGNORE INTO deliveries
           (event_key, email_hash, sent_at) VALUES (?1, ?2, ?3)`,
        ).bind(eventKey, subscriber.email_hash, new Date().toISOString()).run();
        sent += 1;
      } catch {
        failed += 1;
      }
    }
  }
  return jsonResponse(request, env, { ok: true, sent, failed });
}

async function cleanup(env) {
  const now = new Date();
  const stalePending = new Date(now.getTime() - 7 * 86400_000).toISOString();
  const staleUnsubscribed = new Date(now.getTime() - 30 * 86400_000).toISOString();
  await env.DB.batch([
    env.DB.prepare(
      `DELETE FROM subscribers
       WHERE status = 'pending' AND created_at < ?1`,
    ).bind(stalePending),
    env.DB.prepare(
      `DELETE FROM subscribers
       WHERE status = 'unsubscribed' AND unsubscribed_at < ?1`,
    ).bind(staleUnsubscribed),
  ]);
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (request.method === "OPTIONS") {
      return new Response(null, {
        status: 204,
        headers: corsHeaders(request, env),
      });
    }
    if (request.method === "GET" && url.pathname === "/health") {
      return new Response("ok");
    }
    if (request.method === "POST" && url.pathname === "/subscribe") {
      return subscribe(request, env);
    }
    if (request.method === "GET" && url.pathname === "/confirm") {
      return confirm(request, env, url);
    }
    if (
      ["GET", "POST"].includes(request.method) &&
      url.pathname === "/unsubscribe"
    ) {
      return unsubscribe(env, url);
    }
    if (request.method === "POST" && url.pathname === "/admin/notify") {
      return notify(request, env);
    }
    return new Response("Not found", { status: 404 });
  },
  async scheduled(_controller, env) {
    await cleanup(env);
  },
};
