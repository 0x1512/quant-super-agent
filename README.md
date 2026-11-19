# Quant Super Agent

**The quant edition of DeepSeek's Super Agent — one orchestrator, a crew of workers, research orders in, reports out, minute-level throughput.** Every number is machine-settled and gate-recomputed.

![status](https://img.shields.io/badge/status-v0.1.0--fresh%20seed-green) ![tests](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/0x1512/quant-super-agent/main/docs/badge/tests.json) ![license](https://img.shields.io/badge/license-MIT-blue) ![python](https://img.shields.io/badge/python-3.10%2B-blue)

<!-- BEGIN STATUS CARD — rendered from docs/STATUS.json by `make readme-render`; hand edits are overwritten at release -->
**Release status card — v0.2.0 (2026-11-19)** · machine-generated, frozen until the next release.

| as of v0.2.0 | |
|---|---|
| test suite | 544 tests, offline & deterministic — `make verify` (live count: the badge above) |
| reference full run | 78 candidates → 14 settled orders, minute-level, auto-sized worker crew, on the 300-ticker × 1210-day pinned panel |
| parallelism | 4.0x parallel vs sequential, byte-identical for any N |
| conversation | bar-only follow-ups rescore zero rows; universe recomputes finish in tens of seconds |

Numbers live in [EVIDENCE](docs/EVIDENCE.md) · [NEWS](docs/NEWS.md) · [CASES](docs/CASES.md) · [TOUR_NUMBERS.json](docs/TOUR_NUMBERS.json) (regenerate & drift-check: `make tour`). This card is the README's only numeric content and changes only via `make release-readme`.
<!-- END STATUS CARD -->

**What you get, how fast, why you can trust it, and where to start — in one screen:**

- **What:** one sentence in → a research plan tree, a named crew (GateKeeper / RepoSmith / FlowMapper / SmokeRunner), a scored factor campaign, and settled, frozen-parameter orders out. Conversational follow-ups ("raise the bar", "drop smallcaps") reuse or recompute only what changed.
- **How fast:** a reference full run on the pinned panel completes in **minutes** on one box, with the worker crew auto-sized; bar-only follow-ups rescore zero rows. Throughput as a magnitude, not a stopwatch — the status card above is the pinned versioned reference.
- **Why you can trust it:** every claim is a machine-verified evidence card (fingerprinted data, no look-ahead, factor code re-executed in a sandbox); retries are deflation-floored so the loop cannot p-hack itself; claims settle on a horizon the admission never touched, and a tighten-only ratchet never loosens a bar. A fabrication-injection harness measures these failure modes instead of assuming them.
- **Start now:**

```bash
git clone https://github.com/0x1512/quant-super-agent.git && cd quant-super-agent
make offense-full   # the reference full run: plan tree, crew, settled orders (or honest zero)
make tour           # regenerate every demo-quoted number from artifacts; drift alarms
```

> **Thesis** ([docs/THESIS.md](docs/THESIS.md)): *throughput is cheap; verification is the constraint* — the deployable information ratio factors into stage efficiencies that compose multiplicatively, and the field's budget terminates before the binding terms.
>
> **What is designed but not shipped yet:** running the published FIB scenarios against third-party agent frameworks (the builders are importable; see [docs/RUBRICS.md](docs/RUBRICS.md)). See the [roadmap](#roadmap-summary).
>
> Research use only — not financial advice.

## Quickstart

Everything below runs in seconds to minutes on a fresh clone, no network, no keys. Each line names its artifacts and its self-verify command, so the numbers are yours to generate:

```bash
git clone https://github.com/0x1512/quant-super-agent.git
cd quant-super-agent

# 1) lifecycle: order issue → cards → verify gate as CI → PR → merge
python examples/run_lifecycle.py            # honest run: verdict=fail, gate green, merges anyway
python examples/run_lifecycle.py --fib 7    # inject a silent-pass fabrication: gate blocks the merge

# 2) research loop: LLM proposes hypotheses + factor code under a budget;
#    the registry and the deflation floor discipline every retry
python examples/run_mining.py

# 3) v0.4 acceptance: roles x debate-rounds ablation table
#    (planted-signal worlds -> discovery, noise worlds -> false positives)
python examples/run_ablation.py

# 4) v0.5 acceptance: settlement ledger + calibration curve
#    (admitted claims settle on data the admission never touched)
python examples/run_calibration.py

# 5) v0.6 acceptance: Fabrication Injection Benchmark harness
#    (17 injection scenarios x 2 baselines + full gate, K=3 repeats)
python examples/run_fib.py

# 6) v0.7 acceptance: the budget estimators
#    discovery@B (breadth decays as trials accumulate) +
#    alpha-frontier / envelope (P-hat vs power; the operating point)
python examples/run_discovery.py
python examples/run_frontier.py

# 7) v1.2: the zoo as an order book — every hypothesis has a lifecycle
#    (infra gate -> blackboard -> fork cards -> orders -> drift caught)
python examples/run_orders.py
python examples/run_orders.py            # second run: recall, not recompute

# 8) v1.3: offense layer — 30-factor cited library x residual objective
#    (score everything orthogonal to the zoo survivors; clones score 0;
#     winners settle as frozen orders, honest zero if none clear the bar)
python examples/run_offense.py           # smoke window, tens of seconds
python examples/run_offense.py --full    # pinned fixtures, 300 tickers x 1210 days
make offense-full                        # same, one target

# 8b) v1.4: the conversation plane — plan tree, auto crew, follow-ups,
#     sandbox forge loop, memory receipts, layered report, drift alarm
python -m qsa.planner "小盘股隔夜反转，沙盒生成补缺口"   # intent -> fingerprinted plan
make followup    # "raise the bar": rows reused, 0 rescored
make mem         # memory ledger + tighten-only ratchet check + run manifest
make tour        # regenerate every demo number from artifacts; drift alarms

# 9) your own data: CSV -> legal, fingerprinted snapshot (local-first)
python -m qsa.ingest myprices.csv mydata/

# the whole contract, machine-checked (live count: the tests badge)
python -m unittest discover -s tests -v
```

What the mining demo prints (abbreviated):

```
[1] settled     E-0001 verdict=fail (N=1) attribution=threshold_miss
[2] settled     E-0002 verdict=fail (N=2) attribution=deflation
[3] settled     E-0003 verdict=fail (N=3) attribution=deflation
final_verdict: fail — an honest negative chain under budget, every card gate-checked and settled.
```

Iteration 1 misses its pre-registered bar. Iterations 2 and 3 are the classic researcher move — retest a cousin of the rejected idea — and the deflation floor rejects them mechanically, because the registry counted every look. The loop ends in an honest negative instead of a p-hacked positive. That is the product.

The gate also stands alone (`--registry` enables ledger ordering, deflation, and `factor_code` recomputation):

```bash
python -m qsa.verify --hypothesis cards/H.json --result cards/E.json \
                     --snapshot snapshot/ --registry registry.jsonl
```

## What it can do

The storefront answers in verbs, not in per-round numbers. Each capability is a shipped, test-covered plane with its own acceptance script (Quickstart) and evidence address ([EVIDENCE.md](docs/EVIDENCE.md)):

- **Plans research** — a one-sentence intent compiles to a fingerprinted plan tree with named crew roles; re-runs recall settled work instead of recomputing it
- **Scores candidate factors** — a 30-factor cited library (WorldQuant 101 subset, range-vol, liquidity), pairwise interactions, and mutation search, all scored against a **residual objective** orthogonal to the zoo survivors — clones of what the zoo already knows score zero
- **Forgets nothing it was told** — conversational increments: a bar-only follow-up re-verdicts the cached leaderboard with zero rows rescored; a universe change recomputes only the rows it moves, kept/added/dropped spelled out; an unparseable ask is refused, not guessed
- **Generates missing factors** — a sandbox forge loop fills machine-detected gaps with AST-whitelisted code under the same residual yardstick, every row tagged `source: sandbox-forge` with its code hash
- **Settles claims** — admitted factors settle on a horizon the admission never touched, into a hash-chained ledger with a calibration curve and a **tighten-only** reflection rule
- **Refuses its own failures** — pre-registration ordering, deflation floors, one-shot OOS windows, and a fabrication-injection harness with published rubrics and raw logs measure the failure modes instead of assuming them
- **Stays parallel-safe** — the auto-sized worker crew partitions the candidate pool; the parallel and sequential paths are byte-identical for any N

## Cases

The case index keeps the storefront one line per case; the archive (dates, fingerprints, reproduce commands, full numbers) is [docs/CASES.md](docs/CASES.md).

| # | Case | One line |
|---|---|---|
| 1 | Top-300 baseline | the reference full run behind the status card |
| 2 | Smallcap residual attack | one command, full panel, a forged factor clears the bar |
| 3 | Forge turnaround | a measured gap turned into sandbox-generated candidates |

## Why

Existing agentic quant frameworks generate *signals*; none of them generate *verifiable research*.

| Pain | Reality in current tools |
|---|---|
| **Unverifiable claims** | An agent reports "IC = 0.08" — nothing checks the data fingerprint, the look-ahead window, or whether the metric was computed at all |
| **No honesty feedback** | Claimed performance is never settled against realized performance; hallucinated alpha is indistinguishable from real alpha |
| **Unbounded autonomy** | Autonomous re-scheduling, tool use, and policy interpretation with no containment story (the pilots measured one violating an explicit human instruction seconds after acknowledging it) |
| **Irreproducible runs** | LLM non-determinism is acknowledged in READMEs, rarely measured, never decomposed |

Three mechanisms answer these — machine-checked evidence, honest settlement, bounded autonomy. Two are shipped in this repo; the third is pilot-validated and ships with the harness layers.

## How it works

### 1. Evidence plane — machine-checked claims (shipped, v0.2)

Every research claim is a structured **evidence card** that must pass a mechanical gate before it can be cited:

- **H cards** (hypotheses) are registered *before* experiments: mechanism, falsifiable condition, evaluation window, and the admission bar — thresholds, required metrics, minimum observations — all pre-committed.
- **E cards** (experiment results) cite the exact data snapshot (sha256), the pinned engine version, the window, and carry the factor source itself.

A real E card from the mining demo (`work/mining/cards/` after you run it; values not illustrative — the gate recomputed them):

```json
{
  "schema": "experiment_result",
  "exp_id": "E-0002",
  "hyp_id": "H-0002",
  "window": "20240102:20240506",
  "snapshot_hash": "7b81decd7fdc32d63ef60f22944cbe348a6c052b3fd48ba13f01824aef08053d",
  "engine": "qsa-eval-0.4.0",
  "factor_code": "def factor(closes, tickers, dates, i): … (full source)",
  "factor_code_sha256": "e1c0d7e6b6bd95bd2dc5c6366227bc4f7042056676fb1a61f243fb9b0c94d000",
  "metrics": {"rankic_mean": -0.006586, "rankic_tstat": -0.219072,
              "quintile_spread": 5.1e-05, "monotonicity_proxy": 0.1, "n_dates": 86},
  "verdict": "fail",
  "settled_at": "2024-05-06"
}
```

The gate is deliberately dumb and strict: schema completeness → hypothesis registered before the experiment → snapshot fingerprint match → window alignment (no look-ahead) → engine pin, ledger discipline, deflated verdict, and **re-execution of `factor_code` in a sandbox with metrics required to match**. A claim that cannot be machine-verified does not exist. Fabricated cards are blocked from `main` by branch protection; honest negatives merge.

### 2. Research loop — a loop that cannot p-hack itself (shipped, v0.3 + v0.4)

```mermaid
flowchart LR
    A[Research order<br/>+ iteration budget] --> B[LLM proposes hypothesis<br/>admission bar pre-committed]
    B --> C[(Experiment registry<br/>append-only, hypothesis<br/>before experiment)]
    C --> D[Sandboxed factor code<br/>AST whitelist · sees closes ≤ t only]
    D --> E{Mechanical verdict<br/>Bonferroni floor at family N}
    E -- fail --> F[Attribution<br/>threshold · instability · deflation · oos]
    E -- in-sample pass --> G{One-shot OOS window}
    G -- fail --> F
    G -- pass --> V{Roles + bull/bear review<br/>risk: half-split stability veto<br/>debate: checkable claims verified}
    V -- veto --> F
    V -- admitted --> H[Verify gate as forge CI<br/>recomputes factor_code + vetoes]
    F -- next hypothesis<br/>budget-bounded --> B
    H --> I[PR + merge under<br/>branch protection]
```

Four disciplines make retry pressure harmless:

- **Pre-registration ordering** — the append-only registry refuses an experiment whose hypothesis was not registered first, duplicated IDs, and post-hoc edits (FIB classes 9).
- **Multiple-testing deflation** — with N settled looks in a family, the t-statistic must clear the Bonferroni floor for N. The 10th "new idea" faces a bar the 1st did not; bar-lowering retries fail mechanically (FIB class 11).
- **Sandboxed factor code** — LLM-written factors run under an AST whitelist with a truncated-view contract: v1 `factor(closes≤t, tickers, dates≤t, i)` or v2 `factor(closes≤t, volumes≤t, tickers, dates≤t, i)` (liquidity-aware factors; v1 code runs unchanged). Look-ahead needs a sandbox escape, not a bug (FIB class 2: metrics that don't match the code are rejected by recomputation).
- **One-shot OOS windows** — an out-of-sample window that produced a pass is burned in the ledger; reuse is refused at registration (FIB class 13).
- **Ablatable roles with mechanical duties** (v0.4) — the data role blocks underpowered designs before they burn a trial; the risk role vetoes on measured half-split instability. A role is a persona prompt *plus* a function: ablating it removes a check, not a vibe.
- **Bull/bear review before admission** (v0.4, rounds configurable) — reviewers emit structured R cards; a bear objection is upheld only if its check verifiably fails, bull rhetoric never admits, and every R card lands in the append-only ledger. The gate also verifies *claimed vetoes* recompute from source — a fabricated veto is as much a lie as a fabricated pass.

Failures are classified mechanically (insufficient observations / instability / threshold miss / deflation / OOS miss) and the class feeds the next-hypothesis prompt — with an explicit no-bar-lowering instruction the loop is required to ignore under pressure.

### 3. Honest settlement — claimed vs realized (shipped, v0.5)

Admitted factors are not "done": every claim settles on a 90-day horizon the admission never touched — the world is deterministically continued from the same seed, the factor re-executes in the sandbox, and the realized metrics come from the same engine that gated the admission (never from the card). Results land in a **hash-chained settlement ledger** whose every entry rebuilds and recomputes under audit, and feed two things: the **calibration curve** (claimed vs realized, the headline metric — not return), and a **reflection rule** that tightens a family's admission bar ×1.25 when its settled claims fall short too often (calibration only tightens; it never loosens).

### 4. Fabrication Injection Benchmark harness (shipped, v0.6; extended v0.7)

The failure modes under pressure are measured, not assumed: injection classes from [docs/BENCHMARK.md](docs/BENCHMARK.md) — phantom metrics, silent passes, unit mismatches, post-hoc bar lowering, ledger tampering, settle forgery, cherry universes, cost-blind nets, … — are mechanized as deterministic PR submissions (an otherwise honest H/E card pair with one scripted mutation each) and routed through three judges: an ungated single agent, a schema-only reviewer, and the full gate. The full gate catches every injection with the error naming the touched field; the baselines catch far fewer — the acceptance table and raw logs live in [docs/EVIDENCE.md](docs/EVIDENCE.md) P5/P6, rubrics in [docs/RUBRICS.md](docs/RUBRICS.md).

### 4b. Budget estimators — every term of the thesis equation, measured (shipped, v0.7)

The thesis factors the deployable information ratio as *E[IR] ≈ ĪC·√B_eff·P̂·TC·e^{(λℓ−δ)t}*. v0.7's discipline: a capability ships only together with the estimator that measures its term. What reads out of pipeline state (`qsa/budget.py` + three scripts):

- **B — discovery@B**: one family, one shared ledger; discovery decays as trials accumulate (the ledger's own Bonferroni floor rises) while false positives stay at zero (`run_discovery.py`)
- **P̂ — α-frontier**: power vs false-positive rate across admission floors on planted/noise worlds (truth known by construction); P̂ = power/(power+fpr) (`run_frontier.py`)
- **TC — net-of-cost settlement**: per-side bps pinned in the fingerprinted manifest, turnover and net spreads computed by the engine and recomputed by the gate; on the calibration sweep the toy reversal keeps a small net/gross ratio at a realistic cost — and FIB 22 (net sold at gross) is caught by recomputation
- **λℓ−δ — cohort decay slope**: OLS of realized on claimed across claimed-bins over the settlement horizon (mild leakage)
- **Envelope**: discovery(N)·P̂(N)·√N — breadth net of verification; weak effect pools peak at N\*=1 (they never amortize verification), strong ones far higher. The operating point is a property of the pool, and the instrument says so

### 5. Bounded autonomy (pilot-validated; ships with the harness layers)

Autonomy is a dial with a fence — L0 observe / L1 suggest / L2 admit-gated / L3 autonomous — bounded by a surgery SOP, a watchdog (sub-second detection→stop, measured in the pilots), and prompt discipline. The design is informed by a real incident the pilots caught: an orchestrator re-queued a previously-ignored trigger **seconds after** promising a human it would not start work. The containment stack was validated in a three-arm × 5-round experiment ([Evidence](docs/EVIDENCE.md)).

## Comparison

| | TradingAgents | ai-hedge-fund | RD-Agent (Qlib) | FinRL | **Quant Super Agent** |
|---|---|---|---|---|---|
| Multi-role agents | ✔ analysts + debate | ✔ persona agents | ✔ research/dev loop | ✖ (RL, not agentic workflow) | ✔ **shipped v0.4** — ablatable roles with mechanical duties |
| Adversarial review gate | ✔ debate rounds | ✖ | ✖ | n/a | ✔ **shipped v0.4** — checkable-claim verification, claimed-veto recomputation |
| Claim settlement + calibration | ✖ | ✖ | ✖ | backtests only | ✔ **shipped v0.5** — simulator-authoritative settlement ledger, calibration curve, tighten-only reflection |
| Research loop (H→E→iterate) | ✖ decision per date | ✖ | ✔ | ✖ | ✔ **shipped v0.3** — pre-registered, deflation-floored |
| Claim-level CI gate | ✖ | ✖ | partial (backtest check) | ✖ | ✔ **shipped** — schema + fingerprint + no-lookahead + code recomputation |
| Multiple-testing control | ✖ | ✖ | ✖ | ✖ | ✔ **shipped v0.3** — Bonferroni floor at family N |
| Fabrication benchmark | ✖ | ✖ | ✖ | ✖ | ✔ **shipped v0.6, extended v0.7** — FIB harness with published rubrics and raw logs |
| Budget-equation estimators | ✖ | ✖ | ✖ | ✖ | ✔ **shipped v0.7** — discovery@B, α-frontier/P̂, net-of-cost TC, decay slope, envelope |
| Cross-session memory (blackboard + order book) | ✖ | ✖ | ✖ | ✖ | ✔ **shipped v1.2** — hash-chained blackboard seeded with real lessons, order state machine with frozen admission params, fork cards |
| Offense layer (cited library + residual objective + mutation search) | ✖ | ✖ | ✖ | ✖ | ✔ **shipped v1.3** — cited factor library, IC orthogonal to zoo survivors, pairwise interactions, window mutations, honest zeros |
| Conversation plane (intent, follow-ups, forge loop) | ✖ | ✖ | ✖ | ✖ | ✔ **shipped v1.4** — fingerprinted plan trees, auto-sized crew, zero-rescore follow-ups, sandbox forge |
| Autonomy control | ✖ | ✖ | ✖ | n/a | pilot-validated design (L0–L3 + watchdog, sub-second measured) |
| Reproducibility protocol | acknowledged, unmeasured | ✖ | ✖ | seed-based | ✔ byte-level determinism asserted by tests + data fingerprints |

Related work we admire and borrow from: [TradingAgents](https://github.com/TauricResearch/TradingAgents) (roles, debate, settlement memory), [ai-hedge-fund](https://github.com/virattt/ai-hedge-fund) (independent judgments → aggregation), [RD-Agent](https://github.com/microsoft/RD-Agent) (factor R&D iteration), [FinRL](https://github.com/AI4Finance-Foundation/FinRL) (environment rigor). The harness patterns come from DeepSeek's MIT-licensed dsh-superagent research prototype (order lifecycle, worktree isolation, panel APIs) — see [Acknowledgments](#acknowledgments).

## Evidence & status

The storefront links out; the numbers live here, updated per round:

- **[docs/EVIDENCE.md](docs/EVIDENCE.md)** — the full evidence inventory: per-version acceptance tables, machine-emitted verdicts with reproduce commands, pilot results
- **[docs/NEWS.md](docs/NEWS.md)** — the per-round run log (what shipped, what was measured)
- **[docs/CASES.md](docs/CASES.md)** — the case archive (dates, fingerprints, reproduce commands, full numbers)
- **[docs/STATUS.md](docs/STATUS.md)** — the generated status page (refreshed at each release)
- **[docs/TOUR_NUMBERS.json](docs/TOUR_NUMBERS.json)** — the machine-regenerable tour baseline (`make tour` re-derives and drift-alarms)
- **[README.dev.md](README.dev.md)** — dev-facing working status (churns freely; not the storefront)

Everything claimed for the shipped versions is reproducible from this repo: a fully offline, deterministic test suite (live count: the badge above) and a CI matrix across Python 3.10–3.13 that also runs all the acceptance demos as regression contracts — the acceptance tables in [docs/EVIDENCE.md](docs/EVIDENCE.md) map every discipline to its test.

## Roadmap (summary)

- **v0.1** design + benchmark spec + evidence docs (shipped)
- **v0.2** evidence plane: cards + verify gate + deterministic forge (shipped)
- **v0.3** research loop: registry, deflation, sandboxed mining, one-shot OOS, CSV ingestion (shipped)
- **v0.4** ablatable quant roles + bull/bear review gate + ablation table (shipped)
- **v0.5** settlement ledger + calibration curve + tighten-only reflection rule (shipped)
- **v0.6** Fabrication Injection Benchmark harness + rubrics (shipped; external-framework runs next)
- **v0.7** budget estimators, re-anchored to the transfer theory: sandbox v2 (volumes), coverage/universe pinning, cost-capacity accounting with gate-recomputed net metrics, cohort decay slope, discovery@B + α-frontier + envelope (shipped)
- **v0.8** portfolio claims: P cards, composites, walk-forward folds, real-data settlement (planned)
- **v1.1** factor factory: public-literature factors, one command, fast-lane ranking (IC/ICIR/spread/train-val-oos) + tradeable-metrics backtest (fees, NW Sharpe, turnover, capacity, drawdown, triple-gate) — `python examples/run_factory.py`; evidence: [EVIDENCE.md](docs/EVIDENCE.md) §v1.1
- **v1.0** three classic scenarios end to end (report replication · view verification · regime summarization), each with recorded ungated-agent controls — spec: [docs/V1_SCENARIOS.md](docs/V1_SCENARIOS.md); Scenario A shipped: `python examples/run_replication.py` (evidence: [EVIDENCE.md](docs/EVIDENCE.md) §v1.0)
- **v1.1** paper artifact + reproduction protocol
- **v1.2** organizational memory: blackboard (hash-chained, seeded with real incidents), infra gate, order state machine (admit freezes params; settle/refuse mechanical; refused is terminal; recall on re-run), fork cards (explicit convention decisions) — `python examples/run_orders.py`; self-playing demo: `python examples/build_demo_video.py` → [docs/demo_video.html](docs/demo_video.html)
- **v1.3** offense layer: 30-factor cited library (WorldQuant 101 subset, range-vol, liquidity) on optional high/low/amount/vwap panels, residual objective vs zoo survivors, pairwise interactions + window mutations, one command — `python examples/run_offense.py`; catalog: [FACTOR_LIBRARY.md](docs/FACTOR_LIBRARY.md)
- **v1.3.x (next: v1.3.1)** — the patch line: from v1.3 on, all R&D ships as patches under the current minor (a new minor only for a new capability plane). v1.3.1 = deflation across the offense family + neutralization of the residual basis; v1.3.2 = GTJA191/larger WQ101 subset; backlog folded in from v1.2
- **v1.4** conversation & self-orchestration plane (shipped): intent entry, plan tree, auto crew, conversational increments, repair ladder, sandbox forge loop, fork cards as questions, memory receipts, layered report, tour drift alarm

Full version: [docs/ROADMAP.md](docs/ROADMAP.md).

## Documentation

- [Storefront policy](docs/README_POLICY.md) — where numbers live, what the README may say, how to change it (the 20 mechanisms)
- [Architecture](docs/ARCHITECTURE.md) — components, order lifecycle, gate internals, autonomy supervisor
- [Thesis](docs/THESIS.md) — the transfer theory: budget equation, propositions, estimator protocol
- [Fabrication Injection Benchmark](docs/BENCHMARK.md) — injection classes, metrics, protocol
- [FIB rubrics](docs/RUBRICS.md) — judge definitions, metric formulas, acceptance bar
- [Evidence](docs/EVIDENCE.md) — pilot inventory, public acceptance tables
- [News](docs/NEWS.md) — per-round run log
- [Cases](docs/CASES.md) — case archive with reproduce commands
- [v1.0 scenarios](docs/V1_SCENARIOS.md) — the demo release: report replication · view verification · regime summarization, numbered goals with acceptance
- [Factor library](docs/FACTOR_LIBRARY.md) — the offense layer: cited factors, residual objective, interactions, mutations, honest-zero policy
- [Roadmap](docs/ROADMAP.md) — phases, scope, acceptance criteria
- 中文门面：[README.zh-CN.md](README.zh-CN.md)

## Acknowledgments

- The order-lifecycle harness patterns (orchestrator/worker, worktree isolation, panel API) are adapted from [dsh-superagent](https://github.com/deepseek-ai/dsh-superagent-prototype) (MIT), a research prototype by the DeepSeek Harness team (harness: [deepseek-harness](https://github.com/deepseek-ai/deepseek-harness)). Quant Super Agent is an independent project and is not affiliated with or endorsed by DeepSeek.
- Role/debate/settlement ideas informed by TradingAgents (Xiao et al., arXiv:2412.20138); factor-iteration framing by RD-Agent; portfolio realism by ai-hedge-fund and FinRL.

## Citation

```bibtex
@misc{quantsuperagent2026,
  title  = {Quant Super Agent: A Verifiable Agentic Quant Research Factory},
  author = {Quant Super Agent Contributors},
  year   = {2026},
  note   = {Evidence plane, gated research loop, roles, debate, settlement, calibration, FIB harness, budget estimators, order book, offense layer, conversation plane},
  url    = {https://github.com/0x1512/quant-super-agent}
}
```

## License & disclaimer

MIT — see [LICENSE](LICENSE). This is research software. Nothing here is financial advice, and nothing here should trade real money. All pilot results were obtained in emulation environments.
