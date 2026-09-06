import { evaluate, metricsFor, aggregate, mean } from "./harness.js";

const $ = (s) => document.querySelector(s);
const CHECK_ORDER = [
  "gold_numbers_present", "forbidden_numbers_absent", "forbidden_codes_absent",
  "grounded", "citation_hits_gold", "abstention_correct", "revision_current",
];
const CATEGORY_ORDER = [
  "factual_lookup", "alfanumerico_exacto", "procedimental",
  "multi_documento", "negative_control", "revision_supersedida",
];

const fmt = (v, n = 2) => (v === null || v === undefined ? "n/a" : v.toFixed(n));
const rate = (r) => (!r || r.n === 0 ? "n/a" : `${(r.hits / r.n).toFixed(2)} (${r.hits}/${r.n})`);

let DATA = null, filter = "all";

init();

async function init() {
  DATA = await (await fetch("./data.json")).json();
  const started = new Date(DATA.started_at);
  $("#status").textContent =
    `${DATA.suite.name} · ${DATA.cases.length} cases · run ${started.toISOString().slice(0, 16).replace("T", " ")} UTC` +
    ` · groundcheck ${DATA.groundcheck_version} (${DATA.stage})`;
  $("#prov").innerHTML =
    `Golden set <code>${DATA.suite.name}</code> · sha256 <code>${DATA.suite.sha256.slice(0, 16)}…</code> · ` +
    `system under test <code>${DATA.system.target || DATA.system.kind}</code>`;

  verifyPort();
  renderFilters();
  renderCases();
  $("#k").addEventListener("input", (e) => {
    $("#kv").textContent = e.target.value;
    renderAggregate(Number(e.target.value));
  });
  renderAggregate(DATA.k);
}

// The badge is the claim's own test: recompute everything and diff it against the
// verdicts the Python harness wrote into data.json.
function verifyPort() {
  let checked = 0, agree = 0;
  for (const c of DATA.cases) {
    for (const [name, res] of Object.entries(evaluate(c))) {
      checked += 1;
      if (c.checks[name] && c.checks[name].passed === res.passed) agree += 1;
    }
    const m = metricsFor(c, DATA.k);
    for (const key of ["recall_at_k", "precision_at_k", "reciprocal_rank"]) {
      checked += 1;
      const a = m[key], b = c.metrics[key];
      if (a === b || (a !== null && b !== null && Math.abs(a - b) < 1e-9)) agree += 1;
    }
  }
  const ok = agree === checked;
  const el = $("#verdict");
  el.classList.toggle("bad", !ok);
  el.innerHTML = ok
    ? `<span class="pass">✓</span> <span><b>${agree}/${checked}</b> checks and metrics recomputed in this browser agree with the Python harness that produced the run.</span>`
    : `<span class="fail">✗</span> <span>${checked - agree} of ${checked} recomputed values disagree with the harness. Do not trust this page.</span>`;
}

function renderAggregate(k) {
  const rows = aggregate(DATA.cases, k);
  rows.sort((a, b) => CATEGORY_ORDER.indexOf(a.category) - CATEGORY_ORDER.indexOf(b.category));
  const body = $("#agg tbody");
  body.innerHTML = "";
  for (const row of rows) {
    const negative = row.category === "negative_control";
    const tr = document.createElement("tr");
    if (negative) tr.className = "neg";
    tr.innerHTML = `<td>${row.category}</td><td>${row.n}</td>` +
      `<td>${negative ? "n/a" : fmt(row.recallMean)}</td>` +
      `<td>${negative ? "n/a" : fmt(row.mrr)}</td>` +
      `<td>${negative ? "n/a" : fmt(row.precisionMean)}</td>` +
      `<td>${rate(row.checks.grounded)}</td>` +
      `<td>${rate(row.checks.abstention_correct)}</td>`;
    body.appendChild(tr);
  }
  const all = { hits: 0, n: 0 }, gr = { hits: 0, n: 0 };
  for (const row of rows) {
    for (const [src, dst] of [[row.checks.abstention_correct, all], [row.checks.grounded, gr]]) {
      if (src) { dst.hits += src.hits; dst.n += src.n; }
    }
  }
  const total = document.createElement("tr");
  total.className = "total";
  const answered = rows.filter((r) => r.category !== "negative_control");
  total.innerHTML = `<td>TOTAL</td><td>${rows.reduce((a, r) => a + r.n, 0)}</td>` +
    `<td>${fmt(mean(answered.map((r) => r.recallMean)))}</td>` +
    `<td>${fmt(mean(answered.map((r) => r.mrr)))}</td>` +
    `<td>${fmt(mean(answered.map((r) => r.precisionMean)))}</td>` +
    `<td>${rate(gr)}</td><td>${rate(all)}</td>`;
  body.appendChild(total);
}

function renderFilters() {
  const counts = new Map([["all", DATA.cases.length]]);
  for (const c of DATA.cases) counts.set(c.category, (counts.get(c.category) || 0) + 1);
  const failing = DATA.cases.filter(hasFailure).length;
  const wrap = $("#filters");
  wrap.innerHTML = "";
  const add = (key, label) => {
    const b = document.createElement("button");
    b.className = "chip";
    b.textContent = label;
    b.setAttribute("aria-pressed", String(filter === key));
    b.onclick = () => { filter = key; renderFilters(); renderCases(); };
    wrap.appendChild(b);
  };
  add("all", `all (${counts.get("all")})`);
  add("failing", `failing a check (${failing})`);
  for (const cat of CATEGORY_ORDER) if (counts.get(cat)) add(cat, `${cat} (${counts.get(cat)})`);
}

const hasFailure = (c) => Object.values(evaluate(c)).some((r) => r.passed === false);

function renderCases() {
  const list = $("#cases");
  list.innerHTML = "";
  const shown = DATA.cases.filter((c) =>
    filter === "all" ? true : filter === "failing" ? hasFailure(c) : c.category === filter);
  for (const c of shown) list.appendChild(caseNode(c));
}

function caseNode(c) {
  const checks = evaluate(c);
  const m = metricsFor(c, Number($("#k").value));
  const bad = hasFailure(c);
  const el = document.createElement("details");
  el.className = "case";

  // Naming the failing check matters: several cases answer correctly and still fail one
  // check — citing a superseded revision, say. A bare "fail" would read as a wrong answer.
  const failed = Object.entries(checks).filter(([, r]) => r.passed === false).map(([n]) => n);
  const summary = document.createElement("summary");
  summary.innerHTML =
    `<span class="pill ${bad ? "bad" : "ok"}">${bad ? `${failed.length} failed` : "all pass"}</span>` +
    `<span class="qs">${escapeHtml(c.question)}<span class="cat">${c.category}` +
    `${c.must_abstain ? " · must abstain" : ""} · ${c.difficulty || "—"}` +
    `${failed.length ? ` · <span class="fail">${failed.join(", ")}</span>` : ""}</span></span>`;
  el.appendChild(summary);

  const body = document.createElement("div");
  body.className = "body";
  const gold = c.gold_sources.map((s) =>
    `<code>${s.doc_id.slice(0, 8)}…</code> rev ${s.revision ?? "—"} p.${(s.pages || []).join(", ") || "—"}`).join(" · ");

  body.innerHTML =
    `<div class="ans">${escapeHtml(c.response.answer ?? "(no answer)")}</div>` +
    `<dl class="kv">` +
    `<dt>expected</dt><dd>${escapeHtml(c.gold_answer ?? (c.must_abstain ? "an abstention — this question has no answer in the corpus" : "—"))}</dd>` +
    (c.gold_numbers.length ? `<dt>gold numbers</dt><dd><code>${c.gold_numbers.join(", ")}</code></dd>` : "") +
    (c.forbidden_numbers.length ? `<dt>must not say</dt><dd><code>${c.forbidden_numbers.join(", ")}</code> (other rows of the same table)</dd>` : "") +
    (c.forbidden_codes.length ? `<dt>must not say</dt><dd><code>${c.forbidden_codes.join(", ")}</code> (the neighbouring item)</dd>` : "") +
    `<dt>gold source</dt><dd>${gold || "—"}</dd>` +
    `<dt>metrics</dt><dd>recall ${fmt(m.recall_at_k)} · RR ${fmt(m.reciprocal_rank)} · precision ${fmt(m.precision_at_k)} · ${c.response.latency_ms ?? "—"} ms</dd>` +
    `</dl>`;

  const ul = document.createElement("ul");
  ul.className = "checks";
  for (const name of CHECK_ORDER) {
    const r = checks[name];
    if (!r) continue;
    const cls = r.passed === true ? "pass" : r.passed === false ? "fail" : "skip";
    const mark = r.passed === true ? "✓" : r.passed === false ? "✗" : "–";
    const li = document.createElement("li");
    li.innerHTML = `<span class="mark ${cls}">${mark}</span>` +
      `<span class="cname">${name}</span><span class="cdetail">${escapeHtml(r.detail)}</span>`;
    ul.appendChild(li);
  }
  body.appendChild(ul);

  const hits = document.createElement("ul");
  hits.className = "hits";
  const goldDocs = new Set(c.gold_sources.map((s) => s.doc_id));
  for (const r of c.response.retrieved.slice(0, 5)) {
    const isGold = goldDocs.has(r.doc_id) &&
      c.gold_sources.some((s) => !s.pages?.length || s.pages.includes(r.page));
    const li = document.createElement("li");
    li.innerHTML = `<span class="${isGold ? "gold" : ""}">#${r.rank} ${isGold ? "★ " : ""}` +
      `${escapeHtml(r.title || r.doc_id)} · rev ${r.revision ?? "—"} · p.${r.page ?? "—"}</span>` +
      `<div class="snippet">${escapeHtml((r.text || "").slice(0, 420))}</div>`;
    hits.appendChild(li);
  }
  if (hits.children.length) {
    const h = document.createElement("div");
    h.style.cssText = "color:var(--dim);font-size:12px;margin-top:12px;text-transform:uppercase;letter-spacing:.4px";
    h.textContent = "retrieved (★ = gold source)";
    body.appendChild(h);
    body.appendChild(hits);
  }

  el.appendChild(body);
  return el;
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
