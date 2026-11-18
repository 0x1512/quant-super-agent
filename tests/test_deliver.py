"""Deliver tests — Wave1-live G9 / PLAN2 #8 first half, pinned.

The promise: a settled order becomes a package a third party can
re-verify WITHOUT trusting us — every event hash-matches the ledger,
every card number exists in the settle event, the manifest still
matches the bytes. Editing either side after sealing fails loudly.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from qsa.deliver import build, verify          # noqa: E402
from qsa.orders import OrderBook, OrderError   # noqa: E402
from qsa.resume import execute_rejudge, resume  # noqa: E402

P = {"thresh": 0.03, "min_months": 12, "workers": 2}


def _make_prev_run(root: Path) -> Path:
    prev = root / "offense"
    prev.mkdir(parents=True, exist_ok=True)
    rows = [{"id": "mom_gap_12m", "oos_ic": 0.073, "n_months": 30},
            {"id": "dist_52w_high", "oos_ic": 0.076, "n_months": 22},
            {"id": "weakling", "oos_ic": 0.028, "n_months": 20}]
    (prev / "leaderboard.json").write_text(
        json.dumps({"library": rows}), encoding="utf-8")
    (prev / "run_config.json").write_text(
        json.dumps({"thresh": 0.03, "min_months": 12, "workers": 2,
                    "goal": "deliver fixture", "fingerprint": "fix1"}),
        encoding="utf-8")
    return prev


class DeliverCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="qsa-deliver-"))
        self.root = self.tmp / "work"
        self.root.mkdir()
        self.book = OrderBook(self.root / "orders.jsonl")

    def _settled(self) -> str:
        oid = self.book.create("mom gap beats random", dict(P))
        self.book.admit(oid, dict(P))
        self.book.start(oid, dict(P))
        self.book.settle(oid, {
            "verdict": "replicated", "oos_ic": 0.073, "icir": 1.9,
            "n_months": 30,
            "winners": ["mom_gap_12m"]})
        return oid


class TestPackage(DeliverCase):
    def test_four_files_and_a_four_line_card(self):
        oid = self._settled()
        out = self.tmp / "pkg"
        man = build(self.root, oid, out)
        self.assertEqual(
            sorted(man["files"]),
            ["MANIFEST.json", "conclusion.md", "evidence.json",
             "reproduce.txt"])
        self.assertFalse(man["needs_split"])
        card = (out / "conclusion.md").read_text("utf-8")
        # conclusion first, then numbers, evidence pointer, reproduce
        self.assertIn("**replicated**", card)
        self.assertIn("oos_ic=0.073", card)
        self.assertIn("条事件，链头", card)
        self.assertIn("reproduce.txt", card)
        # every number on the card traces to the settle event
        ev = json.loads((out / "evidence.json").read_text("utf-8"))
        self.assertEqual(ev["number_sources"]["oos_ic"]["value"], 0.073)
        self.assertEqual(ev["n_events"], 4)   # create+admit+start+settle

    def test_verify_passes_and_both_tampering_sides_fail(self):
        oid = self._settled()
        out = self.tmp / "pkg"
        build(self.root, oid, out)
        self.assertEqual(verify(out, self.root)["events_verified"], 4)

        # tamper side A: edit the packaged evidence after sealing
        p = out / "evidence.json"
        d = json.loads(p.read_text("utf-8"))
        d["events"][0]["hypothesis"] = "something we never ran"
        p.write_text(json.dumps(d, ensure_ascii=False), "utf-8")
        with self.assertRaises(OrderError):
            verify(out, self.root)

        # rebuild clean, then tamper side B: edit a packaged FILE so the
        # manifest byte-list disagrees
        build(self.root, oid, out)
        (out / "conclusion.md").write_text("numbers improved!", "utf-8")
        with self.assertRaises(OrderError):
            verify(out, self.root)

    def test_only_settled_orders_are_deliverables(self):
        oid = self.book.create("live", dict(P))
        self.book.admit(oid, dict(P))
        with self.assertRaises(OrderError):
            build(self.root, oid, self.tmp / "nope")
        refused = self.book.create("bad", dict(P))
        self.book.refuse(refused, "dead on arrival")
        with self.assertRaises(OrderError):
            build(self.root, refused, self.tmp / "nope2")

    def test_size_door_marks_needs_split_instead_of_shipping_big(self):
        oid = self._settled()
        man = build(self.root, oid, self.tmp / "pkg2",
                    size_door=10)                # absurdly small door
        self.assertTrue(man["needs_split"])
        self.assertIn("需人工拆分", man["split_suggestion"])
        self.assertIn("size_door_bytes", man)

    def test_resume_delta_package_cites_its_prior(self):
        oid = self._settled()
        prev = _make_prev_run(self.root)
        rec = resume(self.book, oid, "把门槛收到 0.05")
        execute_rejudge(self.book, rec["delta_id"], prev)
        out = self.tmp / "delta-pkg"
        man = build(self.root, rec["delta_id"], out)
        self.assertFalse(man["needs_split"])
        ev = json.loads((out / "evidence.json").read_text("utf-8"))
        self.assertEqual(ev["resume_of"], oid)
        card = (out / "conclusion.md").read_text("utf-8")
        self.assertIn(oid, card)                 # cites the prior order
        self.assertIn("rows_rescored=0", card)   # the zero-rescoring
        # and the prior order packages independently
        man2 = build(self.root, oid, self.tmp / "prior-pkg")
        self.assertEqual(man2["order_id"], oid)


class TestCli(DeliverCase):
    def test_cli_build_and_verify_roundtrip(self):
        import subprocess
        oid = self._settled()
        out = self.tmp / "cli-pkg"
        r = subprocess.run(
            [sys.executable, "-m", "qsa.deliver", "--root",
             str(self.root), "--order", oid, "--out", str(out)],
            capture_output=True, text=True,
            cwd=Path(__file__).resolve().parents[1])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("deliver", r.stdout)
        v = subprocess.run(
            [sys.executable, "-m", "qsa.deliver", "--verify", str(out),
             "--root", str(self.root)],
            capture_output=True, text=True,
            cwd=Path(__file__).resolve().parents[1])
        self.assertEqual(v.returncode, 0, v.stderr)
        self.assertIn("verify OK", v.stdout)


if __name__ == "__main__":
    unittest.main()
