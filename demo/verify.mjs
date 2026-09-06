// Compares the browser port against the Python harness, case by case and check by check.
//
//   node demo/verify.mjs
//
// The demo claims it re-runs the deterministic checks rather than replaying stored
// verdicts. This script is what makes that claim falsifiable: it evaluates every case
// with harness.js and diffs the result against the verdicts data.json carries from
// src/groundcheck/checks.py. Any drift exits 1 and prints the offending case.

import { readFileSync } from "node:fs";
import { evaluate, metricsFor, aggregate } from "./harness.js";

const data = JSON.parse(readFileSync(new URL("./data.json", import.meta.url), "utf8"));
const near = (a, b) => (a === null || b === null ? a === b : Math.abs(a - b) < 1e-9);

let checked = 0, failed = 0;
for (const c of data.cases) {
  for (const [name, res] of Object.entries(evaluate(c))) {
    const python = c.checks[name];
    checked += 1;
    if (!python || python.passed !== res.passed) {
      failed += 1;
      console.error(`✗ ${c.id} · ${name}: python=${python?.passed} js=${res.passed}`);
      console.error(`    answer: ${JSON.stringify(c.response.answer)?.slice(0, 160)}`);
      console.error(`    js says: ${res.detail}`);
    }
  }
  const m = metricsFor(c, data.k);
  for (const key of ["recall_at_k", "precision_at_k", "reciprocal_rank"]) {
    checked += 1;
    if (!near(m[key], c.metrics[key])) {
      failed += 1;
      console.error(`✗ ${c.id} · ${key}: python=${c.metrics[key]} js=${m[key]}`);
    }
  }
}

for (const row of aggregate(data.cases, data.k)) {
  const python = data.categories.find((r) => r.category === row.category);
  for (const [jsKey, pyKey] of [["recallMean", "recall"], ["precisionMean", "precision"], ["mrr", "mrr"]]) {
    checked += 1;
    if (!near(row[jsKey], python[pyKey])) {
      failed += 1;
      console.error(`✗ ${row.category} · ${pyKey}: python=${python[pyKey]} js=${row[jsKey]}`);
    }
  }
}

console.log(`${checked - failed}/${checked} agree with the Python harness`);
process.exit(failed ? 1 : 0);
