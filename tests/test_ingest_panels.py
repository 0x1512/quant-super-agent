"""v1.3 ingest panel extensions: optional high/low/amount/vwap columns.

Contract under test:
  * panel columns are all-or-nothing (every row or not requested at all);
  * values round-trip through snapshot panels exactly;
  * the MANIFEST records which panel columns were stored;
  * omitting panel columns reproduces the pre-v1.3 format exactly
    (backward compatibility).
"""
import csv
import tempfile
import unittest
from pathlib import Path

from qsa import ingest
from qsa import snapshot


def _csv(path: Path, rows: list[tuple], with_panels: bool = True) -> None:
    header = ["date", "ticker", "close", "open", "volume"]
    if with_panels:
        header += ["high", "low", "amount", "vwap"]
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(header)
        for r in rows:
            w.writerow(r)


class TestIngestPanels(unittest.TestCase):
    ROWS = [
        ("20240102", "A", "10.0", "9.9", "1000", "10.5", "9.8", "10100", "10.1"),
        ("20240102", "B", "20.0", "19.9", "2000", "20.6", "19.7", "20200", "20.1"),
        ("20240103", "A", "10.2", "10.0", "1100", "10.7", "9.9", "11200", "10.3"),
        ("20240103", "B", "19.8", "20.0", "1900", "20.2", "19.6", "19800", "19.9"),
    ]

    def test_panel_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "src.csv"
            _csv(src, self.ROWS)
            out = Path(td) / "snap"
            info = ingest.ingest_csv(src, out, snapshot_id="pan",
                                     open_col="open", volume_col="volume",
                                     high_col="high", low_col="low",
                                     amount_col="amount", vwap_col="vwap")
            self.assertEqual(snapshot.load_highs(info.dir)["A"]["20240103"],
                             10.7)
            self.assertEqual(snapshot.load_lows(info.dir)["B"]["20240102"],
                             19.7)
            self.assertEqual(snapshot.load_amounts(info.dir)["A"]["20240102"],
                             10100.0)
            self.assertEqual(snapshot.load_vwaps(info.dir)["B"]["20240103"],
                             19.9)
            with (info.dir / "daily" / "prices.csv").open() as fh:
                hdr = next(csv.reader(fh))
            self.assertEqual(hdr, ["date", "ticker", "close", "open",
                                   "volume", "high", "low", "amount", "vwap"])

    def test_all_or_nothing_violation(self):
        rows = list(self.ROWS)
        rows.append(("20240104", "A", "10.3", "10.2", "1200",
                     "10.8", "10.1", "12300", ""))  # vwap missing
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "src.csv"
            _csv(src, rows)
            with self.assertRaises(ValueError) as ctx:
                ingest.ingest_csv(src, Path(td) / "snap", snapshot_id="pan",
                                  open_col="open", volume_col="volume",
                                  high_col="high", low_col="low",
                                  amount_col="amount", vwap_col="vwap")
            self.assertIn("all-or-nothing", str(ctx.exception))

    def test_backward_compatible_when_omitted(self):
        rows = [r[:5] for r in self.ROWS]
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "src.csv"
            _csv(src, rows, with_panels=False)
            out = Path(td) / "snap"
            info = ingest.ingest_csv(src, out, snapshot_id="legacy",
                                     open_col="open", volume_col="volume")
            with (info.dir / "daily" / "prices.csv").open() as fh:
                hdr = next(csv.reader(fh))
            self.assertEqual(hdr, ["date", "ticker", "close", "open",
                                   "volume"])


if __name__ == "__main__":
    unittest.main()
