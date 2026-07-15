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
const AUTH_CODE_TTL_MS = 10 * 60 * 1000;
const AUTH_SESSION_TTL_MS = 30 * 24 * 60 * 60 * 1000;

function corsHeaders(request, env) {
  const origin = allowedOrigin(
    request.headers.get("Origin"),
    env.ALLOWED_ORIGINS,
  );
  return origin
    ? {
        "Access-Control-Allow-Origin": origin,
        "Access-Control-Allow-Headers": "Content-Type, Authorization, X-GradWindow-Visitor",
        "Access-Control-Allow-Methods": "GET, POST, PATCH, PUT, OPTIONS",
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

function normalizeVisitorId(value) {
  const visitorId = String(value || "").trim();
  if (!/^[A-Za-z0-9-]{16,160}$/.test(visitorId)) {
    throw new Error("invalid visitor");
  }
  return visitorId;
}

function normalizeProposalText(value, maxLength, required = true) {
  const text = String(value || "")
    .replace(/[\u0000-\u001f\u007f]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  if ((required && text.length < 4) || text.length > maxLength) {
    throw new Error("invalid proposal text");
  }
  return text;
}

function normalizeUniversityId(value) {
  const universityId = String(value || "").trim();
  if (!/^[a-z0-9-]{2,180}$/.test(universityId)) {
    throw new Error("invalid university");
  }
  return universityId;
}

function normalizeCommentText(value, maxLength, required = true) {
  const text = String(value || "")
    .replace(/[\u0000-\u001f\u007f]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  if ((required && text.length < 2) || text.length > maxLength) {
    throw new Error("invalid comment text");
  }
  return text;
}

function normalizeProfileText(value, maxLength) {
  const text = String(value || "")
    .replace(/[\u0000-\u001f\u007f]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  if (text.length > maxLength) throw new Error("invalid profile text");
  return text;
}

function normalizeFavoriteKey(value) {
  const itemKey = String(value || "").trim();
  if (!/^(window|university):[A-Za-z0-9._:-]{2,220}$/.test(itemKey)) {
    throw new Error("invalid favorite");
  }
  return itemKey;
}

function authSecret(env) {
  return env.AUTH_SECRET_KEY || env.TOKEN_SIGNING_KEY || env.ROADMAP_VOTER_HASH_KEY;
}

function publicUser(row) {
  return {
    id: row.id,
    displayName: row.display_name || "",
    language: row.language || "en",
    country: row.country || "",
    targetIntake: row.target_intake || "",
  };
}

function randomSixDigitCode() {
  const value = crypto.getRandomValues(new Uint32Array(1))[0] % 1_000_000;
  return String(value).padStart(6, "0");
}

async function authCodeEmail(language, code) {
  if (language === "zh") {
    return {
      subject: "你的 GradWindow 登录验证码",
      text: `你的 GradWindow 登录验证码是：${code}\n\n验证码 10 分钟内有效。如果不是你本人操作，请忽略本邮件。`,
      html: `<p>你的 GradWindow 登录验证码是：</p>
        <p style="font-size:28px;font-weight:700;letter-spacing:0.12em">${escapeHtml(code)}</p>
        <p>验证码 10 分钟内有效。如果不是你本人操作，请忽略本邮件。</p>`,
    };
  }
  return {
    subject: "Your GradWindow login code",
    text: `Your GradWindow login code is: ${code}\n\nThis code expires in 10 minutes. If you did not request it, ignore this email.`,
    html: `<p>Your GradWindow login code is:</p>
      <p style="font-size:28px;font-weight:700;letter-spacing:0.12em">${escapeHtml(code)}</p>
      <p>This code expires in 10 minutes. If you did not request it, ignore this email.</p>`,
  };
}

async function sessionUser(request, env) {
  const header = request.headers.get("Authorization") || "";
  const match = header.match(/^Bearer\s+(.+)$/i);
  if (!match || !authSecret(env)) return null;
  const sessionHash = await sha256Hex(match[1]);
  const row = await env.DB.prepare(
    `SELECT u.id, u.display_name, u.language, u.country, u.target_intake
       FROM auth_sessions s
       JOIN users u ON u.id = s.user_id
      WHERE s.session_hash = ?1
        AND s.expires_at > ?2`,
  ).bind(sessionHash, new Date().toISOString()).first();
  return row || null;
}

async function requireUser(request, env) {
  const user = await sessionUser(request, env);
  if (!user) return null;
  return user;
}

async function consumeRoadmapRateLimit(env, scope, keyHash, maximum, windowMs) {
  const bucket = Math.floor(Date.now() / windowMs);
  const current = await env.DB.prepare(
    `SELECT count FROM roadmap_rate_limits
     WHERE scope = ?1 AND key_hash = ?2 AND bucket = ?3`,
  ).bind(scope, keyHash, bucket).first();
  if ((current?.count || 0) >= maximum) return false;
  await env.DB.prepare(
    `INSERT INTO roadmap_rate_limits (scope, key_hash, bucket, count, updated_at)
     VALUES (?1, ?2, ?3, 1, ?4)
     ON CONFLICT(scope, key_hash, bucket) DO UPDATE SET
       count = count + 1,
       updated_at = excluded.updated_at`,
  ).bind(scope, keyHash, bucket, new Date().toISOString()).run();
  return true;
}

async function roadmapIdentity(request, env, payload = {}) {
  if (!env.ROADMAP_VOTER_HASH_KEY) throw new Error("roadmap unavailable");
  const visitorId = normalizeVisitorId(
    payload.visitorId || request.headers.get("X-GradWindow-Visitor"),
  );
  const visitorHash = await hmacHex(env.ROADMAP_VOTER_HASH_KEY, visitorId);
  const ip = request.headers.get("CF-Connecting-IP") || "";
  const ipHash = ip ? await hmacHex(env.ROADMAP_VOTER_HASH_KEY, ip) : "";
  return { visitorHash, ipHash };
}

function roadmapProposal(row) {
  return {
    id: row.id,
    source: row.source,
    title: { en: row.title_en, zh: row.title_zh || row.title_en },
    description: {
      en: row.description_en || "",
      zh: row.description_zh || row.description_en || "",
    },
    status: row.status || "planned",
    progress: row.progress || 0,
    votes: Number(row.votes || 0),
    viewerVoted: Boolean(row.viewer_voted),
  };
}

async function listRoadmap(request, env) {
  let visitorHash = "";
  try {
    visitorHash = (await roadmapIdentity(request, env)).visitorHash;
  } catch {
    return jsonResponse(request, env, { ok: false }, 400);
  }
  const rows = await env.DB.prepare(
    `SELECT p.id, p.source, p.title_en, p.title_zh, p.description_en,
            p.description_zh, p.status, p.progress,
            COUNT(v.proposal_id) AS votes,
            MAX(CASE WHEN v.visitor_hash = ?1 THEN 1 ELSE 0 END) AS viewer_voted
       FROM roadmap_proposals p
       LEFT JOIN roadmap_votes v ON v.proposal_id = p.id
      WHERE p.hidden_at IS NULL
      GROUP BY p.id
      ORDER BY CASE p.source WHEN 'owner' THEN 0 ELSE 1 END,
               votes DESC, p.created_at ASC`,
  ).bind(visitorHash).all();
  return jsonResponse(request, env, {
    proposals: (rows.results || []).map(roadmapProposal),
  });
}

async function roadmapAdminStats(request, env) {
  const expected = String(env.ROADMAP_ADMIN_API_KEY || "").trim();
  if (
    !expected ||
    request.headers.get("Authorization") !== `Bearer ${expected}`
  ) {
    return jsonResponse(request, env, { ok: false }, 401);
  }
  const [summary, proposals] = await Promise.all([
    env.DB.prepare(
      `SELECT COUNT(v.proposal_id) AS total_votes,
              COUNT(DISTINCT v.visitor_hash) AS unique_voters,
              MIN(v.created_at) AS first_vote_at,
              MAX(v.created_at) AS last_vote_at
         FROM roadmap_proposals p
         LEFT JOIN roadmap_votes v ON v.proposal_id = p.id
        WHERE p.hidden_at IS NULL`,
    ).first(),
    env.DB.prepare(
      `SELECT p.id, p.source, p.title_en, p.title_zh,
              COUNT(v.proposal_id) AS votes,
              MIN(v.created_at) AS first_vote_at,
              MAX(v.created_at) AS last_vote_at
         FROM roadmap_proposals p
         LEFT JOIN roadmap_votes v ON v.proposal_id = p.id
        WHERE p.hidden_at IS NULL
        GROUP BY p.id
        ORDER BY votes DESC, p.created_at ASC`,
    ).all(),
  ]);
  const response = jsonResponse(request, env, {
    summary: {
      totalVotes: Number(summary?.total_votes || 0),
      uniqueVoters: Number(summary?.unique_voters || 0),
      firstVoteAt: summary?.first_vote_at || null,
      lastVoteAt: summary?.last_vote_at || null,
    },
    proposals: (proposals.results || []).map((row) => ({
      id: row.id,
      title: { en: row.title_en, zh: row.title_zh || row.title_en },
      source: row.source,
      votes: Number(row.votes || 0),
      firstVoteAt: row.first_vote_at || null,
      lastVoteAt: row.last_vote_at || null,
    })),
  });
  response.headers.set("Cache-Control", "private, no-store");
  return response;
}

async function voteForRoadmapProposal(request, env) {
  if (!allowedOrigin(request.headers.get("Origin"), env.ALLOWED_ORIGINS)) {
    return jsonResponse(request, env, { ok: false }, 403);
  }
  let payload;
  try {
    payload = await request.json();
  } catch {
    return jsonResponse(request, env, { ok: false }, 400);
  }
  const proposalId = String(payload.proposalId || "");
  if (!/^[a-z0-9-]{3,100}$/.test(proposalId)) {
    return jsonResponse(request, env, { ok: false }, 400);
  }
  let identity;
  try {
    identity = await roadmapIdentity(request, env, payload);
  } catch {
    return jsonResponse(request, env, { ok: false }, 400);
  }
  const [visitorAllowed, ipAllowed] = await Promise.all([
    consumeRoadmapRateLimit(env, "vote-visitor", identity.visitorHash, 20, 60 * 60_000),
    identity.ipHash
      ? consumeRoadmapRateLimit(env, "vote-ip", identity.ipHash, 100, 60 * 60_000)
      : true,
  ]);
  if (!visitorAllowed || !ipAllowed) return jsonResponse(request, env, { ok: false }, 429);
  try {
    await env.DB.prepare(
      `INSERT INTO roadmap_votes (proposal_id, visitor_hash, created_at)
       SELECT id, ?2, ?3 FROM roadmap_proposals
        WHERE id = ?1 AND hidden_at IS NULL`,
    ).bind(proposalId, identity.visitorHash, new Date().toISOString()).run();
    const vote = await env.DB.prepare(
      `SELECT 1 FROM roadmap_votes WHERE proposal_id = ?1 AND visitor_hash = ?2`,
    ).bind(proposalId, identity.visitorHash).first();
    if (!vote) return jsonResponse(request, env, { ok: false }, 404);
  } catch {
    return jsonResponse(request, env, { ok: false, duplicate: true }, 409);
  }
  return jsonResponse(request, env, { ok: true });
}

async function createRoadmapProposal(request, env) {
  if (!allowedOrigin(request.headers.get("Origin"), env.ALLOWED_ORIGINS)) {
    return jsonResponse(request, env, { ok: false }, 403);
  }
  let payload;
  try {
    payload = await request.json();
  } catch {
    return jsonResponse(request, env, { ok: false }, 400);
  }
  if (!(await verifyTurnstile(payload.turnstileToken, env))) {
    return jsonResponse(request, env, { ok: false }, 400);
  }
  let identity;
  let title;
  let description;
  try {
    identity = await roadmapIdentity(request, env, payload);
    title = normalizeProposalText(payload.title, 100);
    description = normalizeProposalText(payload.description, 400, false);
  } catch {
    return jsonResponse(request, env, { ok: false }, 400);
  }
  const [visitorAllowed, ipAllowed] = await Promise.all([
    consumeRoadmapRateLimit(env, "proposal-visitor", identity.visitorHash, 3, 24 * 60 * 60_000),
    identity.ipHash
      ? consumeRoadmapRateLimit(env, "proposal-ip", identity.ipHash, 12, 24 * 60 * 60_000)
      : true,
  ]);
  if (!visitorAllowed || !ipAllowed) return jsonResponse(request, env, { ok: false }, 429);
  const id = `community-${crypto.randomUUID().replaceAll("-", "")}`;
  const now = new Date().toISOString();
  await env.DB.prepare(
    `INSERT INTO roadmap_proposals (
       id, source, title_en, title_zh, description_en, description_zh,
       status, progress, created_at, hidden_at
     ) VALUES (?1, 'community', ?2, ?2, ?3, ?3, 'planned', 0, ?4, NULL)`,
  ).bind(id, title, description, now).run();
  return jsonResponse(request, env, { ok: true, id });
}

async function requestAuthCode(request, env) {
  const origin = request.headers.get("Origin");
  if (!allowedOrigin(origin, env.ALLOWED_ORIGINS)) {
    return jsonResponse(request, env, { ok: false }, 403);
  }
  if (!authSecret(env)) return jsonResponse(request, env, { ok: false }, 503);
  let payload;
  try {
    payload = await request.json();
  } catch {
    return jsonResponse(request, env, { ok: false }, 400);
  }
  if (payload.turnstileToken && !(await verifyTurnstile(payload.turnstileToken, env))) {
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
  const ip = request.headers.get("CF-Connecting-IP") || "";
  const ipHash = ip && env.ROADMAP_VOTER_HASH_KEY
    ? await hmacHex(env.ROADMAP_VOTER_HASH_KEY, ip)
    : "";
  const [emailAllowed, ipAllowed] = await Promise.all([
    consumeRoadmapRateLimit(env, "auth-email", emailHash, 5, 60 * 60_000),
    ipHash ? consumeRoadmapRateLimit(env, "auth-ip", ipHash, 30, 60 * 60_000) : true,
  ]);
  if (!emailAllowed || !ipAllowed) {
    return jsonResponse(request, env, { ok: false }, 429);
  }
  const recent = await env.DB.prepare(
    `SELECT created_at FROM auth_login_codes
      WHERE email_hash = ?1
      ORDER BY created_at DESC
      LIMIT 1`,
  ).bind(emailHash).first();
  if (recent?.created_at && Date.now() - new Date(recent.created_at).getTime() < 60_000) {
    return jsonResponse(request, env, { ok: true });
  }
  const encrypted = await encryptEmail(email, env.EMAIL_ENCRYPTION_KEY);
  const code = randomSixDigitCode();
  const now = new Date();
  const expires = new Date(now.getTime() + AUTH_CODE_TTL_MS);
  const codeHash = await hmacHex(authSecret(env), `${emailHash}:${code}`);
  await env.DB.prepare(
    `INSERT INTO auth_login_codes (
       id, email_hash, email_ciphertext, email_iv, language, code_hash,
       expires_at, consumed_at, created_at
     ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, NULL, ?8)`,
  ).bind(
    `code-${crypto.randomUUID().replaceAll("-", "")}`,
    emailHash,
    encrypted.ciphertext,
    encrypted.iv,
    language,
    codeHash,
    expires.toISOString(),
    now.toISOString(),
  ).run();
  await sendEmail(env, {
    to: email,
    ...(await authCodeEmail(language, code)),
  });
  return jsonResponse(request, env, { ok: true });
}

async function verifyAuthCode(request, env) {
  const origin = request.headers.get("Origin");
  if (!allowedOrigin(origin, env.ALLOWED_ORIGINS)) {
    return jsonResponse(request, env, { ok: false }, 403);
  }
  if (!authSecret(env)) return jsonResponse(request, env, { ok: false }, 503);
  let payload;
  try {
    payload = await request.json();
  } catch {
    return jsonResponse(request, env, { ok: false }, 400);
  }
  let email;
  const code = String(payload.code || "").replace(/\D/g, "");
  if (code.length !== 6) return jsonResponse(request, env, { ok: false }, 400);
  try {
    email = normalizeEmail(payload.email);
  } catch {
    return jsonResponse(request, env, { ok: false }, 400);
  }
  const emailHash = await hmacHex(env.EMAIL_INDEX_KEY, email);
  const codeHash = await hmacHex(authSecret(env), `${emailHash}:${code}`);
  const now = new Date().toISOString();
  const challenge = await env.DB.prepare(
    `SELECT id, email_ciphertext, email_iv, language
       FROM auth_login_codes
      WHERE email_hash = ?1
        AND code_hash = ?2
        AND consumed_at IS NULL
        AND expires_at > ?3
      ORDER BY created_at DESC
      LIMIT 1`,
  ).bind(emailHash, codeHash, now).first();
  if (!challenge) return jsonResponse(request, env, { ok: false }, 400);

  const userId = `user-${crypto.randomUUID().replaceAll("-", "")}`;
  await env.DB.prepare(
    `INSERT INTO users (
       id, email_hash, email_ciphertext, email_iv, display_name,
       language, country, target_intake, created_at, updated_at
     ) VALUES (?1, ?2, ?3, ?4, NULL, ?5, NULL, NULL, ?6, ?6)
     ON CONFLICT(email_hash) DO UPDATE SET
       email_ciphertext = excluded.email_ciphertext,
       email_iv = excluded.email_iv,
       language = excluded.language,
       updated_at = excluded.updated_at`,
  ).bind(
    userId,
    emailHash,
    challenge.email_ciphertext,
    challenge.email_iv,
    challenge.language,
    now,
  ).run();
  await env.DB.prepare(
    `UPDATE auth_login_codes SET consumed_at = ?2 WHERE id = ?1`,
  ).bind(challenge.id, now).run();
  const user = await env.DB.prepare(
    `SELECT id, display_name, language, country, target_intake
       FROM users WHERE email_hash = ?1`,
  ).bind(emailHash).first();
  const token = randomToken(36);
  await env.DB.prepare(
    `INSERT INTO auth_sessions (session_hash, user_id, created_at, expires_at)
     VALUES (?1, ?2, ?3, ?4)`,
  ).bind(
    await sha256Hex(token),
    user.id,
    now,
    new Date(Date.now() + AUTH_SESSION_TTL_MS).toISOString(),
  ).run();
  const favorites = await listUserFavoriteKeys(env, user.id);
  return jsonResponse(request, env, {
    ok: true,
    token,
    user: publicUser(user),
    favorites,
  });
}

async function listUserFavoriteKeys(env, userId) {
  const rows = await env.DB.prepare(
    `SELECT item_key FROM user_favorites
      WHERE user_id = ?1
      ORDER BY created_at ASC`,
  ).bind(userId).all();
  return (rows.results || []).map((row) => row.item_key);
}

async function getMe(request, env) {
  const user = await requireUser(request, env);
  if (!user) return jsonResponse(request, env, { ok: false }, 401);
  return jsonResponse(request, env, {
    user: publicUser(user),
    favorites: await listUserFavoriteKeys(env, user.id),
  });
}

async function updateMe(request, env) {
  const user = await requireUser(request, env);
  if (!user) return jsonResponse(request, env, { ok: false }, 401);
  let payload;
  try {
    payload = await request.json();
  } catch {
    return jsonResponse(request, env, { ok: false }, 400);
  }
  let displayName;
  let country;
  let targetIntake;
  try {
    displayName = normalizeProfileText(payload.displayName, 60);
    country = normalizeProfileText(payload.country, 80);
    targetIntake = normalizeProfileText(payload.targetIntake, 80);
  } catch {
    return jsonResponse(request, env, { ok: false }, 400);
  }
  const language = normalizeLanguage(payload.language);
  await env.DB.prepare(
    `UPDATE users SET
       display_name = ?2,
       language = ?3,
       country = ?4,
       target_intake = ?5,
       updated_at = ?6
     WHERE id = ?1`,
  ).bind(
    user.id,
    displayName || null,
    language,
    country || null,
    targetIntake || null,
    new Date().toISOString(),
  ).run();
  const updated = await env.DB.prepare(
    `SELECT id, display_name, language, country, target_intake
       FROM users WHERE id = ?1`,
  ).bind(user.id).first();
  return jsonResponse(request, env, { ok: true, user: publicUser(updated) });
}

async function updateMyFavorites(request, env) {
  const user = await requireUser(request, env);
  if (!user) return jsonResponse(request, env, { ok: false }, 401);
  let payload;
  try {
    payload = await request.json();
  } catch {
    return jsonResponse(request, env, { ok: false }, 400);
  }
  let favorites;
  try {
    favorites = [...new Set((payload.favorites || []).map(normalizeFavoriteKey))].slice(0, 500);
  } catch {
    return jsonResponse(request, env, { ok: false }, 400);
  }
  const now = new Date().toISOString();
  const statements = [
    env.DB.prepare("DELETE FROM user_favorites WHERE user_id = ?1").bind(user.id),
    ...favorites.map((itemKey) =>
      env.DB.prepare(
        `INSERT INTO user_favorites (user_id, item_key, created_at)
         VALUES (?1, ?2, ?3)`,
      ).bind(user.id, itemKey, now),
    ),
  ];
  await env.DB.batch(statements);
  return jsonResponse(request, env, { ok: true, favorites });
}

async function logout(request, env) {
  const header = request.headers.get("Authorization") || "";
  const match = header.match(/^Bearer\s+(.+)$/i);
  if (match) {
    await env.DB.prepare(
      "DELETE FROM auth_sessions WHERE session_hash = ?1",
    ).bind(await sha256Hex(match[1])).run();
  }
  return jsonResponse(request, env, { ok: true });
}

function universityComment(row) {
  const anonymous = row.author === "good people";
  return {
    id: row.id,
    universityId: row.university_id,
    author: row.author,
    anonymous,
    body: row.body,
    createdAt: row.created_at,
  };
}

async function listUniversityComments(request, env, universityId) {
  let normalizedUniversityId;
  try {
    normalizedUniversityId = normalizeUniversityId(universityId);
  } catch {
    return jsonResponse(request, env, { ok: false }, 400);
  }
  const rows = await env.DB.prepare(
    `SELECT id, university_id, author, body, created_at
       FROM university_comments
      WHERE university_id = ?1 AND hidden_at IS NULL
      ORDER BY created_at DESC
      LIMIT 80`,
  ).bind(normalizedUniversityId).all();
  return jsonResponse(request, env, {
    comments: (rows.results || []).map(universityComment),
  });
}

async function createUniversityComment(request, env, universityId) {
  if (!allowedOrigin(request.headers.get("Origin"), env.ALLOWED_ORIGINS)) {
    return jsonResponse(request, env, { ok: false }, 403);
  }
  const user = await requireUser(request, env);
  if (!user) return jsonResponse(request, env, { ok: false }, 401);
  let payload;
  try {
    payload = await request.json();
  } catch {
    return jsonResponse(request, env, { ok: false }, 400);
  }
  let normalizedUniversityId;
  let author;
  let body;
  try {
    normalizedUniversityId = normalizeUniversityId(universityId);
    author = payload.anonymous === true
      ? "good people"
      : normalizeCommentText(user.display_name || "", 40, false) ||
        "GradWindow user";
    body = normalizeCommentText(payload.body, 800);
  } catch {
    return jsonResponse(request, env, { ok: false }, 400);
  }
  const identity = {
    visitorHash: user.id,
    ipHash: "",
  };
  if (env.ROADMAP_VOTER_HASH_KEY) {
    const ip = request.headers.get("CF-Connecting-IP") || "";
    identity.ipHash = ip ? await hmacHex(env.ROADMAP_VOTER_HASH_KEY, ip) : "";
  }
  const [visitorAllowed, ipAllowed] = await Promise.all([
    consumeRoadmapRateLimit(env, "comment-visitor", identity.visitorHash, 8, 60 * 60_000),
    identity.ipHash
      ? consumeRoadmapRateLimit(env, "comment-ip", identity.ipHash, 40, 60 * 60_000)
      : true,
  ]);
  if (!visitorAllowed || !ipAllowed) {
    return jsonResponse(request, env, { ok: false }, 429);
  }
  const id = `comment-${crypto.randomUUID().replaceAll("-", "")}`;
  const now = new Date().toISOString();
  await env.DB.prepare(
    `INSERT INTO university_comments (
       id, university_id, visitor_hash, author, body, created_at, hidden_at
     ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, NULL)`,
  ).bind(id, normalizedUniversityId, identity.visitorHash, author, body, now).run();
  return jsonResponse(request, env, {
    ok: true,
    comment: universityComment({
      id,
      university_id: normalizedUniversityId,
      author,
      body,
      created_at: now,
    }),
  });
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
      `DELETE FROM auth_login_codes
       WHERE expires_at < ?1 OR consumed_at < ?1`,
    ).bind(stalePending),
    env.DB.prepare(
      `DELETE FROM auth_sessions
       WHERE expires_at < ?1`,
    ).bind(now.toISOString()),
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
    const universityCommentsMatch = url.pathname.match(
      /^\/universities\/([^/]+)\/comments$/,
    );
    if (request.method === "OPTIONS") {
      return new Response(null, {
        status: 204,
        headers: corsHeaders(request, env),
      });
    }
    if (request.method === "GET" && url.pathname === "/health") {
      return new Response("ok");
    }
    if (request.method === "POST" && url.pathname === "/auth/request") {
      return requestAuthCode(request, env);
    }
    if (request.method === "POST" && url.pathname === "/auth/verify") {
      return verifyAuthCode(request, env);
    }
    if (request.method === "POST" && url.pathname === "/auth/logout") {
      return logout(request, env);
    }
    if (request.method === "GET" && url.pathname === "/me") {
      return getMe(request, env);
    }
    if (request.method === "PATCH" && url.pathname === "/me") {
      return updateMe(request, env);
    }
    if (request.method === "PUT" && url.pathname === "/me/favorites") {
      return updateMyFavorites(request, env);
    }
    if (request.method === "GET" && url.pathname === "/roadmap") {
      return listRoadmap(request, env);
    }
    if (request.method === "GET" && url.pathname === "/admin/roadmap/stats") {
      return roadmapAdminStats(request, env);
    }
    if (request.method === "POST" && url.pathname === "/roadmap/votes") {
      return voteForRoadmapProposal(request, env);
    }
    if (request.method === "POST" && url.pathname === "/roadmap/proposals") {
      return createRoadmapProposal(request, env);
    }
    if (universityCommentsMatch && request.method === "GET") {
      return listUniversityComments(
        request,
        env,
        decodeURIComponent(universityCommentsMatch[1]),
      );
    }
    if (universityCommentsMatch && request.method === "POST") {
      return createUniversityComment(
        request,
        env,
        decodeURIComponent(universityCommentsMatch[1]),
      );
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
