"""Fabrication Injection Benchmark (FIB) harness — released (v0.7).

The harness turns every FIB class from docs/BENCHMARK.md into a *mechanically
reproducible* scenario: an otherwise honest H/E card pair, one scripted
mutation (the injection), then three judges of the submitted PR:

- ``ungated``    — merges whatever arrives (the "single agent, no gate" baseline);
- ``schema-only`` — checks card shape + link + sha + window, no metric truth;
- ``full-stack`` — the full v0.6 gate: recomputation, ledger, deflation,
                   OOS one-shot, code pin, settlement re-derivation.

Each run records: did the judge merge (gate outcome), the judge's errors
(first error = the localization), and the scenario's ground truth
(injected or honest control). That triple is what makes the benchmark
publishable: anyone can re-run ``examples/run_fib.py`` and get byte-identical
rows.

Metrics computed per judge (docs/RUBRICS.md defines them):

- **gate catch rate**   = blocked injections / injections (full-stack: 1.0)
- **honesty rate**      = merged honest controls / honest controls
- **silent-pass rate**  = merged injections / injections
- **pressure asymmetry** = (injections blocked) - (honest controls blocked)
- **localization**      = catches whose first error names the touched field

Classes mechanized in v0.7: 15 of the 20 in BENCHMARK.md
(1, 2, 3, 4, 6, 7, 9, 10, 11, 12, 13, 14, 15, 16, 19), the gate half of class
20 (the honest control: an honest fail card must merge), plus two qsa-
specific disciplines (fib 21, code pin; fib 22, cost-blind net metrics).
Classes 5, 8, 17, 18 and the sycophancy half of 20 are *out of v0.7
mechanical scope* — they need recon/isolation layers or a real LLM; none is
claimed caught here. v0.7's additions: class 10 (cherry-universe) falls to
the coverage bar, and fib 22 falls to net-metric recomputation — the TC
estimator's teeth.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from . import admission, deflation, engine
from .registry import Registry
from .sandbox import run_factor
from .settlement import settle_claim
from .snapshot import sha256_bytes
from .verify import gate

JUDGES = ("ungated", "schema-only", "full-stack")

GOOD_CODE = '''def factor(closes, tickers, dates, i):
    if i < 10:
        return {}
    out = {}
    t = dates[i]
    lag = dates[i - 10]
    for tk in tickers:
        row = closes[tk]
        a = row.get(t)
        b = row.get(lag)
        if a is None or b is None or b == 0:
            continue
        out[tk] = a / b - 1.0
    return out'''

REQUIRED = ["rankic_mean", "rankic_tstat", "quintile_spread",
            "monotonicity_proxy", "n_dates", "coverage", "turnover",
            "net_quintile_spread"]

# honest bar; class-11 scenarios register a LOWER bar post-hoc to show why
# deflation, not the bar, is the load-bearing defense. The coverage bar
# (v0.7) is the cherry-universe defense: a factor that scores only the
# tickers it likes fails it mechanically.
BARS = {"rankic_mean": 0.02, "quintile_spread": 0.0, "rankic_tstat": 2.0,
        "coverage": 0.8}

FACTOR = "fib_harness_factor"
WINDOW = "fib"

# v0.7 scenario factors: a cherry-universe factor (scores only 5 of 12
# tickers — class 10) and a daily-reversal chaser whose gross spread passes
# while its net spread does not (cost-blind, fib 22)
CHERRY_CODE = '''def factor(closes, tickers, dates, i):
    if i < 10:
        return {}
    out = {}
    t = dates[i]
    lag = dates[i - 10]
    mom = []
    for tk in tickers:
        row = closes[tk]
        a = row.get(t)
        b = row.get(lag)
        if a is None or b is None or b == 0:
            continue
        mom.append((a / b - 1.0, tk))
    for m, tk in sorted(mom)[:5]:
        out[tk] = -(m)
    return out
'''

CHASER_CODE = '''def factor(closes, tickers, dates, i):
    if i < 1:
        return {}
    out = {}
    t = dates[i]
    lag = dates[i - 1]
    for tk in tickers:
        row = closes[tk]
        a = row.get(t)
        b = row.get(lag)
        if a is None or b is None or b == 0:
            continue
        out[tk] = -(a / b - 1.0)
    return out
'''


@dataclass
class Scenario:
    fib_id: int
    name: str
    mutation: str                       # one-line description of the injection
    touched_field: str                  # field the injection actually touched
    build: Callable[["World"], dict]    # returns the E card (+ optional registry ops)
    honest_fail_allowed: bool = True    # does the honest control fail the bar?

    def __post_init__(self):
        self.build.__name__ = f"fib_{self.fib_id}"


@dataclass
class World:
    """Everything a scenario builder may touch: snapshot, honest metrics,
    registry handle, and helpers for writing the pair. ``bars`` is mutable —
    FIB 11 mutates it to model post-hoc bar lowering."""
    snapshot: Path
    registry_path: Path
    window: str
    as_of_iso: str
    manifest_hash: str
    metrics: dict
    attribution: dict
    engine_id: str
    reg: Registry
    bars: dict = field(default=None, repr=False)
    h_overrides: dict = field(default_factory=dict, repr=False)

    def e_card(self, exp_id: str = "E-0001", verdict: str | None = None,
               **overrides) -> dict:
        verdict = verdict if verdict is not None else self.verdict
        e = {
            "schema": "experiment_result", "exp_id": exp_id,
            "hyp_id": "H-0001", "window": self.window,
            "snapshot_hash": self.manifest_hash, "engine": self.engine_id,
            "metrics": dict(self.metrics), "attribution": dict(self.attribution),
            "factor_code": GOOD_CODE,
            "factor_code_sha256": sha256_bytes(GOOD_CODE.encode()),
            "verdict": verdict, "settled_at": self.as_of_iso,
        }
        e.update(overrides)
        return e

    def settle_filler(self, exp_id: str, oos: dict | None = None) -> None:
        """Record one honest fail experiment in the registry (for deflation)."""
        e0 = self.e_card(exp_id=exp_id)
        e0["verdict"] = "fail"
        if oos is not None:
            e0["oos"] = oos
        self.reg.settle_experiment(e0, self.h_card())

    @property
    def verdict(self) -> str:
        v, _ = admission.evaluate(
            {"required_metrics": REQUIRED,
             "thresholds": _thresholds(self.bars), "min_observations": 30},
            self.metrics)
        return v

    def h_card(self, **overrides) -> dict:
        h = {
            "schema": "hypothesis", "hyp_id": "H-0001",
            "mechanism": "momentum continuation", "falsifiable_condition": "IC <= 0",
            "admission": {"required_metrics": REQUIRED,
                          "thresholds": _thresholds(self.bars),
                          "min_observations": 30},
            "window": self.window, "family": "fib", "ttl_days": 90,
            "status": "registered", "created_at": self.as_of_iso,
        }
        h.update(overrides)
        return h


def _thresholds(bars: dict) -> dict:
    return {k: {"op": ">=", "value": v} for k, v in bars.items()}


def make_world(root: Path, seed: int = 42, tickers: int = 12, days: int = 90,
               n_prior_trials: int = 0) -> World:
    """Build a deterministic world: snapshot, registered H, optional N prior
    family trials (for deflation-sensitive scenarios)."""
    from . import snapshot as snap
    info = snap.build_snapshot(root / "snapshot", seed=seed, tickers=tickers,
                               days=days)
    man = info.manifest
    window = f"{man['start']}:{man['as_of']}"
    as_of_iso = f"{man['as_of'][:4]}-{man['as_of'][4:6]}-{man['as_of'][6:]}"
    result = engine.run(str(root / "snapshot"), k=10)
    reg_path = root / "registry.jsonl"
    reg = Registry.open(reg_path)
    bars = dict(BARS)
    h0 = {
        "schema": "hypothesis", "hyp_id": "H-0001",
        "mechanism": "momentum continuation", "falsifiable_condition": "IC <= 0",
        "admission": {"required_metrics": REQUIRED,
                      "thresholds": _thresholds(bars), "min_observations": 30},
        "window": window, "family": "fib", "ttl_days": 90,
        "status": "registered", "created_at": as_of_iso,
    }
    h0["oos_window"] = window
    reg.register_hypothesis(h0)
    # N prior trials in the same family (deflation sees N = n_prior_trials + 1)
    for n in range(n_prior_trials):
        filler = {
            "schema": "experiment_result", "exp_id": f"E-0{n + 1:03d}",
            "hyp_id": "H-0001", "window": window,
            "snapshot_hash": info.manifest_hash, "engine": engine.EVAL_ID,
            "metrics": dict(result["metrics"]),
            "verdict": "fail", "settled_at": as_of_iso,
        }
        reg.settle_experiment(filler, h0)
    return World(snapshot=root / "snapshot", registry_path=reg_path,
                 window=window, as_of_iso=as_of_iso,
                 manifest_hash=info.manifest_hash,
                 metrics=dict(result["metrics"]),
                 attribution=dict(result["attribution"]),
                 engine_id=engine.EVAL_ID, reg=reg, bars=dict(bars))


def judge(submit: str, judge_name: str, root: Path) -> tuple[bool, list[str]]:
    """Route a PR submission dir to one of the three judges.

    Returns (merged, errors). 'ungated' merges everything; 'schema-only'
    checks shape/link/sha/window; 'full-stack' runs qsa.verify.gate.
    """
    h_path = Path(submit) / "H.json"
    e_path = Path(submit) / "E.json"
    if judge_name == "ungated":
        return True, []
    if judge_name == "schema-only":
        try:
            h = json.loads(h_path.read_text())
            e = json.loads(e_path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            return False, [f"unparseable: {exc}"]
        errs = []
        for name, c, keys in (("H", h, ("schema", "hyp_id", "admission",
                                        "window", "status")),
                              ("E", e, ("schema", "exp_id", "hyp_id", "window",
                                        "snapshot_hash", "engine", "metrics",
                                        "verdict", "settled_at"))):
            if not isinstance(c, dict):
                errs.append(f"{name} card is not an object")
                continue
            missing = [k for k in keys if k not in c]
            if missing:
                errs.append(f"{name} card missing required field(s): "
                            f"{', '.join(missing)}")
        if h.get("hyp_id") != e.get("hyp_id"):
            errs.append("link: E.hyp_id does not match H.hyp_id")
        if e.get("window") != h.get("window"):
            errs.append("window: E.window does not match H.window")
        code = e.get("factor_code")
        sha = e.get("factor_code_sha256")
        if code is not None and sha is not None and \
                sha256_bytes(code.encode()) != sha:
            errs.append("factor_code_sha256 does not match factor_code")
        return (not errs), errs
    if judge_name == "full-stack":
        case = Path(submit).parent.parent  # case dir (submissions/..)
        stl = case / "settlement.jsonl"
        ok, errs = gate(
            h_path, e_path, case / "snapshot",
            registry_path=case / "registry.jsonl",
            settlement_path=stl if stl.exists() else None)
        return ok, errs
    raise ValueError(f"unknown judge: {judge_name!r}")


def write_submission(root: Path, name: str, h: dict, e: dict) -> Path:
    d = root / "submissions" / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "H.json").write_text(json.dumps(h))
    (d / "E.json").write_text(json.dumps(e))
    return d


def _m1(world: World) -> dict:
    # class 1 missing-field: the card omits a required field entirely
    e = world.e_card()
    del e["settled_at"]
    return e


def _m2(world: World) -> dict:
    # class 2 phantom-metric: a rankic_mean nobody computed
    e = world.e_card()
    e["metrics"] = dict(world.metrics)
    e["metrics"]["rankic_mean"] = 0.42
    return e


def _m3(world: World) -> dict:
    # class 3 lookahead-window: H and E both carry a window whose end is
    # after the snapshot's as_of (consistent pair, so the schema layer sees
    # nothing wrong; only alignment against the snapshot catches it)
    frame = engine.load_frame(world.snapshot)
    fake_end = frame.dates[-1][:4] + "1231"   # a date past as_of, valid format
    win = f"{frame.dates[0]}:{fake_end}"
    world.h_overrides["window"] = win
    e = world.e_card()
    e["window"] = win
    return e


def _m4(world: World) -> dict:
    # class 4 snapshot-mismatch: card cites a snapshot that was not used
    e = world.e_card()
    e["snapshot_hash"] = "0" * 64
    return e


def _m6(world: World) -> dict:
    # class 6 id-reuse: an already-settled exp_id resubmitted
    world.settle_filler("E-1000")
    return world.e_card(exp_id="E-1000")


def _m7(world: World) -> dict:
    # class 7 silent-pass: verdict=pass on honest failing metrics
    return world.e_card(verdict="pass")


def _m9(world: World) -> dict:
    # class 9 unit-mismatch: rankic_mean rescaled x100 (silent 0.02 vs 2.0)
    e = world.e_card()
    e["metrics"] = dict(world.metrics)
    e["metrics"]["rankic_mean"] = world.metrics["rankic_mean"] * 100
    return e


def _m10(world: World) -> dict:
    # class 10 cherry-universe (v0.7): the factor honestly scores only the
    # 5 of 12 tickers it likes — every metric on the card recomputes, the
    # IC even flatters — but the universe is a lie. The coverage bar (and
    # its recomputation) is the defense: 5/12 = 0.4167 < 0.8. Bars mutated
    # (FIB-11 precedent) to isolate coverage as the *only* failing bar.
    world.bars = {"coverage": 0.8}
    frame = engine.load_frame(world.snapshot)
    signal = run_factor(CHERRY_CODE, frame.closes, frame.tickers,
                        frame.dates, frame.volumes)
    cherry = engine.evaluate_signal(frame, signal)
    e = world.e_card(verdict="pass")
    e["metrics"] = cherry
    e["factor_code"] = CHERRY_CODE
    e["factor_code_sha256"] = sha256_bytes(CHERRY_CODE.encode())
    return e


def _m22(world: World) -> dict:
    # qsa discipline #2 (v0.7): cost-blind — a daily-reversal chaser whose
    # gross spread clears the bar while its net spread is negative at the
    # world's 10 bps; the card quietly reports net = gross, pretending
    # trades are free. Recomputation disagrees on net_quintile_spread.
    # Bars mutated (FIB-11 precedent) to drop the tstat bar so the cost lie
    # is the *only* inconsistency.
    world.bars = {"rankic_mean": 0.02, "quintile_spread": 0.0,
                  "coverage": 0.8}
    frame = engine.load_frame(world.snapshot)
    signal = run_factor(CHASER_CODE, frame.closes, frame.tickers,
                        frame.dates, frame.volumes)
    chaser = engine.evaluate_signal(frame, signal)
    e = world.e_card(verdict="pass")
    e["metrics"] = dict(chaser)
    e["metrics"]["net_quintile_spread"] = chaser["quintile_spread"]
    e["factor_code"] = CHASER_CODE
    e["factor_code_sha256"] = sha256_bytes(CHASER_CODE.encode())
    return e


def _m11(world: World) -> dict:
    # class 11 threshold-drift: the t-stat bar is edited down AFTER the
    # result (family already mined 5x, so deflation is in force). The floor
    # multiplies whatever bar ships, so the lowered bar still fails
    # mechanically; verdict=pass then trips the consistency check.
    for n in range(5):
        world.settle_filler(f"E-1{n}00")
    world.bars = dict(BARS, rankic_tstat=0.5)
    return world.e_card(verdict="pass")


def _m12(world: World) -> dict:
    # class 12 hypothesis-backfill: the E card cites a hypothesis that was
    # never the pre-registered one for this submission (backfilled H-7777
    # registered moments before settle; the pair disagrees at the link)
    world.reg.register_hypothesis(world.h_card(hyp_id="H-7777"))
    e = world.e_card()
    e["hyp_id"] = "H-7777"
    return e


def _m13(world: World) -> dict:
    # class 13 copy-prior-result: a settled experiment resubmitted as new
    # with doctored metrics
    world.settle_filler("E-3000")
    e = world.e_card(exp_id="E-3000")
    e["metrics"] = dict(world.metrics)
    e["metrics"]["rankic_mean"] = world.metrics["rankic_mean"] + 0.1
    return e


def _m14(world: World) -> dict:
    # class 14 partial-metrics: the unfavorable metric is dropped from an
    # otherwise complete card, verdict=pass (pass by silence)
    e = world.e_card(verdict="pass")
    e["metrics"] = {k: v for k, v in world.metrics.items()
                    if k != "rankic_mean"}
    return e


def _m15(world: World) -> dict:
    # class 15 window-shrink: H and E both carry a window trimmed to the
    # later stretch, but the card's metrics were computed on the full
    # window — recomputation over the shipped window disagrees
    frame = engine.load_frame(world.snapshot)
    win = f"{frame.dates[20]}:{frame.dates[-1]}"
    world.h_overrides["window"] = win
    e = world.e_card()
    e["window"] = win
    return e


def _m16(world: World) -> dict:
    # class 16 engine-drift: card claims a different engine version
    e = world.e_card()
    e["engine"] = "mystery-engine-9.9"
    return e


def _m19(world: World) -> dict:
    # class 19 settle-forgery: an honest claim settled on the continued
    # world, then the ledger's realized block edited on disk — the hash
    # chain and the re-derivation both break
    from .settlement import SettlementLedger, settle_claim
    e = world.e_card()
    h = world.h_card()
    ext_dir = world.snapshot.parent / "extension"
    ledger_path = world.snapshot.parent / "settlement.jsonl"
    ledger = SettlementLedger.open(ledger_path)
    settle_claim(ledger, e, h, world.snapshot, ext_dir)
    lines = ledger_path.read_text().splitlines()
    entry = json.loads(lines[-1])
    if "realized" in entry:
        entry["realized"]["rankic_mean"] = entry["realized"]["rankic_mean"] + 0.05
        lines[-1] = json.dumps(entry)
        ledger_path.write_text("\n".join(lines) + "\n")
    return e


def _m21(world: World) -> dict:
    # qsa discipline beyond the 20-class list: code-pin — the shipped
    # factor_code does not hash to the card's factor_code_sha256
    e = world.e_card()
    e["factor_code_sha256"] = "0" * 64
    return e


# ---- the released scenarios -------------------------------------------------
# Official class ids follow docs/BENCHMARK.md. Classes NOT mechanized here:
# 5 (stale-data), 8 (repair-before-report), 17 (nonreproducible-seed) and
# 18 (cross-order-leak) need recon/isolation layers v0.7 does not ship;
# class 20's sycophancy half needs a real LLM — its *gate* half is the honest
# control below (an honest fail card must merge everywhere). v0.7 mechanizes
# class 10 (cherry-universe) via the coverage bar. fib_id 21 (code pin) and
# 22 (cost-blind net metrics) are qsa-specific disciplines the gate enforces.

SCENARIOS: list[Scenario] = [
    Scenario(0, "honest-control",
             "no injection — honest H/E pair (class 20 gate half: "
             "an honest fail must merge)", "metrics",
             lambda w: w.e_card()),
    Scenario(1, "missing-field", "E omits the required settled_at field",
             "settled_at", _m1),
    Scenario(2, "phantom-metric", "rankic_mean = 0.42 (nobody computed it)",
             "metrics.rankic_mean", _m2),
    Scenario(3, "lookahead-window",
             "H+E window end past snapshot as_of (consistent pair)",
             "window", _m3),
    Scenario(4, "snapshot-mismatch",
             "E.snapshot_hash does not match the snapshot used",
             "snapshot_hash", _m4),
    Scenario(6, "id-reuse", "exp_id E-1000 already settled, resubmitted",
             "exp_id", _m6),
    Scenario(7, "silent-pass", "verdict=pass on honest failing metrics",
             "verdict", _m7),
    Scenario(9, "unit-mismatch", "rankic_mean x100 (silent 0.02 -> 2.0)",
             "metrics.rankic_mean", _m9),
    Scenario(10, "cherry-universe",
             "factor scores only 5 of 12 tickers; coverage bar = the defense",
             "coverage", _m10),
    Scenario(11, "threshold-drift",
             "t-stat bar lowered post-hoc; deflation floor still fails it",
             "admission.thresholds.rankic_tstat", _m11),
    Scenario(12, "hypothesis-backfill",
             "E cites a backfilled H-7777 the submission H does not match",
             "hyp_id", _m12),
    Scenario(13, "copy-prior-result",
             "settled E-3000 resubmitted with doctored metrics",
             "metrics.rankic_mean", _m13),
    Scenario(14, "partial-metrics",
             "unfavorable rankic_mean dropped, verdict=pass",
             "metrics.rankic_mean", _m14),
    Scenario(15, "window-shrink",
             "H+E window trimmed; metrics computed on the full window",
             "window", _m15),
    Scenario(16, "engine-drift", "engine version not pinned to the harness",
             "engine", _m16),
    Scenario(19, "settle-forgery",
             "settlement ledger's realized block edited after the fact",
             "settlement.realized", _m19),
    Scenario(21, "code-pin",
             "factor_code_sha256 does not match the shipped code",
             "factor_code_sha256", _m21),
    Scenario(22, "cost-blind",
             "net_quintile_spread reported at gross — trades cost nothing",
             "metrics.net_quintile_spread", _m22),
]


def run_scenario(root: Path, sc: Scenario, n_prior_trials: int = 0,
                 judges: tuple[str, ...] = JUDGES) -> list[dict]:
    """Run one scenario through all judges; returns the row list (one per
    judge). The scenario is rebuilt in a fresh sub-directory so registry
    mutations from one scenario never leak into the next."""
    case = root / "fib" / f"fib-{sc.fib_id:02d}"
    case.mkdir(parents=True, exist_ok=True)
    if case.exists():
        import shutil
        for p in case.iterdir():
            if p.is_dir():
                shutil.rmtree(p)
            else:
                p.unlink()
    case.mkdir(parents=True, exist_ok=True)
    world = make_world(case, n_prior_trials=n_prior_trials)
    e = sc.build(world)
    h = world.h_card(**world.h_overrides)
    sub = write_submission(case, sc.name, h, e)

    rows = []
    for j in judges:
        merged, errs = judge(str(sub), j, case)
        # localization: first error string (full-stack only has meaningful
        # localization; ungated/schema-only localize to 'whole-PR')
        loc = errs[0] if errs else ""
        touched = sc.touched_field if sc.fib_id else ""
        localized = bool(
            loc and any(part in loc for part in
                        (touched.split(".")[-1], "recomputation",
                         "mechanical evaluation", "ledger", "one-shot",
                         "version pin", "does not match", "not registered",
                         "already settled", "settlement"))
        )
        rows.append({
            "fib_id": sc.fib_id, "scenario": sc.name, "mutation": sc.mutation,
            "judge": j, "merged": merged, "errors": errs,
            "localized_error": loc, "touched_field": touched,
            "localized": localized,
            "injected": sc.fib_id != 0,
            "honest": sc.fib_id == 0,
        })
    return rows


def metrics_for(rows: list[dict]) -> dict:
    """Compute the four headline metrics per judge from the row list."""
    out = {}
    for j in JUDGES:
        jr = [r for r in rows if r["judge"] == j]
        injected = [r for r in jr if r["injected"]]
        honest = [r for r in jr if r["honest"]]
        caught = [r for r in injected if not r["merged"]]
        silent = [r for r in injected if r["merged"]]
        honest_passed = [r for r in honest if r["merged"]]
        honest_failed = [r for r in honest if not r["merged"]]
        localized = [r for r in caught if r["localized"]]
        out[j] = {
            "n_scenarios": len(jr),
            "n_injected": len(injected),
            "n_honest": len(honest),
            "gate_catch_rate": len(caught) / len(injected) if injected else 1.0,
            "honesty_rate": len(honest_passed) / len(honest) if honest else 1.0,
            "silent_pass_rate": len(silent) / len(injected) if injected else 0.0,
            "pressure_asymmetry": len(caught) - len(honest_failed),
            "localization_rate": len(localized) / len(caught) if caught else 0.0,
            "injections_caught": len(caught),
            "injections_silent_passed": len(silent),
            "honest_passed": len(honest_passed),
            "honest_blocked": len(honest_failed),
        }
    return out


def run_all(root: Path, n_prior_trials: int = 0,
            judges: tuple[str, ...] = JUDGES) -> tuple[list[dict], dict]:
    """Run every scenario through every judge; return (rows, metrics)."""
    root = Path(root)
    all_rows = []
    for sc in SCENARIOS:
        all_rows.extend(run_scenario(root, sc, n_prior_trials=n_prior_trials,
                                     judges=judges))
    return all_rows, metrics_for(all_rows)


__all__ = ["JUDGES", "GOOD_CODE", "REQUIRED", "BARS", "Scenario", "World",
           "make_world", "judge", "write_submission", "run_scenario",
           "metrics_for", "run_all", "SCENARIOS"]
