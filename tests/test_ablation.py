"""Ablation-harness tests: planted worlds, byte-frozen default snapshots,
deterministic acceptance table (v0.4)."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from qsa.ablation import CONFIGS, run_ablation
from qsa.snapshot import build_snapshot

# the historical toy snapshot, frozen: the plant feature must never change a
# byte of the default generator's output
FROZEN_SEED42_SHA = ("7b81decd7fdc32d63ef60f22944cbe348a6c052b3fd48ba"
                     "13f01824aef08053d")

SMALL_CONFIGS = (CONFIGS[0], CONFIGS[3])  # factor-only/0 vs factor+risk/1


class TestPlantedSnapshots(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_default_path_is_byte_frozen(self):
        info = build_snapshot(self.root / "a", seed=42, tickers=12, days=90)
        self.assertEqual(info.manifest_hash, FROZEN_SEED42_SHA)

    def test_planted_snapshot_is_deterministic_and_declared(self):
        a = build_snapshot(self.root / "pa", seed=7, tickers=12, days=90,
                           plant={"effect": "reversal", "strength": 0.15})
        b = build_snapshot(self.root / "pb", seed=7, tickers=12, days=90,
                           plant={"effect": "reversal", "strength": 0.15})
        self.assertEqual(a.manifest_hash, b.manifest_hash)
        self.assertEqual(a.manifest["plant"],
                         {"effect": "reversal", "strength": 0.15})
        # and differs from the unplanted world with the same seed
        c = build_snapshot(self.root / "pc", seed=7, tickers=12, days=90)
        self.assertNotEqual(a.manifest_hash, c.manifest_hash)
        self.assertNotIn("plant", c.manifest)

    def test_unknown_plant_effect_rejected(self):
        with self.assertRaises(ValueError):
            build_snapshot(self.root / "x", seed=1,
                           plant={"effect": "alpha", "strength": 0.1})


class TestAblationTable(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.result = run_ablation(cls.root / "abl",
                                  configs=SMALL_CONFIGS,
                                  planted_seeds=(11,),
                                  noise_seeds=(1, 8))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_table_is_pinned_byte_for_byte(self):
        expected = (
            "| config | roles | debate rounds | discovery (planted) | "
            "false positives (noise) | mean trials planted | mean trials noise |\n"
            "|---|---|---|---|---|---|---|\n"
            "| factor-only/0 | data+factor | 0 | 1/1 | 2/2 | 1.00 | 1.00 |\n"
            "| factor+risk/1 | data+factor+risk | 1 | 1/1 | 1/2 | 1.00 | 2.00 |")
        self.assertEqual(self.result["table"], expected)

    def test_discovery_survives_all_layers(self):
        for row in self.result["rows"]:
            self.assertEqual(row["discovery"], [1, 1],
                             f"{row['config']}: layers must not cost discovery")

    def test_risk_and_debate_suppress_the_unstable_false_positive(self):
        by_label = {r["config"]: r for r in self.result["rows"]}
        self.assertEqual(by_label["factor-only/0"]["false_positive"], [2, 2])
        self.assertEqual(by_label["factor+risk/1"]["false_positive"], [1, 2])

    def test_table_file_written(self):
        self.assertTrue((self.result["out_dir"] / "table.md").exists())

    def test_full_matrix_is_deterministic(self):
        # the demo matrix (5 configs x 3 planted x 8 noise) reproduces exactly
        with tempfile.TemporaryDirectory() as td:
            r1 = run_ablation(Path(td) / "r1")
            r2 = run_ablation(Path(td) / "r2")
        self.assertEqual(r1["table"], r2["table"])


if __name__ == "__main__":
    unittest.main()
