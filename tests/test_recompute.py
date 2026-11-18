"""Tests for qsa.recompute (v1.4 ② recompute side): universe filter and
job estimation. The full re-run path shares the dispatcher the main run
uses (pinned by test_dispatch / the offense suite); here we pin the
policy arithmetic: bottom-quartile-by-amount = smallcap, exclusion keeps
the complement, smallcap keeps the small set, dates always survive.
"""
import unittest

from qsa.recompute import _estimate_jobs, filter_universe


def inputs_with_amounts(n_tk: int = 8):
    closes = {f"T{i}": {"20230103": 10.0} for i in range(n_tk)}
    amounts = {f"T{i}": {"20230103": float((i + 1) * 100)}
               for i in range(n_tk)}       # T0 smallest ... T7 largest
    return {"closes": closes, "amounts": amounts,
            "volumes": {tk: {"20230103": 1.0} for tk in closes},
            "dates": ["20230103"]}


class TestFilterUniverse(unittest.TestCase):
    def test_exclude_smallcap_drops_bottom_quartile(self):
        out = filter_universe(inputs_with_amounts(8),
                              {"name": "top300", "exclude": "smallcap"})
        self.assertEqual(sorted(out["closes"]),
                         [f"T{i}" for i in range(2, 8)])   # T0, T1 cut
        self.assertEqual(out["dates"], ["20230103"])

    def test_smallcap_keeps_only_bottom_quartile(self):
        out = filter_universe(inputs_with_amounts(8),
                              {"name": "smallcap"})
        self.assertEqual(sorted(out["closes"]), ["T0", "T1"])

    def test_other_universes_passthrough(self):
        out = filter_universe(inputs_with_amounts(4), {"name": "top300"})
        self.assertEqual(len(out["closes"]), 4)

    def test_min_one_ticker_survives(self):
        out = filter_universe(inputs_with_amounts(2),
                              {"name": "smallcap"})
        self.assertEqual(len(out["closes"]), 1)

    def test_estimate_jobs_positive_and_panel_aware(self):
        n = _estimate_jobs(inputs_with_amounts())
        self.assertGreater(n, 30)


if __name__ == "__main__":
    unittest.main()
