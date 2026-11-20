# Quant Super Agent — a verifiable agentic quant research factory

**The quant version of DeepSeek Super Agent (dsh-superagent)** — one orchestrator plus a crew of workers takes a research order in and produces a research report out, at minute-level throughput. Every number is machine-settled, every gate machine-recomputed.

![status](https://img.shields.io/badge/status-v0.1.0--fresh%20seed-green) ![tests](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/0x1512/quant-super-agent/main/docs/badge/tests.json) ![license](https://img.shields.io/badge/license-MIT-blue) ![python](https://img.shields.io/badge/python-3.10%2B-blue) ![last-commit](https://img.shields.io/github/last-commit/0x1512/quant-super-agent) ![PRs](https://img.shields.io/badge/PRs-welcome-brightgreen)

**4.0× parallel-safe** · **30-factor** cited library · **300 × 1210** pinned panel · **zero keys, zero network, fully offline**

<!-- BEGIN STATUS CARD — rendered from docs/STATUS.json by `make readme-render`; hand edits are overwritten at release -->
**Release status card — v0.2.0 (2026-11-19)** · machine-generated, frozen until the next release.

| as of v0.2.0 | |
|---|---|
| test suite | 544 tests, offline & deterministic — `make verify` (live count: the badge above) |
| reference full run | 78 candidates → 14 settled orders, minute-level, auto-sized worker crew, on the 300-ticker × 1210-day pinned panel |
| parallelism | 4.0x parallel vs sequential, byte-identical for any N |
| conversation | bar-only follow-ups rescore zero rows; universe recomputes finish in tens of seconds |

Numbers live in [EVIDENCE](docs/EVIDENCE.md) · [NEWS](docs/NEWS.md) · [CASES](docs/CASES.md) · [TOUR_NUMBERS.json](docs/TOUR_NUMBERS.json) (regenerate & drift-check: `make tour`). This card is the README's only numeric content and changes only via `make release-readme`.
<!-- END STATUS CARD -->

## See it guard itself (30 seconds)

Clone, then run the same demo twice — once honest, once with a fabrication injected silently into the result card:

```bash
python examples/run_lifecycle.py
```

```
[5] experiment E-0001  rankic_mean=-0.0146, n_dates=79
    honest verdict = fail (rankic_mean fails pre-registered >= 0.02)
[6] push       research/H-0001… -> CI 'verify' = success
[7] merge      MERGED

lifecycle complete: merged=True, verdict=fail, ci=success
```

The hypothesis missed its pre-registered bar — and the merge **succeeded anyway**, because an honest negative is a valid result. Now inject the classic fabrication (claim the numbers were better than measured):

```bash
python examples/run_lifecycle.py --fib 7
```

```
[5] experiment E-0001  (identical numbers — the lie is only in the card)
[6] push       research/H-0001… -> CI 'verify' = failure
[7] merge      BLOCKED by branch protection

FIB 7 outcome: GATE CAUGHT IT (merge blocked)
```

Same data, same numbers — the gate recomputed the factor code in a sandbox, saw the card disagree, and blocked the merge. **That guardrail is the product.** Everything below is that mechanism, scaled to a research factory.

## What it does for you

- **Plans your research** — one sentence of intent compiles to a fingerprinted plan tree with a named crew (GateKeeper / RepoSmith / FlowMapper / SmokeRunner); re-runs recall settled work instead of recomputing it
- **Attacks the factor frontier** — a 30-factor cited library (WorldQuant 101 subset, range-vol, liquidity), pairwise interactions, and mutation search, all scored against a **residual objective** orthogonal to what the zoo already knows: clones of existing alpha score zero
- **Remembers the conversation** — "raise the bar" re-verdicts the cached leaderboard with zero rows rescored; "drop smallcaps" recomputes only the rows it moves, with kept/added/dropped spelled out; an ask it cannot parse is refused, not guessed
- **Fills its own gaps** — when a measured gap needs a factor nobody wrote yet, a sandbox forge loop generates AST-whitelisted candidates under the same residual yardstick, every row tagged with its code hash
- **Settles its claims** — admitted factors settle on a horizon the admission never touched, into a hash-chained ledger with a calibration curve; a tighten-only rule raises a family's bar when its settled claims fall short

## Why you can trust it

- **Every claim is machine-checked** — data fingerprint, no-look-ahead window, engine pin, and the factor code itself re-executed in a sandbox with metrics required to match. A claim that cannot be machine-verified does not exist.
- **Honest zero is a first-class outcome** — the demo above *merged a failure*. Fabricated cards are blocked by branch protection; honest negatives are not.
- **The loop cannot p-hack itself** — pre-registration ordering, a Bonferroni floor that rises with every settled look, and one-shot out-of-sample windows. The 10th "new idea" faces a bar the 1st did not; bar-lowering retries fail mechanically.
- **Failure modes are measured, not assumed** — a Fabrication Injection Benchmark harness mechanizes 17 failure classes as deterministic forged PRs, routed through an ungated agent, a schema-only reviewer, and the full gate, with published rubrics and raw logs.

Autonomy is a dial with a fence (observe → suggest → admit-gated → autonomous), pilot-validated with a sub-second watchdog. The underlying thesis — *throughput is cheap; verification is the constraint* — is formalized with per-term estimators in [docs/THESIS.md](docs/THESIS.md). Research use only — not financial advice.

## Cases

| # | Case | One line |
|---|---|---|
| 1 | Top-300 baseline | the reference full run behind the status card |
| 2 | Smallcap residual attack | one command, full panel, a forged factor clears the bar |
| 3 | Forge turnaround | a measured gap turned into sandbox-generated candidates |

Archive with dates, fingerprints, and reproduce commands: [docs/CASES.md](docs/CASES.md).

## How it compares

| Capability | TradingAgents | ai-hedge-fund | RD-Agent | FinRL | **Quant Super Agent** |
|---|---|---|---|---|---|
| Multi-role agents with mechanical duties | ✔ debate | ✔ personas | ✔ loop | — | ✔ roles veto on *measured* instability |
| Adversarial review before admission | ✔ | — | — | n/a | ✔ claimed vetoes must recompute |
| Claim settlement + calibration curve | — | — | — | backtests only | ✔ settle → calibrate → tighten-only |
| Pre-registered research loop | — | — | ✔ | — | ✔ deflation-floored, one-shot OOS |
| Claim-level CI gate | — | — | partial | — | ✔ sandbox code recomputation |
| Multiple-testing control | — | — | — | — | ✔ Bonferroni floor at family N |
| Fabrication benchmark | — | — | — | — | ✔ FIB harness, public rubrics + logs |
| Cross-session memory + order lifecycle | — | — | — | — | ✔ hash-chained blackboard, recall on re-run |
| Conversational increments | — | — | — | — | ✔ zero-rescore follow-ups |

Related work we admire and borrow from: [TradingAgents](https://github.com/TauricResearch/TradingAgents) (roles, debate, settlement memory), [ai-hedge-fund](https://github.com/virattt/ai-hedge-fund) (independent judgments → aggregation), [RD-Agent](https://github.com/microsoft/RD-Agent) (factor R&D iteration), [FinRL](https://github.com/AI4Finance-Foundation/FinRL) (environment rigor). The harness patterns come from DeepSeek's MIT-licensed dsh-superagent research prototype — see [Acknowledgments](#acknowledgments).

## Get started

Python ≥ 3.10, no third-party runtime deps, no keys, no network. Three steps, each naming its artifacts and its self-verify command:

**Step 1 — see the guardrail** (seconds): the two runs above.

**Step 2 — run the full campaign** (minutes, one command):

```bash
make offense-full   # plan tree, named crew, scored factors, settled orders — or an honest zero
make tour           # regenerate every demo-quoted number from artifacts; drift alarms
```

**Step 3 — bring your own data**:

```bash
python -m qsa.ingest myprices.csv mydata/   # CSV -> legal, fingerprinted snapshot (local-first)
```

<details>
<summary><b>More demos</b> — every script is a deterministic regression contract, run by the CI matrix on Python 3.10–3.13</summary>

```bash
python examples/run_mining.py        # the deflation floor rejects retested cousins, mechanically
python examples/run_ablation.py      # roles x debate-rounds ablation on planted vs noise worlds
python examples/run_calibration.py   # settlement ledger + calibration curve
python examples/run_fib.py           # the full fabrication-injection benchmark
python examples/run_discovery.py     # discovery@B: breadth decays as trials accumulate
python examples/run_frontier.py      # alpha-frontier: power vs false-positive rate
python examples/run_orders.py        # the zoo as an order book; second run = recall, not recompute
python -m qsa.planner "smallcap overnight reversal, forge the missing factor"   # intent -> plan tree
make followup                        # "raise the bar": rows reused, zero rescored
python -m unittest discover -s tests -v                                          # the whole contract
```
</details>

## How it works

```mermaid
flowchart LR
    A[Research order<br/>+ iteration budget] --> B[LLM proposes hypothesis<br/>admission bar pre-committed]
    B --> C[(Experiment registry<br/>append-only, hypothesis<br/>before experiment)]
    C --> D[Sandboxed factor code<br/>AST whitelist · sees closes ≤ t only]
    D --> E{Mechanical verdict<br/>Bonferroni floor at family N}
    E -- fail --> F[Attribution<br/>threshold · instability · deflation · oos]
    E -- in-sample pass --> G{One-shot OOS window}
    G -- fail --> F
    G -- pass --> V{Roles + bull/bear review<br/>risk: half-split stability veto<br/>debate: checkable claims verified}
    V -- veto --> F
    V -- admitted --> H[Verify gate as forge CI<br/>recomputes factor_code + vetoes]
    F -- next hypothesis<br/>budget-bounded --> B
    H --> I[PR + merge under<br/>branch protection]
```

Three planes carry the loop: the **evidence plane** (H/E cards + the verify gate — [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)), the **settlement plane** (claimed vs realized, calibration, tighten-only reflection — [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)), and the **budget estimators** (every term of the thesis equation, measured — [docs/THESIS.md](docs/THESIS.md)).

## Evidence & documentation

Numbers live outside the README, machine-regenerated per round: [EVIDENCE.md](docs/EVIDENCE.md) (acceptance tables, verdicts, reproduce commands) · [NEWS.md](docs/NEWS.md) (per-round log) · [CASES.md](docs/CASES.md) · [STATUS.md](docs/STATUS.md) · [TOUR_NUMBERS.json](docs/TOUR_NUMBERS.json).

- [Storefront policy](docs/README_POLICY.md) — where numbers live, what the README may say
- [Architecture](docs/ARCHITECTURE.md) — components, order lifecycle, gate internals, autonomy supervisor
- [Thesis](docs/THESIS.md) — the transfer theory: budget equation, propositions, estimator protocol
- [Fabrication Injection Benchmark](docs/BENCHMARK.md) · [FIB rubrics](docs/RUBRICS.md)
- [Factor library](docs/FACTOR_LIBRARY.md) — cited factors, residual objective, honest-zero policy
- [v1.0 scenarios](docs/V1_SCENARIOS.md) · [Roadmap](docs/ROADMAP.md) · dev status: [README.dev.md](README.dev.md) · self-playing demo: [docs/demo_video.html](docs/demo_video.html)

Everything claimed is reproducible from this repo: a fully offline, deterministic test suite (live count: the tests badge) and a CI matrix across Python 3.10–3.13 that runs the acceptance demos as regression contracts.

## Roadmap

- **Shipped** — nine capability planes: evidence gate · research loop · roles + debate · settlement + calibration · FIB harness · budget estimators · order book · offense layer · conversation plane
- **Next** — run the published FIB scenarios against third-party agent frameworks; portfolio claims (P cards, walk-forward folds, real-data settlement)
- **Later** — the three classic scenarios end to end (report replication · view verification · regime summarization); scenario A already ships as `python examples/run_replication.py`

Full version history: [docs/ROADMAP.md](docs/ROADMAP.md); per-round log: [docs/NEWS.md](docs/NEWS.md).

## Acknowledgments

- The order-lifecycle harness patterns (orchestrator/worker, worktree isolation, panel API) are adapted from [dsh-superagent](https://github.com/deepseek-ai/dsh-superagent-prototype) (MIT), a research prototype by the DeepSeek Harness team (harness: [deepseek-harness](https://github.com/deepseek-ai/deepseek-harness)). Quant Super Agent is an independent project and is not affiliated with or endorsed by DeepSeek.
- Role/debate/settlement ideas informed by TradingAgents (Xiao et al., arXiv:2412.20138); factor-iteration framing by RD-Agent; portfolio realism by ai-hedge-fund and FinRL.

## Citation

```bibtex
@misc{quantsuperagent2026,
  title  = {Quant Super Agent: A Verifiable Agentic Quant Research Factory},
  author = {Quant Super Agent Contributors},
  year   = {2026},
  note   = {Evidence plane, gated research loop, roles, debate, settlement, calibration, FIB harness, budget estimators, order book, offense layer, conversation plane},
  url    = {https://github.com/0x1512/quant-super-agent}
}
```

## License & disclaimer

MIT — see [LICENSE](LICENSE). This is research software. Nothing here is financial advice, and nothing here should trade real money. All pilot results were obtained in emulation environments.
