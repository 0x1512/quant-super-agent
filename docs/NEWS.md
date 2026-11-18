# NEWS — per-round run log

The storefront (README.md) is frozen between releases; **this file is
where each round's measurements land**. Newest first. Full evidence
inventory: [EVIDENCE.md](EVIDENCE.md); case archive with reproduce
commands: [CASES.md](CASES.md).

## 2026-11-18 — v0.1.0: repository re-seeded (fresh public history)

The public repository was re-seeded today as **v0.1.0**: a single
fresh commit carrying the full current codebase, docs, and evidence
record. Why: the pre-seed history accumulated hygiene problems
(personal author identity, non-English messages, internal planning
artifacts in old trees) that history rewrites cannot fully purge
from the hosting platform's object store. A re-seed is the only
clean-slate guarantee; the old repository was deleted.

Nothing about the RESEARCH record changed: every measurement, loop
seal, and honest zero above is preserved verbatim in this tree
(EVIDENCE.md / CASES.md / docs/loops/). The version counter restarts
at 0.1.0; the v0.x-v1.6 milestones below remain as the research
chronicle. Commit discipline from here: English-only messages,
project identity, `tools/check_public.py` as a pre-commit AND CI
gate (CONTRIBUTING.md).

## 2026-11-18 — S9 wired: the gauntlet executes; two gates, one verdict

Walk-forward OOS + decay detection as a rolling trigger
(`qsa/walkforward.py`), pre-registered: half-year blocks (min 6),
rolling 12-month IC mean < 0 = locally-dead trigger, later-half ≥
50% of earlier-half (block half-life), ≥ 2/3 blocks positive.
`run_gauntlet()` executes the WIRED checks of a queued gauntlet
order (frozen stage-2 recheck, then walk-forward) and settles with
a verdict that names its stage; the unwired checks (FIB budget,
portfolio increment) stay named on the results.

Live fire ([CASES 2b](CASES.md), reproduce in 35 s:
`python examples/run_gauntlet_live.py`): 24 factors on the 300-day
fast lane → 15 settle → funnel promotes 15 gauntlet orders →
**stage-2 recheck kills 15/15, and the walk-forward diagnostic
independently fails 15/15 — every survivor has rolling 12-month
dead windows** (skew_20d: 20 dead windows; rev_1w: 16; mom_12_1:
9). Two independently constructed gates, one verdict: the fast
lane's survivors were short-window artefacts, and the conveyor now
ends in an executed, hash-chained settlement — not a pipe.

Also in this drop: a look-ahead ORACLE factor passes the wired
chain in tests (the gauntlet is a filter, not a mind-reader —
catching look-ahead is the FIB/S5 program's job, stated honestly).

11 new tests; suite 525.

## 2026-11-18 — Graveyard v2: a ledger of doubt, not a wall

User correction on record ([ALPHA_PLAN.md](ALPHA_PLAN.md) decision
4): **factor exclusion is dangerous** — a fail may mean the
implementation detail was wrong (the volume proxy standing in for
market cap), not that the idea is dead. One-fail-permanent-ban
kills ideas that were never properly researched. Shipped the
five-mechanism fix (`qsa/graveyard.py` + `qsa/family.py`):

- **Tiered sentencing** — one implementation's fail = **parked**
  (suspended, retestable); hypothesis-level **banned** needs 2
  INDEPENDENT implementation fails (user 拍板 threshold); replays of
  the same implementation never advance the count (no ban-farming).
- **Autopsy with margins** — every fail stores per-criterion
  distances + the full metric snapshot: a close-call death (within
  20% of the line) is visibly different from a deep death, and any
  future gate re-version can replay verdicts for free.
- **Hypothesis/implementation separation** — records live per
  (cell, implementation); a better implementation starts clean and
  is what can promote a cell to banned — or revive it.
- **Data-triggered revival** — when the data plane grows ≥ 20%,
  thin (unjudgeable) cells automatically get revisit proposals;
  nobody has to remember them.
- **Budgeted revisit queue** — any source files RV-xxx proposals
  that MUST carry a reason and a change; the loop spends its quota
  (user 拍板 20%) on revisits FIRST, and revisit pass-rate is
  sealed per loop (never passing = the gate is hard; often passing
  = the graveyard was over-killing — both are signal).
- **The honest re-sentencing**: Loop 1's 10 v1 death sentences were
  re-sentenced to parked the same day, in the open — the migration
  is recorded in `docs/loops/graveyard.json`'s log.
- 10 new tests (tiers/margins/migration/revival/queue/quota);
  suite 514.

## 2026-11-17 — Loop 1: the momentum family tree, second honest zero

S3 shipped (`qsa/family.py`): pre-registered grid — momentum ×
window {12,18,24,36}m × domain {top300, smallcap (volume-proxy,
stated)} × variant {plain, gap_gate, vol_adj} — 24 cells, budget
24, full sample, S6's frozen stage-2. Reproduce:
`python examples/run_family_loop1.py` → `docs/loops/loop1.json`.

- **survived_stage2 = 0 / 24** — the second honest zero, sealed.
- **10 cells banned in the graveyard** (fail = metrics present,
  thresholds missed): the S2 seed works — Loop 2 skips them free
  (`graveyard_savings` materializes).
- **14 cells unjudgeable, and that is a result**: a 36m lookback on
  a 1210-day sample leaves ~21.6 monthly ICs, under the 24-month
  floor; variant-thinned smallcap cells thin the cross-section
  below judgeability too. The loop now knows WHERE it cannot see —
  supply moves to the judgeable region (12/18m × new variants) or
  the data plane grows (S8).
- Survivors (none this loop) would enter the gauntlet queue with
  criteria frozen and S9/S10 checks listed as unwired on the order
  — `gauntlet_passed` stays 0, honestly, until they are wired.
- 5 new tests; suite 504.

## 2026-11-17 — ALPHA_PLAN opens: funnel + stage-2; Loop 0's honest zero

User 拍板 (2026-11-17, [ALPHA_PLAN.md](ALPHA_PLAN.md)): zero
survivors is legal but the loop must visibly upgrade; **"好策略" =
组合增量** (S10, the formal definition); first tranche S1→S6→S3.

- **S6 stage-2 composite gate** (`qsa/admission.py::STAGE2` +
  `stage2_verdict`): oos_ic>0.03 AND icir>1.0 AND n_months≥24 AND
  top_minus-bottom>0 AND ic_decay_ratio≥0.5 — pre-registered, frozen
  into every promoted order's params (promotion with different
  criteria than admitted is a hard error). Missing metric → no
  verdict, never a judgement call; <24 months → inconclusive.
- **S1 funnel** (`qsa/funnel.py`): a settled fast-lane survivor
  auto-promotes to a GAUNTLET order (same hypothesis, frozen stage-2
  criteria, unwired S9/S10 checks listed honestly ON the order),
  queued at low priority — idle-slot work, never in front of fresh
  research. Double-promotion refused; only fast-lane survivors
  promote. The conveyor from fast lane to gauntlet no longer ends in
  a pipe.
- **Loop 0 closed — the honest zero, on record**: stage-2 over all
  24 public-literature factors on the FULL sample (1210 days ≈ 58
  months): **0 pass / 19 fail / 5 inconclusive-data**, vs 15
  "settled" in the 300-day fast lane. The short window's survivors
  were triage artefacts; the literature family is exhausted — which
  is exactly why Loop 1 = S3 family-tree generation (momentum ×
  window × domain × interaction, budgeted) over the one family that
  ever showed life.
- 9 new tests; suite now 499

## 2026-11-17 — Wave-1 live: the ten-goal show (G1–G10)

The four Wave-1 pieces demonstrated as ONE scripted story:
`python examples/run_wave1_live.py` — offline, deterministic, ~10 s,
and it asserts every beat (a broken promise crashes the show instead
of flattering us). Sealed numbers in
[EVIDENCE.md](EVIDENCE.md#v15-wave-1-live--the-ten-goal-show-automated-reproducible-by-anyone);
the show itself is now a regression test (`tests/test_wave1_live.py`:
10/10 twice, behavior figures identical across runs).

- headline: 24 orders through a 3-slot queue in 9.1 s with the
  completion order re-derived from the replayed ledger; a follow-up
  ("把门槛收到 0.05") answered in **1 ms with zero rescoring**
  (single-factor recompute 0.379 s ≈ 620×); SIGKILL mid-show → 0
  lost, 3 incident lines, 1 backoff restart; panel lit exactly once
  (one real fork); a 4.2 KB delivery package every number of which
  re-verifies against the live ledger
- also shipped: **`qsa/deliver.py`** — PLAN2 #8's first half. A
  settled order becomes a self-proving package (four-line conclusion
  card / full event chain / mechanical reproduce commands / manifest
  with a size door — over-budget packages are marked needs_split,
  never silently shipped). `--verify` re-reads the package against
  the ledger: packaged events must hash-match the replayed chain,
  card numbers must exist in the settle event, manifest bytes must
  match disk. Tampering with EITHER side fails loudly (pinned by
  tests). 6 new tests + 2 show tests, suite now 490

## 2026-11-17 — PLAN2 Wave 1 #6: order resurrection (one human message)

`qsa/resume.py` — a dead order is no longer a dead conversation. dsh
001: an ended Ticket keeps its Subscription — one message revives it
under the same Mandate. Our ledger is hash-chained and terminal states
stay terminal, so revival is a DELTA ORDER, not a rollback:

- **the chain**: the settled/refused order gains a `resume` event
  (stays terminal, cites the delta id); the delta order's `create`
  cites `resume_of` + the prior run's digest. Replayed ledgers show
  the whole conversation: ORD-A → delta → delta-of-delta
- **bar-only, zero rescoring**: "把门槛收到 0.05" on a settled order
  re-verdicts from the cached leaderboard in seconds
  (`rows_rescored == 0` pinned by tests) and settles a fresh verdict;
  structural messages ("剔除小盘重算") produce a recompute delta that
  reuses checkpoints downstream
- **the human gate**: only `by="human"` revives — the watch loops and
  the scheduler never resurrect anything (不拍板零执行); a live order
  doesn't resume, it takes new instructions
- **the refusal gate — deliberately stricter than dsh**: a refused
  order has no results to re-verdict, so bar-only messages on it are
  refused outright, and any revival with the SAME (hypothesis, params)
  hash is refused: re-trying a rejected hypothesis must be an explicit
  parameter change (our multiple-testing discipline)
- **unparseable text creates nothing** — zero ledger events, the
  caller sees the refusal reason; 9 new tests, suite now 482

## 2026-11-17 — PLAN2 Wave 1 #7: attention-first panel (zero JS)

`qsa/panel.py` — the dsh principle (000) made literal: *"A panel that
shows only what needs a person. It lists first what waits for a
person. A healthy state takes no space."* `qsa board` stays the
workshop panorama; the panel is the to-do list.

- **first screen = only what waits for you**: open fork cards
  (拍板待选, each with numbered options and the reply format
  「FORK … 选 N」), unresolved blockers, and queue-overflow receipts
  from #2's backpressure — each card cites its ledger (file, entry
  index, chain hash)
- **healthy takes no space**: a fully healthy workshop shows one green
  line and nothing else; the whole `qsa board` panorama folds into a
  native `<details>` at the tail (zero-JS folding, 三通道制)
- **amendment cards reserved**: PLAN2 #3's 修正案 will join the first
  screen the day it ships — the collector already reads for them
- **zero JavaScript**: `grep -c "<script"` over the output is pinned
  at 0 by tests; the file is the deliverable (no service, no port)
- **recomputable**: every badge number is re-derived from the ledgers
  inside the tests (count cards, post blockers, resolve one, watch it
  leave the screen); 8 new tests, suite now 473

## 2026-11-17 — PLAN2 Wave 1 #2: order queue + slot scheduling

`qsa/queue.py` — orders now WAIT instead of stampeding. The
[dsh principle](https://github.com/dsh-superagent): concurrency has a
budget, and **a human message always keeps its own reserved slot** —
new machine work can never crowd out the person asking.

- **state machine**: `queued` state added to the order ledger
  (`admitted → queued → running`, hop optional — the direct path
  stays legal for compatibility); every order now records `origin`
  (`machine` default, `human` for channel messages) so a replayed
  ledger knows who asked
- **policy**: pick by (priority, FIFO); `slots` machine concurrency
  cap, humans may use `slots + 1` — work-conserving, never idle when
  work is queued
- **driver `run()`**: executes picked orders via a minimal `Job`
  protocol (a `poll()` returning `None` while running), `on_exit`
  callbacks — and it **never settles or refuses**: settlement stays
  with the order's owner, 不拍板零执行
- **backpressure, honestly**: a full queue parks the new draft as a
  blackboard order_note receipt (回执) instead of dropping it; a
  queued order withdrawn before start (`withdraw` = refuse with
  reason) leaves no residue
- **acceptance pinned**: 10 orders on 3 slots run in priority order
  with max 3 concurrent and the ledger replays the sequence; a human
  order starts in the first scheduling round while both machine slots
  are busy; 9 new tests (`tests/test_queue.py`), suite now 465
- drive-by: `tests/test_patrol.py`/`tests/test_watch.py` now import
  `unittest.mock` explicitly — they only passed before because the
  full-suite run imported it for them (subset runs exposed it)

## 2026-11-17 — SUPERAGENT_PLAN2 approved; Wave 1 #1 daemon shipped

User 拍板 (2026-11-16, recorded in [SUPERAGENT_PLAN2.md](SUPERAGENT_PLAN2.md)):
schedule A (Wave 1 = daemon/queue/resume/panel), panel = static
zero-JS HTML, multi-source = simulated-GitHub-first (offline stub by
default, real API opt-in), lessons = auto rule-based. Work started
same day.

- **#1 daemon** (`qsa/daemon.py`): one supervisor for the whole
  workshop — the resident loops (watch daemon mode) restart with
  backoff when they die, one-shot passes (patrol, watchdog `--once`)
  re-run on their interval, and every exit/restart/reap is an incident
  line (`daemon/incidents.jsonl`), never silent
- **start gate**: a broken order chain or an unparseable watch/patrol
  state REFUSES startup with the named reason — a supervisor that
  starts on a corrupted ledger is a multiplier, not a guard
- **degradation, honestly**: a service exiting more than
  `max_restarts_per_window` times inside `window_s` is marked degraded
  and stops being restarted (the incident says so) — a flapping
  service restarted forever would burn attention, not save it
- **crash discipline**: child pids are recorded atomically; after a
  SIGKILLed daemon, the next startup reaps exactly its own orphans
  (identified by the `QSA_DAEMON_CHILD` environ marker) BEFORE
  spawning — a restart can never double-run a service
- **acceptance pinned end-to-end**: real watch under the daemon →
  SIGKILL the daemon → restart → the orphan is reaped and the one
  event that already fired drafts exactly ONE order (no replay, no
  loss — the keyed atomic watch state owns that, the daemon only
  restarts its owner); graceful SIGTERM leaves zero children and a
  shutdown incident
- `python -m qsa.daemon --root work` uses the standard workshop
  config (watch resident + patrol/watchdog periodic, services included
  as their config files exist); `--config` takes a declarative JSON
- 不拍板零执行 unchanged: the daemon supervises processes only — it
  never admits, settles, or touches a fork decision

## 2026-11-16 — provider plane wired into patrol + watch (#10, phase 2)

`provider.judge()` is now a real decision point, not just an adapter:
with `QSA_PROVIDER=gateway` a **user-supplied** OpenAI-compatible
endpoint can veto a rule verdict before any draft is raised — at
exactly two safe spots. Offline (the default, and every CI test)
behavior is byte-identical to before; any gateway failure falls back
to the rule verdict. **446 tests green (+11 this round)**.

- **patrol confirmation** (`qsa/patrol.py`): a target's optional
  `note` field (e.g. "盘后静态快照，盘中不更新属正常") flows into the
  judge question, so the model can distinguish expected staleness
  from real breakage. A dismissal writes one incident line —
  `model-dismissed (by): reason || rule verdict was: <detail>` —
  deduped across passes; a confirmation drafts the repair order as
  before
- **watch event filtering** (`qsa/watch.py`): same `note` mechanism
  on rules; a dismissal marks the event processed (never re-asked)
  and lands in `watch/dismissed.jsonl` with rule, event, reason and
  attribution; a confirmation drafts as before
- **never silent, never sovereign**: every dismissal is recorded next
  to the rule verdict it overrode; dismissals NEVER touch admit /
  fork / 拍板 — those stay 100% human (不拍板零执行 unchanged)
- **live round-trip validated** against a real OpenAI-compatible
  gateway (env-gated live test in `tests.test_provider.TestJudge`,
  plus a manual patrol/watch pass): a stale post-close
  snapshot correctly dismissed with reason, a stale live panel
  correctly confirmed, fresh data confirmed into an order, editor
  junk files correctly dismissed — 4/4 right calls, all recorded
- failure semantics pinned in tests: garbage responses and dead
  endpoints both fall back to `by=fallback` (rule verdict stands) —
  a broken gateway can never silently change behavior, only fail to
  improve it

## 2026-11-16 — SUPERAGENT_PLAN: the 10 dsh-superagent planes, shipped

Design: [SUPERAGENT_PLAN.md](SUPERAGENT_PLAN.md) (user-approved
2026-11-16: #1–#9 built; #10 = user-supplied OpenAI-compatible
gateway, no external vendor dependency). All ten planes are
mechanical and offline-by-default;
**435 tests green (+71 this round)**.

- **#1 async task model** (`qsa/tasks.py`): `start/status/wait/cancel`
  over detached process groups; every transition lands on a task card
  (`running → settled|failed|cancelled|interrupted`); dead-pid cards
  self-heal to `interrupted` (zombie-aware liveness, so an unreaped
  detached child is never mistaken for a live one)
- **#2 checkpoint resume** (`qsa/checkpoint.py` + `--resume`): per-job
  results land under `<work>/checkpoint/` keyed by (stream, job,
  plan-fingerprint); a run that lost HALF its checkpoint files and
  resumed rewrites a byte-identical leaderboard and only actually runs
  the missing jobs (pinned end-to-end in tests/test_checkpoint.py)
- **#3 event trigger bus** (`qsa/watch.py`): file/timer rules → order
  drafts (hash-chained) + blackboard blockers; same event never fires
  twice; **不拍板零执行** pinned (drafts never advance on their own)
- **#4 resident patrol** (`qsa/patrol.py`): healthy targets produce
  zero output; a confirmed problem with a known fix drafts exactly ONE
  repair order (deduped); problems without a fix are incidents, never
  orders
- **#5 worker sessions** (`qsa/crew.py`): every dispatched stream
  leaves a session card (role, job keys, rows, checkpoint accounting) —
  a strict superset of the numeric rows, reconciled against the run
  manifest on every run (`[crew]` would print any mismatch)
- **#6 router + board** (`qsa/router.py`, `qsa/board.py`): multiple
  orders run concurrently in isolated work dirs — concurrent output is
  byte-identical to sequential (real runs, tests/test_router_board.py);
  `python -m qsa.board --root work` reconciles tasks/orders/incidents/
  blockers/crew from the ledgers
- **#7 watchdog** (`qsa/watchdog.py`): external rules-only loop;
  infra_died / budget_exhausted / no_progress each downgrade with an
  attributed incident line; progress = footprint (log bytes + files),
  so a chatty task is never killed
- **#8 cross-channel continuity** (`qsa/channels.py`): cli / inbox dir
  / webhook all funnel into one handler that chains the previous run's
  leaderboard — the same follow-up over any channel yields the same
  re-verdict (zero rescore), pinned across channels
- **#9 speculative execution** (`qsa/speculative.py`): preflight runs
  the pipeline during the human's admit-pause; on admit, delivery
  verifies the fingerprint-bound artifacts and settles in well under
  the 10%-of-a-cold-run gate (asserted in tests/test_speculative.py);
  refusals record their waste in `work/speculative/stats.json`
- **#10 provider plane** (`qsa/provider.py`): default = offline rule
  engine (deterministic, auditable, no key, no network);
  `QSA_PROVIDER=gateway` + `QSA_GATEWAY_URL` routes to the
  **user-supplied** OpenAI-compatible gateway of your choice
  — verified against a local stub server, not a mocked client

- throughput gate untouched and still green (`make throughput`:
  smoke 228/min, full 95.1/min @ 13 workers, floor 20)

## 2026-11-16 — README storefront stabilization (v1.4.1 line)

- the public README stopped being test-result-driven: capability verbs,
  magnitudes, a rendered status card, dynamic badges; all per-round
  numbers moved here / EVIDENCE / CASES / TOUR_NUMBERS
- enforcement shipped: `tools/check_readme.py` (lint + SSOT + freeze)
  in CI and the pre-push hook; release snapshots under
  `docs/releases/`; policy charter in [README_POLICY.md](README_POLICY.md)
- fixed a real dead-link bug: the Documentation section linked
  POSITIONING.md and capability_showcase.html — internal-only files
  that 404 in the public repo (dual-repo rules)

## 2026-11-16 — v1.4.1: effectiveness round (a fresh intent, end to end)

Intent `小盘股残差因子进攻：…门槛 residual oos IC > 0.04，至少 15 个月`,
one command, full panel — all four parameters honored (bar 0.04, floor
15 months, smallcap 75 tickers, forge on), plan fingerprint
`d86e69253189c37b`:

- **84 candidates → 28 settled orders** (vs the top300 baseline's
  78→14 at the looser 0.03/12mo bar) — the smallcap regime is
  measurably richer; head `mom_24m` +0.1372, `mom_18m` +0.1114
- **a sandbox-forged factor cleared the pre-declared bar**:
  `forge_turnover_shock_21` residual oos IC +0.0418 (code@48d9cfc5),
  settled tagged `sandbox-forge`
- conversation on top: 「门槛提到 0.05」 re-verdicted 84 rows with 0
  rescored (28→20); 「剔除小盘」 recomputed 78 rows in 30.1s (kept 2 /
  added 6 / dropped 26 — 26/28 winners are smallcap-specific); an
  unparseable ask refused with exit 1
- `make tour` correctly DRIFTs against this run (it is not the
  baseline); `qsa.memreport` lists all runs with role×job manifests
- cost found: the truncated-view sandbox is O(D²) — 6 template
  candidates took 297.6s of the 336.6s total; the streaming sandbox is
  the concrete follow-up
- fixes shipped from this round: verbose bar parsing, the main run
  honoring the intent's universe, forge jobs mapped to a crew role in
  the manifest

## 2026-11-14 — v1.4.0: conversation & self-orchestration plane

Ten showcase promises made mechanical (intent entry, plan tree,
auto crew, conversational increments, repair ladder, sandbox forge
loop, fork cards as questions, memory receipts, layered report, tour
drift alarm). Measured at ship time: reference full run 78 candidates
→ 14 orders in 49.2s at auto-13 workers (byte-identical to the
sequential path); smoke window honest zero in 20.0s; bar-only follow-up
rescored 0 rows; smallcap recompute 22.7s; forge loop live: 1 gap → 6
sandbox candidates, 6 evaluated, 0 refused. 84 new tests, suite 353.
Details: [EVIDENCE.md](EVIDENCE.md) §v1.4.
