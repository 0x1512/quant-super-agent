"""Settlement ledger — claimed vs realized, simulator-authoritative (v0.5).

An admitted factor is not "done": at a horizon the claim is settled against
realized performance on data the admission never touched. The headline metric
is not return; it is the **calibration curve** (claimed vs realized) plus a
zero-fabrication record.

Mechanics, all deterministic:

* **the simulator is authoritative** — for a synthetic world the extension
  past ``as_of`` is rebuilt from the same seed (byte-prefix asserted in
  ``snapshot.extend_world``), the factor is re-executed in the truncated-view
  sandbox, and the realized metrics are computed by the same engine that
  gated the admission. Nothing the card claims is trusted: not the claimed
  metric, not the code hash, not the outcome;
* **the ledger is a hash chain** — every settlement entry carries
  ``prev_hash``/``entry_hash`` over canonical JSON; editing, deleting or
  reordering any line breaks the chain (FIB class 19). A fabricated entry
  that *rechains* honestly still fails, because its realized metrics must
  recompute from the world spec + factor code it carries;
* **the reflection loop only tightens** — a family whose settled claims fell
  short too often gets its admission bar multiplied (×1.25) for later orders.
  Calibration can raise the bar; it never lowers it. The adjustment is
  recomputed from the ledger by the gate, so a card cannot claim a rosier
  history than it has.

Real (ingested) data has no simulator: those worlds settle when new data
arrives — never by invention.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from . import engine
from .sandbox import SandboxError, run_factor
from .snapshot import (build_snapshot, canonical_json, extend_world,
                       fingerprint, sha256_bytes, sha256_file)

GENESIS = sha256_bytes(b"qsa-settlement-genesis")
EXTENSION_DAYS = 90
TIGHTEN_MULTIPLIER = 1.25
MIN_SETTLED_HISTORY = 5
SHORTFALL_RATIO_TRIGGER = 0.5

CURVE_BINS = (0.0, 0.02, 0.05, 0.08, 0.11, 0.15, 0.20, 1.0)
# the settlement horizon matches the claim's own window length (90 days):
# symmetric by principle, and measured — on horizons this long a pure-noise
# world's realized rank IC centers on 0 (mean +0.016, sd 0.034 over 12 seeds)
# while per-claim verdicts stay noisy (a 20-day horizon measured sd 0.086:
# luck decides, not the claim). The curve, not the single verdict, is the
# instrument.


class SettlementError(ValueError):
    """Every refusal; message is report-safe."""


# -- ledger ------------------------------------------------------------------

class SettlementLedger:
    """Append-only settlement ledger with a per-entry hash chain."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.entries: list[dict[str, Any]] = []
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    self.entries.append(json.loads(line))

    @classmethod
    def open(cls, path: Path) -> "SettlementLedger":
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch(exist_ok=True)
        return cls(path)

    def next_settle_id(self) -> str:
        return f"S-{len(self.entries) + 1:04d}"

    def record(self, core: dict[str, Any]) -> dict[str, Any]:
        settle_id = core.get("settle_id")
        if not settle_id:
            raise SettlementError("settlement entry has no settle_id")
        if any(en.get("settle_id") == settle_id for en in self.entries):
            raise SettlementError(f"settle_id {settle_id!r} already recorded "
                                  f"(IDs are unique forever)")
        exp_id = core.get("exp_id")
        base_hash = core.get("base_snapshot_hash")
        if any(en.get("exp_id") == exp_id
               and en.get("base_snapshot_hash") == base_hash
               for en in self.entries):
            raise SettlementError(
                f"exp_id {exp_id!r} on snapshot "
                f"{str(base_hash)[:12]}… already settled — a claim settles "
                f"exactly once")
        entry = dict(core)
        entry["seq"] = len(self.entries) + 1
        entry["prev_hash"] = (self.entries[-1]["entry_hash"]
                              if self.entries else GENESIS)
        entry["entry_hash"] = _entry_hash(entry)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(canonical_json(entry).decode("utf-8") + "\n")
        self.entries.append(entry)
        return entry

    def settled_for(self, family: str) -> list[dict[str, Any]]:
        return [en for en in self.entries
                if en.get("family") == family
                and en.get("outcome") in ("held", "fell_short")]


def _entry_hash(entry: dict[str, Any]) -> str:
    core = {k: v for k, v in entry.items() if k != "entry_hash"}
    return sha256_bytes(canonical_json(core))


# -- settlement --------------------------------------------------------------

def settle_claim(ledger: SettlementLedger, e: dict[str, Any], h: dict[str, Any],
                 base_dir: Path, ext_dir: Path,
                 *, extension_days: int = EXTENSION_DAYS) -> dict[str, Any]:
    """Settle one admitted claim on a horizon the admission never touched.

    ``e``/``h`` are the merged E/H cards; realized metrics are recomputed
    from ``e['factor_code']`` over the world extension — never read from the
    card. Returns the recorded ledger entry.
    """
    base = fingerprint(base_dir)
    ext = extend_world(ext_dir, base_dir, extension_days)
    settle_id = ledger.next_settle_id()

    ext_frame = engine.load_frame(ext_dir)
    dates = ext_frame.dates
    base_days = base.manifest["days"]
    horizon = f"{dates[base_days]}:{dates[-1]}"

    claimed_metric = "rankic_mean"
    claimed = (e.get("metrics") or {}).get(claimed_metric)
    th = ((h.get("admission") or {}).get("thresholds")
          or {}).get(claimed_metric) or {}
    bar, op = th.get("value"), th.get("op", ">=")

    try:
        frame = engine.load_frame(ext_dir, horizon)
        signal = run_factor(e["factor_code"], ext_frame.closes,
                            ext_frame.tickers, ext_frame.dates,
                            ext_frame.volumes, ext_frame.opens)
        realized = engine.evaluate_signal(frame, signal)
    except (SandboxError, ValueError) as exc:
        realized = None
        outcome = "unverifiable"
        reason = f"factor does not run on the extension: {str(exc)[:120]}"
    else:
        outcome = _outcome(realized.get(claimed_metric), bar, op)
        reason = (f"realized {claimed_metric}="
                  f"{realized.get(claimed_metric)} vs bar {op} {bar} "
                  f"on {horizon}")

    core: dict[str, Any] = {
        "schema": "settlement",
        "settle_id": settle_id,
        "exp_id": e.get("exp_id"),
        "hyp_id": e.get("hyp_id"),
        "family": h.get("family", "default"),
        "iteration": (e.get("attribution") or {}).get("iteration"),
        "world": {"kind": "synthetic", "seed": base.manifest["seed"],
                  "tickers": base.manifest["tickers"],
                  "days": base.manifest["days"],
                  "start": base.manifest["start"],
                  "plant": base.manifest.get("plant"),
                  "costs": base.manifest.get("costs"),
                  "extension_days": extension_days},
        "base_snapshot_hash": base.manifest_hash,
        "extension_hash": ext.manifest_hash,
        "engine": engine.EVAL_ID,
        "factor_code": e["factor_code"],
        "factor_code_sha256": sha256_bytes(e["factor_code"].encode("utf-8")),
        "claimed": {"metric": claimed_metric, "value": claimed,
                    "window": e.get("window"), "bar": bar, "op": op},
        "outcome": outcome,
        "reason": reason,
        "settled_at": e.get("settled_at"),
    }
    if realized is not None:
        # the full harness metric set, gross and net: TC readouts (turnover,
        # cost drag, net spread) settle beside the IC they modify (v0.7)
        core["realized"] = {"window": horizon, **realized}
    return ledger.record(core)


def settle_real_claim(ledger: SettlementLedger, e: dict[str, Any],
                       h: dict[str, Any], base_dir: Path, ext_dir: Path,
                       fixture_root: Path,
                       *, volume_col: str = "volume",
                       open_col: str = "open") -> dict[str, Any]:
    """Settle a claim on real (ingested) data that has since ARRIVED.

    The synthetic path (settle_claim) rebuilds the extension from a seed;
    real data has no simulator, so the extension must be a snapshot whose
    price rows strictly extend the base snapshot's (asserted row by row —
    the extension is the *same world, later*, never a different one). The
    ledger entry pins every source CSV by sha256 so the audit can rebuild
    the extension from the fixture and recompute the realized metrics.

    ``fixture_root`` is the directory the recorded relative source paths
    resolve against at audit time (the repo fixture directory)."""
    base = fingerprint(base_dir)
    ext = fingerprint(ext_dir)
    _assert_real_extension(base_dir, ext_dir)
    settle_id = ledger.next_settle_id()

    ext_frame = engine.load_frame(ext_dir)
    dates = ext_frame.dates
    base_days = base.manifest["days"]
    horizon = f"{dates[base_days]}:{dates[-1]}"

    claimed_metric = "rankic_mean"
    claimed = (e.get("metrics") or {}).get(claimed_metric)
    th = ((h.get("admission") or {}).get("thresholds")
          or {}).get(claimed_metric) or {}
    bar, op = th.get("value"), th.get("op", ">=")

    try:
        frame = engine.load_frame(ext_dir, horizon)
        signal = run_factor(e["factor_code"], ext_frame.closes,
                            ext_frame.tickers, ext_frame.dates,
                            ext_frame.volumes, ext_frame.opens)
        realized = engine.evaluate_signal(frame, signal)
    except (SandboxError, ValueError) as exc:
        realized = None
        outcome = "unverifiable"
        reason = f"factor does not run on the arrived extension: {str(exc)[:120]}"
    else:
        outcome = _outcome(realized.get(claimed_metric), bar, op)
        reason = (f"realized {claimed_metric}="
                  f"{realized.get(claimed_metric)} vs bar {op} {bar} "
                  f"on {horizon}")

    # pin the fixture sources by content hash for the audit's rebuild
    m = ext.manifest
    spec = {
        "main_csv": "examples/data/ashare_top300_main.csv",
        "tail_csv": "examples/data/ashare_top300_tail.csv",
        "meta_dir": "examples/data/replication_meta",
        "snapshot_id": m.get("snapshot_id", "real-extension"),
        "volume_col": volume_col,
        "open_col": open_col,
    }
    meta_path = fixture_root / spec["meta_dir"]
    spec["has_meta"] = meta_path.is_dir() and bool(
        list(meta_path.glob("*.csv")))
    csvs = [spec["main_csv"], spec["tail_csv"]]
    if spec["has_meta"]:
        csvs += [f"{spec['meta_dir']}/{p.name}" for p in
                 sorted(meta_path.glob("*.csv"))]
    spec["csvs"] = sorted(csvs)
    spec["csv_sha256"] = {rel: sha256_file(fixture_root / rel)
                          for rel in spec["csvs"]}
    core: dict[str, Any] = {
        "schema": "settlement",
        "settle_id": settle_id,
        "exp_id": e.get("exp_id"),
        "hyp_id": e.get("hyp_id"),
        "family": h.get("family", "default"),
        "world": {"kind": "real",
                  "spec": spec,
                  "tickers": m["tickers"],
                  "days": m["days"],
                  "start": m["start"],
                  "base_days": base_days},
        "base_snapshot_hash": base.manifest_hash,
        "extension_hash": ext.manifest_hash,
        "engine": engine.EVAL_ID,
        "factor_code": e["factor_code"],
        "factor_code_sha256": sha256_bytes(e["factor_code"].encode("utf-8")),
        "claimed": {"metric": claimed_metric, "value": claimed,
                    "window": e.get("window"), "bar": bar, "op": op},
        "outcome": outcome,
        "reason": reason,
        "settled_at": e.get("settled_at"),
    }
    if realized is not None:
        core["realized"] = {"window": horizon, **realized}
    return ledger.record(core)


def _assert_real_extension(base_dir: Path, ext_dir: Path) -> None:
    """The real extension must strictly extend the base world's price rows."""
    base_rows = (Path(base_dir) / "daily" / "prices.csv").read_text(
        encoding="utf-8").splitlines()
    ext_rows = (Path(ext_dir) / "daily" / "prices.csv").read_text(
        encoding="utf-8").splitlines()
    if len(ext_rows) <= len(base_rows):
        raise ValueError("real extension does not extend the base snapshot")
    for i in range(1, len(base_rows)):
        if ext_rows[i] != base_rows[i]:
            raise ValueError(
                f"real extension row {i} diverges from the base snapshot at "
                f"{base_rows[i].split(',')[0]} — refusing to settle on a "
                f"foreign world")


def _rebuild_real_extension(spec: dict[str, Any], fixture_root: Path
                            ) -> Path:
    """Rebuild the extension snapshot from the pinned fixture CSVs.

    Raises ValueError if any pinned file's content changed — the audit
    never rebuilds from drifted data."""
    import tempfile
    from .ingest import ingest_csv
    root = Path(fixture_root)
    for rel, want in (spec.get("csv_sha256") or {}).items():
        f = root / rel
        if not f.exists() or sha256_file(f) != want:
            raise ValueError(f"fixture {rel} changed or missing — the "
                             f"pinned settlement source drifted")
    main_csv = root / spec["main_csv"]
    tail_csv = root / spec["tail_csv"]
    td = Path(tempfile.mkdtemp(prefix="qsa-real-rebuild-"))
    merged = td / "merged_full.csv"
    merged.write_text("\n".join(
        main_csv.read_text(encoding="utf-8").splitlines()
        + tail_csv.read_text(encoding="utf-8").splitlines()[1:]) + "\n",
        encoding="utf-8")
    out = td / "ext"
    meta_arg = (root / spec["meta_dir"]) if spec.get("has_meta") else None
    ingest_csv(merged, out, volume_col=spec.get("volume_col", "volume"),
               open_col=spec.get("open_col", "open"),
               snapshot_id=spec.get("snapshot_id", "real-extension"),
               meta_dir=meta_arg)
    return out


def _audit_real_entry(en: dict[str, Any], fixture_root: Path | None
                      ) -> list[str]:
    """Audit one real-world settlement entry: rebuild from the pinned
    fixture, verify hashes and the strict extension, recompute realized."""
    sid = en.get("settle_id", "?")
    errs: list[str] = []
    if en.get("factor_code_sha256") != sha256_bytes(
            str(en.get("factor_code", "")).encode("utf-8")):
        return [f"settlement {sid}: factor_code_sha256 does not match the "
                f"attached code"]
    w = en.get("world") or {}
    spec = w.get("spec") if isinstance(w.get("spec"), dict) else None
    if spec is None or fixture_root is None:
        return [f"settlement {sid}: real-world settlement needs a pinned "
                f"source spec and --fixture-root to recompute from"]
    try:
        ext_dir = _rebuild_real_extension(spec, Path(fixture_root))
        ext = fingerprint(ext_dir)
        if ext.manifest_hash != en.get("extension_hash"):
            return [f"settlement {sid}: extension_hash does not rebuild "
                    f"from the pinned fixture"]
        ext_frame = engine.load_frame(ext_dir)
        dates = ext_frame.dates
        horizon = f"{dates[w.get('base_days', 0)]}:{dates[-1]}"
        signal = run_factor(en["factor_code"], ext_frame.closes,
                            ext_frame.tickers, ext_frame.dates,
                            ext_frame.volumes, ext_frame.opens)
        frame = engine.load_frame(ext_dir, horizon)
        realized = engine.evaluate_signal(frame, signal)
    except (SandboxError, ValueError, KeyError) as exc:
        return [f"settlement {sid}: does not recompute ({exc})"]
    rec = en.get("realized") or {}
    for key, val in sorted(rec.items()):
        if key == "window":
            if val != horizon:
                errs.append(f"settlement {sid}: realized.window {val} != "
                            f"recomputed horizon {horizon}")
        elif key not in realized:
            errs.append(f"settlement {sid}: realized.{key} is not a harness "
                        f"metric")
        elif realized[key] != val:
            errs.append(f"settlement {sid}: realized.{key} says {val}, "
                        f"recomputation says {realized[key]}")
    if en.get("outcome") in ("held", "fell_short"):
        expected = _outcome(realized.get("rankic_mean"),
                            (en.get("claimed") or {}).get("bar"),
                            (en.get("claimed") or {}).get("op", ">="))
        if expected != en["outcome"]:
            errs.append(f"settlement {sid}: outcome {en['outcome']!r} "
                        f"does not recompute ({expected!r})")
    return errs


def _outcome(realized: float | None, bar: Any, op: str) -> str:
    if realized is None or not isinstance(bar, (int, float)):
        return "unverifiable"
    ok = {">=": realized >= bar, ">": realized > bar,
          "<=": realized <= bar, "<": realized < bar}.get(op)
    return "held" if ok else "fell_short"


# -- the acceptance sweep (v0.5) --------------------------------------------

CAL_STRENGTHS = (0.05, 0.08, 0.11, 0.14, 0.17, 0.20, 0.25, 0.30)
CAL_PLANT_SEEDS = (11, 22, 33, 44, 55, 66, 77, 88)
CAL_NOISE_SEEDS = tuple(range(1, 25))
CAL_CFG = {"label": "cal", "roles": ("data", "factor", "risk"), "rounds": 1}
MIN_SETTLED = 50


def run_calibration_sweep(out_dir: Path, *,
                          strengths: tuple[float, ...] = CAL_STRENGTHS,
                          plant_seeds: tuple[int, ...] = CAL_PLANT_SEEDS,
                          noise_seeds: tuple[int, ...] = CAL_NOISE_SEEDS,
                          cfg: dict[str, Any] = CAL_CFG,
                          verbose: bool = False) -> dict[str, Any]:
    """The v0.5 acceptance harness: sweep worlds, admit, settle, report.

    Same scripted persona policy on every world (the ablation contract);
    every admitted claim settles on a 90-day horizon; the ledger audits and
    the calibration curve lands in ``out_dir``. Deterministic end to end.
    """
    from .ablation import run_one  # late: mining imports this module first
    from .snapshot import build_snapshot

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    log = print if verbose else (lambda *a, **k: None)
    ledger = SettlementLedger.open(out_dir / "settlement.jsonl")

    worlds: list[dict[str, Any]] = []
    for strength in strengths:
        for seed in plant_seeds:
            worlds.append({"name": f"planted-s{strength}-seed{seed}",
                           "seed": seed,
                           "plant": {"effect": "reversal",
                                     "strength": strength}})
    for seed in noise_seeds:
        worlds.append({"name": f"noise-seed{seed}", "seed": seed,
                       "plant": None})

    for w in worlds:
        d = out_dir / "worlds" / w["name"]
        build_snapshot(d, seed=w["seed"], tickers=12, days=90,
                       plant=w["plant"])
        work = out_dir / "runs" / w["name"]
        summary = run_one(work, d, cfg)
        if not summary["admitted"]:
            continue
        cards = sorted((work / "cards").glob("E-*.json"))
        e = json.loads(cards[-1].read_text("utf-8"))
        if e.get("verdict") != "pass":
            continue
        h = json.loads(
            (work / "cards" / f"{e['hyp_id']}.json").read_text("utf-8"))
        entry = settle_claim(ledger, e, h, d, out_dir / "ext" / w["name"])
        log(f"  settled {entry['settle_id']} {w['name']:28s} "
            f"claimed={entry['claimed']['value']:+.4f} "
            f"realized={entry['realized']['rankic_mean']:+.4f} "
            f"-> {entry['outcome']}")

    errs = audit_ledger(out_dir / "settlement.jsonl")
    if errs:
        raise SettlementError("ledger does not recompute: " + "; ".join(errs))
    report = calibration_report(ledger)
    md = report_markdown(report)
    (out_dir / "calibration.md").write_text(md, encoding="utf-8")
    (out_dir / "report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"ledger": ledger, "report": report, "markdown": md,
            "audit_errors": errs}


# -- audit (FIB 19) ----------------------------------------------------------

def audit_ledger(path: Path, *, registry_path: Path | None = None,
                 fixture_root: Path | None = None
                 ) -> list[str]:
    """Recompute everything the ledger claims. Returns a list of errors.

    Checks, in order: parse + chain (seq, prev_hash, entry_hash — an edit,
    deletion or reorder anywhere breaks it), then per entry: the world
    extension rebuilds byte-identically (extension_hash), the factor code
    hash matches, the realized metrics and the outcome recompute from
    source, and (when a registry is given) the settled exp_id actually
    exists there as an admitted pass — a claim nobody made cannot settle.
    """
    path = Path(path)
    errs: list[str] = []
    if not path.exists():
        return [f"settlement ledger {path}: does not exist"]
    entries: list[dict[str, Any]] = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError as exc:
            errs.append(f"settlement line {i}: unreadable ({exc})")
    prev = GENESIS
    for i, en in enumerate(entries, 1):
        if en.get("seq") != i:
            errs.append(f"settlement {en.get('settle_id', i)}: seq "
                        f"{en.get('seq')} != position {i} (reordered?)")
        if en.get("prev_hash") != prev:
            errs.append(f"settlement {en.get('settle_id', i)}: prev_hash "
                        f"breaks the chain at position {i}")
        if en.get("entry_hash") != _entry_hash(en):
            errs.append(f"settlement {en.get('settle_id', i)}: entry_hash "
                        f"does not match its payload (edited?)")
        if en.get("entry_hash"):
            prev = en["entry_hash"]

    reg = None
    if registry_path is not None:
        from .registry import Registry
        reg = Registry(Path(registry_path))

    for en in entries:
        sid = en.get("settle_id", "?")
        w = en.get("world") or {}
        if w.get("kind") == "real":
            errs.extend(_audit_real_entry(en, fixture_root))
            continue
        if w.get("kind") != "synthetic":
            errs.append(f"settlement {sid}: unknown world kind "
                        f"{w.get('kind')!r}")
            continue
        if en.get("factor_code_sha256") != sha256_bytes(
                str(en.get("factor_code", "")).encode("utf-8")):
            errs.append(f"settlement {sid}: factor_code_sha256 does not "
                        f"match the attached code")
            continue
        try:
            with tempfile.TemporaryDirectory() as td:
                ext_dir = Path(td) / "ext"
                ext = build_snapshot(ext_dir, seed=w["seed"],
                                     tickers=w["tickers"],
                                     days=w["days"] + w["extension_days"],
                                     start=w["start"], plant=w.get("plant"),
                                     costs=w.get("costs"))
                if ext.manifest_hash != en.get("extension_hash"):
                    errs.append(f"settlement {sid}: extension_hash does not "
                                f"rebuild from the world spec")
                    continue
                ext_frame = engine.load_frame(ext_dir)
                dates = ext_frame.dates
                horizon = f"{dates[w['days']]}:{dates[-1]}"
                signal = run_factor(en["factor_code"], ext_frame.closes,
                                    ext_frame.tickers, ext_frame.dates,
                                    ext_frame.volumes, ext_frame.opens)
                frame = engine.load_frame(ext_dir, horizon)
                realized = engine.evaluate_signal(frame, signal)
        except (SandboxError, ValueError, KeyError) as exc:
            errs.append(f"settlement {sid}: does not recompute ({exc})")
            continue
        rec = en.get("realized") or {}
        for key, val in sorted(rec.items()):
            if key == "window":
                if val != horizon:
                    errs.append(f"settlement {sid}: realized.window {val} != "
                                f"recomputed horizon {horizon}")
            elif key not in realized:
                errs.append(f"settlement {sid}: realized.{key} is not a "
                            f"harness metric")
            elif realized[key] != val:
                errs.append(f"settlement {sid}: realized.{key} says {val}, "
                            f"recomputation says {realized[key]}")
        if en.get("outcome") in ("held", "fell_short"):
            expected = _outcome(realized.get("rankic_mean"),
                                (en.get("claimed") or {}).get("bar"),
                                (en.get("claimed") or {}).get("op", ">="))
            if expected != en["outcome"]:
                errs.append(f"settlement {sid}: outcome {en['outcome']!r} "
                            f"does not recompute ({expected!r})")
        if reg is not None:
            exp_ids = {x.get("exp_id") for x in reg.entries
                       if x.get("type") == "experiment"}
            if en.get("exp_id") not in exp_ids:
                errs.append(f"settlement {sid}: exp_id "
                            f"{en.get('exp_id')!r} is not a settled "
                            f"experiment in the registry — a claim nobody "
                            f"made cannot settle")
    return errs


# -- reflection loop ---------------------------------------------------------

def admission_multiplier(ledger: SettlementLedger,
                         family: str) -> tuple[float, str]:
    """The calibration rule: tighten after shortfalls, never loosen.

    With fewer than ``MIN_SETTLED_HISTORY`` settled claims the ledger says
    nothing (×1.0). From five on, if more than half fell short, the family's
    admission bar is multiplied by ``TIGHTEN_MULTIPLIER`` for later orders.
    A spotless or mixed history never relaxes anything — the floor stays.
    """
    settled = ledger.settled_for(family)
    n = len(settled)
    fell = sum(1 for en in settled if en["outcome"] == "fell_short")
    if n >= MIN_SETTLED_HISTORY and fell / n > SHORTFALL_RATIO_TRIGGER:
        return TIGHTEN_MULTIPLIER, (
            f"{n} settled claims in family {family!r}, {fell} fell short "
            f"({fell / n:.0%}) — admission bar tightened x"
            f"{TIGHTEN_MULTIPLIER}")
    return 1.0, (f"{n} settled claims in family {family!r}, {fell} fell "
                 f"short — no adjustment (calibration only tightens)")


# -- calibration report ------------------------------------------------------

def calibration_report(ledger: SettlementLedger) -> dict[str, Any]:
    """Bucketed claimed-vs-realized curve + pressure asymmetry, from the
    ledger only (the report recomputes nothing — audit certifies the input)."""
    settled = [en for en in ledger.entries
               if en.get("outcome") in ("held", "fell_short")]
    unverifiable = sum(1 for en in ledger.entries
                       if en.get("outcome") == "unverifiable")

    def _bin(v: float) -> int:
        for i in range(len(CURVE_BINS) - 1):
            if CURVE_BINS[i] <= v < CURVE_BINS[i + 1]:
                return i
        return len(CURVE_BINS) - 2

    buckets: list[dict[str, Any]] = []
    for i in range(len(CURVE_BINS) - 1):
        rows = [en for en in settled
                if _bin(float(en["claimed"]["value"])) == i]
        if not rows:
            continue
        claimed = [float(en["claimed"]["value"]) for en in rows]
        realized = [float(en["realized"]["rankic_mean"]) for en in rows]
        gaps = [r - c for c, r in zip(claimed, realized)]
        buckets.append({
            "bin": f"[{CURVE_BINS[i]:.2f},{CURVE_BINS[i + 1]:.2f})",
            "n": len(rows),
            "mean_claimed": round(sum(claimed) / len(claimed), 6),
            "mean_realized": round(sum(realized) / len(realized), 6),
            "mean_gap": round(sum(gaps) / len(gaps), 6),
            "held": sum(1 for en in rows if en["outcome"] == "held"),
        })

    pressure: dict[str, dict[str, Any]] = {}
    for it in sorted({en.get("iteration") for en in settled
                      if en.get("iteration")}):
        rows = [en for en in settled if en.get("iteration") == it]
        claimed = [float(en["claimed"]["value"]) for en in rows]
        gaps = [float(en["realized"]["rankic_mean"])
                - float(en["claimed"]["value"]) for en in rows]
        pressure[str(it)] = {
            "n": len(rows),
            "mean_claimed": round(sum(claimed) / len(claimed), 6),
            "mean_gap": round(sum(gaps) / len(gaps), 6),
        }

    gaps_all = ([float(en["realized"]["rankic_mean"])
                 - float(en["claimed"]["value"]) for en in settled])

    # λℓ−δ readout (v0.7): the calibration slope — realized regressed on
    # claimed across claimed-bins (cohorts). A slope < 1 means claims decay
    # over the settlement horizon ℓ: the (λℓ − δ) exponent in the budget
    # equation is negative for this pipeline, i.e. claims leak value faster
    # than the loop compounds it. Slope is OLS over bin means, n-weighted by
    # bins (each cohort is one point).
    xs = [b["mean_claimed"] for b in buckets]
    ys = [b["mean_realized"] for b in buckets]
    if len(xs) >= 2:
        mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
        denom = sum((x - mx) ** 2 for x in xs)
        decay_slope = (sum((x - mx) * (y - my) for x, y in zip(xs, ys))
                       / denom) if denom else 0.0
    else:
        decay_slope = 0.0

    # TC readout (v0.7): measured cost drag on the settled horizons — gross
    # vs net spread, turnover, and the bps the world's cost model actually
    # charged. A pipeline whose net gap eats its gross spread has a TC term
    # near zero regardless of what its IC says.
    tc_rows = [en for en in settled
               if "turnover" in (en.get("realized") or {})
               and "net_quintile_spread" in (en.get("realized") or {})]
    tc = None
    if tc_rows:
        gross = [float(en["realized"]["quintile_spread"]) for en in tc_rows]
        net = [float(en["realized"]["net_quintile_spread"]) for en in tc_rows]
        to = [float(en["realized"]["turnover"]) for en in tc_rows]
        drag = [g - n for g, n in zip(gross, net)]
        tc = {
            "n": len(tc_rows),
            "mean_turnover": round(sum(to) / len(to), 6),
            "mean_gross_spread": round(sum(gross) / len(gross), 6),
            "mean_net_spread": round(sum(net) / len(net), 6),
            "mean_drag": round(sum(drag) / len(drag), 6),
            "net_gross_ratio": round((sum(net) / len(net))
                                     / (sum(gross) / len(gross)), 6)
            if sum(gross) else 0.0,
        }

    horizon_days = next((int((en.get("world") or {}).get("extension_days")
                             or 0) for en in ledger.entries), 0)

    by_truth: dict[str, dict[str, Any]] = {}
    for kind, want in (("planted", True), ("noise", False)):
        rows = [en for en in settled
                if bool((en.get("world") or {}).get("plant")) is want]
        if not rows:
            continue
        claimed = [float(en["claimed"]["value"]) for en in rows]
        realized = [float(en["realized"]["rankic_mean"]) for en in rows]
        gaps = [r - c for c, r in zip(claimed, realized)]
        by_truth[kind] = {
            "n": len(rows),
            "mean_claimed": round(sum(claimed) / len(claimed), 6),
            "mean_realized": round(sum(realized) / len(realized), 6),
            "mean_gap": round(sum(gaps) / len(gaps), 6),
            "held": sum(1 for en in rows if en["outcome"] == "held"),
        }

    return {
        "n_settled": len(settled),
        "n_unverifiable": unverifiable,
        "held": sum(1 for en in settled if en["outcome"] == "held"),
        "fell_short": sum(1 for en in settled
                          if en["outcome"] == "fell_short"),
        "mean_gap": round(sum(gaps_all) / len(gaps_all), 6) if gaps_all else 0,
        "curve": buckets,
        "pressure_by_iteration": pressure,
        "by_truth": by_truth,
        "decay_slope": round(decay_slope, 6),
        "horizon_days": horizon_days,
        "tc": tc,
    }


def report_markdown(report: dict[str, Any]) -> str:
    lines = [
        "| claimed rank IC bin | n | mean claimed | mean realized | "
        "mean gap (realized-claimed) | held |",
        "|---|---|---|---|---|---|",
    ]
    for b in report["curve"]:
        lines.append(f"| {b['bin']} | {b['n']} | {b['mean_claimed']} | "
                     f"{b['mean_realized']} | {b['mean_gap']} | "
                     f"{b['held']}/{b['n']} |")
    lines.append("")
    lines.append(f"settled: {report['n_settled']} "
                 f"(held {report['held']}, fell short {report['fell_short']}, "
                 f"unverifiable {report['n_unverifiable']}); "
                 f"mean gap {report['mean_gap']:+.4f}")
    lines.append(f"decay slope (realized~claimed over "
                 f"{report.get('horizon_days', 0)}-day horizons): "
                 f"{report.get('decay_slope', 0.0):+.4f}")
    tc = report.get("tc")
    if tc:
        lines.append(
            f"transaction costs: n={tc['n']}, mean turnover "
            f"{tc['mean_turnover']:.4f}/day, gross spread "
            f"{tc['mean_gross_spread']:+.6f} -> net {tc['mean_net_spread']:+.6f} "
            f"(drag {tc['mean_drag']:.6f}, net/gross {tc['net_gross_ratio']:+.4f})")
    for kind, row in sorted((report.get("by_truth") or {}).items()):
        lines.append(f"- {kind}: n={row['n']}, mean claimed="
                     f"{row['mean_claimed']}, mean realized="
                     f"{row['mean_realized']}, mean gap={row['mean_gap']:+.4f}, "
                     f"held {row['held']}/{row['n']}")
    if report["pressure_by_iteration"]:
        lines.append("")
        lines.append("pressure asymmetry (claimed vs gap by in-budget "
                     "iteration):")
        for it, row in report["pressure_by_iteration"].items():
            lines.append(f"- iteration {it}: n={row['n']}, mean claimed="
                         f"{row['mean_claimed']}, mean gap={row['mean_gap']:+.4f}")
    return "\n".join(lines) + "\n"
