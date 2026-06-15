const encoder = new TextEncoder();
const decoder = new TextDecoder();

export function normalizeEmail(value) {
  const email = String(value || "").trim().toLowerCase();
  if (
    email.length < 3 ||
    email.length > 254 ||
    !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)
  ) {
    throw new Error("invalid email");
  }
  return email;
}

export function normalizeLanguage(value) {
  return value === "zh" ? "zh" : "en";
}

export function allowedOrigin(origin, configuredOrigins) {
  if (!origin) return "";
  const allowed = String(configuredOrigins || "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
  return allowed.includes(origin) ? origin : "";
}

export function bytesToBase64Url(bytes) {
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary)
    .replaceAll("+", "-")
    .replaceAll("/", "_")
    .replaceAll("=", "");
}

export function base64UrlToBytes(value) {
  const normalized = value.replaceAll("-", "+").replaceAll("_", "/");
  const padded = normalized.padEnd(
    normalized.length + ((4 - (normalized.length % 4)) % 4),
    "=",
  );
  return Uint8Array.from(atob(padded), (character) => character.charCodeAt(0));
}

async function importHmacKey(secret) {
  return crypto.subtle.importKey(
    "raw",
    encoder.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign", "verify"],
  );
}

export async function hmacHex(secret, value) {
  const signature = new Uint8Array(
    await crypto.subtle.sign(
      "HMAC",
      await importHmacKey(secret),
      encoder.encode(value),
    ),
  );
  return [...signature]
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

export async function sha256Hex(value) {
  const digest = new Uint8Array(
    await crypto.subtle.digest("SHA-256", encoder.encode(value)),
  );
  return [...digest]
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

async function importEncryptionKey(base64Key) {
  const bytes = base64UrlToBytes(base64Key);
  if (bytes.length !== 32) throw new Error("encryption key must be 32 bytes");
  return crypto.subtle.importKey(
    "raw",
    bytes,
    { name: "AES-GCM" },
    false,
    ["encrypt", "decrypt"],
  );
}

export async function encryptEmail(email, base64Key) {
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const encrypted = new Uint8Array(
    await crypto.subtle.encrypt(
      { name: "AES-GCM", iv },
      await importEncryptionKey(base64Key),
      encoder.encode(email),
    ),
  );
  return {
    ciphertext: bytesToBase64Url(encrypted),
    iv: bytesToBase64Url(iv),
  };
}

export async function decryptEmail(ciphertext, iv, base64Key) {
  const decrypted = await crypto.subtle.decrypt(
    { name: "AES-GCM", iv: base64UrlToBytes(iv) },
    await importEncryptionKey(base64Key),
    base64UrlToBytes(ciphertext),
  );
  return decoder.decode(decrypted);
}

export function randomToken(byteLength = 32) {
  return bytesToBase64Url(crypto.getRandomValues(new Uint8Array(byteLength)));
}

export async function signedUnsubscribeToken(emailHash, secret) {
  const signature = await hmacHex(secret, emailHash);
  return `${emailHash}.${signature}`;
}

export async function verifyUnsubscribeToken(token, secret) {
  const [emailHash, signature, extra] = String(token || "").split(".");
  if (!emailHash || !signature || extra) return "";
  const expected = await hmacHex(secret, emailHash);
  if (signature.length !== expected.length) return "";
  let mismatch = 0;
  for (let index = 0; index < signature.length; index += 1) {
    mismatch |= signature.charCodeAt(index) ^ expected.charCodeAt(index);
  }
  return mismatch === 0 ? emailHash : "";
}
