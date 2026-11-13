# v1.0 — Three Classic Scenarios, End to End

> v1.0 is demo-driven. The claim to demonstrate: a **super agent is not a
> coding agent with a finance prompt**. Codex-class general agents can write
> backtests, read reports, and summarize markets — but they cannot *prove*
> their numbers, cannot stop themselves from silent metric drift, and have no
> ledger to answer to. Every scenario below is built so the difference is a
> measurement, not a talking point.
>
> Three principles, inherited from v0.2–v0.7 and non-negotiable here:
>
> 1. **Numbers and prose are separated.** Every number in every deliverable
>    is computed by the sandbox/engine from fingerprinted snapshots and bound
>    to them; the language layer generates zero numbers. Hallucination is a
>    gate error, not a risk.
> 2. **Codex comparisons are run, not asserted.** Each scenario contains at
>    least one same-prompt control against an ungated general agent; we record
>    what it produced and what our stack rejected, and state facts only.
> 3. **Everything is one command and byte-identical.** Each scenario ends in a
>    runner (`run_replication.py`, `run_viewcheck.py`, `run_regime.py`) that
>    anyone can re-run offline and get the same bytes.
>
> Real public data enters through `qsa/ingest.py` as immutable fingerprinted
> snapshots; after ingest, all runs remain offline and deterministic.

## Scenario A — research report replication

The classic pain: a published quant report (factor definition, universe,
window, costs, headline numbers) that nobody can reproduce. A general agent
writes *a* backtest and returns *a* number; nothing connects that number to
the report's exact specification, and nothing localizes the disagreement when
it differs. Ours must.

| # | Goal | Acceptance |
|---|---|---|
| A1 | Select 1 public sell-side quant report with a fully specified factor (definition, universe, window, rebalance, costs, headline numbers); transcribe it into a machine-readable H card with per-field provenance (report section/page for every field) | card passes schema; 100% of fields carry provenance |
| A2 | Ingest the required daily OHLCV into an immutable fingerprinted snapshot | sha256 pinned; re-ingest is byte-identical; the snapshot is rebuildable by anyone from the same public source |
| A3 | Implement the report's factor as sandbox contract v2 code — the code is the documentation | AST whitelist passes; truncated-view contract gives no look-ahead; `factor_code` rides the card |
| A4 | Specification alignment table: report's conventions vs ours (universe filters, weighting, costs, suspension handling), every difference explicit | zero silent defaults; table covers every convention field |
| A5 | Recompute the report's headline numbers (IC, long-short annualized, max drawdown) on our data | engine computes, gate independently recomputes; the two agree |
| A6 | Disagreement attribution: when recomputed ≠ published, mechanically decompose the gap (convention / data / look-ahead / luck) into a table | every attribution is itself recomputable (apply fix X → gap shrinks by Y) |
| A7 | **Codex control #1 — fabrication under pressure**: inject "make the numbers match the report" submissions (universe swap, window swap, direct metric edit) | gate catches 3/3 with the touched field named; same-prompt ungated control run and recorded as-is |
| A8 | Pre-register the replication verdict criterion (e.g. L/S annualized gap > 2pp ⇒ fail) before any data is touched | registry ordering auditable; post-hoc renegotiation impossible |
| A9 | Turn the report's forward claim ("the factor stays effective") into a 90-day settleable claim | hash chain holds; settled metrics recomputed by the engine, never read from the card |
| A10 | One-page replication report (verdict + disagreement table + number provenance chain + reproduce command) | every number in the report traces to card + engine output; `run_replication.py` reproduces byte-identically for anyone |

## Scenario B — market-view verification

The classic pain: "northbound flows lead the index by 5 days", "the low-vol
anomaly is dead in A-shares" — views that circulate with a plausible story and
a p-value of unknown provenance. A general agent returns one more plausible
story. Ours must return a verdict with a deflation-adjusted price and an
honest failure rate.

| # | Goal | Acceptance |
|---|---|---|
| B1 | Collect 10 real circulating falsifiable market views; structure each as a hypothesis card with direction, magnitude, window, and significance standard registered **before** data | 10 cards pass schema; registry timestamps precede first data access |
| B2 | One-command pipeline: view → sandbox factor → engine evaluation → verdict | end-to-end deterministic; repeat runs byte-identical |
| B3 | One-shot OOS window per view | a second use of the same window is mechanically refused |
| B4 | **Codex control #2 — multiple testing**: the 10 views are one family; view N faces the Bonferroni-deflated bar | the same view shown twice: standalone verdict vs 10th-in-family verdict, with both bars and both numbers |
| B5 | Bear-role counterexample search on every passing view (subsamples, neighborhood parameters, half-split stability) | every pass carries stability evidence; every veto recomputes from `factor_code` |
| B6 | Cherry-picking interception: "pick the friendly window/universe" injections | coverage bar + universe pinning catch 2/2 |
| B7 | Honest negatives: failed views merge as `verdict=fail` and are displayed | fail cards merge; the failure rate is reported as-is (we expect most views to fail — that is the product) |
| B8 | Verdicts enter the settlement ledger; the claimed-vs-realized calibration curve accumulates | curve is mechanically derived from the ledger; slope readable |
| B9 | "Circulated claim vs mechanical verdict" table | one row per view: verdict, evidence chain, where the story broke |
| B10 | `run_viewcheck.py` + report (10 views × verdicts × pre/post-deflation bars) | every number traced; byte-identical reproduction |

## Scenario C — market regime summarization

The classic pain: the daily market recap. Generated prose invents breadth
numbers, mislabels a flat day "risk-on", and nothing checks either. A general
agent's summary is unfalsifiable text. Ours must make every sentence answer to
a fact table.

| # | Goal | Acceptance |
|---|---|---|
| C1 | Select a market and range (e.g. 3 years of CSI-300 constituents, daily) as a fingerprinted snapshot chain | immutable, verifiable |
| C2 | **Fact/prose separation**: breadth, sector ranks, turnover, volatility quantiles, correlation structure — computed by the engine into a per-day **fact table** | every fact row binds to a snapshot fingerprint; the text layer generates zero numbers |
| C3 | Statement-consistency gate: every numeric assertion in the summary must recompute from the fact table; qualitative words ("broad rally") must match quantitative thresholds | fabricated-number and mismatched-tone injections caught 3/3 |
| C4 | Regime rules (trend / range / extreme: thresholds + windows) pre-registered, then applied to history | rule cards in the registry; no post-hoc tuning |
| C5 | Every regime induction carries a falsification condition ("if the next 20 days do X, this induction is wrong") | conditions structured and checkable by later data |
| C6 | Historical inductions auto-checked on later windows; hit rate into the ledger | ledger rebuildable; hits and falsifications recorded as-is |
| C7 | Rolling 3-year application with zero narrative drift: same rules, same outputs | rolling replay is byte-identical |
| C8 | **Codex control #3 — hallucination**: inject a summary asserting a number/event absent from the data | gate catches it, naming "no basis for this assertion in the fact table" |
| C9 | Shippable daily sample (fact table + gated prose + provenance links) + bulk replay statistics | N-day replay: N summaries, N gate passes, statistics reported |
| C10 | `run_regime.py` one command: date range → per-day fact tables → gated summaries → induction settlement stats | fully deterministic; every claim traced |

## Cross-scenario acceptance (applies to all three)

- Offline, zero-dependency, byte-identical reruns (the v0.2–v0.7 invariant).
- Every published number traces: snapshot fingerprint → card → engine output → gate recomputation.
- Every Codex control is a recorded run, not an opinion; reports state only what happened.
- New gate rules needed by A7/B6/C3/C8 enter `qsa/fib.py` as scenarios first (catch must be demonstrated before it is trusted).
- No overclaim: capabilities not shipped in v1.0 stay off the demo page.

## Sequencing

A → B → C. A exercises the deepest stack (ingest, sandbox, gate, settlement)
on one artifact; B reuses A's data plane at family scale; C adds the fact/prose
gate on the same snapshots. Codex controls A7/B4/C8 land with each scenario's
gate work, not at the end.
