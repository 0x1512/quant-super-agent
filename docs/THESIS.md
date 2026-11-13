# Verifiable Research at Machine Speed — a Transfer Theory of Agentic Quant Systems

> **Thesis.** Throughput is cheap; verification is the constraint.
>
> **One-line result.** The expected deployable information ratio of a research
> pipeline factors into stage efficiencies that compose multiplicatively —
> equivalently, into an additive budget in log space (the structure of the
> Tsiolkovsky equation). The field's resource allocation terminates before
> the binding terms.

Version 0.6. This document is the design rationale for the roadmap; every
symbol it introduces has an estimator on pipeline state (§5), and every
architectural layer maps to exactly one term (§7).

## 1. Object of study

An agentic quant research system is a loop: hypotheses in, deployed claims
out. We do not model model capability. We model the *pipeline* — the process
that converts a hypothesis stream into net deployable performance, at machine
speed, without human trust in the middle.

## 2. Formalization: staged transfer

A research cycle transfers mass from the hypothesis manifold to the deployed
book: three burns, one return leg.

```
E[IR_t]  ≈  ĪC · √B_eff · P̂ · TC · e^{(λℓ − δ)·t}
```

| symbol | name | definition |
|---|---|---|
| ĪC | skill | mean realized information coefficient of deployed true claims |
| B_eff | effective breadth | B / (1 + (B−1)·ρ̄²), B = independent trials per period, ρ̄ = mean inter-claim correlation |
| P̂ | precision | 1 − FDR, with P̂ = π·ψ / [π·ψ + (1−π)·α_Bonf(N)] |
| TC | transfer coefficient | corr(signal-implied weights, deployed net-of-cost weights) |
| λℓ − δ | meta-drift | learning rate minus alpha decay, drift in log space |

The positions are derived, not chosen:

- **breadth under the square root** — n independent equal-vol bets give
  mean ∝ n·IC and volatility ∝ √n, so IR ∝ IC·√n (Grinold);
- **precision linear** — noise claims occupy risk budget (volatility ∝ √n is
  unchanged) while contributing zero mean, so E ∝ P̂·n·ĪC;
- **TC linear** — the Clark–de Silva–Thorley extension of the fundamental
  law of active management;
- **meta-drift exponential** — compounding is drift in log space (Kelly).

The budget equation is the log-linear form:

```
log E[IR]  =  log ĪC  +  ½·log B_eff  +  log P̂  +  log TC  +  (λℓ − δ)·t
```

This is the structure of the rocket equation: stage efficiencies multiply;
stage budgets add. §8 states exactly which correspondences below are
isomorphisms, which are formal, and which are analogy.

### Figure 1 — mission profile of a research cycle

```
E[IR]
  ▲
  │                                                ╭────────── payload
  │                                         burn 3 ╯   TC          transfer
  │                                  burn 2 ╯    P̂ = 1 − FDR      precision
  │                           burn 1 ╯    √B_eff                   breadth
  │                     ╯
  └──────●───────────────────────────────────────────────────────▶ t
       H₀
   hypothesis          n candidates      P̂·n true claims       net book

  return leg ─────────────────────────────────────────────────────┐
     H₀ ◀── prior / sizing update ◀── settlement archive (flyby)  │
                        boost Δv = λℓ − δ                          │
              station-keeping:  λℓ > δ  (learn faster than decay) │
  flight envelope (not in the objective):  autonomy ≲ verification
```

The return leg is not a fourth burn. A pipeline without a settlement archive
is an open trajectory: it deorbits by decay, at machine speed.

### Figure 2 — budget allocation (log space)

```
log E[IR]  =  log ĪC  +  ½·log B  +  log P̂  +  log TC  +  (λℓ − δ)·t

field allocation:   [██████████████████░░░░░░░░░░░░░░░░░░░░░░]
                     └────── B ──────┘ └─── unallocated ────┘
                                        (where the constraints live)

this system:        [███░]   [█████]   [████░]   [███░]   [████]
                       B        P̂         TC      ĪC      λℓ−δ
                   (compute) (mechanism) (accounting) (skill) (archive)
```

The field's budget bar terminates before the binding terms. This is stated
as an allocation fact, not a criticism of any group.

## 3. Propositions

**P1 (N-exogeneity).** In an agent-native pipeline every trial is an
append-only ledger entry; the trial count N is therefore an exogenous,
auditable statistic. *Consequence:* FDR control ceases to be an assumption
and becomes a mechanism (a Bonferroni floor at ledger N). Human labs cannot
satisfy the premise — selective reporting makes N latent, which is why
multiple-testing correction is honored in statistics and absent in practice.

**P2 (Separability).** Each term of the budget equation has an estimator on
pipeline state (§5). *Consequence:* the marginal allocation problem is
well-posed — direct the next unit of resources to the term with the highest
∂ log E[IR] / ∂ cost. Movement costs differ sharply: P̂ is a mechanism
problem (cheap, far from ceiling), TC is an accounting problem (cheap,
currently unmeasured), λℓ arrives automatically once the archive exists,
and B is what the field already buys.

**P3 (Station-keeping).** If λℓ ≤ δ the system has no long-run steady
state, regardless of B, P̂, TC. *Corollary:* throughput without settlement
accelerates the descent.

## 4. Where the field's budget terminates

Essentially all marginal resources in the field go to B — more data, larger
models, faster backtests. The budget terminates before:

- **P̂** — N is latent in human and report-driven pipelines, so correction is
  unenforceable, and what cannot be enforced is quietly not attempted;
- **TC** — gross metrics are the evaluation target, so transfer loss to
  costs, turnover and capacity is not merely suffered but unmeasured;
- **λℓ − δ** — undefined wherever no archive of (claim, realized) pairs
  exists, i.e. almost everywhere.

## 5. Estimator protocol

A symbol without an estimator is decoration. Each term is computed from
pipeline state as follows:

| symbol | estimator | source |
|---|---|---|
| ĪC | mean of `realized.rankic_mean` over settled claims with `outcome=held` | settlement ledger (`settlement.jsonl`) |
| B | count of `type=experiment` entries in the period | registry (`registry.jsonl`) |
| ρ̄ | mean pairwise correlation of settled claims' realized streams | settlement ledger |
| P̂ | (i) analytic from (π, ψ, α_Bonf(N)); (ii) empirical: false-deployment rate on noise worlds; (iii) adversarial: FIB catch rate | registry N + v0.4 ablation + v0.6 FIB |
| TC | corr(claimed net metric, realized net metric) across settled claims | settlement ledger (v0.7 adds the net accounting this requires) |
| λℓ − δ | cohort slope of the calibration curve (claimed-vs-realized gap by settlement cohort) | calibration report (v0.5 report; slope estimator ships v0.7) |
| envelope | autonomy level vs verification coverage/latency; incident-free windows | watchdog + fence pilots |

## 6. Empirical status (as of v0.6)

| term | status | evidence |
|---|---|---|
| B | exact by construction | registry counts (v0.3) |
| P̂ | measured, adversarially | FIB 15/15 caught by the full stack vs 3/15 schema-only, 0/15 ungated (v0.6); noise-world false positives 3/52, all exposed at settlement (v0.5) |
| ĪC | measurable now | ledger realized blocks (v0.5) |
| TC | **unmeasured** | ships v0.7 |
| λℓ − δ | curve exists, **slope uncomputed** | calibration report (v0.5); slope ships v0.7 |
| envelope | pilot-validated | watchdog 0.21 s detection→stop; G-1 containment 5/5 |

All quantitative evidence is from deterministic synthetic worlds (§9).

## 7. Architecture as the theory's instrument

The system's layers are not features; they are the terms' instruments:

| layer | term |
|---|---|
| sandbox, mining loop, budget | B |
| registry (N-exogeneity), deflation floor, metric recomputation | P̂ |
| FIB adversarial harness | P̂ (under attack) |
| cost / turnover / capacity accounting, portfolio layer (v0.7) | TC |
| settlement ledger, calibration, reflection rule | λℓ − δ, ĪC |
| bounded autonomy (L ≲ V) | envelope |

Roadmap corollary: a capability layer ships only together with the
verification layer that measures its term — capability without its
estimator cannot be claimed.

## 8. Correspondence declaration

Precision about the physics language is part of the argument:

| statement | grade |
|---|---|
| multiplicative composition ⟺ additive log budget ⟺ Tsiolkovsky equation | **mathematical isomorphism** (same structural equation) |
| λℓ > δ station-keeping ⟺ orbital maintenance | **formal correspondence** (positive drift vs. decay) |
| settlement archive ⟺ gravity assist | **controlled analogy** (prior encounters boost later cycles; rhetoric only) |
| flight envelope ⟺ safety constraints | **naming only** |

## 9. Limitations

- First-order approximation: near-independence of claims (B_eff corrects),
  within-period stationarity, equal-volatility sizing.
- π, the prior probability of true effects, is unobservable on real data;
  P̂ is anchored on planted worlds and reported with sensitivity bands.
- All quantitative evidence to date is from deterministic synthetic worlds;
  the real-data settlement path is exercised in v0.7.
- The theory predicts the *structure* of expected deployable IR. It makes no
  claim about the achievable level of ĪC on real data, and nothing here is
  a return forecast.

## 10. Relation to prior work

- **Fundamental law of active management** (Grinold–Kahn; Clark–de
  Silva–Thorley's transfer coefficient) — this theory is its descendant;
  the contributions here are the precision term made enforceable (P1) and
  the meta-drift term made measurable (P3).
- **Multiple-testing literature** (Bonferroni; Benjamini–Hochberg; Bailey &
  López de Prado on backtest overfitting) — supplies P̂'s statistics; P1
  supplies the missing enforceability premise.
- **Adversarial evaluation in LLM safety** — supplies the methodology for
  measuring P̂ under attack (the FIB harness).
- **Scaling-laws methodology** (Kaplan; Hoffmann) — supplies the discipline
  of §5: controlled resources on one side, estimable quantities on the
  other, allocation rules as the output.
