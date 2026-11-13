# Roadmap

Public, version-gated. Each version has scope + acceptance criteria; code lands here phase by phase out of the internal pilot environment.

## v0.1 — design skeleton (now)
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

## v0.7 — instrument-grade quant plane (planned)

Theme: **every capability upgrade lands with its verification layer** — the evidence discipline scales to real quant work. Capability without a gate is what the comparison projects already ship.

**A. Data plane v2**
- OHLCV into the factor contract: `Frame` loads volume (already fingerprinted, invisible to factors today); sandbox contract v2 `factor(closes, volumes, tickers, dates, i)` with v1 factors still running; synthetic worlds gain sectors and a size column
- Universe pinning — mechanizes FIB 10: membership-as-of schedule in the manifest; the evaluation universe must equal pinned membership; a survivorship-biased favorable subset is a gate error
- Real-data settlement closure (closes an [EVIDENCE.md](EVIDENCE.md) admission): ingested worlds settle when the adapter appends new rows — recorded fixture test, no network in CI

**B. Engine realism**
- Cost/turnover/capacity accounting: turnover, a manifest-declared per-side bps cost model, net-of-cost spreads, ADV-participation capacity; admission bars may be net; the gate recomputes all of it; new FIB class — cost omission (gross sold as net)
- Exposure + neutralization: sector-neutral IC and size/momentum loadings computed by the engine and recomputed by the gate; the risk role's veto upgrades from half-split stability to exposure-based
- Walk-forward folds: rolling folds with per-fold metrics on the E card; every fold counts as a look for deflation; fold-window reuse refused at registration

**C. Portfolio layer**
- Signal → portfolio: rank-to-weights construction (dollar-neutral, position caps), portfolio return stream, Sharpe / max drawdown; a P card schema with its own gate checks (weights sum, caps, one-shot windows)
- Portfolio claims settle: the settlement ledger accepts P cards; realized portfolio metrics recompute on the extended world
- Multi-factor composites: a composite is a pre-registered linear combination of settled factor IDs with weights on the H card; post-hoc weight drift is a gate error (FIB 11 family)

**D. Benchmark externalization**
- FIB scenarios export as framework-agnostic order JSON (issue body + card contract); a reference consumer implementing only the published contract — not the qsa gate — runs them; one external-consumer run published with raw logs (the deferred v0.6 promise, done properly)

**E. Tooling**
- `python -m qsa` CLI: order → run → verify → settle → report in one command; cold-start full loop < 10 min from a fresh clone
- K-run variance decomposition protocol: data plane and gate asserted zero-variance; model-path variance measured and reported when a real LLM is attached (ScriptedLLM stays the CI contract)

Acceptance:
- FIB harness ≥ 18 scenarios — cherry-universe (10) and cost-omission mechanized and caught with localization; the honest control still merges everywhere
- a high-turnover factor that passes gross fails the net bar mechanically; a size-tilted factor's raw IC survives while its neutralized IC collapses, exposed in attribution
- a portfolio claim settles end-to-end on the extended world; a composite settles; post-hoc weight drift blocked
- real-data settlement exercised on a recorded append fixture (offline)
- CLI cold-start documented and timed; the variance report is deterministic under ScriptedLLM

Non-goals (unchanged): no ML/DL training loop, no RL, no news/sentiment planes, no live trading; the LLM stays BYO (`OpenAICompatLLM`) with `ScriptedLLM` as the CI contract.

## v1.0 — paper artifact
- Reproduction protocol (variance decomposition, K-run reporting), paper, cached environments
- Acceptance: cold-start reproduction by a non-author within one day

## Out of scope (explicitly)
- Live trading, brokerage APIs, real-money anything
- Persona-of-famous-investors agents (demo bait, not science)
- Chasing backtest returns as the headline metric — calibration and honesty are the product
