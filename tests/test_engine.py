"""Engine tests: determinism, lookahead refusal, window bounds."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from qsa import engine, snapshot


class TestEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.snap = snapshot.build_snapshot(Path(cls.tmp.name) / "snapshot",
                                           seed=42, tickers=12, days=90)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_deterministic_metrics(self):
        a = engine.run(str(self.snap.dir), k=10)
        b = engine.run(str(self.snap.dir), k=10)
        self.assertEqual(a["metrics"], b["metrics"])
        self.assertEqual(a["attribution"], b["attribution"])

    def test_metric_shape(self):
        m = engine.run(str(self.snap.dir), k=10)["metrics"]
        for key in ("rankic_mean", "rankic_tstat", "quintile_spread",
                    "monotonicity_proxy", "n_dates"):
            self.assertIn(key, m)
        self.assertIsInstance(m["n_dates"], int)
        self.assertGreater(m["n_dates"], 30)

    def test_window_beyond_snapshot_refused(self):
        as_of = self.snap.manifest["as_of"]
        beyond = str(int(as_of) + 1)
        window = f"{self.snap.manifest['start']}:{beyond}"
        with self.assertRaisesRegex(ValueError, "lookahead refused"):
            engine.run(str(self.snap.dir), k=10, window=window)

    def test_window_too_short_refused(self):
        start = self.snap.manifest["start"]
        with self.assertRaisesRegex(ValueError, "dates"):
            engine.run(str(self.snap.dir), k=10, window=f"{start}:{start}")

    def test_neighborhood_attribution_present(self):
        attr = engine.run(str(self.snap.dir), k=10)["attribution"]
        self.assertIn("neighborhood_stable", attr)
        self.assertIn("neighborhood_rankic", attr)
        self.assertEqual(len(attr["neighborhood_rankic"]), 4)  # k±1, k±2


if __name__ == "__main__":
    unittest.main()
