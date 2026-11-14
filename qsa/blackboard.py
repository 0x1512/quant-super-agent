"""Blackboard — cross-session team memory (v1.2).

Everything v1.0/v1.1 learned died in one agent's session: the tushare
field-name trap, the elastic rate-limit behavior, the truncated-pickle
crash, the factor-decay observations. A single-session agent (any codex)
re-learns all of it, expensively. The blackboard makes those lessons
first-class organizational assets:

* ``data_pitfall``  — a trap in the data layer + the defense that fixed it
* ``decay_event``   — a factor/regime dying, with the numbers that showed it
* ``convention_decision`` — a fork that was decided, by whom, why
* ``order_note``    — anything an order's successor must know

Discipline (what makes it a blackboard and not a log):

* entries are append-only JSONL with content hashes — a tampered board
  is detectable the same way a tampered snapshot is;
* ``require_clear()`` lets the infra gate refuse to start work while an
  unresolved ``blocker`` entry is on the board;
* ``bootstrapped()`` seeds the board with the project's real, paid-for
  lessons (each one cost actual hours on 2026-11-13/14) so the memory
  starts non-empty and every claim is checkable in git history.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

KINDS = ("data_pitfall", "decay_event", "convention_decision", "order_note")


def _now() -> float:
    return time.time()


class Blackboard:
    """Append-only board persisted as JSONL; hash-chained like the ledger."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.touch()
        self._entries: list[dict[str, Any]] = [
            json.loads(ln) for ln in
            self.path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        self._verify_chain()

    # -- chain integrity -------------------------------------------------
    def _verify_chain(self) -> None:
        prev = ""
        for i, e in enumerate(self._entries):
            expect = hashlib.sha256(
                (prev + json.dumps(
                    {k: v for k, v in e.items() if k != "chain"},
                    sort_keys=True, ensure_ascii=False)).encode()
            ).hexdigest()
            if e.get("chain") != expect:
                raise ValueError(
                    f"blackboard chain broken at entry {i} — tampered board")
            prev = expect

    # -- write -----------------------------------------------------------
    def post(self, kind: str, title: str, body: str, *,
             status: str = "info", tags: list[str] | None = None,
             resolves: int | None = None) -> dict:
        if kind not in KINDS:
            raise ValueError(f"kind must be one of {KINDS}, got {kind}")
        prev = (self._entries[-1].get("chain")
                if self._entries else "")
        entry = {"kind": kind, "title": title, "body": body,
                 "status": status, "tags": tags or [],
                 "posted_at": _now()}
        if resolves is not None:
            entry["resolves"] = resolves
        entry["chain"] = hashlib.sha256(
            (prev + json.dumps(entry, sort_keys=True,
                               ensure_ascii=False)).encode()).hexdigest()
        self._entries.append(entry)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return entry

    def resolve(self, index: int) -> dict:
        """Mark a blocker as resolved (append-only: adds a linked note,
        never rewrites history). The note carries ``resolves=<index>``;
        ``blockers()`` then skips it until that note appears."""
        e = self._entries[index]
        if e.get("status") != "blocker":
            raise ValueError(f"entry {index} is not a blocker")
        return self.post("order_note", f"RESOLVED: {e['title']}",
                         f"blocker #{index} cleared", status="info",
                         resolves=index)

    def _resolved_indices(self) -> set[int]:
        return {e["resolves"] for e in self._entries
                if "resolves" in e}

    def blockers(self) -> list[dict[str, Any]]:
        done = self._resolved_indices()
        return [e for i, e in enumerate(self._entries)
                if e["status"] == "blocker" and i not in done]

    # -- read ------------------------------------------------------------
    def entries(self, kind: str | None = None,
                status: str | None = None) -> list[dict[str, Any]]:
        out = self._entries
        if kind:
            out = [e for e in out if e["kind"] == kind]
        if status:
            out = [e for e in out if e["status"] == status]
        return out

    def search(self, text: str) -> list[dict[str, Any]]:
        t = text.lower()
        return [e for e in self._entries
                if t in e["title"].lower() or t in e["body"].lower()]

    def require_clear(self) -> None:
        """Raise if any unresolved blocker is on the board. The infra
        gate calls this before admitting new work."""
        bs = self.blockers()
        if bs:
            titles = "; ".join(b["title"] for b in bs)
            raise RuntimeError(f"blackboard has unresolved blockers: {titles}")

    def __len__(self) -> int:
        return len(self._entries)


def bootstrapped(path: Path) -> Blackboard:
    """Seed the board with the project's real, paid-for lessons.

    Each entry below maps to an actual incident in this repo's history
    (fetch v1/v2/v3 crashes on 2026-11-13/14; the cap_proxy decision;
    the Scenario-A decay finding). They are the reason the infra gate
    and the atomic-dump defenses exist.
    """
    bb = Blackboard(path)
    if len(bb) > 0:
        return bb
    bb.post("data_pitfall",
            "tushare daily: pre-close field is pre_close, NOT preclose",
            "Requesting 'preclose' is silently dropped: 7.2M rows came "
            "back 8-wide with no error. Cost: a full 40-min re-fetch. "
            "Defense: builder asserts row width == 9 before chaining hfq.",
            status="info", tags=["tushare", "schema"])
    bb.post("data_pitfall",
            "tushare low-credit token: elastic rate limit (per-minute "
            "-> per-hour after quota burn)",
            "daily_basic/stock_basic degrade from 1/min to 1/hour once "
            "the day's quota is spent, with no schedule published. "
            "Defense: exponential backoff + persistent cache + the "
            "cap_proxy convention decision below.",
            status="info", tags=["tushare", "ratelimit"])
    bb.post("data_pitfall",
            "long fetch killed mid-dump leaves a truncated pickle",
            "pickle.load -> EOFError; 47MB cache lost. Defense: atomic "
            "writes (tmp + os.replace) — a killed run never truncates.",
            status="info", tags=["fetch", "persistence"])
    bb.post("data_pitfall",
            "nohup background workers get reaped with the tool's "
            "process group",
            "Silent death ~10-30s in, empty log, no traceback. Defense: "
            "run long fetches as managed tasks, not detached shells.",
            status="info", tags=["ops"])
    bb.post("convention_decision",
            "cap_proxy = monthly mean traded value (replaces total_mv)",
            "daily_basic (total_mv) is unfetchable at this token's rate "
            "limit (63 month-ends x 1/hour is not a plan). Decided "
            "2026-11-13: neutralization uses ln(mean daily amount), "
            "declared in the H-card convention table, not hidden.",
            status="info", tags=["convention", "neutralization"])
    bb.post("convention_decision",
            "universe = top-300 by 2021-H1 mean daily amount",
            "Chosen from the data itself (rebuildable by anyone), fixed "
            "before the sample window to avoid look-ahead. Fork card "
            "BB-FORK-02 re-examines full-market vs CSI500/1000 variants.",
            status="info", tags=["convention", "universe"])
    bb.post("decay_event",
            "overnight_gap_21d decays post-2023 (Scenario-A verdict)",
            "Half-sample raw IC: front -0.056 / back -0.040; D1/D2 fail, "
            "verdict not_replicated on 2021-07..2026-06. Not a bug: "
            "attributed to sample period + universe per D3.",
            status="info", tags=["decay", "scenarioA"])
    bb.post("decay_event",
            "public-literature factors are collectively OOS-dead on the "
            "2021-2026 top-300 sample",
            "v1.1 zoo run: 17/24 factors with oos IC <= 0.03; leaders "
            "show train 0.10+ -> oos -0.01..-0.05. Survivors: mom_gap_12m "
            "(oos +0.073), dist_52w_high (+0.076), vol_of_vol (+0.040).",
            status="info", tags=["decay", "zoo"])
    return bb
