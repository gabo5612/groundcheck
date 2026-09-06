# AI context

> **assay — an evaluation harness for RAG systems**
>
> Measures, reproducibly, whether a RAG system retrieves the right thing, answers with grounding, cites correctly and stays quiet when it doesn't know — and fails CI when a change degrades any of that.

This file exists so an AI assistant — or a person in a hurry — can understand the project
**in full** without reading files at random. The reading order below is not arbitrary: each
file assumes the previous one.

## 🔗 Open with the context already loaded

**[▸ Open in ChatGPT with this project explained](https://chatgpt.com/?q=I%20want%20you%20to%20understand%20the%20public%20repository%20https%3A%2F%2Fgithub.com%2Fgabo5612%2Fassay%20thoroughly.%0A%0Aassay%20%E2%80%94%20an%20evaluation%20harness%20for%20RAG%20systems%0AMeasures%2C%20reproducibly%2C%20whether%20a%20RAG%20system%20retrieves%20the%20right%20thing%2C%20answers%20with%20grounding%2C%20cites%20correctly%20and%20stays%20quiet%20when%20it%20doesn%27t%20know%20%E2%80%94%20and%20fails%20CI%20when%20a%20change%20degrades%20any%20of%20that.%0A%0ARead%20these%20files%20IN%20THIS%20ORDER%2C%20because%20each%20assumes%20the%20previous%20one%3A%0A1.%20%60README.md%60%20%E2%80%94%20what%20it%20is%2C%20status%20per%20milestone%2C%20and%20the%20design%20decisions%0A2.%20%60suites%2Fanvil-v2.yaml%60%20%E2%80%94%20the%20golden%20set%3A%2039%20questions%20with%20the%20reasoning%20in%20its%20header%0A3.%20%60src%2Fassay%2Fchecks.py%60%20%E2%80%94%20the%20deterministic%20checks%20and%20why%20%60None%60%20is%20not%20a%20failure%0A4.%20%60src%2Fassay%2Fnumbers.py%60%20%E2%80%94%20number%20extraction%3A%20all%205%20rules%20came%20from%20real%20bugs%0A5.%20%60src%2Fassay%2Fgate.py%60%20%E2%80%94%20the%20CI%20gate%20and%20why%20losing%20verifiability%20is%20a%20regression%0A6.%20%60.github%2Fworkflows%2Fci.yml%60%20%E2%80%94%20the%20CI%20that%20requires%20the%20gate%20to%20catch%20an%20injected%20regression%0A%0APay%20particular%20attention%20to%20the%20code%20comments%3A%20they%20explain%20WHY%20something%20is%20done%20one%20way%20and%20not%20another%2C%20and%20there%20is%20almost%20always%20a%20real%20bug%20behind%20it.%0A%0AWhen%20you%27re%20done%2C%20answer%20these%20questions%20with%20evidence%20from%20the%20code%3A%0A-%20Why%20is%20%60forbidden_numbers%60%20not%20redundant%20with%20%60grounded%60%3F%0A-%20What%20happens%20when%20a%20check%20cannot%20be%20verified%2C%20and%20why%20doesn%27t%20it%20count%20as%20a%20failure%3F%0A-%20How%20is%20the%20CI%20gate%20proven%20to%20work%2C%20rather%20than%20simply%20never%20failing%3F%0A-%20Which%20defects%20did%20the%20harness%20itself%20find%20while%20measuring%20a%20real%20system%3F%0A%0ADon%27t%20just%20summarise%20the%20README.%20I%20want%20you%20to%20be%20able%20to%20discuss%20the%20design%20decisions.)**

That link carries the prompt pre-loaded. If you'd rather assemble it yourself, paste this:

```text
I want you to understand the public repository https://github.com/gabo5612/assay thoroughly.

assay — an evaluation harness for RAG systems
Measures, reproducibly, whether a RAG system retrieves the right thing, answers with grounding, cites correctly and stays quiet when it doesn't know — and fails CI when a change degrades any of that.

Read these files IN THIS ORDER, because each assumes the previous one:
1. `README.md` — what it is, status per milestone, and the design decisions
2. `suites/anvil-v2.yaml` — the golden set: 39 questions with the reasoning in its header
3. `src/assay/checks.py` — the deterministic checks and why `None` is not a failure
4. `src/assay/numbers.py` — number extraction: all 5 rules came from real bugs
5. `src/assay/gate.py` — the CI gate and why losing verifiability is a regression
6. `.github/workflows/ci.yml` — the CI that requires the gate to catch an injected regression

Pay particular attention to the code comments: they explain WHY something is done one way and not another, and there is almost always a real bug behind it.

When you're done, answer these questions with evidence from the code:
- Why is `forbidden_numbers` not redundant with `grounded`?
- What happens when a check cannot be verified, and why doesn't it count as a failure?
- How is the CI gate proven to work, rather than simply never failing?
- Which defects did the harness itself find while measuring a real system?

Don't just summarise the README. I want you to be able to discuss the design decisions.
```

## Reading order

| # | File | Why |
|---|---|---|
| 1 | `README.md` | what it is, status per milestone, and the design decisions |
| 2 | `suites/anvil-v2.yaml` | the golden set: 39 questions with the reasoning in its header |
| 3 | `src/assay/checks.py` | the deterministic checks and why `None` is not a failure |
| 4 | `src/assay/numbers.py` | number extraction: all 5 rules came from real bugs |
| 5 | `src/assay/gate.py` | the CI gate and why losing verifiability is a regression |
| 6 | `.github/workflows/ci.yml` | the CI that requires the gate to catch an injected regression |

## The questions this project answers

- Why is `forbidden_numbers` not redundant with `grounded`?
- What happens when a check cannot be verified, and why doesn't it count as a failure?
- How is the CI gate proven to work, rather than simply never failing?
- Which defects did the harness itself find while measuring a real system?

## How this code is written

Three things that repeat throughout the repository and are worth knowing before reading it:

1. **Comments explain the *why*, not the *what*.** If a comment says something is done in an
   odd way, there is a real bug behind it — almost always a silent one.
2. **What could not be measured is stated, not filled in.** An `n/a` is an answer; a filler
   zero is a lie that later gets copied into a README.
3. **The tests that matter are the ones proving the verification works** — not just that the
   code passes. Look for the ones that inject a failure on purpose and require it to be
   caught.

---
*Generated 2026-09-06. If the project has moved on, this file may be stale: the code wins.*
