"""Snapshot tests: determinism, fingerprint self-check, tamper detection."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from qsa.snapshot import build_snapshot, fingerprint


class TestSnapshot(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dir = Path(cls.tmp.name)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_build_is_byte_deterministic(self):
        a, b = self.dir / "snap-a", self.dir / "snap-b"
        build_snapshot(a, seed=42, tickers=12, days=90)
        build_snapshot(b, seed=42, tickers=12, days=90)
        for rel in ("MANIFEST.json", "daily/prices.csv"):
            self.assertEqual((a / rel).read_bytes(), (b / rel).read_bytes(),
                             f"{rel} differs across identical builds")

    def test_fingerprint_matches_and_self_checks(self):
        info = fingerprint(self.dir / "snap-a")
        self.assertEqual(len(info.manifest_hash), 64)
        self.assertEqual(info.manifest["rows"], 12 * 90)
        self.assertLess(info.manifest["start"], info.manifest["as_of"])
        # fingerprint is a pure function of content
        again = fingerprint(self.dir / "snap-a")
        self.assertEqual(info.manifest_hash, again.manifest_hash)

    def test_different_seed_changes_fingerprint(self):
        a = fingerprint(self.dir / "snap-a")
        c = build_snapshot(self.dir / "snap-c", seed=7, tickers=12, days=90)
        self.assertNotEqual(a.manifest_hash, c.manifest_hash)

    def test_tampered_data_file_breaks_reconciliation(self):
        d = self.dir / "snap-tamper"
        build_snapshot(d, seed=42, tickers=12, days=90)
        csv = d / "daily" / "prices.csv"
        csv.write_text(csv.read_text().replace("100.0", "999.9", 1))
        with self.assertRaisesRegex(ValueError, "tampered"):
            fingerprint(d)


if __name__ == "__main__":
    unittest.main()
