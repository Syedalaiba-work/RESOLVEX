// OPT-IN load profile (read-only). Refuses to run unless K6_LOAD_OPT_IN=yes, and only against the QA stack.
// Ramps to 20 VUs. The /api/v1 rate limit (100 req / 10 s per client IP) will start returning 429 under
// this load by design, so only the public read endpoints are used here; this measures the API under
// concurrency on one laptop and says nothing about production capacity.
import http from 'k6/http';
import { check, sleep } from 'k6';
import { BASE_URL, assertSafeTarget, summaryText } from './lib.js';

export const options = {
  stages: [
    { duration: '30s', target: 10 },
    { duration: '1m', target: 20 },
    { duration: '30s', target: 0 },
  ],
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<1000'],
    checks: ['rate>0.99'],
  },
};

export function setup() {
  if (__ENV.K6_LOAD_OPT_IN !== 'yes') throw new Error('Load profile is opt-in: set K6_LOAD_OPT_IN=yes.');
  assertSafeTarget();
}

export default function () {
  const r1 = http.get(`${BASE_URL}/health`, { tags: { name: 'GET /health' } });
  const r2 = http.get(`${BASE_URL}/audit/v1/standings/league-alpha-1`, { tags: { name: 'GET /audit/v1/standings/{id}' } });
  const r3 = http.get(`${BASE_URL}/audit/v1/score/la1-m5`, { tags: { name: 'GET /audit/v1/score/{id}' } });
  check(r1, { 'health 200': (r) => r.status === 200 });
  check(r2, { 'standings 200': (r) => r.status === 200 });
  check(r3, { 'score 200': (r) => r.status === 200 });
  sleep(0.5);
}

export function handleSummary(data) {
  return {
    stdout: summaryText(data, 'load (opt-in, up to 20 VUs)'),
    '/results/load-summary.json': JSON.stringify(data, null, 2),
    '/results/load-summary.txt': summaryText(data, 'load (opt-in, up to 20 VUs)'),
  };
}
