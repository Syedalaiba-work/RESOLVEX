// Shared, read-only request mix for the k6 profiles. No orders, events, transfers or resets are sent.
import http from 'k6/http';
import { check, group, sleep } from 'k6';

export const BASE_URL = (__ENV.BASE_URL || 'http://api:8080').replace(/\/$/, '');

// Safety guard: only run against the disposable QA stack. On the nascon-qa_default network the host
// name "api" resolves only to that stack; the official stack is on a different network. Any other
// target must be named explicitly with ALLOW_TARGET=<exact BASE_URL>.
export function assertSafeTarget() {
  if (BASE_URL !== 'http://api:8080' && __ENV.ALLOW_TARGET !== BASE_URL) {
    throw new Error(`Refusing to test ${BASE_URL}: set ALLOW_TARGET to the same URL to confirm it is not the judging/demo backend.`);
  }
}

export function login() {
  const r = http.post(`${BASE_URL}/api/v1/auth/login`,
    JSON.stringify({ email: 'viewer@nascon.test', password: 'Nascon@26' }),
    { headers: { 'Content-Type': 'application/json' }, tags: { name: 'POST /api/v1/auth/login' } });
  if (r.status !== 200) throw new Error(`login failed: ${r.status} ${r.body}`);
  return r.json('token');
}

export function readOnlyMix(token) {
  const auth = { headers: { Authorization: `Bearer ${token}` } };
  group('public', () => {
    const h = http.get(`${BASE_URL}/health`, { tags: { name: 'GET /health' } });
    check(h, { 'health 200 ok': (r) => r.status === 200 && r.json('status') === 'ok' });
    const s = http.get(`${BASE_URL}/audit/v1/standings/league-alpha-1`, { tags: { name: 'GET /audit/v1/standings/{id}' } });
    check(s, { 'standings 200 with 4 rows': (r) => r.status === 200 && r.json('table').length === 4 });
    const m = http.get(`${BASE_URL}/audit/v1/score/la1-m5`, { tags: { name: 'GET /audit/v1/score/{id}' } });
    check(m, { 'score 200': (r) => r.status === 200 && r.json('match_id') === 'la1-m5' });
    const i = http.get(`${BASE_URL}/audit/v1/inventory/var-jersey-001-M`, { tags: { name: 'GET /audit/v1/inventory/{id}' } });
    check(i, { 'inventory 200': (r) => r.status === 200 && r.json('reserved') === 0 });
  });
  group('mobile api (rate limited 100 req / 10 s per IP)', () => {
    const f = http.get(`${BASE_URL}/api/v1/fixtures`, Object.assign({ tags: { name: 'GET /api/v1/fixtures' } }, auth));
    check(f, { 'fixtures 200 (6)': (r) => r.status === 200 && r.json().length === 6 });
  });
  sleep(1);
}

export function summaryText(data, label) {
  const m = data.metrics;
  const dur = m.http_req_duration.values;
  const lines = [
    `k6 ${label} profile against ${BASE_URL}`,
    `  requests:     ${m.http_reqs.values.count} (${m.http_reqs.values.rate.toFixed(2)} req/s)`,
    `  latency:      median ${dur.med.toFixed(1)} ms, p95 ${dur['p(95)'].toFixed(1)} ms, max ${dur.max.toFixed(1)} ms`,
    `  http failed:  ${(m.http_req_failed.values.rate * 100).toFixed(2)} %`,
    `  checks:       ${(m.checks.values.rate * 100).toFixed(2)} % passed (${m.checks.values.passes} / ${m.checks.values.passes + m.checks.values.fails})`,
    `  thresholds:   ${Object.entries(data.metrics).filter(([, v]) => v.thresholds).map(([k, v]) => `${k} ${Object.values(v.thresholds).every((t) => t.ok) ? 'OK' : 'FAILED'}`).join(', ')}`,
  ];
  return lines.join('\n') + '\n';
}
