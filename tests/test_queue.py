"""Queue tests — SUPERAGENT_PLAN2 #2 acceptance, mechanically pinned.

From the plan:
* 10 orders on 3 slots: three run first, one starts as one finishes,
  and the run order is the priority order — the ledger replays it;
* with every machine slot busy, a human-channel order still starts
  immediately (the reserved lane);
* a queued order withdrawn before it starts leaves no residue;
* a full queue parks new drafts as blackboard receipts, never drops
  them;
* the state machine hop (admitted -> queued -> running) is optional —
  the direct path stays legal;
* the driver NEVER settles or refuses: settlement stays with the
  order's owner (不拍板零执行).
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from qsa.orders import OrderBook, OrderError          # noqa: E402
from qsa.queue import Queue                           # noqa: E402


class FakeJob:
    """Completes after ``ticks`` polls, exit code ``rc``."""

    def __init__(self, ticks: int = 1, rc: int = 0):
        self.left = ticks
        self.rc = rc

    def poll(self) -> int | None:
        if self.left > 0:
            self.left -= 1
            return None
        return self.rc


class QueueCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="qsa-queue-"))
        self.root = self.tmp / "work"
        self.root.mkdir()

    def _q(self, slots: int = 3, max_queue: int = 100) -> Queue:
        return Queue(self.root, slots=slots, max_queue=max_queue)

    def _submit(self, q: Queue, tag: str, priority: int = 5,
                origin: str = "machine") -> str:
        return q.submit(f"goal {tag}", {"tag": tag}, priority=priority,
                        origin=origin)


class TestPolicy(QueueCase):
    def test_ten_orders_three_slots_run_in_priority_order(self):
        q = self._q(slots=3)
        prios = [7, 3, 9, 1, 5, 0, 8, 2, 6, 4]
        ids = [self._submit(q, f"t{i}", priority=p) for i, p in
               enumerate(prios)]
        max_seen = 0
        running_now = 0

        def execute(order: dict) -> FakeJob:
            nonlocal max_seen, running_now
            running_now += 1
            max_seen = max(max_seen, running_now)
            return FakeJob(ticks=1)

        def on_exit(oid: str, rc: int) -> None:
            nonlocal running_now
            running_now -= 1

        out = q.run(execute, tick_s=0, on_exit=on_exit)
        self.assertEqual(len(out["started"]), 10)
        self.assertLessEqual(max_seen, 3)          # never over the budget
        # started in (priority, creation) order — the ledger replays it
        expect = [oid for oid, p in
                  sorted(zip(ids, prios), key=lambda x: x[1])]
        self.assertEqual(out["started"], expect)
        # the book re-instantiates from disk (chain verifies) and every
        # order is running — settlement is NOT the scheduler's business
        book2 = OrderBook(self.root / "orders.jsonl")
        self.assertEqual(len(book2.by_state("running")), 10)
        self.assertEqual(book2.summary()["settled"], 0)

    def test_fifo_among_equal_priorities(self):
        q = self._q(slots=2)
        a = self._submit(q, "a", priority=5)
        b = self._submit(q, "b", priority=5)
        c = self._submit(q, "c", priority=5)
        out = q.run(lambda o: FakeJob(ticks=1), tick_s=0)
        self.assertEqual(out["started"], [a, b, c])

    def test_human_order_starts_on_the_reserved_slot(self):
        q = self._q(slots=2)
        m1 = self._submit(q, "m1", priority=1)                 # machine
        m2 = self._submit(q, "m2", priority=2)                 # machine
        self.assertIsNone(q.pick([m1, m2]))    # machine budget exhausted
        h = self._submit(q, "h", priority=9, origin="human")
        self.assertEqual(q.pick([m1, m2]), h)  # the reserved lane opens
        # once m1 and the human order are actually running, no further
        # machine order fits (the budget is machine-exhausted again)
        q.book.start(m1)
        q.book.start(h)
        self.assertIsNone(q.pick([m1, h]))

    def test_human_message_runs_immediately_when_slots_full(self):
        q = self._q(slots=2)
        self._submit(q, "m1", priority=1)
        self._submit(q, "m2", priority=2)
        h = self._submit(q, "h", priority=9, origin="human")
        max_seen = 0
        running_now = 0

        def execute(order: dict) -> FakeJob:
            nonlocal max_seen, running_now
            running_now += 1
            max_seen = max(max_seen, running_now)
            return FakeJob(ticks=2)

        def on_exit(oid: str, rc: int) -> None:
            nonlocal running_now
            running_now -= 1

        out = q.run(execute, tick_s=0, on_exit=on_exit)
        # all three started in the FIRST scheduling round: the human
        # order never waited behind the machine work
        self.assertEqual(out["started"][:3][-1], h)
        self.assertEqual(max_seen, 3)            # slots + the human lane

    def test_withdrawn_order_leaves_no_residue(self):
        q = self._q(slots=1)
        a = self._submit(q, "a", priority=1)
        b = self._submit(q, "b", priority=2)
        q.withdraw(b, "user withdrew before start")
        self.assertEqual(q.depth(), 1)
        out = q.run(lambda o: FakeJob(ticks=1), tick_s=0)
        self.assertEqual(out["started"], [a])
        s = OrderBook(self.root / "orders.jsonl").summary()
        self.assertEqual(s["refused"], 1)
        self.assertEqual(s["running"], 1)


class TestBackpressure(QueueCase):
    def test_full_queue_parks_the_draft_as_a_blackboard_receipt(self):
        q = self._q(slots=1, max_queue=2)
        self.assertIsNotNone(self._submit(q, "a"))
        self.assertIsNotNone(self._submit(q, "b"))
        parked = q.submit("goal overflow", {"tag": "z"})
        self.assertIsNone(parked)                 # no order was created
        self.assertEqual(q.depth(), 2)            # queue unchanged
        notes = [json.loads(x) for x in
                 (self.root / "blackboard.jsonl").read_text("utf-8")
                 .splitlines() if x.strip()]
        self.assertTrue(any("队列已满" in n.get("title", "")
                            and "goal overflow" in n.get("body", "")
                            for n in notes))


class TestStateMachine(QueueCase):
    def test_queue_hop_is_optional_and_the_direct_path_stays_legal(self):
        book = OrderBook(self.root / "orders.jsonl")
        hop = book.create("queued path", {"a": 1})
        book.admit(hop, {"a": 1})
        book.enqueue(hop)
        book.start(hop)
        direct = book.create("direct path", {"a": 2})
        book.admit(direct, {"a": 2})
        book.start(direct)                        # no queue, still legal
        self.assertEqual(book.summary()["running"], 2)

    def test_illegal_hops_are_refused(self):
        book = OrderBook(self.root / "orders.jsonl")
        oid = book.create("h", {})
        with self.assertRaises(OrderError):
            book.enqueue(oid)                     # drafted -> queued, no
        book.admit(oid, {})
        book.enqueue(oid)
        book.start(oid)
        with self.assertRaises(OrderError):
            book.enqueue(oid)                     # running -> queued, no

    def test_origin_survives_replay(self):
        book = OrderBook(self.root / "orders.jsonl")
        oid = book.create("human ask", {}, origin="human")
        book2 = OrderBook(self.root / "orders.jsonl")
        self.assertEqual(book2.orders[oid]["origin"], "human")


if __name__ == "__main__":
    unittest.main()
