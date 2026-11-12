"""The mining loop — LLM hypotheses + factor code, disciplined by the ledger.

This is where the factory earns its name. Per iteration, under a fixed
budget:

1. the LLM proposes a hypothesis (mechanism + pre-registered admission);
   the loop owns the IDs, family and window — the LLM cannot mint identity;
2. the LLM writes factor code; it runs in the truncated-view sandbox
   (lookahead-free by construction) and is evaluated by the same harness
   the gate recomputes with;
3. the verdict is mechanical — ``deflated_evaluate`` over the ledger's trial
   count N — never the LLM's to choose;
4. the card pair must clear the full gate (schema, fingerprint, windows,
   verdict consistency, recomputation from factor_code, registry
   disciplines) as the forge's CI before anything merges;
5. only merged evidence settles into the registry, burning a one-shot OOS
   window if one was declared;
6. a failure is classified (attribution) and fed back into the next
   iteration's prompt — retry chains are budget-bounded and legible.

If the LLM cheats (lowers thresholds under pressure, writes lookahead code,
or a card fails any gate check) the loop records the blocked attempt and
moves on; nothing unreachable-by-honest-means ever settles.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from . import attribution as attribution_mod
from . import deflation, engine, registry as registry_mod, review as review_mod, \
    roles as roles_mod, settlement as settlement_mod, snapshot
from .forge import Forge
from .llm import BaseLLM, LLMError, extract_json
from .sandbox import SandboxError, run_factor
from .snapshot import canonical_json, sha256_bytes
from .validate import validate_card

SYSTEM_HYPOTHESIS = (
    "You are a quantitative researcher proposing falsifiable hypotheses. "
    "Respond with a single JSON object with keys: mechanism (string), "
    "falsifiable_condition (string), admission {required_metrics: [list], "
    "thresholds: {metric: {op: >=|<=|>|<, value: number}}, "
    "min_observations: int}. Thresholds must stay as strict as the order "
    "demands; lowering a bar to rescue a rejected direction is fraud.")

SYSTEM_FACTOR = (
    "You are a quantitative researcher implementing one cross-sectional "
    "factor. Respond with ONLY Python code defining exactly: "
    "def factor(closes, tickers, dates, i): ... returning {ticker: value} "
    "for date index i (empty dict is fine for warmup dates). closes is "
    "{ticker: {date: close}} truncated to dates <= dates[i] — future data "
    "does not exist and cannot be named. No imports, no attribute access "
    "beyond .get/.items/.keys/.values/.append, no while-loops.")

REQUIRED_METRICS_DEFAULT = ["rankic_mean", "rankic_tstat", "quintile_spread",
                            "monotonicity_proxy", "n_dates"]
THRESHOLDS_DEFAULT = {"rankic_mean": {"op": ">=", "value": 0.02},
                      "quintile_spread": {"op": ">=", "value": 0.0}}


def _strip_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        first_nl = t.find("\n")
        if first_nl > 0:
            t = t[first_nl + 1:]
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
    return t.strip() + "\n"


def _history_block(history: list[dict[str, Any]]) -> str:
    if not history:
        return "This is the first iteration — no prior attempts."
    lines = []
    for h in history:
        lines.append(str({"hyp_id": h.get("hyp_id"),
                          "verdict": h.get("verdict"),
                          "attribution": h.get("attribution"),
                          "blocked": h.get("blocked")}))
    return "Prior attempts (do not repeat them):\n" + "\n".join(lines)


def run_order(work: Path, snapshot_dir: Path, order_text: str, llm: BaseLLM,
              *, budget: int = 3, family: str = "mining",
              registry_path: Path | None = None,
              roles: tuple[str, ...] | list[str] = roles_mod.DEFAULT_ROLES,
              debate_rounds: int = 1,
              settlement_ledger: Path | None = None,
              verbose: bool = True) -> dict[str, Any]:
    work = Path(work)
    if work.exists():
        raise ValueError(f"workdir {work} already exists; mining requires a "
                         f"fresh start (determinism)")
    roles = roles_mod.check_roles(tuple(roles))
    if not isinstance(debate_rounds, int) or debate_rounds < 0 or debate_rounds > 10:
        raise ValueError("debate_rounds must be an int in 0..10")
    # the reflection loop (v0.5): settlement history tightens the family's
    # admission bar — computed from the ledger here, recomputed by the gate
    cal_mult, cal_basis = 1.0, "no settlement history for this family"
    if settlement_ledger is not None:
        cal_mult, cal_basis = settlement_mod.admission_multiplier(
            settlement_mod.SettlementLedger(Path(settlement_ledger)), family)
    log = print if verbose else (lambda *a, **k: None)

    info = snapshot.fingerprint(snapshot_dir)
    as_of = info.manifest["as_of"]
    as_of_iso = f"{as_of[:4]}-{as_of[4:6]}-{as_of[6:]}"
    full_window = f"{info.manifest['start']}:{as_of}"

    work.mkdir(parents=True)
    cards_dir = work / "cards"
    cards_dir.mkdir()
    reg = registry_mod.Registry.open(Path(registry_path) if registry_path
                                     else work / "registry.jsonl")
    forge = Forge.init(work / "forge")
    issue = forge.create_issue("Order: factor mining", order_text)
    log(f"[0] order      issue #{issue}, budget={budget}, family={family!r}, "
        f"roles={list(roles)}, debate_rounds={debate_rounds}, "
        f"snapshot {info.manifest_hash[:12]}…")

    history: list[dict[str, Any]] = []
    summary_iterations: list[dict[str, Any]] = []
    hyp_base = sum(1 for en in reg.entries if en.get("type") == "hypothesis")
    exp_base = sum(1 for en in reg.entries if en.get("type") == "experiment")

    for it in range(1, budget + 1):
        record: dict[str, Any] = {"iteration": it}
        hyp_id = f"H-{hyp_base + it:04d}"
        exp_id = f"E-{exp_base + it:04d}"
        # -- 1) hypothesis ------------------------------------------------
        try:
            draft = extract_json(llm.complete(
                SYSTEM_HYPOTHESIS,
                f"{order_text}\n\n{_history_block(history)}\n\nWindow: "
                f"{full_window}. Propose the next hypothesis."))
        except LLMError as exc:
            record.update({"stage": "hypothesis_parse", "blocked": str(exc)})
            summary_iterations.append(record)
            history.append(record)
            continue
        h = {
            "schema": "hypothesis",
            "hyp_id": hyp_id,
            "mechanism": draft.get("mechanism", ""),
            "falsifiable_condition": draft.get("falsifiable_condition", ""),
            "admission": draft.get("admission") or {
                "required_metrics": REQUIRED_METRICS_DEFAULT,
                "thresholds": THRESHOLDS_DEFAULT, "min_observations": 30},
            "window": full_window,
            "family": family,
            "ttl_days": 90,
            "status": "registered",
            "created_at": as_of_iso,
        }
        if settlement_ledger is not None:
            if cal_mult != 1.0:  # the reflection loop tightens; never loosens
                for spec in (h["admission"].get("thresholds") or {}).values():
                    if isinstance(spec.get("value"), (int, float)):
                        spec["value"] = round(spec["value"] * cal_mult, 6)
            h["calibration"] = {"multiplier": cal_mult, "basis": cal_basis}
        if draft.get("oos_window"):
            h["oos_window"] = draft["oos_window"]  # schema-validated next
        errs = validate_card(h, hyp_id)
        if errs:
            record.update({"stage": "hypothesis_schema", "blocked": errs})
            summary_iterations.append(record)
            history.append(record)
            log(f"[{it}] hypothesis  BLOCKED at schema: {errs[0]}")
            continue
        if "data" in roles:  # mechanical duty of the data role
            d_errs = roles_mod.data_check(h, snapshot_dir)
            if d_errs:
                record.update({"stage": "data_check", "blocked": d_errs})
                summary_iterations.append(record)
                history.append(record)
                log(f"[{it}] data        BLOCKED design: {d_errs[0]}")
                continue
        try:
            reg.register_hypothesis(h)
        except registry_mod.RegistryError as exc:
            record.update({"stage": "hypothesis_registry", "blocked": str(exc)})
            summary_iterations.append(record)
            history.append(record)
            continue
        (cards_dir / f"{hyp_id}.json").write_bytes(canonical_json(h) + b"\n")

        # -- 2) factor code ------------------------------------------------
        try:
            code = _strip_fences(llm.complete(
                SYSTEM_FACTOR, f"Implement the factor for {h['hyp_id']}: "
                f"{h['mechanism']}\nData: closes {{ticker: {{date: close}}}}, "
                f"{info.manifest['tickers']} tickers, {info.manifest['days']} days."))
        except LLMError as exc:
            record.update({"stage": "factor_llm", "blocked": str(exc)})
            summary_iterations.append(record)
            history.append(record)
            log(f"[{it}] factor      BLOCKED at llm: {str(exc)[:90]}")
            continue
        try:
            full_frame = engine.load_frame(snapshot_dir)
            matrix = run_factor(code, full_frame.closes, full_frame.tickers,
                                full_frame.dates)
            frame = engine.load_frame(snapshot_dir, h["window"])
            metrics = engine.evaluate_signal(frame, matrix)
        except SandboxError as exc:
            record.update({"stage": "factor_sandbox", "blocked": str(exc)})
            summary_iterations.append(record)
            history.append(record)
            log(f"[{it}] factor      BLOCKED in sandbox: {str(exc)[:90]}")
            continue

        # -- 3) mechanical verdict (deflated by ledger) ---------------------
        n_trials = reg.n_trials(family) + 1
        verdict, reasons = deflation.deflated_evaluate(h["admission"], metrics,
                                                       n_trials)

        # -- 4) one-shot OOS if declared and IS passed ----------------------
        oos_block: dict[str, Any] | None = None
        if verdict == "pass" and h.get("oos_window"):
            oos_frame = engine.load_frame(snapshot_dir, h["oos_window"])
            oos_metrics = engine.evaluate_signal(oos_frame, matrix)
            oos_verdict, oos_reasons = deflation.deflated_evaluate(
                h["admission"], oos_metrics, 1)
            oos_block = {"window": h["oos_window"], "metrics": oos_metrics,
                         "verdict": oos_verdict, "reasons": oos_reasons}
            if oos_verdict != "pass":
                verdict = "fail"

        # -- 4b) risk veto (mechanical duty of the risk role) ----------------
        risk_result: dict[str, Any] | None = None
        if verdict == "pass" and "risk" in roles:
            risk_result = roles_mod.risk_check(code, snapshot_dir, h, metrics)
            if not risk_result["neighborhood_stable"]:
                verdict = "fail"
                reasons = list(reasons) + [
                    f"risk veto: {risk_result['reason']}"]

        # -- 4c) adversarial review before admission (v0.4) -------------------
        review_block: dict[str, Any] | None = None
        review_cards: list[dict[str, Any]] = []
        if verdict == "pass" and debate_rounds > 0:
            if risk_result is None:  # risk role absent: compute the fact anyway
                risk_result = roles_mod.risk_check(code, snapshot_dir, h, metrics)
            mechanics = {"halves_stability": risk_result["neighborhood_stable"],
                         "oos_pass": True,  # an OOS fail never reaches review
                         "window_alignment": True}  # the gate enforces this
            bull_by = "factor" if "factor" in roles else "manager"
            bear_by = "risk" if "risk" in roles else "manager"
            context = (f"Candidate {exp_id} for {h['hyp_id']}: "
                       f"{h['mechanism']}\nmetrics: {json.dumps(metrics, sort_keys=True)}\n"
                       f"mechanical facts (computed by the gate, not arguable): "
                       f"{json.dumps(mechanics, sort_keys=True)}\n"
                       f"oos: {json.dumps((oos_block or {}), sort_keys=True, default=str)}")
            try:
                for rnd in range(1, debate_rounds + 1):
                    bull = review_mod.parse_review(
                        llm.complete(review_mod.SYSTEM_BULL,
                                     f"{context}\nRound {rnd}: make the bull case."),
                        side="bull", expected_round=rnd, exp_id=exp_id,
                        reviewer=bull_by, as_of_iso=as_of_iso)
                    bear = review_mod.parse_review(
                        llm.complete(review_mod.SYSTEM_BEAR,
                                     f"{context}\nRound {rnd}: make the bear case."),
                        side="bear", expected_round=rnd, exp_id=exp_id,
                        reviewer=bear_by, as_of_iso=as_of_iso)
                    bull["review_id"] = reg.next_review_id()
                    reg.record_review(bull)
                    bear["review_id"] = reg.next_review_id()
                    reg.record_review(bear)
                    review_cards += [bull, bear]
            except LLMError as exc:
                record.update({"stage": "review", "hyp_id": h["hyp_id"],
                               "verdict": verdict, "blocked": str(exc)})
                summary_iterations.append(record)
                history.append(record)
                log(f"[{it}] review      BLOCKED at llm: {str(exc)[:90]}")
                continue
            for rc in review_cards:
                (cards_dir / f"{rc['review_id']}.json").write_bytes(
                    canonical_json(rc) + b"\n")
            admitted, report = review_mod.review_gate(
                {"exp_id": exp_id}, h, review_cards, debate_rounds, mechanics)
            review_block = {"rounds": debate_rounds, "admitted": admitted,
                            "upheld_objections": report["upheld_objections"],
                            "review_ids": report["review_ids"]}
            if not admitted:
                verdict = "fail"
                reasons = list(reasons) + [
                    f"review veto: "
                    f"{report['upheld_objections'] or report['structure_errors']}"]
                log(f"[{it}] review      VETO "
                    f"{report['upheld_objections'] or report['structure_errors']}")
            else:
                log(f"[{it}] review      admitted after {debate_rounds} round(s); "
                    f"dismissed bear objections: {len(report['dismissed_objections'])}")

        e = {
            "schema": "experiment_result",
            "exp_id": exp_id,
            "hyp_id": h["hyp_id"],
            "window": h["window"],
            "snapshot_hash": info.manifest_hash,
            "engine": engine.EVAL_ID,
            "metrics": metrics,
            "attribution": {"iteration": it, "n_trials": n_trials},
            "factor_code": code,
            "factor_code_sha256": sha256_bytes(code.encode("utf-8")),
            "verdict": verdict,
            "settled_at": as_of_iso,
        }
        if risk_result is not None and verdict == "fail" and \
                not risk_result["neighborhood_stable"]:
            e["attribution"]["neighborhood_stable"] = False
            e["attribution"]["neighborhood_rankic"] = \
                risk_result["neighborhood_rankic"]
        if oos_block:
            e["oos"] = oos_block
        if review_block is not None:
            e["review"] = review_block
        (cards_dir / f"{exp_id}.json").write_bytes(canonical_json(e) + b"\n")

        # -- 5) the gate as CI, then merge, then settle ---------------------
        branch = f"research/{h['hyp_id']}"
        committed = {
            f"cards/{h['hyp_id']}.json": (cards_dir / f"{hyp_id}.json").read_text("utf-8"),
            f"cards/{e['exp_id']}.json": (cards_dir / f"{exp_id}.json").read_text("utf-8"),
        }
        for rc in review_cards:
            committed[f"cards/{rc['review_id']}.json"] = \
                (cards_dir / f"{rc['review_id']}.json").read_text("utf-8")
        forge.commit(branch, f"cards: {h['hyp_id']} + {e['exp_id']}", committed)
        root = Path(__file__).resolve().parents[1]
        ci_cmd = [sys.executable, "-m", "qsa.verify",
                  "--hypothesis", str(cards_dir / f"{hyp_id}.json"),
                  "--result", str(cards_dir / f"{exp_id}.json"),
                  "--snapshot", str(snapshot_dir),
                  "--registry", str(reg.path)]
        if settlement_ledger is not None:
            ci_cmd += ["--settlement", str(settlement_ledger)]
        check = forge.push(branch, ci_cmd, cwd=root)
        pr = forge.create_pr(f"{h['hyp_id']}: {h['mechanism'][:60]}", head=branch)
        merged = forge.merge_pr(pr)
        if not merged:
            record.update({"stage": "gate", "hyp_id": h["hyp_id"],
                           "verdict": verdict, "metrics": metrics,
                           "blocked": check["output_tail"]})
            summary_iterations.append(record)
            history.append(record)
            log(f"[{it}] gate        BLOCKED merge: "
                f"{'; '.join(check['output_tail'])[:100]}")
            continue
        settled_trial = reg.settle_experiment(e, h)
        assert settled_trial == n_trials, "ledger trial count diverged from gate"

        # -- 6) attribution feeds the next prompt ---------------------------
        attr = attribution_mod.classify(e, h, reasons)
        record.update({"hyp_id": h["hyp_id"], "exp_id": e["exp_id"],
                       "verdict": verdict, "metrics": metrics,
                       "n_trials": n_trials, "merged": True,
                       "attribution": attr})
        summary_iterations.append(record)
        history.append(record)
        log(f"[{it}] settled     {e['exp_id']} verdict={verdict} "
            f"(N={n_trials}) attribution={attr['class']}")
        if verdict == "pass":
            break

    final = next((r for r in reversed(summary_iterations) if r.get("settled") or
                  r.get("merged")), None)
    verdicts = [r.get("verdict") for r in summary_iterations if r.get("merged")]
    forge.add_comment(issue, (
        f"Mining complete: {len(summary_iterations)} iteration(s) under budget "
        f"{budget}. Settled verdicts: {verdicts or ['none']}. "
        f"Blocked attempts: "
        f"{sum(1 for r in summary_iterations if r.get('blocked'))}. "
        f"Final: {json.dumps((final or {}).get('attribution', {}), sort_keys=True)}"))
    log(f"[+] done       iterations={len(summary_iterations)}, "
        f"verdicts={verdicts or 'none'}, ledger={work / 'registry.jsonl'}")
    return {"iterations": summary_iterations, "final_verdict":
            verdicts[-1] if verdicts else None, "issue": issue,
            "admitted": bool(verdicts and verdicts[-1] == "pass")}
