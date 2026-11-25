import assert from 'node:assert/strict';

const frontend = process.env.HASHTI_FRONTEND_ORIGIN ?? 'http://127.0.0.1:3000';
const backend = process.env.HASHTI_BACKEND_ORIGIN ?? 'http://127.0.0.1:8000';

async function request(url) {
  const response = await fetch(url, { signal: AbortSignal.timeout(10000) });
  assert.equal(response.status, 200, `Expected HTTP 200 from ${url}`);
  return response;
}

const html = await (await request(frontend)).text();
assert.ok(/<html[^>]*lang="fa"/.test(html), 'Homepage must declare Persian.');
assert.ok(/<html[^>]*dir="rtl"/.test(html), 'Homepage must be RTL.');
assert.ok(html.includes('جدیدترین هشتی‌ها'), 'Homepage must show the latest events heading.');
await request(`${frontend}/archive`);
await request(`${frontend}/upcoming`);
const loginHtml = await (await request(`${frontend}/login`)).text();
assert.ok(loginHtml.includes('ورود هشتی‌نشین'), 'Guest login must be available.');
assert.ok(loginHtml.includes('ورود دبیر'), 'Secretary login must be available.');
await request(`${frontend}/panel/events`);
await request(`${frontend}/panel/events/new`);
await request(`${frontend}/panel/locations`);
assert.deepEqual(await (await request(`${backend}/api/health`)).json(), {
  status: 'ok', service: 'hashti-api',
});
const expectedReadiness = { status: 'ok', database: 'postgresql' };
assert.deepEqual(await (await request(`${backend}/api/health/ready`)).json(), expectedReadiness);
assert.deepEqual(await (await request(`${frontend}/api/health/ready`)).json(), expectedReadiness);
const publicEvents = await (await request(`${frontend}/api/public/events`)).json();
assert.ok(Array.isArray(publicEvents.items));
const privateEvents = await fetch(`${frontend}/api/admin/events`, {
  signal: AbortSignal.timeout(10000),
});
assert.equal(privateEvents.status, 401, 'Private event API must reject anonymous requests');
console.log('PASS: Persian RTL page, API liveness, real PostgreSQL readiness, same-origin API proxy.');
