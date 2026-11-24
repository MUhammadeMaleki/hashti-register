import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import ts from "typescript";

async function loadSource(path) {
  const source = await readFile(new URL(path, import.meta.url), "utf8");
  const javascript = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  return import(`data:text/javascript,${encodeURIComponent(javascript)}`);
}

const { api, auth, ApiError, errorMessage } = await loadSource("../src/lib/api.ts");
const { normalizeMobile, formatToman, formatJalali, isoToJalali, jalaliToIso, persianDigits } =
  await loadSource("../src/lib/format.ts");

test("mutations send CSRF and same-origin cookies", async () => {
  globalThis.document = { cookie: "other=1; hashti_csrf=test-token" };
  let seen;
  globalThis.fetch = async (url, options) => {
    seen = { url, options };
    return new Response(JSON.stringify({ actor_type: "user" }), {
      status: 200, headers: { "Content-Type": "application/json" },
    });
  };
  await auth.adminLogin("boss", "password");
  assert.equal(seen.url, "/api/auth/admin/login");
  assert.equal(seen.options.credentials, "same-origin");
  assert.equal(seen.options.headers.get("X-CSRF-Token"), "test-token");
});

test("expired access session refreshes and retries once", async () => {
  globalThis.document = { cookie: "hashti_csrf=test-token" };
  const calls = [];
  globalThis.fetch = async (url) => {
    calls.push(url);
    const status = calls.length === 1 ? 401 : 200;
    return new Response(JSON.stringify(status === 401
      ? { detail: "invalid_session" } : { status: "ok" }), {
      status, headers: { "Content-Type": "application/json" },
    });
  };
  await api("/auth/session");
  assert.deepEqual(calls, ["/api/auth/session", "/api/auth/refresh", "/api/auth/session"]);
});

test("API errors are translated without exposing internals", async () => {
  globalThis.fetch = async () => new Response(JSON.stringify({ detail: "invalid_credentials" }), {
    status: 401, headers: { "Content-Type": "application/json" },
  });
  await assert.rejects(auth.guestLogin("09120000000", "wrong"), (error) => {
    assert.ok(error instanceof ApiError);
    assert.match(errorMessage(error), /درست نیست/);
    return true;
  });
});

test("Persian mobile, Jalali and toman helpers", () => {
  assert.equal(normalizeMobile("+۹۸ ۹۱۲-۰۰۰ ۰۰۰۰"), "09120000000");
  assert.match(formatToman(125000), /۱۲۵٬۰۰۰ تومان/);
  assert.match(formatJalali("2026-11-23T12:00:00Z"), /۱۴۰۵/);
  assert.equal(persianDigits("5047061113404855"), "۵۰۴۷۰۶۱۱۱۳۴۰۴۸۵۵");
  assert.equal(isoToJalali("2026-11-23"), "1405/09/02");
  assert.equal(jalaliToIso("۱۴۰۵/۰۹/۰۲"), "2026-11-23");
  assert.equal(jalaliToIso("1405/13/01"), null);
});
