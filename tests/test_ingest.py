"""Ingestion tests: user CSV → legal snapshot; validation fails loudly."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from qsa.engine import load_frame, evaluate_signal, momentum_matrix
from qsa.ingest import ingest_csv
from qsa.snapshot import fingerprint

GOOD_CSV = """date,ticker,close,volume
2024-01-02,AAA,100.0,1000
2024-01-02,BBB,50.5,2000
2024-01-03,AAA,101.0,1100
2024-01-03,BBB,49.5,2100
2024-01-04,AAA,99.0,900
2024-01-04,BBB,52.0,2200
"""


class TestIngest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _write(self, text, name="prices.csv"):
        p = self.root / name
        p.write_text(text)
        return p

    def test_ingest_produces_working_snapshot(self):
        info = ingest_csv(self._write(GOOD_CSV), self.root / "snap")
        self.assertEqual(info.manifest["tickers"], 2)
        self.assertEqual(info.manifest["rows"], 6)
        # everything downstream works unchanged on user data
        frame = load_frame(self.root / "snap")
        self.assertEqual(len(frame.dates), 3)
        with self.assertRaises(ValueError):  # too few names for quintiles
            evaluate_signal(frame, momentum_matrix(frame.closes, frame.tickers,
                                                   frame.dates, 1))

    def test_ingest_is_deterministic(self):
        a = ingest_csv(self._write(GOOD_CSV, "a.csv"), self.root / "snap-a")
        b = ingest_csv(self._write(GOOD_CSV, "b.csv"), self.root / "snap-b")
        self.assertEqual(a.manifest_hash, b.manifest_hash)

    def test_yyyymmdd_dates_accepted(self):
        csv = GOOD_CSV.replace("2024-01-0", "2024010")
        info = ingest_csv(self._write(csv), self.root / "snap2")
        self.assertEqual(info.manifest["start"], "20240102")

    def test_missing_column_rejected(self):
        with self.assertRaisesRegex(ValueError, "'close' column"):
            ingest_csv(self._write("date,ticker,price\n"), self.root / "s")

    def test_bad_number_rejected_with_row(self):
        csv = GOOD_CSV.replace("101.0", "1O1.0")
        with self.assertRaisesRegex(ValueError, "row 4.*not numeric"):
            ingest_csv(self._write(csv), self.root / "s")

    def test_duplicate_pair_rejected(self):
        csv = GOOD_CSV + "2024-01-04,AAA,99.5,800\n"
        with self.assertRaisesRegex(ValueError, "duplicate"):
            ingest_csv(self._write(csv), self.root / "s")

    def test_empty_rejected(self):
        with self.assertRaisesRegex(ValueError, "no data rows"):
            ingest_csv(self._write("date,ticker,close\n"), self.root / "s")


if __name__ == "__main__":
    unittest.main()
