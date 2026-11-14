"""Infra gate + fork briefing cards (v1.2).

infra_gate: the pre-flight check the 2026-11-13 fetch disasters proved
we needed. Three crashes (truncated pickle, reaped workers, elastic
rate-limit lockout) each cost 30-60 minutes because work started before
the data layer's health was known. The gate refuses to admit orders
until the pinned fixtures verify and the blackboard has no unresolved
blocker — every check offline, deterministic, and honest about WHY.

fork_card: research forks (universe choice, cost assumptions, verdict
bandwidth) were decided silently by one agent's defaults — exactly the
anti-pattern the project's own zero-silent-conventions rule forbids.
A fork card makes the fork VISIBLE: question, options with stated
impact, a recommended default, and a decided-by field. Undecided forks
are surfaced by the demo; decided ones are append-only records.

Both are deliberately boring, stdlib-only, and testable — that is the
point: a gate you cannot test is a gate you route around.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from .blackboard import Blackboard

# ---------------------------------------------------------------- infra gate


def infra_gate(fixture_dir: Path, board: Blackboard,
               min_main_rows: int = 300_000) -> dict[str, Any]:
    """Offline pre-flight: refuse work when the data plane is not sound.

    Checks (each independent, each with a human-readable failure):
      1. main fixture exists, row count sane, header as pinned
      2. tail fixture exists (settlement horizon)
      3. cap-proxy meta present and non-empty
      4. universe json parses to TOP_N tickers
      5. blackboard carries no unresolved blocker
    Returns {"ok": bool, "checks": [...]} — the caller prints it; the
    order book refuses to admit orders when not ok.
    """
    checks: list[dict[str, Any]] = []

    def record(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "ok": ok, "detail": detail})

    main = fixture_dir / "ashare_top300_main.csv"
    if main.exists():
        with main.open(encoding="utf-8") as fh:
            header = fh.readline().strip()
            n = sum(1 for _ in fh)
        record("main fixture", n >= min_main_rows,
               f"{main.name}: {n} rows (min {min_main_rows}), "
               f"header='{header}'")
    else:
        record("main fixture", False, f"missing: {main}")

    tail = fixture_dir / "ashare_top300_tail.csv"
    if tail.exists():
        with tail.open(encoding="utf-8") as fh:
            fh.readline()
            n = sum(1 for _ in fh)
        record("tail fixture", n > 0, f"{tail.name}: {n} rows")
    else:
        record("tail fixture", False, f"missing: {tail}")

    caps = fixture_dir / "replication_meta" / "monthly_caps.csv"
    if caps.exists():
        with caps.open(encoding="utf-8") as fh:
            fh.readline()
            n = sum(1 for _ in fh)
        record("cap-proxy meta", n > 0, f"monthly_caps.csv: {n} rows")
    else:
        record("cap-proxy meta", False, f"missing: {caps}")

    uni = fixture_dir / "ashare_top300_universe.json"
    if uni.exists():
        try:
            data = json.loads(uni.read_text(encoding="utf-8"))
            n_tk = len(data.get("tickers", []))
            record("universe", n_tk == 300,
                   f"{n_tk} tickers, rule='{data.get('rule', '?')}'")
        except json.JSONDecodeError as e:
            record("universe", False, f"unparsable json: {e}")
    else:
        record("universe", False, f"missing: {uni}")

    blockers = board.blockers()
    record("blackboard clear", not blockers,
           f"{len(blockers)} unresolved blocker(s)"
           if blockers else "no unresolved blockers")

    return {"ok": all(c["ok"] for c in checks), "checks": checks,
            "checked_at": time.time()}


def render_gate(report: dict[str, Any]) -> str:
    mark = lambda ok: "PASS" if ok else "FAIL"  # noqa: E731
    lines = [f"infra gate: {'OPEN' if report['ok'] else 'SHUT'}",
             "-" * 60]
    for c in report["checks"]:
        lines.append(f"  [{mark(c['ok'])}] {c['name']}: {c['detail']}")
    return "\n".join(lines)


# ---------------------------------------------------------------- fork cards


class ForkCards:
    """Append-only registry of research forks and their decisions."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.touch()
        self.cards: dict[str, dict[str, Any]] = {}
        for ln in self.path.read_text(encoding="utf-8").splitlines():
            if ln.strip():
                ev = json.loads(ln)
                if ev["type"] == "fork":
                    self.cards[ev["fork_id"]] = ev
                elif ev["type"] == "decision":
                    self.cards[ev["fork_id"]]["decision"] = ev

    def _append(self, ev: dict[str, Any]) -> None:
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(ev, ensure_ascii=False) + "\n")

    def raise_fork(self, fork_id: str, question: str,
                   options: list[dict[str, str]],
                   recommended: str, default: str) -> dict[str, Any]:
        if fork_id in self.cards:
            return self.cards[fork_id]
        ev = {"type": "fork", "fork_id": fork_id, "question": question,
              "options": options, "recommended": recommended,
              "default": default, "raised_at": time.time()}
        self.cards[fork_id] = ev
        self._append(ev)
        return ev

    def decide(self, fork_id: str, choice: str, by: str,
               rationale: str) -> dict[str, Any]:
        card = self.cards.get(fork_id)
        if card is None:
            raise ValueError(f"unknown fork {fork_id}")
        if "decision" in card:
            raise ValueError(
                f"{fork_id} already decided "
                f"({card['decision']['choice']}) — append-only registry")
        labels = [o["label"] for o in card["options"]] + [card["default"]]
        if choice not in labels:
            raise ValueError(f"{choice} not among options {labels}")
        ev = {"type": "decision", "fork_id": fork_id, "choice": choice,
              "by": by, "rationale": rationale, "decided_at": time.time()}
        card["decision"] = ev
        self._append(ev)
        return card

    def open_forks(self) -> list[dict[str, Any]]:
        return [c for c in self.cards.values() if "decision" not in c]

    def digest(self, fork_id: str) -> str:
        """Stable short hash tying an order to the forks it depends on."""
        c = self.cards.get(fork_id)
        if c is None:
            return ""
        body = {k: c[k] for k in ("question", "options", "recommended")}
        return hashlib.sha256(json.dumps(body, sort_keys=True,
                                         ensure_ascii=False).encode()
                              ).hexdigest()[:10]


def bootstrap_forks(path: Path) -> ForkCards:
    """The forks v1.0/v1.1 actually faced — now visible instead of silent."""
    fc = ForkCards(path)
    fc.raise_fork(
        "BB-FORK-01",
        "neutralization size variable when total_mv is unfetchable?",
        [{"label": "cap_proxy = mean daily amount", "impact": "offline, "
          "rebuildable, declared substitution"},
         {"label": "wait for daily_basic quota (1/hour x 63 months)",
          "impact": "3 days of wall clock for exact market cap"}],
        recommended="cap_proxy = mean daily amount",
        default="cap_proxy = mean daily amount")
    if "decision" not in fc.cards["BB-FORK-01"]:
        fc.decide("BB-FORK-01", "cap_proxy = mean daily amount",
                  by="principal", rationale="63 sequential hourly calls "
                  "is not a plan; proxy declared in H-card table")
    fc.raise_fork(
        "BB-FORK-02",
        "stock universe for screening?",
        [{"label": "top-300 by 2021-H1 amount", "impact": "large caps, "
          "high pricing efficiency, conservative"},
         {"label": "full market ex-ST", "impact": "wider alpha, more "
          "noise, suspension handling needed"},
         {"label": "CSI-500/1000 slice", "impact": "mid/small caps where "
          "literature factors usually live longer"}],
        recommended="top-300 by 2021-H1 amount",
        default="top-300 by 2021-H1 amount")
    if "decision" not in fc.cards["BB-FORK-02"]:
        fc.decide("BB-FORK-02", "top-300 by 2021-H1 amount",
                  by="principal", rationale="data we already pinned; "
                  "widening is the next experiment (zoo tracks it)")
    fc.raise_fork(
        "BB-FORK-03",
        "one-sided cost assumption for tradeable metrics?",
        [{"label": "8 bps (commission+stamp+slippage, industry common)",
          "impact": "conservative for large caps"},
         {"label": "5 bps", "impact": "optimistic; assumes best execution"}],
        recommended="8 bps", default="8 bps")
    if "decision" not in fc.cards["BB-FORK-03"]:
        fc.decide("BB-FORK-03", "8 bps (commission+stamp+slippage, industry common)",
                  by="principal", rationale="conservative default; "
                  "explicit parameter, re-runnable")
    return fc
