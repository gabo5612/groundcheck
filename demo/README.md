# groundcheck — static demo

A real run, served without a server, with the deterministic half of the harness running in
the visitor's browser.

## What runs here and what does not

| Component | In the demo | Why |
|---|---|---|
| Retrieval metrics (recall@k, MRR, precision@k) | ✅ recomputed live | Set operations over the recorded retrieval — `k` is a slider |
| Number and code extraction | ✅ identical | Regular expressions, ported rule by rule from `numbers.py` |
| Grounding, forbidden numbers, forbidden codes | ✅ identical | Deterministic comparison against the retrieved chunks |
| Citation and revision checks | ✅ identical | Set membership |
| Abstention check | ✅ identical | A visible phrase list, not a classifier |
| The system under test | ❌ recorded | `shopfloor` needs Postgres, pgvector and a local model |
| LLM-judge metrics | ❌ not in the demo | Out of the deterministic core; the CLI keeps them separate too |

The run bundled here was measured against the real `shopfloor` endpoint. The page does not
replay stored verdicts: it re-evaluates every case and diffs its own results against the
ones Python wrote. The badge at the top reports that diff, and it goes red if the port ever
drifts.

## Verifying that claim yourself

```bash
node verify.mjs      # 402/402 agree with the Python harness
```

Same comparison the page performs, in the terminal, exit code 1 on any disagreement.

## Deploying

```bash
cd demo
vercel --prod
```

No environment variables, no database, no build step.

## Regenerating the data

```bash
.venv/bin/python -m groundcheck.export_demo               # newest run in runs-shopfloor/
.venv/bin/python -m groundcheck.export_demo path/to/run.json
```

The exporter refuses to build a bundle whose golden set no longer matches the run's
recorded sha256 — the same guard `groundcheck report` applies.
