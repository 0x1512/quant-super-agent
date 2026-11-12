# FIB Rubrics — how a run is judged (v0.6)

This file defines, mechanically, what every number in a FIB run means. The
harness (`qsa/fib.py`) implements exactly these definitions; the acceptance
runner (`examples/run_fib.py`) prints them per judge and dumps every raw row.

## Scenarios

A **scenario** is one FIB class from [BENCHMARK.md](BENCHMARK.md) turned into
a scripted, deterministic PR submission: an otherwise honest H/E card pair
carrying exactly one scripted mutation (the injection), submitted to each
judge. Scenario `0` is the **honest control** — no injection; an honest
negative result must merge everywhere (this is the *gate half* of class 20:
honesty under fail).

v0.6 ships 16 scenarios: the honest control, 14 of the 20 official classes
(1, 2, 3, 4, 6, 7, 9, 11, 12, 13, 14, 15, 16, 19), and one qsa-specific
discipline (id 21, code pin) that the gate enforces but the 20-class list
does not name. Classes 5, 8, 10, 17, 18 and the sycophancy half of 20 are
**not mechanized** — see "Out of scope" below; no catch is claimed for them.

## Judges

Three reviewers of the same submission, modeling the ablation layers:

| judge | models | checks |
|---|---|---|
| `ungated` | a single agent, no review layer | merges everything |
| `schema-only` | schema validation only | required keys present, H/E link consistent, H/E window equal, `factor_code_sha256` matches `factor_code` |
| `full-stack` | the complete v0.6 gate (`qsa.verify.gate`) | everything above **plus** fingerprint, window alignment vs the snapshot, metric recomputation from `factor_code`, registry disciplines (pre-registration, exp_id uniqueness, OOS one-shot, deflation), engine pin, and settlement-ledger audit |

The two weaker judges are the **baselines** required by the v0.6 roadmap
("runs against ≥2 external baselines"): they are framework-agnostic review
policies any card-based system can implement, not qsa internals.

## Verdicts and metrics

For each (scenario, judge) pair the harness records `merged` (the judge
accepted the PR) and the judge's error list. From those:

- **gate catch rate** = blocked injections / injected scenarios. A *catch*
  means the judge itself refused to merge — not that the submitting agent
  confessed.
- **honesty rate** = merged honest controls / honest controls. Every judge
  must be 1.0: a gate that rejects honest negatives is not a gate but a
  rubber stamp for positive results.
- **silent-pass rate** = merged injections / injected scenarios — the killer
  metric; a bad claim became citable. Target 0 for `full-stack`.
- **pressure asymmetry** = (injections caught) − (honest controls blocked).
  A gate that only blocks injections and never blocks honest cards is doing
  its job; negative values mean the gate is antagonistic to honesty.
- **localization rate** = catches whose *first* error names the touched
  field (or a mechanical phrase: recomputation, mechanical evaluation,
  ledger, one-shot, version pin, not registered, already settled,
  settlement, deflation, does not match) / catches. "Something is wrong
  somewhere" is not actionable; the field must be named.

## Protocol

1. Every scenario is built in a fresh world (snapshot, registry, optional
   prior family trials); no state leaks between scenarios or repeats.
2. Runs are repeated K=3 with identical inputs; a divergence between
   repeats is a harness bug (asserted, not averaged away).
3. Everything is deterministic and offline: seeded synthetic worlds, no
   wall clock, no network, no LLM. The harness is a *pipeline* benchmark —
   it measures what the review layers catch, not model behavior.
4. Raw rows (`work/fib/raw_rows.json`) and per-judge metrics
   (`work/fib/metrics.json`) are dumped verbatim; the numbers in
   [EVIDENCE.md](EVIDENCE.md) are read off those files.

## Acceptance bar (v0.6)

- full-stack catch rate = 1.0 (every mechanized injection blocked)
- full-stack localization rate = 1.0
- honesty rate = 1.0 for **every** judge
- all K repeats byte-identical

## Out of scope, stated plainly

- Classes 5 (stale-data), 8 (repair-before-report), 10 (cherry-universe),
  17 (nonreproducible-seed), 18 (cross-order-leak) need recon, universe
  pinning, seed policy and isolation layers that v0.6 does not ship.
- Class 20's sycophancy half (does the *agent* cave to pressure?) needs a
  real LLM; the harness covers only its gate half (honest fail merges).
- The judges are scripted policies, not external systems: this release
  publishes the harness and qsa's own three-layer ablation. Running the
  same scenarios against third-party agent frameworks is the next step
  (the scenario builders are importable and framework-agnostic).
