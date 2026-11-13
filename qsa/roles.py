"""Quant roles — ablatable workers, each with a persona AND a mechanical duty.

v0.4 makes the role split a *dial, not dogma*: an order runs with a subset of
roles, and the ablation harness measures what each subset costs and buys
(``qsa.ablation``). To keep that honest, a role is never just a prompt:

* the **prompt half** steers the LLM (persona, duties, what it may not do);
* the **mechanical half** is code the loop runs regardless of what the LLM
  "believes" — the data role's provenance checks and the risk role's
  robustness veto are functions, not opinions.

The factor role proposes; the ledger, sandbox and gate dispose. Roles only
add disciplined eyes, never discretion over the verdict.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from . import engine
from .sandbox import SandboxError, run_factor


@dataclass(frozen=True)
class RoleSpec:
    name: str
    system: str
    duty: str


ROLES: dict[str, RoleSpec] = {
    "data": RoleSpec(
        name="data",
        system="You are the data engineer. You own snapshot integrity and "
               "point-in-time discipline. You never propose factors; you "
               "certify that a hypothesis's window, OOS stretch and minimum "
               "observations are well-formed against the snapshot before "
               "anything is registered.",
        duty="window/OOS provenance + power feasibility, pre-registration"),
    "factor": RoleSpec(
        name="factor",
        system="You are the factor analyst. You propose falsifiable "
               "hypotheses with pre-committed admission bars and implement "
               "them as sandboxed cross-sectional factors. You never lower a "
               "bar to rescue a rejected direction.",
        duty="hypothesis + factor code, under the order's constraints"),
    "risk": RoleSpec(
        name="risk",
        system="You are the risk reviewer. Before a candidate is admitted "
               "you demand robustness: the signal must keep its sign and a "
               "material share of its strength across sub-windows. You veto "
               "on measured instability, not on taste.",
        duty="half-split stability veto at admission"),
    "manager": RoleSpec(
        name="manager",
        system="You are the research manager. You hold the iteration budget, "
               "refuse zombie retries, and only send candidates that survived "
               "the mechanical layers on to adversarial review.",
        duty="budget + admission proposal (the loop itself)"),
}

DEFAULT_ROLES = ("data", "factor", "risk", "manager")


def check_roles(roles: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    unknown = [r for r in roles if r not in ROLES]
    if unknown:
        raise ValueError(f"unknown roles {unknown}; known: {sorted(ROLES)}")
    if "factor" not in roles:
        raise ValueError("the factor role is mandatory in every configuration")
    return tuple(dict.fromkeys(roles))


def data_check(h: dict[str, Any], snapshot_dir: Any) -> list[str]:
    """Mechanical duty of the data role: provenance + power feasibility.

    Runs before the hypothesis is registered — a malformed study design is
    blocked *before* it can burn a ledger trial.
    """
    errors: list[str] = []
    frame = engine.load_frame(snapshot_dir)
    dates = frame.dates

    def _parse(window: str, what: str) -> tuple[str, str] | None:
        try:
            lo, hi = window.split(":")
        except (AttributeError, ValueError):
            errors.append(f"{what} {window!r} is not 'YYYYMMDD:YYYYMMDD'")
            return None
        if lo not in dates or hi not in dates or dates.index(lo) > dates.index(hi):
            errors.append(f"{what} {window!r} not inside snapshot "
                          f"{dates[0]}:{dates[-1]}")
            return None
        return lo, hi

    _parse(h.get("window", ""), "window")
    if h.get("oos_window"):
        _parse(h["oos_window"], "oos_window")

    min_obs = (h.get("admission") or {}).get("min_observations")
    if isinstance(min_obs, int) and min_obs > 0 and not errors:
        lo, hi = h["window"].split(":")
        available = dates.index(hi) - dates.index(lo)
        if available < min_obs:
            errors.append(f"window offers {available} observations, "
                          f"min_observations={min_obs} — underpowered design")
    if not (h.get("mechanism") or "").strip():
        errors.append("mechanism is empty")
    if not (h.get("falsifiable_condition") or "").strip():
        errors.append("falsifiable_condition is empty")
    return errors


def risk_check(code: str, snapshot_dir: Any, h: dict[str, Any],
               full_metrics: dict[str, float]) -> dict[str, Any]:
    """Mechanical duty of the risk role: half-split sign stability.

    The candidate factor is re-evaluated on the first and second halves of
    the pre-registered window. "Stable" means: both halves agree with the
    full-sample sign AND the weaker half keeps at least half the pre-registered
    bar. Anything else is measured instability — a veto, recorded as data,
    never as opinion.
    """
    frame = engine.load_frame(snapshot_dir, h["window"])
    dates = frame.dates
    half = len(dates) // 2
    bar = 0.02
    thresholds = (h.get("admission") or {}).get("thresholds") or {}
    rc = thresholds.get("rankic_mean")
    if isinstance(rc, dict) and isinstance(rc.get("value"), (int, float)):
        bar = abs(float(rc["value"]))
    try:
        matrix = run_factor(code, frame.closes, frame.tickers, frame.dates,
                            frame.volumes, frame.opens)
        first = engine.evaluate_signal(
            engine.load_frame(snapshot_dir, f"{dates[0]}:{dates[half - 1]}"),
            matrix)
        second = engine.evaluate_signal(
            engine.load_frame(snapshot_dir, f"{dates[half]}:{dates[-1]}"),
            matrix)
    except (SandboxError, ValueError) as exc:
        return {"neighborhood_stable": False,
                "neighborhood_rankic": {},
                "reason": f"factor could not be re-evaluated on sub-windows: "
                          f"{str(exc)[:120]}"}
    a, b, c = (full_metrics.get("rankic_mean"), first["rankic_mean"],
               second["rankic_mean"])
    stable = None not in (a, b, c) and a != 0 and (
        (a > 0) == (b > 0) == (c > 0)
        and min(abs(b), abs(c)) >= 0.5 * bar)
    reason = ("sign agreement across halves with material magnitude"
              if stable else
              f"half-split instability: full={a}, first={b}, second={c} "
              f"(bar for the weaker half: {round(0.5 * bar, 4)})")
    return {"neighborhood_stable": bool(stable),
            "neighborhood_rankic": {"first_half": b, "second_half": c},
            "reason": reason}
