"""Append-only experiment registry — pre-registration order made mechanical.

The registry is the ledger the gate trusts: unique IDs, hypothesis-before-
experiment ordering enforced by construction (a hypothesis must be registered
before its experiments settle), per-family trial counts for deflation, and
one-shot OOS windows (a pre-registered out-of-sample stretch is *consumed*
the first time it is used; any later hypothesis that overlaps it is refused).

Storage is a single JSONL file — one canonical JSON object per line, seq =
line number. No database, no migration, fully deterministic to replay.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .snapshot import canonical_json


class RegistryError(ValueError):
    """Raised for every refusal; the message is gate-report safe."""


def _overlaps(a: tuple[str, str], b: tuple[str, str]) -> bool:
    return a[0] <= b[1] and b[0] <= a[1]


class Registry:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.entries: list[dict[str, Any]] = []
        self._hyp_ids: set[str] = set()
        self._exp_ids: set[str] = set()
        self._families: dict[str, list[str]] = {}   # family -> [exp_id]
        self._oos_consumed: list[tuple[str, str, str]] = []  # (start, end, hyp_id)
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    self._index(json.loads(line))

    @classmethod
    def open(cls, path: Path) -> "Registry":
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch(exist_ok=True)
        return cls(path)

    # -- internal --------------------------------------------------------
    def _index(self, entry: dict[str, Any]) -> None:
        self.entries.append(entry)
        if entry["type"] == "hypothesis":
            self._hyp_ids.add(entry["hyp_id"])
        elif entry["type"] == "experiment":
            self._exp_ids.add(entry["exp_id"])
            self._families.setdefault(entry.get("family", "default"),
                                      []).append(entry["exp_id"])
            if entry.get("oos_window"):
                w = entry["oos_window"]
                self._oos_consumed.append((w.split(":")[0], w.split(":")[1],
                                           entry["hyp_id"]))

    def _append(self, entry: dict[str, Any]) -> None:
        entry["seq"] = len(self.entries) + 1
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(canonical_json(entry).decode("utf-8") + "\n")
        self._index(entry)

    # -- surface ---------------------------------------------------------
    def register_hypothesis(self, h: dict[str, Any]) -> None:
        hyp_id = h.get("hyp_id")
        if not hyp_id:
            raise RegistryError("hypothesis has no hyp_id")
        if hyp_id in self._hyp_ids:
            raise RegistryError(f"hyp_id {hyp_id!r} already registered "
                                f"(IDs are unique forever)")
        if h.get("oos_window"):
            self.check_oos_available(h["oos_window"])
        self._append({"type": "hypothesis", "hyp_id": hyp_id,
                      "family": h.get("family", "default"),
                      "oos_window": h.get("oos_window")})

    def has_hypothesis(self, hyp_id: str) -> bool:
        return hyp_id in self._hyp_ids

    def record_review(self, r: dict[str, Any]) -> None:
        """Append a debate R card (bull/bear) — evidence trail, not a trial.

        Reviews never count toward family trial counts; they are the audit
        record of *how* a candidate was admitted or vetoed.
        """
        rid = r.get("review_id")
        if not rid:
            raise RegistryError("review has no review_id")
        if any(en.get("review_id") == rid for en in self.entries
               if en.get("type") == "review"):
            raise RegistryError(f"review_id {rid!r} already recorded")
        self._append({"type": "review", "review_id": rid,
                      "exp_id": r.get("exp_id"), "side": r.get("side"),
                      "round": r.get("round")})

    def next_review_id(self) -> str:
        n = sum(1 for en in self.entries if en.get("type") == "review")
        return f"R-{n + 1:04d}"

    def n_trials(self, family: str = "default") -> int:
        """Number of experiments already settled in *family*."""
        return len(self._families.get(family, []))

    def check_oos_available(self, oos_window: str) -> None:
        start, _, end = oos_window.partition(":")
        if not start or not end:
            raise RegistryError(f"oos_window must be 'YYYYMMDD:YYYYMMDD', got {oos_window!r}")
        for b_start, b_end, by in self._oos_consumed:
            if _overlaps((start, end), (b_start, b_end)):
                raise RegistryError(
                    f"OOS window {oos_window} overlaps {b_start}:{b_end} already "
                    f"consumed by {by} — out-of-sample stretches are one-shot")

    def settle_experiment(self, e: dict[str, Any], h: dict[str, Any]) -> int:
        """Record a settled experiment; returns its 1-based trial number
        within the family (the N used for deflation)."""
        exp_id = e.get("exp_id")
        if not exp_id:
            raise RegistryError("experiment has no exp_id")
        if exp_id in self._exp_ids:
            raise RegistryError(f"exp_id {exp_id!r} already settled "
                                f"(IDs are unique forever)")
        if not self.has_hypothesis(h.get("hyp_id", "")):
            raise RegistryError(
                f"hypothesis {h.get('hyp_id')!r} is not registered — "
                f"experiments settle only against pre-registered hypotheses")
        family = h.get("family", "default")
        oos = e.get("oos_window") or (e.get("oos") or {}).get("window")
        if oos:
            self.check_oos_available(oos)
        trial_number = self.n_trials(family) + 1
        self._append({"type": "experiment", "exp_id": exp_id,
                      "hyp_id": h["hyp_id"], "family": family,
                      "oos_window": oos,
                      "verdict": e.get("verdict")})
        return trial_number
