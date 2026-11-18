"""Repair ladder — v1.4: classified, pre-registered data repairs.

The showcase promise "中途出错，它自己换路" gets a mechanical floor
here. Ingest violations are CLASSIFIED, and only repairs that are
pre-registered in this module may run; every applied repair is logged
and shows up in the run's research tree and report. Anything without a
policy REFUSES exactly as before — the ladder adds options, never
discretion, and never silently.

Policies (each is a pure function rows->rows, all-or-nothing per
violation class):

* ``missing_tail`` — a ticker's series stops before the panel's last
  date. Policy: TRUNCATE THE PANEL to the longest common calendar this
  violation class allows to be dropped without shrinking the panel below
  ``min_dates``; the affected tickers are recorded, not guessed.
* ``bad_number`` / ``duplicate_pair`` — NO repair policy: refusing is
  the honest move (v1.0 behaviour, unchanged).

Determinism: repairs carry no wall-clock into scoring paths; the repair
LOG may carry elapsed time (it never feeds leaderboards).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

MIN_DATES_AFTER_REPAIR = 60     # pre-declared floor


class IngestViolation(Exception):
    """Unrepairable (or unrepaired) violation — the run refuses."""


@dataclass
class Violation:
    kind: str                 # missing_tail | bad_number | duplicate_pair
    detail: str
    affected: list[str] = field(default_factory=list)


@dataclass
class RepairLog:
    applied: list[dict[str, Any]] = field(default_factory=list)
    refused: list[dict[str, Any]] = field(default_factory=list)
    elapsed_s: float = 0.0

    def render(self) -> str:
        if not self.applied and not self.refused:
            return ""
        out = ["## 数据修复梯（预注册策略）", ""]
        for a in self.applied:
            out.append(f"- ✅ {a['kind']} → {a['policy']}：{a['detail']}")
        for r in self.refused:
            out.append(f"- ⛔ {r['kind']}：无预注册修复策略，拒绝开跑")
        out.append(f"\n（修复耗时 {self.elapsed_s}s，策略白名单之外一律拒绝）")
        return "\n".join(out)


def classify(rows: list[dict[str, Any]]) -> list[Violation]:
    """Detect violations from parsed CSV rows (date,ticker,close,...)."""
    by_tk: dict[str, set[str]] = {}
    seen_pairs: set[tuple[str, str]] = set()
    dup: set[tuple[str, str]] = set()
    bad: list[str] = []
    for r in rows:
        pair = (r["ticker"], r["date"])
        if pair in seen_pairs:
            dup.add(pair)
        seen_pairs.add(pair)
        for col in ("close", "open", "volume"):
            v = r.get(col)
            try:
                float(v)
            except (TypeError, ValueError):
                bad.append(f"{col}={v!r}@{pair}")
        by_tk.setdefault(r["ticker"], set()).add(r["date"])
    out: list[Violation] = []
    if dup:
        out.append(Violation("duplicate_pair", f"{len(dup)} duplicated "
                                               "(ticker,date) pairs",
                             sorted(f"{t}/{d}" for t, d in dup)[:10]))
    if bad:
        out.append(Violation("bad_number", f"{len(bad)} unparseable numbers",
                             bad[:10]))
    if by_tk:
        all_dates = set.intersection(*by_tk.values()) if by_tk else set()
        last_common = max(all_dates) if all_dates else None
        panel_last = max(d for s in by_tk.values() for d in s)
        if last_common != panel_last:
            short = sorted(tk for tk, s in by_tk.items()
                           if max(s) < panel_last)
            out.append(Violation(
                "missing_tail",
                f"{len(short)} ticker(s) stop before panel end "
                f"{panel_last}", short[:10]))
    return out


def _repair_missing_tail(rows: list[dict[str, Any]],
                         v: Violation) -> tuple[list[dict[str, Any]], str]:
    """Truncate the panel to the common calendar (>= MIN_DATES floor)."""
    by_tk: dict[str, set[str]] = {}
    for r in rows:
        by_tk.setdefault(r["ticker"], set()).add(r["date"])
    common = set.intersection(*by_tk.values())
    cut = max(common)
    kept = [r for r in rows if r["date"] <= cut]
    dates_kept = {r["date"] for r in kept}
    if len(dates_kept) < MIN_DATES_AFTER_REPAIR:
        raise IngestViolation(
            f"missing_tail repair would shrink the panel to "
            f"{len(dates_kept)} dates (< {MIN_DATES_AFTER_REPAIR}) — "
            f"refusing instead of guessing")
    return kept, (f"panel truncated to common calendar end {cut} "
                  f"({len(v.affected)} short ticker(s) recorded, "
                  f"{len(dates_kept)} dates kept)")


POLICIES = {"missing_tail": _repair_missing_tail}


def apply_ladder(rows: list[dict[str, Any]],
                 log: RepairLog | None = None) -> tuple[list[dict[str, Any]],
                                                        RepairLog]:
    """Run the ladder: classify -> apply whitelisted policies -> refuse rest.

    Idempotent-ish by construction: applying twice finds no violations
    the second time (the repair removes what it matched).
    """
    log = log or RepairLog()
    t0 = time.perf_counter()
    violations = classify(rows)
    for v in violations:
        policy = POLICIES.get(v.kind)
        if policy is None:
            log.refused.append({"kind": v.kind, "detail": v.detail,
                                "affected": v.affected})
            log.elapsed_s = round(time.perf_counter() - t0, 3)
            raise IngestViolation(
                f"{v.kind}: {v.detail} — no pre-registered repair policy")
        rows, detail = policy(rows, v)
        log.applied.append({"kind": v.kind, "policy": policy.__name__,
                            "detail": detail, "affected": v.affected})
    log.elapsed_s = round(time.perf_counter() - t0, 3)
    return rows, log
