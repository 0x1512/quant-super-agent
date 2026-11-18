"""Bull/bear adversarial review — structured claims, mechanical aggregation.

Before a passing candidate is admitted, it survives ``debate_rounds`` rounds
of adversarial review (v0.4; rounds configurable, 0 disables). The debate is
LLM-voiced but not LLM-decided:

* each reviewer emits a structured **R card**: a list of claims, each either
  rhetorical (``checkable: false``) or machine-checkable (``check`` names a
  fact the gate computes itself — half-split stability, OOS verdict, window
  alignment);
* a **bear** objection is *upheld* only if its check actually fails — bears
  cannot veto on rhetoric;
* **bull** claims can rebut but never admit; an unverified bull claim is
  recorded as note, a refuted one as a credibility mark;
* admission = every round produced one bull + one bear card AND no upheld
  bear objection. Deterministic, replayable, boring on purpose.

R cards are append-only ledger entries, so the debate that admitted (or
killed) a factor is part of its permanent evidence trail.
"""
from __future__ import annotations

from typing import Any

from .llm import LLMError, extract_json

SYSTEM_BULL = (
    "You are the bull reviewer: advocate for admitting this factor. Respond "
    "with a single JSON object {\"side\": \"bull\", \"claims\": [{\"kind\": "
    "\"mechanism\"|\"statistical\"|\"robustness\"|\"data\", \"statement\": "
    "string, \"checkable\": bool, \"check\": null|\"halves_stability\"|"
    "\"oos_pass\"|\"window_alignment\"}]}. A checkable claim asserts the named "
    "check PASSES; the gate verifies it mechanically and your claim carries "
    "no weight unless it does. At least one claim is required.")

SYSTEM_BEAR = (
    "You are the bear reviewer: hunt for the reason this factor must NOT be "
    "admitted. Respond with a single JSON object {\"side\": \"bear\", "
    "\"claims\": [{\"kind\": \"mechanism\"|\"statistical\"|\"robustness\"|"
    "\"data\", \"statement\": string, \"checkable\": bool, \"check\": null|"
    "\"halves_stability\"|\"oos_pass\"|\"window_alignment\"}]}. A checkable "
    "claim asserts the named check FAILS; the gate upholds your objection "
    "only if the check verifiably fails — rhetoric never vetoes. At least one "
    "claim is required.")

KNOWN_CHECKS = ("halves_stability", "oos_pass", "window_alignment")


def build_review_card(*, review_id: str, exp_id: str, side: str, rnd: int,
                      claims: list[dict[str, Any]], reviewer: str,
                      as_of_iso: str) -> dict[str, Any]:
    return {"schema": "review", "review_id": review_id, "exp_id": exp_id,
            "side": side, "round": rnd, "reviewer": reviewer,
            "claims": claims, "created_at": as_of_iso}


def parse_review(text: str, *, side: str, expected_round: int, exp_id: str,
                 reviewer: str, as_of_iso: str) -> dict[str, Any]:
    """Parse one LLM review utterance into an R card, or raise LLMError."""
    draft = extract_json(text)
    if not isinstance(draft, dict):
        raise LLMError(f"review for {exp_id} round {expected_round}: not a JSON object")
    if draft.get("side") not in ("bull", "bear"):
        raise LLMError(f"review side must be 'bull' or 'bear', got {draft.get('side')!r}")
    if draft["side"] != side:
        raise LLMError(f"reviewer answered for side {draft['side']!r}, expected {side!r}")
    claims = draft.get("claims")
    if not isinstance(claims, list) or not claims:
        raise LLMError(f"{side} review for {exp_id}: claims must be a non-empty list")
    clean: list[dict[str, Any]] = []
    for c in claims:
        if not isinstance(c, dict) or not isinstance(c.get("statement"), str):
            raise LLMError(f"{side} review: claim without a statement")
        check = c.get("check")
        if check is not None and check not in KNOWN_CHECKS:
            raise LLMError(f"{side} review: unknown check {check!r} "
                           f"(known: {list(KNOWN_CHECKS)})")
        clean.append({"kind": str(c.get("kind", "statistical")),
                      "statement": c["statement"],
                      "checkable": bool(c.get("checkable")) and check is not None,
                      "check": check})
    rnd = draft.get("round", expected_round)
    if not isinstance(rnd, int) or rnd != expected_round:
        raise LLMError(f"review round {rnd!r} != expected {expected_round}")
    return build_review_card(review_id=draft.get("review_id") or "",
                             exp_id=exp_id, side=side, rnd=rnd,
                             claims=clean, reviewer=reviewer,
                             as_of_iso=as_of_iso)


def review_gate(e: dict[str, Any], h: dict[str, Any],
                reviews: list[dict[str, Any]], rounds: int,
                mechanics: dict[str, bool]) -> tuple[bool, dict[str, Any]]:
    """Mechanically aggregate a debate. Returns (admitted, report).

    ``mechanics`` carries the facts the gate computed itself, e.g.
    ``{"halves_stability": True, "oos_pass": True, "window_alignment": True}``.
    """
    upheld: list[dict[str, Any]] = []
    dismissed: list[dict[str, Any]] = []
    refuted_bull: list[dict[str, Any]] = []
    structure_errors: list[str] = []

    for rnd in range(1, rounds + 1):
        for side in ("bull", "bear"):
            card = next((r for r in reviews
                         if r.get("round") == rnd and r.get("side") == side), None)
            if card is None:
                structure_errors.append(f"round {rnd}: missing {side} review")

    for r in reviews:
        for c in r.get("claims", []):
            entry = {"review_id": r.get("review_id"), "side": r["side"],
                     "round": r["round"], "statement": c["statement"],
                     "check": c["check"]}
            if not c["checkable"] or c["check"] is None:
                continue  # rhetoric: recorded on the card, decides nothing
            fact = mechanics.get(c["check"])
            if fact is None:
                structure_errors.append(
                    f"{r['side']} round {r['round']}: check {c['check']!r} "
                    f"has no mechanical fact behind it")
            elif r["side"] == "bear" and fact is False:
                upheld.append(entry)          # bear said it fails; it does
            elif r["side"] == "bear" and fact is True:
                dismissed.append(entry)       # bear said it fails; it doesn't
            elif r["side"] == "bull" and fact is False:
                refuted_bull.append(entry)    # bull said it passes; it doesn't

    admitted = (not structure_errors) and (not upheld)
    report = {"rounds": rounds, "admitted": admitted,
              "upheld_objections": upheld, "dismissed_objections": dismissed,
              "refuted_bull_claims": refuted_bull,
              "structure_errors": structure_errors,
              "review_ids": [r.get("review_id") for r in reviews]}
    return admitted, report
