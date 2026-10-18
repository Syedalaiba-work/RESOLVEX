// Low-load smoke profile: read-only, VUS (default 3, max 5) for DURATION (default 30s).
import { assertSafeTarget, login, readOnlyMix, summaryText } from './lib.js';

const vus = Math.min(parseInt(__ENV.VUS || '3', 10), 5);

export const options = {
  vus,
  duration: __ENV.DURATION || '30s',
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<500', 'med<200'],
    checks: ['rate>0.99'],
  },
};

export function setup() {
  assertSafeTarget();
  return { token: login() };
}

export default function (data) {
  readOnlyMix(data.token);
}

export function handleSummary(data) {
  delete data.setup_data; // holds the login token; never write it to results
  return {
    stdout: summaryText(data, `smoke (${vus} VUs)`),
    '/results/smoke-summary.json': JSON.stringify(data, null, 2),
    '/results/smoke-summary.txt': summaryText(data, `smoke (${vus} VUs)`),
  };
}
