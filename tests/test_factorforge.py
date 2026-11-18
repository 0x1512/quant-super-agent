"""Tests for qsa.factorforge (v1.4 ⑥): sandbox factor generation loop.

The loop must be closed AND honest:
* gaps are machine-detected (missing panels, promised-but-empty streams)
  or explicitly requested by the intent (never silent);
* generated code passes the AST whitelist and declares its sandbox
  contract (v2/v3);
* candidates are scored by the SAME residual objective;
* every row carries source=sandbox-forge + code fingerprint; a banned
  template is a refused row, not a crash.
"""
import random
import unittest

from qsa import factorforge, sandbox


def tiny_inputs(n_dates: int = 80, n_tk: int = 6, seed: int = 7):
    rng = random.Random(seed)
    dates = [f"2023{1 + i // 28:02d}{1 + i % 28:02d}" for i in
             range(n_dates)]
    tks = [f"T{i}" for i in range(n_tk)]
    px = {tk: 10.0 for tk in tks}
    closes, opens, volumes = {}, {}, {}
    for tk in tks:
        closes[tk], opens[tk], volumes[tk] = {}, {}, {}
        for d in dates:
            px[tk] *= 1 + rng.gauss(0, 0.02)
            closes[tk][d] = round(px[tk], 4)
            opens[tk][d] = round(px[tk] * (1 + rng.gauss(0, 0.004)), 4)
            volumes[tk][d] = round(1e6 * (1 + rng.expovariate(2)), 1)
    return {"closes": closes, "opens": opens, "volumes": volumes,
            "amounts": {tk: {d: v * closes[tk][d]
                             for d, v in volumes[tk].items()}
                        for tk in tks},
            "dates": dates}


class TestDetectGaps(unittest.TestCase):
    def test_panel_gap(self):
        inputs = tiny_inputs()
        inputs.pop("amounts")            # a catalog family needs this
        healthy = [{"id": "x", "oos_ic": 0.05}]
        gaps = factorforge.detect_gaps(inputs, {"library": True},
                                       {"library": healthy},
                                       catalog_needs={"amounts"})
        self.assertEqual([(g["kind"], g["name"]) for g in gaps],
                         [("panel", "amounts")])

    def test_stream_gap_when_promised_stream_dead(self):
        inputs = tiny_inputs()
        dead = [{"id": "x", "oos_ic": -0.01}]
        gaps = factorforge.detect_gaps(
            inputs, {"library": True, "mutations": True},
            {"library": dead, "mutations": dead})
        self.assertEqual({g["name"] for g in gaps},
                         {"library", "mutations"})

    def test_healthy_run_no_gaps(self):
        inputs = tiny_inputs()
        healthy = [{"id": "x", "oos_ic": 0.05}]
        self.assertEqual(factorforge.detect_gaps(
            inputs, {"library": True}, {"library": healthy}), [])

    def test_unpromised_stream_is_not_a_gap(self):
        inputs = tiny_inputs()
        healthy = [{"id": "x", "oos_ic": 0.05}]
        self.assertEqual(factorforge.detect_gaps(
            inputs, {"library": True, "mutations": False},
            {"library": healthy, "mutations": []}), [])


class TestGenerate(unittest.TestCase):
    def test_six_specs_all_tagged(self):
        specs = factorforge.generate([{"kind": "panel", "name": "amounts",
                                       "why": "x"}])
        self.assertEqual(len(specs), 6)          # 3 families x 2 windows
        for s in specs:
            self.assertEqual(s["source"], "sandbox-forge")
            self.assertEqual(len(s["code_fp"]), 8)
            self.assertIn("panel:amounts", s["fills"])

    def test_templates_pass_ast_whitelist_with_contracts(self):
        contracts = {"forge_turnover_shock": "v2",
                     "forge_overnight_reversal": "v3",
                     "forge_price_volume_div": "v2"}
        for s in factorforge.generate([]):
            sandbox.check_code(s["code"])        # must not raise
            self.assertEqual(sandbox.contract_of(s["code"]),
                             contracts[s["family"]])


class TestEvaluate(unittest.TestCase):
    def test_scored_rows_carry_source_and_fingerprint(self):
        inputs = tiny_inputs()
        specs = factorforge.generate([])
        rows = factorforge.evaluate_specs(specs[:2], inputs, basis=None)
        for r in rows:
            self.assertEqual(r["source"], "sandbox-forge")
            self.assertTrue(r["ok"])
            self.assertIn("code_fp", r)
            self.assertIn("forge_", r["id"])

    def test_banned_code_is_a_refused_row_not_a_crash(self):
        inputs = tiny_inputs()
        bad = {"id": "evil", "family": "evil", "source": "sandbox-forge",
               "desc": "imports os", "needs": [],
               "code": "import os\n\ndef factor(closes, tickers, dates,"
                       " i):\n    return {}\n",
               "code_fp": "deadbeef", "fills": []}
        rows = factorforge.evaluate_specs([bad], inputs, basis=None)
        self.assertFalse(rows[0]["ok"])
        self.assertIn("SandboxError", rows[0]["refused"])

    def test_fill_gaps_end_to_end_on_dead_stream(self):
        inputs = tiny_inputs()
        dead = [{"id": "x", "oos_ic": -0.01}]
        rows, gaps = factorforge.fill_gaps(
            inputs, {"library": True}, {"library": dead})
        self.assertTrue(gaps)
        self.assertEqual(len(rows), 6)
        self.assertTrue(any(r.get("ok") for r in rows))

    def test_force_runs_even_without_gaps(self):
        inputs = tiny_inputs()
        healthy = [{"id": "x", "oos_ic": 0.05}]
        rows, gaps = factorforge.fill_gaps(
            inputs, {"library": True, "forge": True},
            {"library": healthy}, force=True)
        self.assertEqual(len(rows), 6)
        self.assertTrue(any(g["kind"] == "request" for g in gaps))

    def test_no_force_no_gaps_noop(self):
        inputs = tiny_inputs()
        healthy = [{"id": "x", "oos_ic": 0.05}]
        rows, gaps = factorforge.fill_gaps(
            inputs, {"library": True}, {"library": healthy})
        self.assertEqual((rows, gaps), ([], []))


class TestRenderLog(unittest.TestCase):
    def test_no_gap_render(self):
        md = factorforge.render_forge_log([], [])
        self.assertIn("无缺口", md)

    def test_log_lists_gaps_and_verdicts(self):
        inputs = tiny_inputs()
        dead = [{"id": "x", "oos_ic": -0.01}]
        rows, gaps = factorforge.fill_gaps(
            inputs, {"library": True}, {"library": dead})
        md = factorforge.render_forge_log(rows, gaps)
        self.assertIn("缺口（机器检测）", md)
        self.assertIn("stream", md)
        self.assertIn("code@", md)
        self.assertIn("来源标注", md)


if __name__ == "__main__":
    unittest.main()
