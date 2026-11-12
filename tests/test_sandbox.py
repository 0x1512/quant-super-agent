"""Sandbox tests: AST whitelist, truncated-view lookahead defence, output
validation."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from qsa.sandbox import SandboxError, run_factor
from qsa.snapshot import build_snapshot, load_closes, fingerprint

GOOD = '''def factor(closes, tickers, dates, i):
    if i < 10:
        return {}
    out = {}
    t = dates[i]
    lag = dates[i - 10]
    for tk in tickers:
        row = closes[tk]
        a = row.get(t)
        b = row.get(lag)
        if a is None or b is None or b == 0:
            continue
        out[tk] = a / b - 1.0
    return out'''


class TestSandbox(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.snap = build_snapshot(Path(cls.tmp.name) / "snapshot",
                                  seed=42, tickers=12, days=90)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def _run(self, code):
        closes = load_closes(self.snap.dir)
        manifest = self.snap.manifest
        dates = sorted({d for row in closes.values() for d in row
                        if manifest["start"] <= d <= manifest["as_of"]})
        tickers = sorted(closes)
        return run_factor(code, closes, tickers, dates)

    def test_good_factor_runs(self):
        matrix = self._run(GOOD)
        self.assertGreaterEqual(len(matrix), 5)
        self.assertTrue(all(isinstance(v, float) for row in matrix.values()
                            for v in row.values()))

    def _assert_rejected(self, code, fragment: str):
        with self.assertRaises(SandboxError) as ctx:
            self._run(code)
        self.assertIn(fragment, str(ctx.exception))

    def test_import_rejected(self):
        self._assert_rejected(
            "def factor(closes, tickers, dates, i):\n"
            "    import os\n    return {}\n", "imports are not allowed")

    def test_dunder_attribute_rejected(self):
        self._assert_rejected(
            "def factor(closes, tickers, dates, i):\n"
            "    x = closes.__class__\n    return {}\n",
            "attribute access")

    def test_open_rejected(self):
        self._assert_rejected(
            "def factor(closes, tickers, dates, i):\n"
            "    f = open('/etc/passwd')\n    return {}\n",
            "not allowed")

    def test_while_rejected(self):
        self._assert_rejected(
            "def factor(closes, tickers, dates, i):\n"
            "    while i > 0:\n        i = i - 1\n    return {}\n",
            "while-loops")

    def test_wrong_signature_rejected(self):
        self._assert_rejected(
            "def factor(data):\n    return {}\n", "closes, tickers, dates, i")

    def test_two_functions_rejected(self):
        self._assert_rejected(
            "def helper():\n    return 1\n"
            "def factor(closes, tickers, dates, i):\n    return {}\n",
            "exactly one function")

    def test_future_data_cannot_be_named(self):
        """The structural lookahead defence: a factor trying to read the next
        date's close gets nothing (the truncated view has no tomorrow)."""
        code = '''def factor(closes, tickers, dates, i):
    out = {}
    if i + 1 >= len(dates):
        return out
    t = dates[i]
    nxt = dates[i + 1]
    for tk in tickers:
        row = closes[tk]
        a = row.get(t)
        b = row.get(nxt)
        if b is not None and a is not None and a != 0:
            out[tk] = b / a - 1.0
    return out'''
        with self.assertRaises(SandboxError) as ctx:
            self._run(code)
        # the cheat never produces a usable signal: tomorrow is never there
        self.assertIn("only", str(ctx.exception))

    def test_non_finite_output_rejected(self):
        self._assert_rejected(
            "def factor(closes, tickers, dates, i):\n"
            "    return {tk: 1e308 * 10.0 for tk in tickers}\n",
            "finite")

    def test_runtime_error_wrapped(self):
        self._assert_rejected(
            "def factor(closes, tickers, dates, i):\n"
            "    return {tk: 1.0 / 0.0 for tk in tickers}\n",
            "factor raised ZeroDivisionError")

    def test_capped_range(self):
        self._assert_rejected(
            "def factor(closes, tickers, dates, i):\n"
            "    x = list(range(100000000))\n"
            "    return {tk: len(x) for tk in tickers}\n",
            "exceeds sandbox limit")


if __name__ == "__main__":
    unittest.main()
