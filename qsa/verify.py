"""The verify gate — schema · fingerprint · no-lookahead · verdict consistency.

Exit 0 = PASS (evidence is machine-consistent; it may still be a *negative*
result — that is fine, honesty is the product). Exit 1 = FAIL with one line
per inconsistency, each naming the field/window/step precisely. Exit 2 =
usage error.

Modes:

* ``verify.py CARD.json [CARD.json ...]``  — schema-only validation
  (cards routed by their ``schema`` field; unregistered types fail).
* ``verify.py --hypothesis H.json --result E.json --snapshot DIR``
  — the full linked gate used by CI and the forge's post-receive hook.

FIB classes covered by design here: 1 (missing-field), 3 (lookahead-window),
4 (snapshot-mismatch), 7 (silent-pass), 14 (partial-metrics), 15
(window-shrink). Class 11 (threshold-drift) is structurally next to impossible
because verdicts are recomputed from the cited H card, whose file the PR
carries — post-hoc threshold edits change the H card and thus the recomputed
verdict, which the E card must then match.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from . import admission, engine, deflation, registry, roles, settlement, snapshot
from .sandbox import SandboxError, run_factor
from .snapshot import sha256_bytes
from .validate import validate_card


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def gate(hypothesis_path: Path, result_path: Path, snapshot_dir: Path,
         registry_path: Path | None = None,
         settlement_path: Path | None = None) -> tuple[bool, list[str]]:
    """Full linked gate. Returns (ok, errors).

    Without *registry_path* the gate checks the pair in isolation (schema,
    linkage, fingerprint, windows, verdict consistency). With a registry it
    additionally enforces ledger disciplines: pre-registration order, ID
    uniqueness, OOS one-shot windows, multiple-testing deflation — and if the
    E card carries ``factor_code`` it *recomputes* every metric from that
    code, so numbers that were never computed cannot survive (FIB 2/9).

    With *settlement_path* (v0.5) the settlement ledger's hash chain and
    every realized metric must recompute (FIB 19), and an H card that claims
    a calibration adjustment must match the ledger's own rule — a rosier
    history than the ledger supports is a lie, and so is omitting a
    tightening the ledger demands.
    """
    errs: list[str] = []
    h = _load(hypothesis_path)
    e = _load(result_path)
    errs.extend(validate_card(h, "H"))
    errs.extend(validate_card(e, "E"))

    # settlement ledger (v0.5, FIB 19): the chain must hold and every
    # realized metric must recompute from the world spec + factor code each
    # entry carries; a calibration block on H must match the ledger's rule
    if settlement_path is not None:
        errs.extend(settlement.audit_ledger(settlement_path))
        if isinstance(h, dict):
            led = settlement.SettlementLedger(Path(settlement_path))
            exp_mult, exp_basis = settlement.admission_multiplier(
                led, h.get("family", "default"))
            cal = h.get("calibration")
            if cal is None:
                if exp_mult != 1.0:
                    errs.append(
                        f"H.calibration missing but the settlement ledger "
                        f"demands x{exp_mult} for family "
                        f"{h.get('family', 'default')!r} — a tightening the "
                        f"ledger justifies cannot be dropped")
            elif not isinstance(cal, dict):
                errs.append("H.calibration must be an object "
                            "{multiplier, basis}")
            else:
                if cal.get("multiplier") != exp_mult:
                    errs.append(
                        f"H.calibration.multiplier {cal.get('multiplier')} "
                        f"!= the ledger's rule x{exp_mult} for family "
                        f"{h.get('family', 'default')!r} — claiming a rosier "
                        f"history than the ledger supports is a lie")
                if cal.get("basis") != exp_basis:
                    errs.append(f"H.calibration.basis does not match the "
                                f"ledger-derived basis {exp_basis!r}")
    elif isinstance(h, dict) and isinstance(h.get("calibration"), dict):
        errs.append("H.calibration is present but no settlement ledger was "
                    "given — an unverifiable calibration claim")


    # linkage
    if isinstance(h, dict) and isinstance(e, dict) \
            and h.get("hyp_id") and e.get("hyp_id") and h["hyp_id"] != e["hyp_id"]:
        errs.append(f"E.hyp_id {e['hyp_id']!r} does not match H.hyp_id {h['hyp_id']!r}")

    # fingerprint (FIB 4): recomputed snapshot hash must equal the cited one,
    # and the snapshot's own files must match its manifest (reconciliation).
    try:
        info = snapshot.fingerprint(snapshot_dir)
    except ValueError as exc:
        errs.append(f"fingerprint: {exc}")
    else:
        if isinstance(e, dict) and e.get("snapshot_hash") != info.manifest_hash:
            errs.append(
                f"E.snapshot_hash {str(e.get('snapshot_hash'))[:12]}… != recomputed "
                f"{info.manifest_hash[:12]}… (card cites a snapshot that was not used)")

        # no-lookahead (FIB 3) + window-shrink (FIB 15)
        if isinstance(e, dict) and isinstance(h, dict) \
                and h.get("window") and e.get("window"):
            if e["window"] != h["window"]:
                errs.append(
                    f"E.window {e['window']} != H.window {h['window']} "
                    f"(pre-registered window; trimming the evaluation window "
                    f"to the profitable stretch is not allowed)")
            w_start, _, w_end = e["window"].partition(":")
            if w_end > info.manifest["as_of"]:
                errs.append(
                    f"E.window end {w_end} is after snapshot as_of "
                    f"{info.manifest['as_of']} (evaluation extends past the "
                    f"data that existed — lookahead)")
            if w_start < info.manifest["start"]:
                errs.append(
                    f"E.window start {w_start} is before snapshot start "
                    f"{info.manifest['start']}")

    # partial-metrics (FIB 14) + verdict consistency (FIB 7), deflated when
    # the ledger is present (the ledger knows how many trials came before)
    n_trials = 1
    if registry_path is not None:
        try:
            reg = registry.Registry(Path(registry_path))
        except (OSError, json.JSONDecodeError) as exc:
            errs.append(f"registry: unreadable ({exc})")
            reg = None
        if reg is not None and isinstance(e, dict) and isinstance(h, dict):
            if e.get("exp_id") and reg.entries:
                settled = {en.get("exp_id") for en in reg.entries
                           if en.get("type") == "experiment"}
                if e.get("exp_id") in settled:
                    errs.append(f"E.exp_id {e['exp_id']!r} is already settled — "
                                f"IDs are unique forever (no resubmission)")
            if not reg.has_hypothesis(h.get("hyp_id", "")):
                errs.append(f"H.hyp_id {h.get('hyp_id')!r} is not registered — "
                            f"hypotheses pre-register before experiments settle")
            oos_win = (e.get("oos") or {}).get("window")
            if oos_win:
                try:
                    reg.check_oos_available(oos_win)
                except registry.RegistryError as exc:
                    errs.append(f"ledger: {exc}")
            family = h.get("family", "default")
            n_trials = reg.n_trials(family) + 1

    if isinstance(h, dict) and isinstance(e, dict) and "admission" in h:
        try:
            admission.parse_thresholds(h["admission"])
        except ValueError as exc:
            errs.append(f"H.admission: {exc}")
        else:
            if registry_path is not None:
                expected, reasons = deflation.deflated_evaluate(
                    h["admission"], e.get("metrics", {}), n_trials)
            else:
                expected, reasons = admission.evaluate(
                    h["admission"], e.get("metrics", {}))
            # an OOS block changes the expected verdict: a candidate that
            # passes in-sample but fails its pre-registered OOS window is an
            # honest fail (class oos_miss) — the gate must expect that, not
            # brand it inconsistent
            oos_block = e.get("oos") if isinstance(e.get("oos"), dict) else None
            if expected == "pass" and oos_block:
                oos_expected, oos_reasons = deflation.deflated_evaluate(
                    h["admission"], oos_block.get("metrics", {}), 1)
                if oos_expected != "pass":
                    expected = "fail"
                    reasons = list(reasons) + [
                        f"oos window {oos_block.get('window')}: "
                        f"{'; '.join(oos_reasons)}"]
            # a *claimed* risk veto must recompute: the card records
            # half-split instability (attribution.neighborhood_stable=false)
            # only if the attached factor code verifiably exhibits it — a
            # fabricated veto is as much a lie as a fabricated pass
            stability = None
            claimed_veto = (isinstance(e.get("attribution"), dict)
                            and e["attribution"].get("neighborhood_stable")
                            is False)
            rb = e.get("review") if isinstance(e.get("review"), dict) else None
            if (claimed_veto or rb) and e.get("factor_code"):
                try:
                    stability = roles.risk_check(
                        e["factor_code"], snapshot_dir, h,
                        e.get("metrics", {})).get("neighborhood_stable")
                except (SandboxError, ValueError):
                    stability = None  # the recompute block below will complain
            if claimed_veto:
                if stability is not False:
                    errs.append("E.attribution.neighborhood_stable=false does "
                                "not recompute from factor_code — fabricated "
                                "veto")
                else:
                    expected = "fail"
                    reasons = list(reasons) + [
                        "risk veto verified: half-split instability"]
            # a review block must agree with the facts: admission requires
            # stability; a veto requires a verified objection
            if rb is not None:
                for obj in rb.get("upheld_objections") or []:
                    fact = {"halves_stability": stability}.get(obj.get("check"))
                    if fact is not False:
                        errs.append(
                            f"E.review.upheld_objections: {obj.get('check')!r} "
                            f"does not verify — a fabricated veto is a lie")
                if rb.get("admitted") and stability is False:
                    errs.append("E.review.admitted=true but the candidate is "
                                "unstable across halves — veto was mandatory")
                if not rb.get("admitted") and not (rb.get("upheld_objections")
                                                   or []):
                    errs.append("E.review.admitted=false without a verifiable "
                                "upheld objection")
                if not rb.get("admitted") and rb.get("upheld_objections"):
                    expected = "fail"
            for r in reasons:
                if expected is None:
                    errs.append(f"E.metrics: {r}")
            if expected is not None and e.get("verdict") != expected:
                errs.append(
                    f"E.verdict {e.get('verdict')!r} is inconsistent with the "
                    f"pre-registered criteria — mechanical evaluation of "
                    f"E.metrics says '{expected}' ({'; '.join(reasons)})")

    # recomputation (FIB 2 phantom-metric / 9 unit-mismatch): if the card
    # carries its factor code, every metric must be reproducible from it
    if isinstance(e, dict) and e.get("factor_code"):
        if e.get("engine") != engine.EVAL_ID:
            errs.append(f"E.engine {e.get('engine')!r} != evaluation harness "
                        f"{engine.EVAL_ID!r} (version pin)")
        claimed_sha = e.get("factor_code_sha256", "")
        actual_sha = sha256_bytes(e["factor_code"].encode("utf-8"))
        if claimed_sha != actual_sha:
            errs.append("E.factor_code_sha256 does not match the attached code")
        else:
            try:
                # the signal is a function of the snapshot (truncated-view
                # sandbox: values at t depend only on closes <= t); windows
                # select which dates to score, warmup uses pre-window data
                full_frame = engine.load_frame(snapshot_dir)
                signal = run_factor(e["factor_code"], full_frame.closes,
                                    full_frame.tickers, full_frame.dates)
                frame = engine.load_frame(snapshot_dir, e.get("window"))
                recomputed = engine.evaluate_signal(frame, signal)
            except (SandboxError, ValueError) as exc:
                errs.append(f"factor_code does not recompute: {exc}")
            else:
                claimed = e.get("metrics", {})
                if set(claimed) != set(recomputed):
                    errs.append(
                        f"E.metrics keys {sorted(claimed)} != recomputed keys "
                        f"{sorted(recomputed)} — metrics must be exactly what "
                        f"the harness produces")
                for key in sorted(set(claimed) & set(recomputed)):
                    if claimed[key] != recomputed[key]:
                        errs.append(
                            f"E.metrics.{key}: card says {claimed[key]}, "
                            f"recomputation from factor_code says "
                            f"{recomputed[key]} (phantom or rescaled metric)")
                oos_blk = e.get("oos") if isinstance(e.get("oos"), dict) else None
                if oos_blk and oos_blk.get("window"):
                    try:
                        oos_frame = engine.load_frame(snapshot_dir,
                                                      oos_blk["window"])
                        oos_recomputed = engine.evaluate_signal(oos_frame,
                                                                signal)
                    except (SandboxError, ValueError) as exc:
                        errs.append(f"E.oos does not recompute: {exc}")
                    else:
                        for key, val in sorted((oos_blk.get("metrics") or {}).items()):
                            if key not in oos_recomputed:
                                errs.append(f"E.oos.metrics.{key}: not a harness "
                                            f"metric")
                            elif val != oos_recomputed[key]:
                                errs.append(
                                    f"E.oos.metrics.{key}: card says {val}, "
                                    f"recomputation says {oos_recomputed[key]}")
    return (not errs), errs


def main(argv: list[str]) -> int:
    args = argv[1:]
    if not args:
        print("usage: verify.py CARD.json [CARD.json ...]\n"
              "       verify.py --hypothesis H.json --result E.json --snapshot DIR",
              file=sys.stderr)
        return 2

    if args[0] == "--hypothesis" or args[0] == "--h":
        opts = dict(zip(args, args[1:]))
        try:
            h = Path(opts["--hypothesis"] if "--hypothesis" in opts else opts["--h"])
            e = Path(opts["--result"] if "--result" in opts else opts["--e"])
            snap = Path(opts["--snapshot"] if "--snapshot" in opts else opts["--s"])
        except KeyError as exc:
            print(f"missing option {exc}", file=sys.stderr)
            return 2
        reg = Path(opts["--registry"]) if "--registry" in opts else None
        stl = Path(opts["--settlement"]) if "--settlement" in opts else None
        try:
            ok, errs = gate(h, e, snap, registry_path=reg, settlement_path=stl)
        except (json.JSONDecodeError, OSError) as exc:
            ok, errs = False, [f"unreadable card: {exc}"]
        print(("PASS " if ok else "FAIL ") + f"gate: {e.name} vs {h.name}"
              + (" [ledger]" if reg else ""))
        for line in errs:
            print("  - " + line)
        return 0 if ok else 1

    all_ok = True
    for arg in args:
        p = Path(arg)
        if not p.exists():
            print(f"FAIL {p}: file does not exist")
            all_ok = False
            continue
        try:
            doc = _load(p)
        except (json.JSONDecodeError, OSError) as exc:
            print(f"FAIL {p}: unreadable ({exc})")
            all_ok = False
            continue
        errs = validate_card(doc, str(p))
        print(("PASS " if not errs else "FAIL ") + str(p))
        for line in errs:
            print("  - " + line)
        all_ok = all_ok and not errs
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
