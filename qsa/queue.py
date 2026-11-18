"""Queue — SUPERAGENT_PLAN2 #2 (slots, priorities, and the human lane).

dsh-superagent runs each accepted Ticket under a concurrency-slot
budget, keeps launches in a ``working/queued`` stage while they wait,
and reserves ONE EXTRA SLOT so a person's message can never be crowded
out by machine work ("new work therefore cannot prevent a person from
continuing an existing Ticket" — docs/003). Our router spawned
everything at once and waited; this module is the queue it was
missing, in the repo's register:

* **the state machine hop** — an admitted order may be ``enqueue``d
  (``admitted -> queued``); the scheduler starts it when a slot frees
  (``queued -> running``); a queued order can be withdrawn to
  ``refused`` at any time before it starts, leaving no residue. The
  direct ``admitted -> running`` path stays legal (single-order quick
  runs never see the queue).
* **priority** — lower number = more urgent (offense winners are 4,
  routine drafts 5, watch triggers 7, drift re-tests 9); ties break
  FIFO by creation order. The ledger replays the whole sequence, so
  the ORDER in which things ran is auditable, not just the fact.
* **the human lane** — orders carrying ``origin="human"`` (channel
  work) may occupy one slot BEYOND the machine budget: machine orders
  fill at most ``slots``, human orders at most ``slots + 1``. Machine
  work can never crowd out the person.
* **backpressure, honestly** — when the queue is at ``max_queue``,
  a new draft is NOT an order: it becomes a blackboard ``order_note``
  entry saying so. Nothing is silently dropped; the note is the
  receipt.

不拍板零执行 unchanged: the queue schedules ADMITTED orders only;
admission itself stays a human decision, and the scheduler never
settles or refuses on its own.

    python -m qsa.queue --root work --slots 3
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any, Callable, Protocol

from . import blackboard as bb
from . import tasks as T
from .orders import OrderBook


class Job(Protocol):
    """The minimal thing the driver needs from an execution."""

    def poll(self) -> int | None: ...        # None = still running


class Queue:
    """A slot scheduler over an OrderBook's ``queued`` orders."""

    def __init__(self, root: Path, slots: int = 3, max_queue: int = 100):
        self.root = Path(root)
        self.book = OrderBook(self.root / "orders.jsonl")
        self.slots = int(slots)
        self.max_queue = int(max_queue)

    # ----------------------------------------------------------- intake
    def depth(self) -> int:
        return len(self.book.by_state("queued"))

    def submit(self, hypothesis: str, params: dict[str, Any],
               priority: int = 5, note: str = "",
               origin: str = "machine") -> str | None:
        """Draft + admit + enqueue one order. If the queue is full the
        draft becomes a blackboard note instead — the receipt, never a
        silent drop. Returns the order id, or None when parked."""
        if self.depth() >= self.max_queue:
            board = bb.bootstrapped(self.root / "blackboard.jsonl")
            board.post("order_note",
                       f"队列已满（{self.depth()}/{self.max_queue}），"
                       f"草案暂记账未入队",
                       f"目标「{hypothesis}」到达时队列已满，未创建订单、"
                       f"未丢弃：本条即回执，等队列腾出后重新提交。",
                       status="blocker", tags=["queue", "backpressure"])
            return None
        oid = self.book.create(hypothesis, params, priority=priority,
                               note=note, origin=origin)
        self.book.admit(oid, params)
        self.book.enqueue(oid)
        return oid

    def withdraw(self, order_id: str, reason: str) -> None:
        """A queued order leaves the queue (refused, with the reason)."""
        self.book.refuse(order_id, reason)

    # ----------------------------------------------------------- policy
    def _candidates(self) -> list[tuple[int, int, str, dict]]:
        out = []
        for seq, (oid, o) in enumerate(self.book.orders.items()):
            if o["state"] == "queued":
                out.append((int(o["history"][0].get("priority", 5)),
                            seq, oid, o))
        return sorted(out, key=lambda x: (x[0], x[1]))

    def pick(self, running: list[str]) -> str | None:
        """Which queued order may start now, given the ids running.

        Machine orders may fill at most ``slots``; human-origin orders
        at most ``slots + 1`` (the reserved lane). Priority first,
        FIFO among equals; among the orders that CAN run now (a human
        behind a machine queue head still fits the reserved lane), the
        highest-priority one starts — the scheduler never idles a free
        slot to preserve an ordering the slots cannot honor anyway.
        """
        n = len(running)
        human_running = sum(
            1 for oid in running
            if self.book.orders[oid].get("origin") == "human")
        for _prio, _seq, oid, o in self._candidates():
            if o.get("origin") == "human":
                if n < self.slots + 1 and human_running < self.slots + 1:
                    return oid                 # a normal or reserved slot
            else:
                if n < self.slots:
                    return oid                 # a normal slot is free
        return None

    # ----------------------------------------------------------- driver
    def run(self, execute: Callable[[dict], Job], tick_s: float = 0.2,
            max_ticks: int | None = None,
            on_exit: Callable[[str, int], None] | None = None,
            settle_ok: Callable[[str, int], dict[str, Any]] | None = None,
            ) -> dict[str, Any]:
        """Drive the queue to exhaustion: start what the policy allows,
        reap what finished, repeat. ``execute(order)`` must return a
        Job (``poll()`` -> None | exit code). When a job finishes, the
        driver reports it through ``on_exit`` — it NEVER settles or
        refuses the order itself; that stays with the order's owner
        (settle is mechanical against the pre-declared bar, not a
        scheduler's opinion)."""
        running: dict[str, Job] = {}
        started: list[str] = []
        ticks = 0
        while True:
            for oid, job in list(running.items()):
                rc = job.poll()
                if rc is not None:
                    del running[oid]
                    if on_exit is not None:
                        on_exit(oid, rc)
            while True:
                nxt = self.pick(list(running))
                if nxt is None:
                    break
                order = self.book.orders[nxt]
                self.book.start(nxt)
                running[nxt] = execute(order)
                started.append(nxt)
            ticks += 1
            if not running and not self.depth():
                break
            if max_ticks is not None and ticks >= max_ticks:
                break
            if running:
                time.sleep(tick_s)
        return {"started": started, "ticks": ticks,
                "summary": self.book.summary()}


# ----------------------------------------------------------------- CLI
def _offense_runner(root: Path) -> Callable[[dict], Job]:
    """The default executor: one offense run per order, in its own
    work dir, as a detached task (the #1 async model)."""
    import sys
    repo = Path(__file__).resolve().parents[1]

    def execute(order: dict) -> Job:
        argv = [sys.executable, str(repo / "examples" / "run_offense.py"),
                "--work", str(root / "queue" / order["order_id"])]
        goal = order.get("hypothesis")
        if goal:
            argv += ["--goal", str(goal)]
        card = T.start(argv, root=str(root))
        return _TaskJob(str(root), card["id"])

    return execute


class _TaskJob:
    """A detached task card wrapped in the Job protocol."""

    def __init__(self, root: str, tid: str):
        self._root = Path(root)
        self._tid = tid

    def poll(self) -> int | None:
        card = T.read_card(self._root, self._tid)
        if card is None:
            return -1
        card = T.refresh(card, self._root)
        state = card.get("state")
        if state == "settled":
            return 0
        if state == "failed":
            return int(card.get("exit_code") or 1)
        return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="work")
    ap.add_argument("--slots", type=int, default=3)
    ap.add_argument("--max-queue", type=int, default=100)
    ap.add_argument("--tick-s", type=float, default=1.0)
    a = ap.parse_args(argv)
    root = Path(a.root)
    q = Queue(root, slots=a.slots, max_queue=a.max_queue)
    for oid in q.book.by_state("admitted"):          # auto-enqueue
        q.book.enqueue(oid)
    print(f"[queue] {q.depth()} queued, {q.slots} slots "
          f"(+1 reserved for humans)")

    def _report(oid: str, rc: int) -> None:
        print(f"[queue] {oid} exited {rc} — settlement stays with the "
              f"order's owner (不拍板零执行)", flush=True)

    out = q.run(_offense_runner(root), tick_s=a.tick_s, on_exit=_report)
    print(f"[queue] done: {len(out['started'])} started, "
          f"{json.dumps(out['summary'], ensure_ascii=False)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
