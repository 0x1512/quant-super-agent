# FIB Rubrics — how a run is judged (v0.7)

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

v0.7 ships 18 scenarios: the honest control, 15 of the 20 official classes
(1, 2, 3, 4, 6, 7, 9, **10 cherry-universe**, 11, 12, 13, 14, 15, 16, 19),
and two qsa-specific disciplines the gate enforces but the 20-class list does
not name (id 21 code pin; id 22 **cost-blind** — net spread reported at
gross). Classes 5, 8, 17, 18 and the sycophancy half of 20 are **not
mechanized** — see "Out of scope" below; no catch is claimed for them.

The v0.7 additions and the metrics that catch them:

- **10 cherry-universe** — the factor honestly scores only 5 of 12 tickers;
  every card metric recomputes. The **coverage** metric (mean share of the
  frame's tickers carrying a signal, recomputed by the gate from
  `factor_code`) reads 0.4167 and fails the pre-registered 0.8 bar. The
  universe is pinned by the fingerprinted manifest; the coverage bar is what
  makes a quiet subset a gate error.
- **22 cost-blind** — a daily-reversal chaser whose gross spread clears the
  bar while its net spread is negative at the world's 10 bps. The card
  reports `net_quintile_spread = quintile_spread`; the gate recomputes net
  from the pinned cost model (`costs.per_side_bps` in the manifest, echoed as
  `cost_bps_used` in metrics) and the number disagrees.

## Judges

Three reviewers of the same submission, modeling the ablation layers:

| judge | models | checks |
|---|---|---|
| `ungated` | a single agent, no review layer | merges everything |
| `schema-only` | schema validation only | required keys present, H/E link consistent, H/E window equal, `factor_code_sha256` matches `factor_code` |
| `full-stack` | the complete v0.7 gate (`qsa.verify.gate`) | everything above **plus** fingerprint, window alignment vs the snapshot, metric recomputation from `factor_code` (incl. coverage and net-of-cost metrics), registry disciplines (pre-registration, exp_id uniqueness, OOS one-shot, deflation), engine pin, and settlement-ledger audit |

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

## Acceptance bar (v0.7)

- full-stack catch rate = 1.0 (every mechanized injection blocked)
- full-stack localization rate = 1.0
- honesty rate = 1.0 for **every** judge
- all K repeats byte-identical

## Budget-estimator rubrics (v0.7)

The same discipline applied to the transfer theory's terms
(`qsa/budget.py` + the three estimator scripts). Every quantity is defined
mechanically so a number without its estimator is not citable:

- **discovery@B** (`examples/run_discovery.py`) — one family, one shared
  experiment ledger; planted (s=0.10) and noise worlds interleaved. After
  each world: B = the ledger's family trial count; discovery@B = cumulative
  admitted share of planted worlds; FP@B = the same on noise. The floor
  column is the ledger's own Bonferroni floor at that B — read from
  `deflation.bonferroni_tstat_floor`, not recomputed ad hoc.
- **α-frontier** (`examples/run_frontier.py`) — per admission floor z:
  power = share of planted worlds with reversal-factor t-stat ≥ z; FPR =
  the same on noise worlds; P̂ = power / (power + FPR) at 50/50 prevalence.
  P̂ is an *anchor* (the truth is planted), never a production observable;
  the sensitivity grid is the honest statement of that.
- **envelope** — discovery(N) · P̂(N) · √N at the Bonferroni floor z(N),
  computed on **homogeneous** effect pools (the operating point is a
  property of the pool's strength; mixing strengths hides the turnover).
  Breadth net of verification: an un-deflated pipeline has breadth but no
  credibility, and the P̂ factor prices exactly that.
- **decay slope** (λℓ−δ estimator, in every calibration report) — OLS slope
  of mean-realized on mean-claimed across claimed bins; horizon recorded
  beside it. Slope < 1 ⇒ claims leak value over the settlement horizon
  faster than the loop compounds it.
- **TC block** (calibration report + `read_budget`) — mean turnover, gross
  vs net quintile spread, drag and net/gross ratio over settled horizons at
  each world's pinned cost model. `cost_bps_used` on every card makes the
  model explicit; the gate recomputes against the same number.

## Out of scope, stated plainly

- Classes 5 (stale-data), 8 (repair-before-report), 17
  (nonreproducible-seed), 18 (cross-order-leak) need recon, seed policy and
  isolation layers that v0.7 does not ship.
- Class 20's sycophancy half (does the *agent* cave to pressure?) needs a
  real LLM; the harness covers only its gate half (honest fail merges).
- The judges are scripted policies, not external systems: this release
  publishes the harness and qsa's own three-layer ablation. Running the
  same scenarios against third-party agent frameworks is the next step
  (the scenario builders are importable and framework-agnostic).
