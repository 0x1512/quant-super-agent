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

from . import admission, snapshot
from .validate import validate_card


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def gate(hypothesis_path: Path, result_path: Path, snapshot_dir: Path) -> tuple[bool, list[str]]:
    """Full linked gate. Returns (ok, errors)."""
    errs: list[str] = []
    h = _load(hypothesis_path)
    e = _load(result_path)
    errs.extend(validate_card(h, "H"))
    errs.extend(validate_card(e, "E"))

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

    # partial-metrics (FIB 14) + verdict consistency (FIB 7)
    if isinstance(h, dict) and isinstance(e, dict) and "admission" in h:
        try:
            admission.parse_thresholds(h["admission"])
        except ValueError as exc:
            errs.append(f"H.admission: {exc}")
        else:
            expected, reasons = admission.evaluate(h["admission"], e.get("metrics", {}))
            for r in reasons:
                if expected is None:
                    errs.append(f"E.metrics: {r}")
            if expected is not None and e.get("verdict") != expected:
                errs.append(
                    f"E.verdict {e.get('verdict')!r} is inconsistent with the "
                    f"pre-registered criteria — mechanical evaluation of "
                    f"E.metrics says '{expected}' ({'; '.join(reasons)})")
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
        try:
            ok, errs = gate(h, e, snap)
        except (json.JSONDecodeError, OSError) as exc:
            ok, errs = False, [f"unreadable card: {exc}"]
        print(("PASS " if ok else "FAIL ") + f"gate: {e.name} vs {h.name}")
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
