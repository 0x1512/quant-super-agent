"""Tests for the infra gate + fork cards (v1.2).

The gate's value is its FAIL paths: a gate that always passes is worse
than no gate (false safety). So these tests build healthy and broken
fixture dirs and assert each check fires independently.

Fork cards: raise/decide lifecycle, double-decide refusal, unknown
choice refusal, bootstrap idempotency, digest stability.
"""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from qsa.blackboard import Blackboard
from qsa.infragate import ForkCards, bootstrap_forks, infra_gate, render_gate

REPO = Path(__file__).resolve().parents[1]
FIXTURES = REPO / "examples" / "data"


def make_fixture_dir(name: str, *, main: bool = True, tail: bool = True,
                     caps: bool = True, uni: bool = True,
                     uni_bad: bool = False) -> Path:
    d = Path(tempfile.mkdtemp(prefix=f"gate_{name}_"))
    if main:
        src = FIXTURES / "ashare_top300_main.csv"
        # small slice is enough — gate checks header + row count floor low
        with src.open(encoding="utf-8") as fh:
            lines = [fh.readline()] + [fh.readline() for _ in range(400)]
        (d / "ashare_top300_main.csv").write_text("".join(lines),
                                                  encoding="utf-8")
    if tail:
        src = FIXTURES / "ashare_top300_tail.csv"
        with src.open(encoding="utf-8") as fh:
            lines = [fh.readline()] + [fh.readline() for _ in range(50)]
        (d / "ashare_top300_tail.csv").write_text("".join(lines),
                                                  encoding="utf-8")
    if caps:
        (d / "replication_meta").mkdir(parents=True, exist_ok=True)
        (d / "replication_meta" / "monthly_caps.csv").write_text(
            "month,ticker,cap_proxy\n202107,000001.SZ,1.0e10\n",
            encoding="utf-8")
    if uni:
        src = FIXTURES / "ashare_top300_universe.json"
        if uni_bad:
            (d / "ashare_top300_universe.json").write_text(
                "{not json", encoding="utf-8")
        else:
            shutil.copy(src, d / "ashare_top300_universe.json")
    return d


class TestInfraGate(unittest.TestCase):
    def setUp(self):
        self.dirs = []
        self.boards = []

    def tearDown(self):
        for d in self.dirs:
            shutil.rmtree(d, ignore_errors=True)

    def _board(self, **post) -> Blackboard:
        d = tempfile.mkdtemp(prefix="bb_")
        self.dirs.append(d)
        b = Blackboard(Path(d) / "bb.jsonl")
        if post:
            b.post(**post)
        self.boards.append(b)
        return b

    def test_healthy_gate_opens(self):
        d = make_fixture_dir("good")
        self.dirs.append(d)
        report = infra_gate(d, self._board(), min_main_rows=100)
        self.assertTrue(report["ok"])
        self.assertEqual(len(report["checks"]), 5)
        text = render_gate(report)
        self.assertIn("OPEN", text)
        self.assertNotIn("FAIL", text)

    def test_missing_main_shuts(self):
        d = make_fixture_dir("nomain", main=False)
        self.dirs.append(d)
        report = infra_gate(d, self._board(), min_main_rows=100)
        self.assertFalse(report["ok"])
        failed = [c for c in report["checks"] if not c["ok"]]
        self.assertEqual([c["name"] for c in failed], ["main fixture"])

    def test_missing_tail_shuts(self):
        d = make_fixture_dir("notail", tail=False)
        self.dirs.append(d)
        report = infra_gate(d, self._board(), min_main_rows=100)
        self.assertFalse(report["ok"])
        self.assertEqual([c["name"] for c in report["checks"]
                          if not c["ok"]], ["tail fixture"])

    def test_missing_caps_shuts(self):
        d = make_fixture_dir("nocaps", caps=False)
        self.dirs.append(d)
        report = infra_gate(d, self._board(), min_main_rows=100)
        self.assertFalse(report["ok"])
        self.assertEqual([c["name"] for c in report["checks"]
                          if not c["ok"]], ["cap-proxy meta"])

    def test_bad_universe_shuts(self):
        d = make_fixture_dir("baduni", uni_bad=True)
        self.dirs.append(d)
        report = infra_gate(d, self._board(), min_main_rows=100)
        self.assertFalse(report["ok"])
        self.assertEqual([c["name"] for c in report["checks"]
                          if not c["ok"]], ["universe"])

    def test_too_few_rows_shuts(self):
        d = make_fixture_dir("short")
        self.dirs.append(d)
        report = infra_gate(d, self._board(), min_main_rows=999_999)
        self.assertFalse(report["ok"])
        self.assertEqual([c["name"] for c in report["checks"]
                          if not c["ok"]], ["main fixture"])

    def test_blocker_on_board_shuts(self):
        d = make_fixture_dir("blocker")
        self.dirs.append(d)
        b = self._board(kind="data_pitfall", title="disk full",
                        body="cache exhausted", status="blocker")
        report = infra_gate(d, b, min_main_rows=100)
        self.assertFalse(report["ok"])
        failed = [c for c in report["checks"] if not c["ok"]]
        self.assertEqual([c["name"] for c in failed], ["blackboard clear"])
        self.assertIn("1 unresolved blocker", failed[0]["detail"])

    def test_real_fixtures_pass(self):
        # the shipped fixtures must open the gate on the real blackboard
        b = Blackboard(Path(tempfile.mkdtemp(prefix="real_bb_")) / "bb.jsonl")
        self.boards.append(b)
        report = infra_gate(FIXTURES, b)
        self.assertTrue(report["ok"], render_gate(report))


class TestForkCards(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory(prefix="fork_")
        self.path = Path(self.d.name) / "forks.jsonl"

    def tearDown(self):
        self.d.cleanup()

    def _fc(self) -> ForkCards:
        return ForkCards(self.path)

    def _card(self, fc: ForkCards) -> None:
        fc.raise_fork("F-1", "which cost?",
                      [{"label": "5bps", "impact": "optimistic"},
                       {"label": "8bps", "impact": "conservative"}],
                      recommended="8bps", default="8bps")

    def test_raise_is_idempotent(self):
        fc = self._fc()
        self._card(fc)
        fc2 = self._fc()  # reload from disk
        self._card(fc2)   # no duplicate
        self.assertEqual(len(fc2.cards), 1)
        lines = self.path.read_text(encoding="utf-8").splitlines()
        forks = [json.loads(l) for l in lines
                 if json.loads(l)["type"] == "fork"]
        self.assertEqual(len(forks), 1)

    def test_decide_roundtrip(self):
        fc = self._fc()
        self._card(fc)
        fc.decide("F-1", "8bps", by="principal", rationale="conservative")
        fc2 = self._fc()
        c = fc2.cards["F-1"]
        self.assertEqual(c["decision"]["choice"], "8bps")
        self.assertEqual(c["decision"]["by"], "principal")
        self.assertEqual(fc2.open_forks(), [])

    def test_double_decide_refused(self):
        fc = self._fc()
        self._card(fc)
        fc.decide("F-1", "8bps", by="a", rationale="x")
        with self.assertRaises(ValueError) as ctx:
            fc.decide("F-1", "5bps", by="b", rationale="y")
        self.assertIn("already decided", str(ctx.exception))

    def test_unknown_choice_refused(self):
        fc = self._fc()
        self._card(fc)
        with self.assertRaises(ValueError):
            fc.decide("F-1", "12bps", by="a", rationale="y")

    def test_unknown_fork_refused(self):
        fc = self._fc()
        with self.assertRaises(ValueError):
            fc.decide("F-99", "x", by="a", rationale="y")

    def test_digest_stable_across_instances(self):
        fc = self._fc()
        self._card(fc)
        d1 = fc.digest("F-1")
        d2 = self._fc().digest("F-1")
        self.assertEqual(d1, d2)
        self.assertEqual(len(d1), 10)
        self.assertEqual(self._fc().digest("F-404"), "")

    def test_bootstrap_idempotent_and_decided(self):
        fc = bootstrap_forks(self.path)
        ids = set(fc.cards)
        self.assertEqual(ids, {"BB-FORK-01", "BB-FORK-02", "BB-FORK-03"})
        n = len(list(self.path.open()))
        # 3 forks + 3 decisions
        self.assertEqual(n, 6)
        fc2 = bootstrap_forks(self.path)
        self.assertEqual(len(list(self.path.open())), n)
        self.assertEqual(fc2.open_forks(), [])
        for c in fc2.cards.values():
            self.assertIn("decision", c)
            self.assertEqual(c["decision"]["by"], "principal")


if __name__ == "__main__":
    unittest.main()
