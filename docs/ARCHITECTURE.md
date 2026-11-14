# Architecture (design; mechanism state as of v1.2)

Quant Super Agent runs the full quant research lifecycle as an **order-driven agent workflow**. This document describes the target architecture and how each component maps to mechanisms already validated in internal pilots (see [EVIDENCE.md](EVIDENCE.md)).

## System overview

```mermaid
flowchart TB
    subgraph PlaneA["Supervision plane"]
        PANEL["Web panel<br/>(pause · policy · tickets)"]
        WD["Autonomy watchdog<br/>(read-only poll, stop/pause write-face)"]
        SOP["Surgery SOP<br/>(checklist for policy changes)"]
    end
    subgraph PlaneB["Research plane"]
        ORCH["Orchestrator / Eval<br/>policy gate · strength routing"]
        W1["Worker: data engineer"]
        W2["Worker: factor analyst"]
        W3["Worker: risk & attribution"]
        W4["Worker: research manager"]
    end
    subgraph PlaneC["Evidence plane"]
        GATE["CI verify gate<br/>schema · fingerprint · no-lookahead"]
        REG[("Experiment registry")]
        LEDGER[("Settlement ledger<br/>claimed vs realized")]
    end
    subgraph PlaneD["Data plane"]
        SNAP["As-of snapshots<br/>(immutable, sha256-manifested)"]
        RECON["Reconciliation checks"]
    end
    subgraph PlaneE["Simulation plane"]
        FORGE["Deterministic git-forge emulation<br/>(issues · PRs · CI hooks)"]
        SIM["Backtest / settlement simulator"]
    end
    PANEL & WD & SOP -.govern.- ORCH
    ORCH --> W1 & W2 & W3 & W4
    W2 --> GATE --> REG --> LEDGER --> SIM --> W2
    W1 --> SNAP --> RECON
    W2 & GATE --> FORGE
```

## Order lifecycle

A factor study is an **order**. Each order walks:

1. **Issue** — a human (or a scheduled task) files a research order: scope, constraints, and — optionally — pre-registered hypothesis IDs. Orders without pre-registered H cards cannot produce citable E cards.
2. **Eval gate** — the orchestrator decides *strength* (explicit / inferred / follow-up) and checks *policy* (who may order what). Non-allowed triggers are ignored — and, in observe mode, recorded as **would-accept decisions** with full rule assessments, so the panel shows what the system *would* have done.
3. **Ticket + isolation** — accepted orders open a ticket and a worktree. Every worker session is isolated per order; cross-order contamination is structurally impossible (one order = one tree).
4. **Workers** — quant roles collaborate (see below).
5. **Evidence cards** — the deliverable is never prose; it is H/E cards (JSON, schema-versioned).
6. **CI verify gate** — a push hook runs the gate: schema completeness, snapshot fingerprint match, window alignment (no look-ahead), engine version pinning, and metric recomputation on a sampled basis. **A failing card can never be marked ready** — the agent must report failure as failure.
7. **Review & admission** — humans (L1/L2) or the manager (L3) admit or reject. Admission writes to the registry.
8. **Settlement** (shipped, v0.5) — at horizon end the world is deterministically continued from its seed, the factor re-executes in the sandbox, and realized performance is written to the hash-chained ledger against the claim. The calibration curve and a tighten-only reflection rule (family bar ×1.25 after repeated shortfalls) feed back into future admissions.

## Order book, blackboard, gate, forks (shipped, v1.2)

The lifecycle above has a **local, testable implementation** (`qsa/orders.py`,
`qsa/blackboard.py`, `qsa/infragate.py`; demo `examples/run_orders.py`):

- **State machine** — `drafted → admitted → running → settled/refused`,
  illegal transitions are hard errors, both terminal states are final.
  *Admission freezes a hash of the evaluation parameters*; `start` with
  different parameters raises — pre-registration enforced per order, not
  per flagship. The event log is hash-chained (JSONL); a reload verifies
  the chain and refuses tampered history.
- **Settle vs refuse is mechanical** — the settle threshold is declared in
  the admitted params; results attach at `settle`, a reason at `refuse`.
  Refused orders cannot restart; re-entry is a NEW order with a changed
  hypothesis, which the registry then counts (deflation composition).
- **Blackboard** — cross-session memory, four kinds (`data_pitfall`,
  `decay_event`, `convention_decision`, `order_note`), append-only and
  hash-chained; `resolve()` clears a blocker by appending a linked note,
  never rewriting. Bootstrapped with this repo's real incidents.
- **Infra gate** — five offline pre-flight checks over the pinned fixture
  plus blackboard-clear; orders are not admitted while it is shut.
- **Fork cards** — research conventions (universe, cost, proxy variable)
  raised as explicit questions with option impacts, decided once,
  append-only; order params cite fork digests, so a convention change
  invalidates old orders instead of silently drifting them.
- **Recall** — a terminal order for the same hypothesis+params hash is a
  remembered verdict; re-runs recall instead of recomputing (the book is
  the memoization layer a batch script lacks).

## Worker roles

| Role | Owns | Typical outputs |
|---|---|---|
| data engineer | snapshots, reconciliation, PIT discipline | manifests, recon reports |
| factor analyst | hypothesis → experiment | H cards, E cards, attribution |
| risk & attribution | robustness, kill criteria | neighborhood stability, capacity/turnover notes, veto cards |
| research manager | prioritization, admission proposals, iteration budget | next-hypothesis proposals, debate synthesis |

Roles are a **dial, not dogma**: the pilot ran a single generic worker successfully; v0.4 shipped the split as an ablation axis — measured, the risk duty and one debate round each remove a third of noise-world false positives at zero cost to discovery (see [EVIDENCE.md](EVIDENCE.md)).

## Autonomy supervisor

Three layers, validated in three-arm × 5-round pilots:

1. **Surgery SOP (L1)** — any policy change follows a six-step checklist: pause → change → verify → observe window → revert → resume. Mechanism analysis showed pause-first structurally removes the risk turn (notifications are injected without waking the agent; resume reads the reverted state).
2. **Watchdog (L2)** — an out-of-band process polls the panel API read-only; on rule triggers (e.g., a ticket whose mandate cites a surgery-window policy version) it stops the ticket. Measured detection→stop: **0.21 s**.
3. **Prompt discipline (L3)** — worker/orchestrator prompts carry requeue/policy-window discipline, applied and reverted as versioned settings with full audit trail.

Known platform gaps (no requeue permission surface; no configurable tool allowlist for main sessions) are documented and reported upstream; the supervisor exists precisely because the platform underneath does not provide these controls.

## Evidence card gate internals

The gate is intentionally dumb and strict — it checks, in order:

1. schema completeness (required fields, types)
2. `hyp_id` exists and was registered **before** the experiment window opened
3. `snapshot_sha256` matches the manifest of an immutable as-of snapshot
4. factor window ⊆ snapshot window; evaluation uses only data at or before each decision point (no look-ahead)
5. engine version pinned; with a ledger (`--registry`, v0.3): hypothesis-before-experiment ordering, family trial counts, one-shot OOS windows, and the deflated (multiple-testing-adjusted) verdict; when the card carries `factor_code`, the gate re-executes it in the AST-whitelist sandbox and requires the recomputed metrics to match — sampled recomputation becomes exhaustive
6. role duties and review (v0.4, shipped): the data role's feasibility pre-registration and the risk role's half-split stability veto are mechanical functions; a claimed risk veto must recompute from `factor_code` (a fabricated veto is a lie), an OOS block feeds the expected-verdict consistency check and its metrics are recomputed from source, and a review block must agree with the verifiable checks — a bear objection is upheld only if its check actually fails, bull rhetoric never admits
7. settlement ledger (v0.5, shipped): with `--settlement`, the ledger's hash chain must hold and every entry's realized metrics and outcome must recompute from the world spec + factor code it carries (FIB 19); an H card's `calibration` block must match the ledger-derived tighten-only reflection rule — dropping a justified tightening or claiming a rosier multiplier is a gate error
8. FIB harness (v0.6, extended v0.7): `qsa/fib.py` turns the injection classes of [BENCHMARK.md](BENCHMARK.md) into deterministic scenarios — honest card pairs with one scripted mutation each — and routes each submission through two baseline judges (`ungated`, `schema-only`) and this gate; catch rate, honesty, silent-pass, pressure asymmetry and localization are computed per judge ([RUBRICS.md](RUBRICS.md))
9. budget/cost plane (v0.7, shipped): the sandbox gains contract v2 (`closes, volumes, tickers, dates, i`) for liquidity-aware factors; the manifest may pin `costs.per_side_bps`; the engine computes coverage, turnover and net-of-cost spreads, and the gate recomputes them — a cherry universe dies on the pre-registered coverage bar (FIB 10) and a net-sold-at-gross card dies on cost recomputation (FIB 22). `qsa/budget.py` reads the budget-equation terms (ĪC, B, P̂, TC, decay slope) straight out of pipeline state; default worlds stay byte-frozen
10. replication plane (v1.0, Scenario A): the sandbox gains contract v3 (`closes, opens, volumes, tickers, dates, i`) for overnight-gap factors; `qsa/replication.py` carries the report card (per-number provenance, convention-alignment table), the sandbox factor code, the monthly-plane evaluators (month-end rank IC with a two-implementation cross-check to 1e-12, equal-weight quintiles with G1 = lowest factor, OLS neutralization over manifest-pinned meta) and the pre-registered rules D1/D2/D3. An E card may carry a `replication_block`: the gate recomputes it with the **whitelisted evaluator only** (no code travels on the card) and demands exact equality — including the mechanically re-derived verdict (FIB 23); the monthly-caps/industry meta is copied into the snapshot by ingest and pinned by content hash, so a meta swap breaks the fingerprint (FIB 24); real-data settlement (`settle_real_claim`) asserts the arrived extension extends the base world row by row, pins every source CSV by sha256 in the ledger entry, and the audit rebuilds from the pinned fixture (FIB 25)
10b. **Factor factory (v1.1)** — the fast lane of candidate production: `qsa/factorzoo.py` (24 public-literature templates, O(N) rolling kernels, signed leaderboard) + `qsa/backtest.py` (tradeable metrics: fees, Newey-West Sharpe with padded PSD floor, one-sided turnover, capacity under a participation cap, drawdown/Calmar, triple-gate partitions). Deliberately outside the verify gate: it ranks, it does not certify — promotion to a claim still runs the full pre-registered gauntlet.
11. verdict honesty: a `fail` with real metrics beats a fabricated `pass` — the gate cannot detect every fabrication, but the settlement ledger eventually can (see [BENCHMARK.md](BENCHMARK.md) for the adversarial side)

## Reproducibility

- The forge emulation is deterministic; data snapshots are immutable and fingerprinted.
- Variance decomposition protocol: run the same order K times; data plane and gate are expected to be zero-variance, model-path decisions are not. The protocol separates the two and reports per-stage variance (pilot infrastructure logs every event append-only to make this measurable).
