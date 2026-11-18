"""Resume tests — SUPERAGENT_PLAN2 #6 acceptance, mechanically pinned.

From the plan:
* a settled order receiving "把门槛收到 0.05": a NEW verdict with
  ZERO rescoring, and the revival chain (old id -> resume event ->
  delta order) is auditable in the ledger;
* a refused order cannot be revived with the same hypothesis and the
  same params (our multiple-testing discipline, deliberately stricter
  than dsh);
* structural instructions produce a delta order that cites the old
  order and its result digest — checkpoints are reused downstream.

Plus the gates: only humans revive; live orders don't; unparseable
messages create nothing.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from qsa.orders import OrderBook, OrderError  # noqa: E402
from qsa.resume import execute_rejudge, resume  # noqa: E402

P = {"thresh": 0.03, "min_months": 12, "workers": 2}


def _make_prev_run(root: Path) -> Path:
    """A minimal v1.3-shaped prior run: leaderboard + config."""
    prev = root / "offense"
    prev.mkdir(parents=True, exist_ok=True)
    rows = [
        {"id": "mom_gap_12m", "oos_ic": 0.073, "n_months": 30},
        {"id": "dist_52w_high", "oos_ic": 0.076, "n_months": 22},
        {"id": "vol_of_vol", "oos_ic": 0.040, "n_months": 25},
        {"id": "weakling", "oos_ic": 0.028, "n_months": 20},
    ]
    (prev / "leaderboard.json").write_text(
        json.dumps({"library": rows}), encoding="utf-8")
    (prev / "run_config.json").write_text(
        json.dumps({"thresh": 0.03, "min_months": 12, "workers": 2,
                    "goal": "resume fixture", "fingerprint": "fix1"}),
        encoding="utf-8")
    return prev


class ResumeCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="qsa-resume-"))
        self.root = self.tmp / "work"
        self.root.mkdir()
        self.book = OrderBook(self.root / "orders.jsonl")

    def _settled(self, hypothesis="mom gap beats random") -> str:
        oid = self.book.create(hypothesis, dict(P))
        self.book.admit(oid, dict(P))
        self.book.start(oid, dict(P))
        self.book.settle(oid, {"verdict": "replicated", "n_winners": 2,
                               "winners": ["mom_gap_12m", "dist_52w_high"],
                               "config": dict(P)})
        return oid

    def _refused(self, hypothesis="bad idea", params=None) -> str:
        p = params or {"thresh": 0.03, "universe": "top300"}
        oid = self.book.create(hypothesis, dict(p))
        self.book.admit(oid, dict(p))
        self.book.refuse(oid, "gate: not enough months")
        return oid


class TestHappyResume(ResumeCase):
    def test_bar_only_message_revives_with_zero_rescoring(self):
        oid = self._settled()
        prev_dir = _make_prev_run(self.root)
        rec = resume(self.book, oid, "把门槛收到 0.05")
        self.assertTrue(rec["ok"])
        self.assertEqual(rec["mode"], "rejudge")
        self.assertEqual(rec["params_delta"], {"thresh": 0.05})
        res = execute_rejudge(self.book, rec["delta_id"], prev_dir)
        # zero rescoring, by contract
        self.assertEqual(res["rows_rescored"], 0)
        self.assertEqual(res["new_thresh"], 0.05)
        # 0.05 bar: the 0.040 and 0.028 candidates drop out
        self.assertEqual(res["winners"], ["dist_52w_high", "mom_gap_12m"])
        self.assertEqual(res["resume_of"], oid)
        # the delta order settled; the chain is complete on disk
        book2 = OrderBook(self.root / "orders.jsonl")
        self.assertEqual(book2.orders[rec["delta_id"]]["state"],
                         "settled")
        self.assertEqual(book2.summary()["settled"], 2)

    def test_revival_chain_is_auditable_in_the_ledger(self):
        oid = self._settled()
        rec = resume(self.book, oid, "把门槛收到 0.05")
        book2 = OrderBook(self.root / "orders.jsonl")   # fresh replay
        old = book2.orders[oid]
        self.assertEqual(old["state"], "settled")       # terminal stays
        self.assertEqual(old.get("resumed_by"), [rec["delta_id"]])
        delta = book2.orders[rec["delta_id"]]
        self.assertEqual(delta["resume_of"], oid)
        self.assertEqual(delta["origin"], "human")      # a human revived
        self.assertEqual(delta["context"]["prev_state"], "settled")
        self.assertEqual(delta["context"]["prev_results_keys"],
                         ["config", "n_winners", "verdict", "winners"])
        # the resume event itself is in the old order's history
        kinds = [ev["type"] for ev in old["history"]]
        self.assertEqual(kinds.count("resume"), 1)

    def test_structural_message_makes_a_recompute_delta(self):
        oid = self._settled()
        rec = resume(self.book, oid, "剔除小盘重新算")
        self.assertTrue(rec["ok"])
        self.assertEqual(rec["mode"], "recompute")
        self.assertEqual(rec["params_delta"]["universe"],
                         {"name": "top300", "exclude": "smallcap"})
        # a recompute delta stays drafted for the scheduler/checkpoint
        # path — execute_rejudge refuses it loudly
        with self.assertRaises(OrderError):
            execute_rejudge(self.book, rec["delta_id"],
                            _make_prev_run(self.root))


class TestRefusalGate(ResumeCase):
    def test_same_hypothesis_same_params_is_refused(self):
        oid = self._refused()
        # rejudge on a refused order: nothing to re-verdict -> refuse
        rec = resume(self.book, oid, "把门槛收到 0.05")
        self.assertFalse(rec["ok"])
        self.assertIn("没有结果可重判", rec["reason"])
        # structural change with an UNCHANGED effective param set is
        # the same (hypothesis, params) hash -> the gate holds
        rec2 = resume(self.book, oid, "剔除小盘重新算")
        self.assertTrue(rec2["ok"])                    # first time: new
        self.book.admit(rec2["delta_id"], {"x": 1})
        self.book.refuse(rec2["delta_id"], "gate again")
        rec3 = resume(self.book, rec2["delta_id"], "剔除小盘重新算")
        self.assertFalse(rec3["ok"])
        self.assertIn("同假设同参数", rec3["reason"])

    def test_refused_revives_through_explicit_structural_change(self):
        oid = self._refused()
        rec = resume(self.book, oid, "换小盘样本重跑")
        self.assertTrue(rec["ok"])
        self.assertEqual(rec["mode"], "recompute")
        delta = self.book.orders[rec["delta_id"]]
        self.assertEqual(delta["resume_of"], oid)
        self.assertEqual(delta["history"][0]["params"]["universe"],
                         {"name": "smallcap"})          # params CHANGED


class TestGates(ResumeCase):
    def test_machines_do_not_resurrect(self):
        oid = self._settled()
        with self.assertRaises(OrderError):
            resume(self.book, oid, "把门槛收到 0.05", by="watch")
        self.assertEqual(self.book.orders[oid].get("resumed_by"), None)

    def test_live_orders_do_not_resume(self):
        oid = self.book.create("live one", dict(P))
        self.book.admit(oid, dict(P))
        self.book.start(oid, dict(P))
        with self.assertRaises(OrderError):
            resume(self.book, oid, "把门槛收到 0.05")
        self.assertEqual(self.book.summary()["running"], 1)

    def test_unparseable_message_creates_nothing(self):
        oid = self._settled()
        n_events = len(self.book._events)
        rec = resume(self.book, oid, "帮我看看今天心情如何")
        self.assertFalse(rec["ok"])
        self.assertEqual(len(self.book._events), n_events)  # zero writes
        self.assertIsNone(self.book.orders[oid].get("resumed_by"))

    def test_second_bar_only_resume_keeps_the_chain_growing(self):
        oid = self._settled()
        prev = _make_prev_run(self.root)
        r1 = resume(self.book, oid, "把门槛收到 0.05")
        execute_rejudge(self.book, r1["delta_id"], prev)
        r2 = resume(self.book, r1["delta_id"], "再严格一点")
        self.assertTrue(r2["ok"])
        execute_rejudge(self.book, r2["delta_id"], prev)
        book2 = OrderBook(self.root / "orders.jsonl")
        self.assertEqual(book2.orders[oid]["resumed_by"],
                         [r1["delta_id"]])
        self.assertEqual(
            book2.orders[r1["delta_id"]]["resumed_by"], [r2["delta_id"]])
        # conversational continuity: 3 settled orders, one mandate
        self.assertEqual(book2.summary()["settled"], 3)


if __name__ == "__main__":
    unittest.main()
