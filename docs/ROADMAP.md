# Roadmap

Public, version-gated. Each version has scope + acceptance criteria; code lands here phase by phase out of the internal pilot environment.

## v0.1 — design skeleton (now)
- README (EN/zh), architecture, FIB benchmark spec, evidence inventory, roadmap
- Acceptance: docs coherent, no overclaim of unimplemented features

## v0.2 — evidence plane, runnable
- Evidence card schemas (H/E, versioned) + verify gate (schema · fingerprint · no-lookahead · verdict consistency)
- Toy dataset + immutable snapshot tooling + reconciliation stub
- Deterministic forge emulation (issues/PRs/CI hooks) so anyone can run `order → cards → gate → PR` offline in <10 min
- Acceptance: FIB classes 1, 4, 7, 14, 15 caught by gate in automated tests

## v0.3 — research loop
- Hypothesis attribution taxonomy (threshold / instability / neutralization residual / universe) and attribution-driven next-hypothesis proposal under an iteration budget
- Experiment registry (append-only, unique IDs, pre-registration order enforced)
- Acceptance: a seeded negative result produces a correctly-classified attribution and a budget-bounded retry chain, all gated

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
