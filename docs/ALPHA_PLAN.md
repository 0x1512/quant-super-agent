# ALPHA_PLAN — the research-supply line (why the shop exists)

> SUPERAGENT_PLAN2 builds the workshop (orchestration, memory,
> self-correction). This plan builds what the workshop MUST produce:
> factors that survive honest gates and add to the portfolio.
> 拍板 2026-11-17（用户三项决定）。

## Four decisions on record

1. **Zero survivors is a legal outcome — but then the loop must
   visibly upgrade.** A family sweep that ends 0-for-N is recorded
   honestly in EVIDENCE, feeds the graveyard (#4/S2), and the NEXT
   loop must be measurably better (see loop metrics below). Research
   is provably upgradable or we are just burning CPU.
2. **"好策略"的正式定义 = 组合增量（S10）。** Not "another IC 0.05
   factor": a strategy is good when it clears the gauntlet AND shows
   significant incremental contribution to the existing portfolio
   (incremental IC within a correlation budget). Single-factor
   verdicts are intermediate goods.
3. **First tranche ordered: S1 → S6 → S3.**

4. **Factor exclusion is dangerous (user correction, 2026-11-18): a
   fail may mean "implementation detail was wrong", not "the idea
   is dead".** The graveyard must be a ledger of doubt, not a wall.
   Five mechanisms shipped as graveyard v2 (`qsa/graveyard.py`):
   tiered sentencing (parked vs banned), autopsy with margins
   (close-call vs deep death), hypothesis/implementation separation,
   data-triggered revival for thin cells, and a budgeted revisit
   queue. Parameters 拍板 on record: **revisit quota = 20% of each
   loop's budget; hypothesis-level ban requires 2 INDEPENDENT
   implementation fails** (replays of the same implementation never
   advance the count). v1's 10 death sentences were re-sentenced
   to parked the same day, in the open (`graveyard.json` log).

## The ten programs (S1–S10)

| # | program | tier | status |
|---|---------|------|--------|
| S1 | funnel closure: fast-lane survivors auto-promote to gauntlet orders | 1 | shipped 2026-11-17 (`qsa/funnel.py`) |
| S6 | composite survival gate (stage-2, pre-registered) | 1 | shipped 2026-11-17 (`qsa/admission.py::STAGE2`); **Loop 0 closed: 0/24 public-literature factors pass on full sample** |
| S3 | family-tree search with budgeted generation | 1 | shipped 2026-11-17 (`qsa/family.py`); **Loop 1 closed: 0/24 survived, 10 cells graveyard-banned, 14 unjudgeable — Loop 2 = judgeable region + new variants** |
| S2 | family graveyard + generation-time bans (= #4 hook) | 2 | **v2 shipped 2026-11-18** (`qsa/graveyard.py`): tiers (thin/parked/banned/revived), autopsy margins, hypothesis×implementation records, data-triggered revival, budgeted revisit queue (拍板 4); v1's 10 bans re-sentenced to parked |
| S4 | regime-conditional hypotheses (= #3 first amendment source) | 2 | planned |
| S9 | walk-forward OOS (decay detection as a rolling trigger) | 2 | **wired 2026-11-18** (`qsa/walkforward.py` + `run_gauntlet()`); live fire: 15 fast-lane survivors → 15 gauntlet orders → stage-2 recheck 15/15 + walk-forward diag 15/15 fail |
| S5 | LLM hypothesis line (same pipeline, same bar, own budget) | 3 | planned |
| S7 | universe as hypothesis, not config | 3 | planned |
| S8 | data plane: A-share event face (limit hits, earnings calendar) | 3 | planned |
| S10 | settlement object = portfolio increment | 3 | definition adopted (this file); gauntlet wiring pending |

## Loop metrics — research is provably upgradable (decision 1)

Every family sweep (S3) closes a LOOP with these sealed numbers; loop
n+1 must improve at least one without regressing honesty:

- `tested` — hypotheses ordered this loop (search budget spent)
- `survived_stage2` — composite-gate survivors (may be 0, honestly)
- `gauntlet_passed` — full-chain survivors (may be 0)
- `portfolio_added` — factors that entered the portfolio (S10)
- `graveyard_savings` — hypotheses NOT re-generated because the
  graveyard banned the family (#4/S2) — the loop's learning made
  visible
- `cost_per_survivor` — budget / max(survived, 1); no survivor ->
  cost per EXCLUDED family (cheaper honest negatives still count)

A loop with 0 survivors is a SUCCESS of the funnel (it stopped bad
factors early) and a FAILURE of supply (hypothesis sources must
change: S5/S8/S7 escalate).

## Loop 0 — CLOSED 2026-11-17: the public-literature family is dead

The stage-2 gate (S6) judged all 24 catalog factors on the FULL
sample (1210 days ≈ 58 months, the pinned fixture):

| stage-1 (300-day fast lane) | stage-2 (full sample, composite) |
|---|---|
| 15 "settled" / 9 refused | **0 pass** / 19 fail / 5 inconclusive-data |

This is the honest zero decision 1 allows, now on record: the fast
lane's 15 survivors were triage artefacts of a short window; under
the pre-registered composite criteria on the full sample the
public-literature family is EXHAUSTED (consistent with, and stricter
than, the blackboard lesson "17/24 OOS-dead"). The 300-day fast lane
returning 18 inconclusive + 6 no-verdict under stage-2 is by design:
~14 monthly ICs cannot clear a 24-month floor, and the gate refuses
to guess.

Consequence: **Loop 1 = S3 family-tree search** (momentum × window ×
domain × interaction, budgeted) — hypothesis supply must come from
structured generation over the one family that ever showed life
(v1.4 smallcap momentum), not from more literature transplants.
Loop-1 metrics to seal per ALPHA_PLAN above.

## Loop 1 — CLOSED 2026-11-17: momentum family tree, second honest zero

S3's pre-registered grid (momentum × window {12,18,24,36} × domain
{top300, smallcap} × variant {plain, gap_gate, vol_adj} = 24 cells,
full sample, frozen stage-2). Sealed SSOT:
`docs/loops/loop1.json`; graveyard seed: `docs/loops/graveyard.json`;
order chain: `docs/loops/loop1_orders.jsonl`. Reproduce:
`python examples/run_family_loop1.py`.

| metric | Loop 0 (literature) | Loop 1 (family tree) |
|---|---|---|
| tested | 24 | 24 |
| survived_stage2 | 0 | 0 |
| fail → graveyard | 19 (graveyard not yet kept) | **10 banned cells** |
| inconclusive | 5 | 14 |
| cost_per_survivor | — | — (0 survivors) |
| cost_per_excluded_family | 1.26 | 2.4 |

Decision 1 demands the loop visibly upgrade; Loop 1's honest claim to
learning is twofold and mechanical:

1. **10 cells are now permanently free.** Loop 2 re-running this
   grid skips all 10 for zero budget (graveyard savings materialize
   — the S2 seed exists and works).
2. **A structural un-testability result**: every 36m-window cell
   (and most smallcap/variant-thinned cells) is INCONCLUSIVE, not
   fail — a 36m lookback on a 1210-day sample leaves ~21.6 monthly
   ICs < the 24-month floor. No amount of tuning makes these cells
   judgeable on this data plane. Supply must move to the judgeable
   region (12/18m windows, richer variants) or the data plane must
   grow (S8) — the loop's feedback is now driving supply choice,
   which is exactly what decision 1 bought.

Loop 2 (next): budget 24 over the judgeable region — 12/18m ×
domain × NEW variants (seasoning, residual-momentum, skip-k) — with
the 10 banned cells skipped free and `graveyard_savings > 0`
expected on the same grid.

## Gate definitions

**Stage-1 (fast lane, unchanged)**: oos_ic > 0.03 — cheap triage
only; a stage-1 pass means NOTHING by itself ("survivor (fast lane;
gauntlet still required)").

**Stage-2 (S6, pre-registered at promotion)**:
oos_ic > 0.03 AND icir > 1.0 AND n_months >= 24 AND
top_minus_bottom > 0 AND oos_ic >= 0.5 * train_ic (same sign).
Layered monotonicity across all 5 quantiles and rolling last-12-month
survival are gauntlet-stage checks (S9/S10 wiring) — v1 uses the
spread direction as the monotonicity proxy, stated honestly.

**Gauntlet (full chain, S9/S10 when wired)**: walk-forward OOS +
FIB budget accounting + portfolio incremental contribution.
