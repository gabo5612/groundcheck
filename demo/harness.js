// Port of the deterministic half of groundcheck, so the page verifies instead of
// replaying. Everything here mirrors a Python module one-to-one:
//
//   numbers.js part  <- src/groundcheck/numbers.py
//   checks           <- src/groundcheck/checks.py
//   metrics          <- src/groundcheck/metrics.py
//
// `verify.mjs` runs this file against the exported run and compares every check and
// every metric with what the Python harness produced. If the port drifts, that script
// fails and the badge on the page goes red — the numbers on screen are never allowed to
// be prettier than the ones the harness measured.

const TOKEN = /[A-Za-z0-9]+(?:[.,\-/:][A-Za-z0-9]+)*/g;
const SEPARATORS = ".,-/:";
const ENUMERATOR = /(?:^|[\s(\[])\d{1,2}[.)](?=\s|$)/gm;
const CITATION_MARK = /\[\s*\d{1,3}(?:\s*[,;-]\s*\d{1,3})*\s*\]/g;

const ABSTENTION_PHRASES = [
  "no encontre", "no encontré", "no aparece", "no figura", "no dispongo",
  "no tengo informacion", "no tengo información", "no hay informacion",
  "no hay información", "no se especifica", "no esta especificado",
  "no está especificado", "no puedo confirmar", "no consta",
  "i could not find", "i don't have", "i do not have", "not specified",
  "no information", "cannot confirm", "not found in",
];

function splitGroups(token) {
  const groups = [], seps = [];
  let current = "";
  for (const ch of token) {
    if (SEPARATORS.includes(ch)) { groups.push(current); seps.push(ch); current = ""; }
    else current += ch;
  }
  groups.push(current);
  return [groups, seps];
}

const isDigits = (s) => s.length > 0 && /^\d+$/.test(s);

// Rules 1 and 2: a digit glued to a letter is an identifier, and three or more separated
// groups are an identifier unless they read as thousands + decimal.
export function isNumber(token) {
  const [groups, seps] = splitGroups(token);
  if (!groups.every(isDigits)) return false;
  if (seps.length === 0) return true;
  if (seps.length === 1) return seps[0] !== ":";
  const uniq = new Set(seps);
  if (uniq.size === 2 && uniq.has(".") && uniq.has(",")) return true;
  if (seps.includes(":")) return false;
  if ("-/".includes(seps[0])) return false;
  return groups.slice(1).every((g) => g.length === 3);
}

export function canonicalize(raw) {
  let token = raw.replace(/ /g, "").replace(/ /g, "");
  if (token.includes(".") && token.includes(",")) {
    const decimal = token.lastIndexOf(".") > token.lastIndexOf(",") ? "." : ",";
    const thousands = decimal === "." ? "," : ".";
    token = token.split(thousands).join("").split(decimal).join(".");
  } else {
    for (const sep of [".", ","]) {
      if (token.includes(sep)) {
        const at = token.lastIndexOf(sep);
        const head = token.slice(0, at), tail = token.slice(at + 1);
        token = (tail.length === 3 && isDigits(head.split(sep).join("")))
          ? token.split(sep).join("")        // thousands separator
          : token.split(sep).join(".");      // decimal
        break;
      }
    }
  }
  if (token.includes(".")) token = token.replace(/0+$/, "").replace(/\.$/, "");
  return token || "0";
}

function skipSpans(text) {
  const spans = [];
  for (const m of text.matchAll(ENUMERATOR)) spans.push([m.index, m.index + m[0].length]);
  for (const m of text.matchAll(CITATION_MARK)) spans.push([m.index, m.index + m[0].length]);
  return spans;
}

function splitUnit(token) {
  if (!token.includes("/")) return [token];
  const parts = token.split("/");
  const hasDigit = (p) => /\d/.test(p);
  if (parts.every(hasDigit)) return [token];   // 12/07/2024 stays whole
  return parts.filter(hasDigit);
}

function tokensOf(text) {
  if (!text) return [];
  const skip = skipSpans(text);
  const out = [];
  for (const m of text.matchAll(TOKEN)) {
    if (!/\d/.test(m[0])) continue;
    const [s, e] = [m.index, m.index + m[0].length];
    if (skip.some(([a, b]) => a <= s && e <= b)) continue;
    out.push(...splitUnit(m[0]));
  }
  return out;
}

export const extractNumbers = (text) =>
  tokensOf(text).filter(isNumber).map((raw) => ({ raw, canonical: canonicalize(raw) }));

export const extractCodes = (text) =>
  tokensOf(text).filter((t) => !isNumber(t)).map((t) => t.toUpperCase());

export const containsNumber = (haystack, needle) => {
  const target = canonicalize(needle);
  return extractNumbers(haystack).some((t) => t.canonical === target);
};

export const containsCode = (haystack, needle) =>
  extractCodes(haystack).includes(needle.toUpperCase());

export function looksLikeAbstention(answer) {
  if (answer === null || answer === undefined || !answer.trim()) return true;
  const low = answer.toLowerCase();
  return ABSTENTION_PHRASES.some((p) => low.includes(p));
}

// ── metrics ──────────────────────────────────────────────────────────────────
const matches = (item, doc, pages) => {
  if (item.doc_id === null || item.doc_id === undefined || String(item.doc_id) !== doc) return false;
  if (!pages || pages.length === 0) return true;
  return item.page !== null && item.page !== undefined && pages.includes(item.page);
};

const relevanceVector = (retrieved, targets) =>
  retrieved.map((it) => targets.some(([doc, pages]) => matches(it, doc, pages)));

export function recallAtK(retrieved, targets, k) {
  if (!targets.length) return null;
  const top = retrieved.slice(0, k);
  const covered = targets.filter(([doc, pages]) => top.some((i) => matches(i, doc, pages))).length;
  return covered / targets.length;
}

export function precisionAtK(retrieved, targets, k) {
  if (!targets.length) return null;
  return relevanceVector(retrieved.slice(0, k), targets).filter(Boolean).length / k;
}

export function reciprocalRank(retrieved, targets) {
  if (!targets.length) return null;
  const rel = relevanceVector(retrieved, targets);
  const at = rel.indexOf(true);
  return at === -1 ? 0.0 : 1.0 / (at + 1);
}

export function mean(values) {
  const real = values.filter((v) => v !== null && v !== undefined);
  return real.length ? real.reduce((a, b) => a + b, 0) / real.length : null;
}

// ── checks ───────────────────────────────────────────────────────────────────
const result = (name, passed, detail, evidence = {}) => ({ name, passed, detail, evidence });
const targetsOf = (c) => (c.gold_sources || []).map((s) => [s.doc_id, s.pages || []]);
const citationTexts = (r) => (r.retrieved || []).map((c) => c.text).filter((t) => t && t.trim());

export function checkGoldNumbers(c, r) {
  if (!c.gold_numbers.length) return result("gold_numbers_present", null, "the case defines no gold numbers");
  if (r.abstained) return result("gold_numbers_present", false, "abstained on a case that does have an answer");
  const missing = c.gold_numbers.filter((n) => !containsNumber(r.answer, n));
  return result("gold_numbers_present", missing.length === 0,
    missing.length ? `missing ${JSON.stringify(missing)}` : "all present", { missing });
}

export function checkForbiddenNumbers(c, r) {
  if (!c.forbidden_numbers.length) return result("forbidden_numbers_absent", null, "the case defines none");
  const present = c.forbidden_numbers.filter((n) => containsNumber(r.answer, n));
  return result("forbidden_numbers_absent", present.length === 0,
    present.length ? `${JSON.stringify(present)} appear — it crossed rows` : "none present", { present });
}

export function checkForbiddenCodes(c, r) {
  if (!c.forbidden_codes.length) return result("forbidden_codes_absent", null, "the case defines no forbidden codes");
  const present = c.forbidden_codes.filter((x) => containsCode(r.answer, x));
  return result("forbidden_codes_absent", present.length === 0,
    present.length ? `${JSON.stringify(present)} appear — it answered about the neighbour` : "none present",
    { present });
}

export function checkGrounded(c, r) {
  if (r.abstained) return result("grounded", null, "abstained: there is nothing to ground");
  const texts = citationTexts(r);
  if (!texts.length) return result("grounded", null, "citations carry no text — the system does not expose chunk content");

  const corpus = texts.join("\n");
  const numbers = extractNumbers(r.answer);
  const codes = extractCodes(r.answer);
  const questionNumbers = new Set(extractNumbers(c.question).map((t) => t.canonical));
  const questionCodes = new Set(extractCodes(c.question));

  const orphanNumbers = numbers
    .filter((t) => !questionNumbers.has(t.canonical) && !containsNumber(corpus, t.raw))
    .map((t) => t.raw);
  const corpusCodes = new Set(extractCodes(corpus));
  const orphanCodes = codes.filter((x) => !questionCodes.has(x) && !corpusCodes.has(x));
  const orphans = [...orphanNumbers, ...orphanCodes];

  if (!numbers.length && !codes.length)
    return result("grounded", null, "the answer carries no numbers or codes to verify");
  return result("grounded", orphans.length === 0,
    orphans.length ? `unsupported: ${JSON.stringify(orphans)}` : "fully grounded",
    { numbers: numbers.map((t) => t.raw), codes, unsupported: orphans });
}

export function checkCitationHitsGold(c, r) {
  const targets = targetsOf(c);
  if (!targets.length) return result("citation_hits_gold", null, "the case defines no gold source");
  const items = r.retrieved || [];
  if (!items.length) return result("citation_hits_gold", false, "it cited nothing");
  const hits = items.filter((it) => targets.some(([doc, pages]) => matches(it, doc, pages)));
  return result("citation_hits_gold", hits.length > 0,
    hits.length ? "correct citation" : "no citation points at the gold source", { hits: hits.length });
}

export function checkAbstention(c, r) {
  const declared = Boolean(r.abstained);
  const byPhrase = looksLikeAbstention(r.answer);
  const abstained = declared || byPhrase;
  if (c.must_abstain)
    return result("abstention_correct", abstained,
      abstained ? "abstained, correct" : "HALLUCINATED: answered a question that has no answer",
      { declared, byPhrase });
  return result("abstention_correct", !abstained,
    abstained ? "abstained on a case that does have an answer" : "answered, correct",
    { declared, byPhrase });
}

export function checkRevisionCurrent(c, r) {
  const gold = new Set((c.gold_sources || []).map((s) => s.revision).filter(Boolean));
  if (!gold.size) return result("revision_current", null, "the case pins no gold revision");
  const cited = new Set((r.retrieved || []).map((x) => x.revision).filter((v) => v !== null && v !== undefined).map(String));
  if (!cited.size) return result("revision_current", null, "citations report no revision — cannot verify");
  const stale = [...cited].filter((v) => !gold.has(v));
  return result("revision_current", stale.length === 0,
    stale.length ? `cited a superseded revision: ${JSON.stringify(stale.sort())}` : "current revision",
    { cited: [...cited], current: [...gold] });
}

export const CHECKS = [
  checkGoldNumbers, checkForbiddenNumbers, checkForbiddenCodes, checkGrounded,
  checkCitationHitsGold, checkAbstention, checkRevisionCurrent,
];

export function evaluate(c) {
  const r = c.response;
  const out = {};
  for (const fn of CHECKS) { const res = fn(c, r); out[res.name] = res; }
  return out;
}

export function metricsFor(c, k) {
  const targets = targetsOf(c);
  const items = c.response.retrieved || [];
  return {
    recall_at_k: recallAtK(items, targets, k),
    precision_at_k: precisionAtK(items, targets, k),
    reciprocal_rank: reciprocalRank(items, targets),
  };
}

// Aggregate by category, the same shape `report.aggregate` produces.
export function aggregate(cases, k) {
  const rows = new Map();
  for (const c of cases) {
    if (!rows.has(c.category))
      rows.set(c.category, { category: c.category, n: 0, recall: [], precision: [], rr: [], checks: {} });
    const row = rows.get(c.category);
    row.n += 1;
    const m = metricsFor(c, k);
    row.recall.push(m.recall_at_k);
    row.precision.push(m.precision_at_k);
    row.rr.push(m.reciprocal_rank);
    for (const [name, res] of Object.entries(evaluate(c))) {
      const rate = (row.checks[name] ||= { hits: 0, n: 0, total: 0 });
      rate.total += 1;
      if (res.passed !== null) { rate.n += 1; rate.hits += res.passed ? 1 : 0; }
    }
  }
  return [...rows.values()].map((row) => ({
    ...row, recallMean: mean(row.recall), precisionMean: mean(row.precision), mrr: mean(row.rr),
  }));
}
