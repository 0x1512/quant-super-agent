"""Tests for the order book state machine (v1.2).

The point of the machine is the NEGATIVE paths:
* illegal transitions are hard errors (drafted -> running, settled -> anything)
* admit freezes parameters; start with drifted params is refused
* every transition is hash-chained; rewriting the log is detected
* settle must happen from running; refuse is reachable from any open state
"""
import json
import tempfile
import unittest
from pathlib import Path

from qsa.orders import OrderBook, OrderError


def fresh_book() -> tuple[OrderBook, tempfile.TemporaryDirectory]:
    d = tempfile.TemporaryDirectory()
    return OrderBook(Path(d.name) / "orders" / "orders.jsonl"), d


P = {"factor": "mom_gap_12m", "universe": "top300", "cost_bps": 8,
     "train": ["2021-07", "2024-06"], "test": ["2024-07", "2026-06"]}


class TestOrders(unittest.TestCase):
    def tearDown(self):
        self.dir.cleanup()

    def _create(self, book: OrderBook) -> str:
        return book.create("mom gap 12m beats random", dict(P),
                           priority=3, note="zoo candidate")

    def test_full_happy_path(self):
        book, self.dir = fresh_book()
        oid = self._create(book)
        self.assertEqual(book.summary(), {"drafted": 1, "admitted": 0,
                                          "running": 0, "settled": 0,
                                          "refused": 0})
        book.admit(oid, dict(P))
        book.start(oid, dict(P))
        book.settle(oid, {"ic_full": 0.04, "ic_oos": 0.073,
                          "gate": "fastlane", "verdict": "survivor"})
        o = book.orders[oid]
        self.assertEqual(o["state"], "settled")
        self.assertEqual(o["results"]["ic_oos"], 0.073)
        self.assertIsNotNone(o["params_frozen"])
        self.assertEqual(len(o["history"]), 4)  # create+admit+start+settle

    def test_illegal_transitions_refused(self):
        book, self.dir = fresh_book()
        oid = self._create(book)
        # skip admit
        with self.assertRaises(OrderError):
            book.start(oid)
        # skip admit+start
        with self.assertRaises(OrderError):
            book.settle(oid, {"x": 1})
        book.admit(oid, dict(P))
        # settle before running
        with self.assertRaises(OrderError):
            book.settle(oid, {"x": 1})
        book.start(oid)
        book.settle(oid, {"x": 1})
        # settled is terminal
        with self.assertRaises(OrderError):
            book.refuse(oid, "too late")
        with self.assertRaises(OrderError):
            book.start(oid)

    def test_unknown_order_refused(self):
        book, self.dir = fresh_book()
        with self.assertRaises(OrderError):
            book.admit("ORD-0000000000", dict(P))

    def test_param_drift_rejected(self):
        book, self.dir = fresh_book()
        oid = self._create(book)
        book.admit(oid, dict(P))
        # same params: fine
        book.start(oid, dict(P))
        book.settle(oid, {"ok": True})
        # second order: admit with A, run with B -> hard error
        oid2 = self._create(book)
        book.admit(oid2, dict(P))
        P2 = dict(P)
        P2["universe"] = "csi500"  # post-admit change
        with self.assertRaises(OrderError) as ctx:
            book.start(oid2, P2)
        self.assertIn("pre-registration", str(ctx.exception))

    def test_refuse_paths(self):
        book, self.dir = fresh_book()
        a = self._create(book)
        book.admit(a, dict(P))
        book.start(a, dict(P))
        book.refuse(a, "oos ic <= 0.03 — decay event filed")
        self.assertEqual(book.by_state("refused"), [a])
        b = self._create(book)
        book.refuse(b, "data not available")  # refuse from admitted
        c = self._create(book)
        book.refuse(c, "duplicate")  # refuse from drafted
        self.assertEqual(len(book.by_state("refused")), 3)

    def test_reload_and_chain_tamper(self):
        book, self.dir = fresh_book()
        oid = self._create(book)
        book.admit(oid, dict(P))
        book.start(oid, dict(P))
        book.settle(oid, {"v": 1})
        # reload in a fresh instance
        book2 = OrderBook(book.path)
        self.assertEqual(book2.orders[oid]["state"], "settled")
        self.assertEqual(book2.orders[oid]["params_frozen"], P)
        # tamper: edit a settled result
        lines = book.path.read_text(encoding="utf-8").splitlines()
        ev = json.loads(lines[-1])
        ev["results"]["v"] = 999
        lines[-1] = json.dumps(ev, ensure_ascii=False)
        book.path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        with self.assertRaises(OrderError) as ctx:
            OrderBook(book.path)
        self.assertIn("chain broken", str(ctx.exception))

    def test_summary_counts_multiple(self):
        book, self.dir = fresh_book()
        for i in range(3):
            oid = book.create(f"h{i}", {"i": i})
            book.admit(oid, {"i": i})
            if i < 2:
                book.start(oid, {"i": i})
                book.settle(oid, {"i": i})
            else:
                book.refuse(oid, "nope")
        s = book.summary()
        self.assertEqual(s["settled"], 2)
        self.assertEqual(s["refused"], 1)
        self.assertEqual(s["drafted"], 0)


if __name__ == "__main__":
    unittest.main()
