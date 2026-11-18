# Roadmap

Public, version-gated. Each version has scope + acceptance criteria; code lands here phase by phase out of the internal pilot environment.

## v0.1 — design skeleton (shipped)
- README (EN/zh), architecture, FIB benchmark spec, evidence inventory, roadmap
- Acceptance: docs coherent, no overclaim of unimplemented features

## v0.2 — evidence plane, runnable (shipped)
- Evidence card schemas (H/E, versioned) + verify gate (schema · fingerprint · no-lookahead · verdict consistency)
- Toy dataset + immutable snapshot tooling + reconciliation stub
- Deterministic forge emulation (issues/PRs/CI hooks) so anyone can run `order → cards → gate → PR` offline in <10 min
- Acceptance: FIB classes 1, 4, 7, 14, 15 caught by gate in automated tests — **met** (also 3 and the reverse verdict lie; see `tests/test_gate.py`, 31 tests green)

## v0.3 — research loop (shipped)
- Experiment registry: append-only JSONL ledger, unique IDs, hypothesis-before-experiment ordering enforced, one-shot OOS windows (a window that produced a pass is burned — reuse refused at registration)
- Multiple-testing deflation: Bonferroni t-stat floor at the family trial count, direction-aware — bar-lowering retries fail mechanically
- LLM factor mining under budget: sandboxed factor code (AST whitelist, truncated-view contract `factor(closes≤t, …)` so look-ahead needs a sandbox escape, not a bug), attribution-classified failures feeding next-hypothesis prompts, gate recomputes `factor_code` from source (FIB 2/9)
- Real-data ingestion: user CSV → legal snapshot (local-first, schema-validated)
- Acceptance: a seeded negative result produces a correctly-classified attribution and a budget-bounded retry chain, all gated — **met** (`examples/run_mining.py`; 79 tests green)

## v0.4 — roles + adversarial review (shipped)
- Quant roles (data / factor / risk / manager) as **ablatable workers** — each role is a persona prompt *plus* a mechanical duty (data: provenance + power feasibility pre-registration; risk: half-split stability veto at admission), so ablating a role removes a check, not a vibe
- Bull/bear **review gate before admission**, rounds configurable (0–10): reviewers emit structured R cards whose checkable claims are verified against facts the gate computes itself — rhetoric never vetoes, and an unverified bull claim admits nothing; R cards are append-only ledger entries
- Gate extensions: a claimed risk veto must recompute from `factor_code` (a fabricated veto is a lie); an `E.oos` block now feeds the expected-verdict consistency check and its metrics are recomputed from source
- Ablation harness: identical scripted persona policy across configurations, planted-signal worlds (real but modest reversal, strength 0.15) for discovery, pure-noise worlds for false positives; byte-reproducible table
- Acceptance: ablation table — role specialization and debate rounds vs discovery rate and false-positive rate — **met**: `python examples/run_ablation.py` (pinned byte-for-byte in `tests/test_ablation.py`)

## v0.5 — settlement ledger + calibration (shipped)
- **Simulator-authoritative settlement**: every admitted claim settles on a 90-day horizon the admission never touched — the synthetic world is deterministically continued from the same seed (byte-prefix asserted), the factor re-executes in the truncated-view sandbox, and realized metrics come from the same engine that gated the admission. Real (ingested) data has no simulator: those worlds settle when new data arrives, never by invention
- **Hash-chained settlement ledger** (FIB class 19): every entry chains over canonical JSON; audit recomputes the chain, rebuilds each world from its recorded spec, re-runs the factor code, and re-derives every realized metric and outcome — a rechained lie fails recompute, a phantom exp_id fails the registry cross-check
- **Reflection loop that only tightens**: a family with ≥5 settled claims of which >50% fell short gets its admission bar ×1.25 for later orders — recorded on the H card as a `calibration` block the gate re-derives from the ledger (dropping a justified tightening, or claiming a rosier multiplier, is a gate error)
- Calibration report: bucketed claimed-vs-realized curve, per-truth breakdown, pressure-asymmetry by in-budget iteration
- Acceptance: calibration curve from ≥50 settled claims; ledger tamper paths covered — **met**: `python examples/run_calibration.py` (52 settled claims in ~15 s; byte-pinned in `tests/test_settlement.py`)

## v0.6 — benchmark release (shipped)
- FIB harness public (`qsa/fib.py` + [RUBRICS.md](RUBRICS.md)): 14 of the 20 injection classes mechanized as deterministic scenarios, plus the gate half of class 20 (honest control) and the code-pin discipline; every scenario judged by two baseline reviewers (`ungated`, `schema-only`) and the full stack, K=3 repeats asserted byte-identical
- Acceptance: third party can reproduce at least one baseline run from published artifacts — **met**: `python examples/run_fib.py` (~2 min, offline) reproduces the full 16×3×3 matrix; results in [EVIDENCE.md](EVIDENCE.md) P5, rubrics in [RUBRICS.md](RUBRICS.md); the two baselines are framework-agnostic review policies, and the scenario builders are importable for external frameworks

## v0.7 — instrument-grade quant plane (shipped; scope converged to the estimators)

Reference: [THESIS.md](THESIS.md). The v0.7 discipline: **a capability ships
only together with the estimator that measures its budget-equation term.** The
version is done when all five estimators read out of pipeline state; portfolio
construction (P cards, composites, walk-forward folds) moved to v0.8 — it is a
claim surface, not an estimator, and claims land after instruments.

**B — breadth (shipped)**
- Sandbox contract v2 `factor(closes, volumes, tickers, dates, i)` — the
  volume panel under the same truncation rule as closes; v1 factors still run
  unchanged (`contract_of` detects the declared contract; v2 without volumes
  is refused loudly, never silently degraded)
- `Frame` carries volumes and the world's cost model; `load_volumes` degrades
  gracefully for snapshots without a volume column
- Acceptance: **discovery@B curve** — one family, one shared ledger, planted
  and noise worlds interleaved: discovery decays 1.000 → 0.571 as B grows
  1 → 13 (the Bonferroni floor rises 0 → 2.89) while false positives stay
  0/8 — **met**: `python examples/run_discovery.py` (byte-deterministic)

**P̂ — precision (shipped)**
- `coverage` metric: mean share of the frame's tickers carrying a signal —
  recomputed by the gate, pre-registrable as a bar (0.8 default). Universe
  pinning = the fingerprinted manifest + coverage: a factor that quietly
  scores only the names it likes fails mechanically
- FIB 10 (cherry-universe) and FIB 22 (cost-blind) mechanized: 17 injections,
  full-stack catch 1.0, localization 1.0, honest control merges everywhere;
  schema-only catch 0.176 (they are invisible without recomputation — by
  design)
- Acceptance: **α-frontier** — power 0.861 → 0.417 and P̂ 0.912 → 1.000 as
  the floor rises 1.5 → 3.5 (planted vs noise worlds, truth known by
  construction) — **met**: `python examples/run_frontier.py`

**TC — transfer (shipped)**
- Manifest cost model (`costs.per_side_bps`, optional and pinned in the
  fingerprint; default worlds stay byte-frozen at 10 bps via
  `DEFAULT_COST_BPS`, recorded on every card as `cost_bps_used`)
- Engine: `turnover` (daily one-sided, quintile long-short book),
  `net_quintile_spread` = gross − 2·τ·c/1e4, `volume_dollar_median`
  (capacity readout); the gate recomputes all of it from `factor_code`
- Settlement realizes net metrics beside gross; the calibration report
  carries the cost block; FIB 22 (net sold at gross) is caught by
  recomputation
- Acceptance: **TC from settlement** — measured drag on 52 settled claims:
  gross +0.004467 → net +0.000894/day (turnover 1.7865, net/gross **0.2001**)
  — the toy reversal keeps a fifth of its gross at 10 bps — **met**:
  `python examples/run_calibration.py` (cost block in the report)

**λℓ − δ — meta-drift (shipped)**
- `decay_slope`: OLS slope of realized on claimed across claimed-bins
  (cohorts), in every calibration report; horizon recorded beside it
- `qsa/budget.py`: `read_budget(ledger, registry)` reads the whole budget
  vector off pipeline state — B (trial count), ĪC (mean realized IC over
  held), P̂ anchor, TC block, decay slope
- Acceptance: **cohort slope deterministic under ScriptedLLM** — 0.9019 over
  90-day horizons on the v0.5 sweep (claims decay ~10%: the λℓ−δ exponent is
  mildly negative) — **met** (pinned in `tests/test_settlement.py` /
  `tests/test_budget.py`)

**Envelope + instrumentation (shipped)**
- `budget.envelope`: discovery(N) · P̂(N) · √N — breadth net of verification.
  Measured on homogeneous effect pools: strength 0.08 peaks at **N\*=1**
  (weak edges do not amortize verification); strength 0.15 peaks at
  **N\*≈2.6e5** (strong edges amortize almost indefinitely) — the operating
  point is a property of the effect pool, and the instrument says so
- `python examples/run_frontier.py` emits frontier + both envelopes with
  their peaks

Overall v0.7 acceptance: [EVIDENCE.md](EVIDENCE.md) P6 reports the **budget
vector** (ĪC 0.162, B 52, P̂ anchor 0.942, TC net/gross 0.200, λℓ−δ slope
0.902 on 90-day horizons) with the envelope axes separate, per environment —
**met**.

## v0.8 — portfolio claims (planned; moved out of v0.7)

The claim surface the instruments now deserve:

- Walk-forward folds: rolling evaluation with per-fold metrics on the E card;
  every fold counts as a trial for deflation; fold-window reuse refused at
  registration
- Portfolio layer: rank-to-weights construction (dollar-neutral, position
  caps), portfolio return stream, Sharpe/max drawdown; a P card schema with
  its own gate checks (weights sum, caps, one-shot windows)
- Multi-factor composites: pre-registered linear combinations of settled
  factor IDs, weights on the H card; post-hoc weight drift is a gate error
  (FIB 11 family)
- Real-data settlement closure: ingested worlds settle when the adapter
  appends new rows — recorded fixture test, no network in CI
- Acceptance: a composite P card settles end-to-end; every fold deflated;
  real-CSV settlement demonstrated on a fixture

Non-goals (unchanged): no ML/DL training loop, no RL, no news/sentiment planes, no live trading; the LLM stays BYO (`OpenAICompatLLM`) with `ScriptedLLM` as the CI contract.

## v1.0 — three classic scenarios, end to end (the demo release)
- Full spec with per-goal acceptance: [V1_SCENARIOS.md](V1_SCENARIOS.md) — 30 numbered goals (10 per scenario)
- **A. Research report replication**: one public quant report transcribed to a provenance-carrying H card; recomputed on an ingested fingerprinted snapshot; disagreement mechanically attributed; verdict criterion pre-registered; forward claim settled at 90 days; `run_replication.py`
- **B. Market-view verification**: 10 real circulating views as pre-registered hypothesis cards, one family under deflation; one-shot OOS; bear-role counterexamples; honest failure rate; calibration from the ledger; `run_viewcheck.py`
- **C. Market regime summarization**: engine-computed per-day fact tables bound to snapshot fingerprints; a statement-consistency gate (no number without a fact-table basis, no "broad rally" without the threshold); pre-registered regime rules with falsification conditions; rolling replay with zero narrative drift; `run_regime.py`
- Each scenario contains a recorded same-prompt control against an ungated general agent (fabrication-under-pressure, multiple-testing, hallucination) — the differentiation is measured, not asserted
- Acceptance: all three runners reproduce byte-identically offline; every demo number traces to snapshot → card → engine → gate recomputation; paper artifact + cold-start reproduction protocol rides along

## v1.1 — paper artifact
- Reproduction protocol (variance decomposition, K-run reporting), paper, cached environments
- Acceptance: cold-start reproduction by a non-author within one day
- Status: factor factory (the fast lane that feeds it) shipped ahead of the paper — `run_factory.py`; see [EVIDENCE.md](EVIDENCE.md) §v1.1

## v1.2 — organizational memory (shipped)
- **Blackboard** — append-only, hash-chained cross-session memory (`data_pitfall` / `decay_event` / `convention_decision` / `order_note`), bootstrapped with this repo's real incidents; blockers shut the infra gate until resolved by a linked note
- **Infra gate** — 5 offline pre-flight checks over the pinned fixture; no orders admitted while shut; every FAIL path pinned by tests
- **Order state machine** — `drafted→admitted→running→settled/refused`; admission freezes a params hash (drift = hard error); settle/refuse mechanical against the pre-declared threshold; terminal states final; event log hash-chained; recall on re-run
- **Fork cards** — research conventions raised as explicit questions with option impacts, decided once, append-only; order params cite fork digests
- Acceptance: `run_orders.py` full run — 24 factor orders + drift demo, 7 settled / 17 refused on the pinned fixture with numbers matching §v1.1; second run recalls all 24; 36 new tests; self-playing honest demo reel (`build_demo_video.py`) whose planned-capabilities scene is explicitly stamped 未实现
- Remaining backlog moved to the v1.3.x patch line below (adversary recompute, red-team robustness runs, parallel miners, LLM hypothesis generation feeding the same state machine, calendar-driven settlement, portfolio attribution)

## v1.3 — offense layer (shipped)
- **Cited factor library** (`qsa/factorlib.py`) — 30 buildable factors: WorldQuant 101 subset (12), range-vol family (Parkinson/Garman-Klass/Rogers-Satchell + candle anatomy), liquidity family (Amihud, vwap), parameterized momentum/dist families with window variants; every spec carries its source; `build_catalog(available)` builds only what the snapshot's panel columns support
- **Panel extension** — ingest/snapshot accept optional high/low/amount/vwap columns (all-or-nothing, backward compatible); extension fixture derived from the raw cache with qfq recovery verified (median rel. dev 1e-6)
- **Residual objective** (`qsa/offense.py`) — per-day cross-sectional orthogonalization against the zoo survivors; clones score ~0; matches closed-form OLS to 1e-9
- **Mining channels** — library scan + pairwise interactions (product/ratio/spread of top-k survivors) + window mutations; winners settle into frozen-parameter orders against the pre-declared bar (residual oos IC > 0.03, n_months >= 12); honest zero when nothing clears
- Acceptance: `run_offense.py --full` — 78 candidates, 14 unique fast-lane orders (head ix:dist_52w_high×sharpe_20d:ratio +0.0759, wq_a19 +0.0730); 5 of the 14 winners have negative raw IC yet positive residual oos IC — only visible orthogonal to the basis; smoke window produces the honest zero; 25 new tests

## v1.4 — conversation & self-orchestration plane (shipped)

The showcase made ten promises about the product being an agent rather
than a batch script; this version makes each one mechanical. New plane
justification: the unit of interaction changes from "run the script" to
"talk to the researcher".

- **① intent entry** (`qsa/planner.py`) — one sentence → Plan (streams,
  bar, sample floor, windows, universe), fingerprint = sha256[:16] over
  canonical JSON; every non-default parameter carries a note naming the
  phrase that set it; 「至少 N 个月」 is the sample floor, never a sweep
  window
- **③ plan tree materialized** — every run writes `research_tree.json`
  (per-node status/note/timing, updated as stages land) and the report
  leads with its rendering, crew roles named
- **④ auto crew** — `--workers auto` (default): N = clamp(ceil(jobs/8),
  1, cpus, 16); `manifest.json` records the role×job split
  (GateKeeper/RepoSmith/FlowMapper/SmokeRunner); output byte-identical
  for any N (numbers move never, only the clock)
- **② conversational increment** (`qsa/followup.py` + `recompute.py`) —
  bar-only follow-ups re-verdict from the cached leaderboard (0 rows
  rescored); universe changes rerun the affected streams and report
  kept/added/dropped; unparseable asks refuse
- **⑤ repair ladder** (`qsa/repair.py`) — missing_tail truncates to the
  common calendar (floor 60 dates); bad_number / duplicate_pair refuse;
  a repair that would shrink below the floor refuses too
- **⑥ sandbox forge loop** (`qsa/factorforge.py`) — machine-detected
  gaps (missing panels, promised-but-empty streams) or an intent that
  says 沙盒生成 trigger deterministic template codegen → AST-whitelisted
  sandbox → the same residual yardstick; rows tagged
  `source: sandbox-forge` + code sha256[:8]; banned code is a refused
  row, not a crash. Known cost: the truncated-view sandbox is O(D²) per
  candidate — fine at smoke scale, the streaming sandbox is the
  follow-up
- **⑦ fork cards as conversation** (`qsa/forkask.py`) — numbered
  options on stdin, invalid re-prompts, EOF → declared default (and
  says so in the ledger); a decided fork is reused, never re-asked
- **⑧ memory with receipts** (`qsa/memreport.py`) — ledger page over
  the hash-chained blackboard + the tighten-only ratchet over
  `standard` entries (sense-aware min/max; any loosening FAILS) + the
  run manifest table; CLI: `python -m qsa.memreport <run_dir>`
- **⑨ layered report** (`qsa/researchreport.py`) — archive strip →
  top-3 four-line cards (是什么/多强/凭什么信/下一步) → leaderboard →
  appendices (library manifest, forge log, honesty)
- **⑩ tour self-proof** (`tools/regen_tour_numbers.py` + Makefile +
  `docs/TOUR_NUMBERS.json`) — every demo-quoted number regenerates from
  run artifacts; counts/ids exact, elapsed within 1.6× slack; drift
  exits nonzero
- Acceptance: **met** — `make offense-full` (78 candidates, 14 orders,
  53.7 s at auto-13), `make followup` (0 rescored for the bar ask; 22.7
  s recompute for smallcap, kept 5 / added 27 / dropped 9), forge loop
  run live (1 gap → 6 sandbox candidates, 6 evaluated 0 refused), `make
  tour` green against the committed baseline; 84 new tests across 9
  files, suite 353 green

## v1.4.2 — SUPERAGENT_PLAN: the dsh-superagent capability planes (shipped)

The ten capabilities that make dsh-superagent a *super agent* rather
than a batch script — async tasks, checkpoint resume, event triggers,
resident patrol, worker sessions, multi-order routing + board,
watchdog, cross-channel continuity, speculative execution, pluggable
provider — each rebuilt in this repo's register: mechanical, offline by
default, and verified byte-for-byte where determinism is the claim.
Design and acceptance table: [SUPERAGENT_PLAN.md](SUPERAGENT_PLAN.md);
per-plane measurements: [NEWS.md](NEWS.md) 2026-11-16 entry.

- `qsa/tasks.py` (#1), `qsa/checkpoint.py` (#2), `qsa/watch.py` (#3),
  `qsa/patrol.py` (#4), `qsa/crew.py` (#5), `qsa/router.py` +
  `qsa/board.py` (#6), `qsa/watchdog.py` (#7), `qsa/channels.py` (#8),
  `qsa/speculative.py` (#9), `qsa/provider.py` (#10)
- Acceptance: **met** — 435 tests green (+71); resume after losing
  half the checkpoint is byte-identical; concurrent routing is
  byte-identical to sequential; cross-channel follow-ups agree;
  speculative delivery settles under the 10%-of-cold-run gate; the
  no-key offline default covers the whole product

## Versioning policy (from v1.3 on)

Version bumps were outpacing delivery: v0.x–v1.3 minted a new minor every
release. The rule now: **a new minor only for a new capability plane
(evidence, loop, roles, settlement, benchmark, budget, org-memory,
offense). All ongoing R&D ships as patches under the current line** —
v1.3.0 → v1.3.1 → v1.3.2 …, tracked in this section. `qsa.__version__`
carries the patch number.

## v1.3.x — the patch line (all R&D continues here)

- **v1.3.1** — super-agent throughput + honesty hardening:
  - repositioning shipped first: POSITIONING.md constitution + README/showcase
    rewritten to team/orders/one-command/minute-level-throughput narrative
  - **dispatcher shipped**: `qsa/dispatch.py` shards the candidate space
    (zoo + library + interactions + mutations) across N FactorMiner
    worker processes (`--workers`, default min(4, cpus)); jobs are pure,
    Pool.map preserves order — leaderboards byte-identical to the
    sequential path for any N (pinned by tests/test_dispatch.py)
  - remaining: deflation across the 78-candidate offense family
    (Bonferroni/registry discipline) before any external claim — winners
    currently owe this plus the v1.0 gauntlet (costs, capacity,
    triple-gate, injection controls); neutralization (industry/size) of
    the residual basis, so the residual objective answers "new
    information", not "new sector tilt"
- **v1.3.2 (planned)** — catalog growth as panel columns allow: GTJA191
  subset, larger WQ101 subset; each entry must carry a checkable source
- **v1.3.x backlog (unscheduled, folded in from v1.2's next-list)** —
  adversary recompute, red-team robustness runs, parallel miners, LLM
  hypothesis generation feeding the same state machine, calendar-driven
  settlement, portfolio attribution

## Out of scope (explicitly)
- Live trading, brokerage APIs, real-money anything
- Persona-of-famous-investors agents (demo bait, not science)
- Chasing backtest returns as the headline metric — calibration and honesty are the product
