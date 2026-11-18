# CASES — case archive

The README keeps an index (case + one line, no ICs); **this file keeps
the archive**: date, intent, plan fingerprint, reproduce command, full
numbers. The four-line story pattern (settled what / at what bar /
with what cost / how to re-run) applies to every entry.

## Index

| # | Case | One line |
|---|---|---|
| 1 | Top-300 baseline (v1.4 line) | the reference full run behind the status card |
| 2 | Smallcap residual attack (v1.4.1) | one command, full panel, a forged factor clears the bar |
| 3 | Forge turnaround (v1.4.0) | 1 measured gap → 6 sandbox candidates → 6 evaluated |

---

## Case 1 — top-300 baseline (the reference run)

- **settled**: the reference full run behind the status card's
  candidates/orders/throughput tier
- **bar**: residual oos IC > 0.03, ≥ 12 months in sample
- **cost**: reference runs complete in minutes on one box; the
  parallel (auto-N) and sequential paths are byte-identical, 4.0× at
  13 workers — see EVIDENCE.md §v1.4 for the exact seconds
- **re-run**: `make offense-full` (artifacts under `work/auto1`-style
  run dirs; `qsa.memreport` lists every run with its plan fingerprint)

## Case 2b — gauntlet live: the funnel executes 15 short-window survivors (S9)

Reproduce: `python examples/run_gauntlet_live.py` (35 s wall, fully offline).

1. fast lane (300 days): 15 of 24 literature factors "settle" (oos_ic > 0.03 triage);
2. funnel (S1): 15 gauntlet orders, stage-2 criteria frozen at promotion, anti-double-spend enforced;
3. gauntlet (S6 recheck + S9 walk-forward, full 1210-day sample): **stage-2 recheck kills 15/15**; the walk-forward diagnostic (attached, non-binding) shows **15/15 also fail the rolling gate — every single one has rolling 12-month dead windows** (skew_20d: 20 windows, rev_1w: 16, run_length: 15, ret_vol_scaled_21d: 12, rev_1m: 11, mom_12_1: 9, dist_52w_high: 9, gap_vol_21d: 5).

Reading: two independently constructed gates reach the same verdict
on the same 15 orders — the fast lane's survivors were triage
artefacts of a short window, and the chain (order -> fast lane ->
funnel -> gauntlet -> settled verdict with reasons) removes them
mechanically, 35 seconds end to end, every step hash-chained.

## Case 2 — smallcap residual attack (v1.4.1)

- **intent**: 小盘股残差因子进攻 — smallcap universe (75 tickers), bar
  residual oos IC > 0.04 (≥ 0.04), ≥ 15 months in sample, forge enabled
- **plan fingerprint**: `d86e69253189c37b`
- **settled**: 84 candidates → 28 orders; head `mom_24m` +0.1372;
  sandbox-forged `forge_turnover_shock_21` +0.0418 (code@48d9cfc5),
  tagged `sandbox-forge`
- **cost**: 336.6s total, of which 297.6s is the O(D²) truncated-view
  sandbox (6 forge candidates) — the streaming sandbox is the known
  follow-up
- **re-run** (adjust WORK/FORGE paths as needed):

```bash
qsa "小盘股残差因子进攻：30因子库，小盘宇宙（非沪深300），bar residual oos IC > 0.04（残差口径），至少15个月样本内，forge 开启"
# conversation on top:
#   「门槛提到 0.05」  -> re-verdict 84 rows, 0 rescored, 28->20
#   「剔除小盘」       -> recompute 78 rows, 30.1s, 2 kept / 6 added / 26 dropped
```

- **notes**: vs the top300 baseline (78→14 at the looser 0.03/12mo
  bar) the smallcap regime is measurably richer; 26/28 winners are
  smallcap-specific. `make tour` DRIFTs against this run by design (it
  is not the tour baseline) — that alarm firing is the check working.

## Case 3 — forge turnaround (v1.4.0 line)

- **settled**: 1 measured gap → 6 sandbox-generated candidates → 6
  evaluated, 0 refused by the gate
- **bar**: same as the parent run's pre-declared bar
- **cost**: sandbox evaluation dominates; see EVIDENCE.md §v1.4
- **re-run**: `make forge-demo` (or any intent with forge enabled and
  a gap under the bar)
