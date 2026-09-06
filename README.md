# groundcheck

**An evaluation harness for RAG systems.** It measures, reproducibly, whether a system
**retrieves the right thing, answers with grounding, cites correctly, and stays quiet when
it doesn't know** — and it fails CI when a change degrades any of that.

Sibling to [`crew`](https://github.com/gabo5612/crew): same thesis, **deterministic
verification, no model ever judging another model**.

> *groundcheck* = checking the **ground** under an answer: that every number and every
> citation is literally there in a retrieved chunk. That is the tool's central metric,
> turned into its name.

## Status: M7–M8 in progress

| Milestone | What it adds | Status |
|---|---|---|
| **M0** | CLI skeleton + suite format + adapters | ✅ |
| **M1** | recall@k, MRR, precision@k | ✅ |
| **M2** | Deterministic generation checks | ✅ |
| **M3** | Golden set v1 (20 questions, 20% negative controls) | ✅ |
| **M4** | Per-category report | ✅ |
| **M5** | CI gate | ✅ |
| **M6** | `groundcheck diff` | ✅ |
| M7 | Optional LLM judge (reports, never blocks) | 🟡 sheet ready, human labels pending |
| M8 | Golden set v2 | 🟡 **39/50** — two categories lack corpus, see below |

**A run emits no metrics at all, on purpose.** A run stores only what was observed: what was
asked and what the system answered. A test fails if anyone adds a "provisional" average to
the output — a filler zero in an evaluation JSON gets copied into a README and stops being
provisional.

## Demo

`demo/` is a static page carrying a real run: the golden set against `shopfloor`. It is not
a replay — the browser re-runs the deterministic half of the harness (number extraction,
the seven checks, recall@k, MRR, precision@k, with `k` as a slider) and diffs its own
results against the verdicts Python produced. `node demo/verify.mjs` is the same check in
the terminal: 402/402 agree. Deploy with `cd demo && vercel --prod` — static files, no
build step. See [`demo/README.md`](demo/README.md).

## Usage

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest

# against a scripted system (no RAG needs to be running)
.venv/bin/groundcheck run --suite suites/mock.yaml \
                    --system mock:tests/fixtures/mock_responses.yaml --out runs/

# against a real system
.venv/bin/groundcheck run --suite suites/shopfloor-v2.yaml \
                    --system http://localhost:8080/api/ask \
                    --mapping adapters/shopfloor.yaml --out runs/
```

```bash
.venv/bin/groundcheck report runs/2026-09-04T19-02-31Z.json --k 5   # per-category table
.venv/bin/groundcheck report runs/….json --json                     # same breakdown as JSON
```

```bash
.venv/bin/groundcheck report runs/….json --json > baselines/mock.json    # freeze a baseline
.venv/bin/groundcheck gate runs/new.json --against baselines/mock.json --max-regression 0.02
```

```bash
.venv/bin/groundcheck diff runs/before.json runs/after.json    # what changed and why
```

## The CI gate

Exit codes are the contract with CI: **0** pass · **1** regression (fails the build) ·
**2** could not compare.

Inject the most banal and most common RAG regression — drop top-k to 1, *"fewer chunks,
it's faster"* — and the gate names it:

```
  REGRESIONES — bloquean el build
    alfanumerico_exacto/recall_at_5: 1.000 → 0.750  · fell 0.250, over the 0.020 tolerance
    alfanumerico_exacto/mrr: 0.812 → 0.750          · fell 0.062, …
    procedimental/precision_at_5: 0.400 → 0.200     · fell 0.200, …

  ✗ gate FAILS: 5 blocking finding(s)
```

Four decisions, each with a test:

1. **It refuses to compare if the golden set changed** (sha256) or if `k` differs. recall@1
   against recall@5 would produce a "regression" invented by the parameter.
2. **Losing the ability to verify is a regression.** If the baseline said
   `grounded 0.88 (7/8)` and now says `n/a` because the system stopped exposing its chunk
   text, the number didn't hold — it vanished. That is the quietest degradation there is,
   and it blocks.
3. **An improvement never blocks, but it is printed** — a large jump upward is usually a bug
   in the evaluation, not a miracle in the system.
4. **CI proves the gate works.** A gate that never fails is decoration: the workflow feeds
   it the degraded system on purpose and **requires** exit code 1. If that step ever passes,
   the gate is broken.

## The per-category report

A single global number ("78% accurate") supports no decision. The breakdown names **what to
fix**:

```
  categoria                  n      recall@5         MRR      prec@5      grounded    abstencion
  ──────────────────────────────────────────────────────────────────────────────────────────────
  factual_lookup             8      1.00 (8)    1.00 (8)    0.23 (8)    0.88 (7/8)    1.00 (8/8)
  alfanumerico_exacto        4      1.00 (4)    1.00 (4)    0.20 (4)    1.00 (4/4)    1.00 (4/4)
  procedimental              4      1.00 (4)    1.00 (4)    0.40 (4)    1.00 (3/3)    1.00 (4/4)
  negative_control           4           n/a         n/a         n/a    1.00 (2/2)    0.50 (2/4)   ← the one that matters
```

*(Run against the scripted system in `tests/fixtures/`, not a real RAG — the report says so
in its own header.)*

Three decisions hold this table up:

1. **The report reloads the golden set and compares its sha256 against the run's. If they
   differ, it refuses to report.** Without that, the silent failure is one step away: run the
   eval, see it go badly, soften the set, and report the same JSON as if nothing happened.
2. **Every cell carries its denominator.** `0.88 (7/8)` is not `1.00 (2/2)`, and an average
   without `n` is an opinion with decimals.
3. **The header says which system was measured.** A pretty table from a run against a mock,
   without that line, ends up screenshotted into a portfolio as if it were a real measurement.

## The adapter contract

`groundcheck` talks to any system exposing
`question → {answer, citations[], retrieved[], abstained}`. It knows nothing about any RAG's
internals, which is exactly what makes it usable against any of them.

**`retrieved` is not `citations`, and that difference is the entire diagnosis.** Retrieved is
what entered the context; cited is what the system chose to show. recall@k, MRR and
precision@k are computed over the first. The smoke suite contains a case that retrieves the
correct chunk at rank 1 and **still answers wrong**: without `retrieved` in the contract, that
case would be diagnosed as a retrieval failure when it is a generation failure. If a system
does not expose what it retrieved, retrieval metrics report `n/a` — never zero.

- `mock:file.yaml` — a hand-scripted system. **It does not answer well on its own:** the
  script includes a deliberate failure (it answers with a number from another row of the
  table), because without a real failure the M2 checks would be written against data that
  always passes.
- `http(s)://…` — JSON POST. Field names are configurable through a mapping file; there is no
  standard here and pretending otherwise helps no one.

## The golden set format

```yaml
- id: torque-m24-88
  question: "¿Cuál es el torque del perno M24 grado 8.8 del cabezal del laminador 2?"
  category: factual_lookup          # one of six, closed list
  gold_answer: "720 ± 30 N·m"
  gold_numbers: ["720", "30"]       # must appear literally in the answer
  forbidden_numbers: ["950", "190"] # other rows of the table: if present, it crossed rows
  gold_source: { doc_id: c0d5f95f636967d1, revision: F, pages: [1] }
  must_abstain: false
```

*(Questions stay in the language of the source document — the corpus is mixed Spanish and
English, and translating a question would break the literal match against its chunk.)*

`gold_source` also accepts a **list** of sources, because a `multi_documento` case has its
answer split across several and with a single source that category — 10% of the set — cannot
be measured at all. A `multi_documento` with fewer than two distinct `doc_id`s fails to load.

**The validator is severe on purpose.** In an evaluation harness a typo does not raise an
error: it silently switches a check off. If someone writes `forbiden_numbers`, the very check
that catches the split-table bug disappears, the report stays green, and the published metric
becomes a lie. So an unknown key **fails the load**, as does a `negative_control` with a
`gold_answer`, a `must_abstain: true` outside its category, or the same number in both
`gold_numbers` and `forbidden_numbers`.

Every run stores the **sha256 of the suite file**. That is what lets you prove to a third
party that the set you measured with is the one committed, not a version softened after
seeing the results.

## Why this exists

You change chunk size from 512 to 1024, try three questions, feel like it answers better,
and ship it. You just made an engineering decision with n=3 and "seems better" as the
criterion. That is how most existing RAG systems were built.

The **20% negative controls** is what almost everyone forgets: without them, a system that
always answers confidently scores perfect.

## The golden set

| | v1 | v2 |
|---|---|---|
| questions | 20 | **39** |
| negative controls | 4 (20%) | **9 (23%)** |
| documents | 2 | **3** |
| languages | es | **es + en** |

**Why v2 exists:** v1 had 18 of 20 questions against a **single-page** document. Since gold
is matched at page level, its recall was trivially `1.00` — any chunk from that page counted
as relevant. v2 adds 19 questions over multi-page documents (a 117-page manual in English and
a 15-page one in Spanish), and those are the ones that produce real retrieval signal.

**Two categories remain absent, and the file itself says so:** `multi_documento` (the corpus
holds no genuine relationship between two documents; a question spanning two would be
artificial, and a false gold question is worse than an empty category) and
`revision_supersedida` (each document exists in a single revision). Both need new corpus, not
more work.

`scripts/verify_against_corpus.py` proves the set is backed by the source: it checks that
every `doc_id` exists, that the declared revision matches, that every `gold_number` appears
literally on the cited page — **and that every `forbidden_number` is also in the corpus**.
That last point is the least obvious and the most important: a forbidden number that isn't in
the document is not a trap, it's noise, and the check would never fire. The trap has to be a
real number from another row.

```
checked: 18 gold_numbers · 28 forbidden_numbers/codes · 9 negative controls (23%)
✓ the whole golden set is backed by the corpus
```

**The negative controls are plausible on purpose.** An obvious one — *"what is the capital of
France?"* — measures nothing: any RAG abstains. These ask for data that doesn't exist *right
next to* data that does: bolt M30 in a table that only holds M24 and M16; the M24 in **grade
12.9** when the table only lists 8.8 and 10.9 (the bolt exists, the grade doesn't); alarm
`E-200` among `E-114`, `E-115` and `E-141`; and material A312, real in ASTM but absent from
this documentation.

## `gate` and `diff` — division of labour

| | question it answers | answers with |
|---|---|---|
| `gate` | does this block the build? | an exit code |
| `diff` | what changed and **why**? | concrete cases |

A gate saying *"recall@5 fell 0.25"* is not enough to fix anything. What's actionable is
**which cases flipped**:

```
  Retrieval que se movio, por categoria
    ↓ alfanumerico_exacto/recall@5: 1.000 → 0.750

  alfanumerico_exacto  (1 broke)
    · alarma-e114/grounded: ok → FAIL   [broke]
```

`diff` distinguishes six transitions, and two of them are invisible to an average:
`se_apago` (the check stopped being verifiable — the number didn't drop, it **vanished**) and
`se_prendio`. A case appearing or disappearing from the set is **one** finding, not six:
otherwise adding a question floods the diff and hides the real regressions.

## The six deterministic checks

No model participates: these are set operations and normalised string comparisons.

| Check | What it verifies |
|---|---|
| `gold_numbers_present` | Every gold number appears literally in the answer |
| `forbidden_numbers_absent` | No number from another table row slipped in |
| `forbidden_codes_absent` | No identifier from a neighbouring entry slipped in |
| `grounded` | Every number **and code** in the answer is in a cited chunk |
| `citation_hits_gold` | Some citation points at the gold document/page |
| `abstention_correct` | On negative controls, the system abstained |
| `revision_current` | It cited the current revision, not a superseded one |

### Three states, and the difference between the last two is the point

`True` verified and passes · `False` verified and **fails** · `None` **could not be
verified** — the input is missing (the system didn't expose the chunk text, or the case
defines no gold numbers).

`None` counts as neither failure nor success. A harness that turns "I couldn't verify" into
"it failed" sends you to fix things that were never broken; one that turns it into "it
passes" publishes a number that measured nothing.

### Why `forbidden_numbers` is not redundant with `grounded`

If the answer carries `950` when it should carry `720`, and the whole table is in the cited
chunk, **`grounded` passes** — the 950 is literally there. It is `forbidden_numbers` that
names the failure: it crossed rows. That is the split-table bug, and one check alone cannot
see it.

### The alphanumeric-code trap

`E-114` **does not contribute the number 114**, and `M24` does not contribute 24. If they were
extracted as numbers, the *correct* answer "alarm E-114 indicates overtemperature" would
return `grounded: false` because "114" never appears loose in the chunk. That false negative
is worse than not measuring: it sends you to "fix" a system that was fine. Codes are extracted
and compared as codes.

Comparison is canonical, never substring: searching for `30` as a substring would find it
inside `1300` and declare grounded a number that was never there.

The same rule covers **citation markers**: in `720 +/- 30 N.m [1]`, the `[1]` is a reference,
not a magnitude. Requiring it to be grounded in the chunk would fail a system **for citing
properly** — which is the behaviour every other check rewards.

### The abstention detector is a phrase list, not a model

Deliberate (§8 of the spec): a visible, auditable list plus manual review of the
disagreements. A classifier would be a black box inside the verifier itself, and the house
rule is that no model judges another model.

## Three metric conventions, written down so nobody changes them by accident

These are the decisions that, taken silently, make two runs stop being comparable. Each has a
test that breaks if someone changes it.

1. **`precision@k` divides by `k`**, not by the number retrieved — the standard IR
   definition. A system returning 3 chunks with k=5 takes the penalty, and correctly so: it
   asked for less context than was available. The retrieved count is recorded so anyone can
   recompute under the other convention.
2. **`recall@k` counts targets covered, not relevant items.** Two copies of the same chunk
   cover one target, not two. Counting items would return 1.0 where 0.5 is correct — the
   classic bug that inflates the number.
3. **Negative controls return `None`, not zero**, and the average ignores `None`. A zero gets
   averaged in and drags the mean with a data point that does not exist.
