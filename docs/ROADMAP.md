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

## v0.4 — roles + adversarial review
- Quant roles (data / factor / risk / manager) as ablatable workers
- Bull/bear review gate before admission (rounds configurable)
- Acceptance: ablation table — role specialization and debate rounds vs discovery rate and false-positive rate

## v0.5 — settlement ledger + calibration
- Horizon settlement (simulator-authoritative realized performance), reflection loop feeding admissions
- Calibration report (claimed vs realized), pressure-asymmetry tracking
- Acceptance: calibration curve generated from ≥50 settled claims; ledger tamper path covered by FIB class 19

## v0.6 — benchmark release
- FIB harness public; runs against ≥2 external baselines published with rubrics and raw logs
- Acceptance: third party can reproduce at least one baseline run from published artifacts

## v1.0 — paper artifact
- Reproduction protocol (variance decomposition, K-run reporting), paper, cached environments
- Acceptance: cold-start reproduction by a non-author within one day

## Out of scope (explicitly)
- Live trading, brokerage APIs, real-money anything
- Persona-of-famous-investors agents (demo bait, not science)
- Chasing backtest returns as the headline metric — calibration and honesty are the product
