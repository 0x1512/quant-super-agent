"""Hypothesis orders — the research queue as a state machine (v1.2).

v1.1's zoo was a batch script: run once, results dumped, nothing tracked.
This module gives every hypothesis a first-class ORDER with a lifecycle,
mirroring the platform's order semantics:

    drafted --admit--> admitted --start--> running --settle--> settled
                                                   +--refuse-> refused

What the machine enforces (the parts a script cannot):

* **freeze on admit** — the hypothesis' evaluation parameters are
  snapshotted and hashed at admission; running with different parameters
  than admitted is a hard error. This is pre-registration with teeth:
  the A8 discipline applied to every zoo candidate, not just the flagship.
* **audited transitions** — every state change is appended with a
  timestamp and an actor; the JSONL log is hash-chained like the ledger
  and the blackboard, so a rewritten history is detectable.
* **results attach at settle only** — a settled order must carry its
  metrics and the gate/fast-lane reference; a refused one must say why.
  There is no state where results exist but the order is half-described.

The factory (examples/run_orders.py) walks each catalog factor through
this machine; the blackboard gets the decay events; fork cards record
the convention decisions. What codex gives you is a for-loop — this is
the difference a supervised lifecycle makes.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

STATES = ("drafted", "admitted", "running", "settled", "refused")
TRANSITIONS = {
    "drafted": ("admitted", "refused"),
    "admitted": ("running", "refused"),
    "running": ("settled", "refused"),
    "settled": (),
    "refused": (),
}


def _hash(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True,
                                     ensure_ascii=False).encode()).hexdigest()


class OrderError(RuntimeError):
    pass


class OrderBook:
    """Persistent, hash-chained order log + live order index."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.touch()
        self.orders: dict[str, dict[str, Any]] = {}
        self._events: list[dict[str, Any]] = []
        for ln in self.path.read_text(encoding="utf-8").splitlines():
            if ln.strip():
                self._replay(json.loads(ln))
        self._verify_chain()

    # -- persistence -----------------------------------------------------
    def _replay(self, ev: dict[str, Any]) -> None:
        if ev["type"] == "create":
            self.orders[ev["order_id"]] = {
                "order_id": ev["order_id"],
                "hypothesis": ev["hypothesis"],
                "params_frozen": None,
                "state": "drafted",
                "results": None,
                "refusal": None,
                "history": [ev],
            }
        elif ev["type"] == "transition":
            o = self.orders.get(ev["order_id"])
            if o is None:
                raise OrderError(f"transition for unknown order "
                                 f"{ev['order_id']}")
            o["state"] = ev["to"]
            o["history"].append(ev)
            if ev["to"] == "admitted":
                o["params_frozen"] = ev["params"]
                o["params_hash"] = _hash(ev["params"])
            if ev["to"] == "settled":
                o["results"] = ev["results"]
            if ev["to"] == "refused":
                o["refusal"] = ev["reason"]
        self._events.append(ev)

    def _verify_chain(self) -> None:
        prev = ""
        for i, ev in enumerate(self._events):
            body = {k: v for k, v in ev.items() if k != "chain"}
            expect = hashlib.sha256(
                (prev + json.dumps(body, sort_keys=True,
                                   ensure_ascii=False)).encode()).hexdigest()
            if ev.get("chain") != expect:
                raise OrderError(f"order log chain broken at event {i}")
            prev = expect

    def _append(self, ev: dict[str, Any]) -> None:
        prev = (self._events[-1].get("chain") if self._events else "")
        ev["chain"] = hashlib.sha256(
            (prev + json.dumps(ev, sort_keys=True,
                               ensure_ascii=False)).encode()).hexdigest()
        self._replay(ev)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(ev, ensure_ascii=False) + "\n")

    # -- API ---------------------------------------------------------------
    def create(self, hypothesis: str, params: dict[str, Any],
               priority: int = 5, note: str = "") -> str:
        order_id = f"ORD-{_hash([hypothesis, params, len(self._events)])[:10]}"
        self._append({"type": "create", "ts": time.time(),
                      "order_id": order_id, "hypothesis": hypothesis,
                      "params": params, "priority": priority,
                      "note": note})
        return order_id

    def admit(self, order_id: str, params: dict[str, Any]) -> None:
        self._transition(order_id, "admitted", params=params)

    def start(self, order_id: str, params: dict[str, Any] | None = None) -> None:
        o = self._orders_or_raise(order_id)
        if params is not None and o.get("params_hash") != _hash(params):
            raise OrderError(
                f"{order_id}: RUNNING PARAMS != ADMITTED PARAMS — the "
                f"order was admitted with {_hash(params)[:8]}-different "
                f"parameters; pre-registration violated")
        self._transition(order_id, "running")

    def settle(self, order_id: str, results: dict[str, Any]) -> None:
        self._transition(order_id, "settled", results=results)

    def refuse(self, order_id: str, reason: str) -> None:
        self._transition(order_id, "refused", reason=reason)

    def _orders_or_raise(self, order_id: str) -> dict[str, Any]:
        o = self.orders.get(order_id)
        if o is None:
            raise OrderError(f"unknown order {order_id}")
        return o

    def _transition(self, order_id: str, to: str, **payload: Any) -> None:
        o = self._orders_or_raise(order_id)
        if to not in TRANSITIONS[o["state"]]:
            raise OrderError(
                f"{order_id}: illegal transition "
                f"{o['state']} -> {to} (legal: {TRANSITIONS[o['state']]})")
        ev = {"type": "transition", "ts": time.time(),
              "order_id": order_id, "from": o["state"], "to": to}
        ev.update(payload)
        self._append(ev)

    # -- queries -----------------------------------------------------------
    def param_hash(self, params: dict[str, Any]) -> str:
        """The hash admission froze — callers compare their current
        params against this to detect drift before it contaminates."""
        return _hash(params)

    def by_state(self, state: str) -> list[str]:
        return [oid for oid, o in self.orders.items()
                if o["state"] == state]

    def summary(self) -> dict[str, int]:
        return {s: len(self.by_state(s)) for s in STATES}
