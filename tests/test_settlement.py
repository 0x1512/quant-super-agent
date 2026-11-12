"""Settlement-ledger tests: simulator extension, hash-chain tamper paths
(FIB 19), the reflection rule, gate integration, calibration report (v0.5)."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from qsa import settlement, verify
from qsa.ablation import run_one
from qsa.snapshot import build_snapshot, extend_world, fingerprint

PLANT = {"effect": "reversal", "strength": 0.15}
FULL_STACK = {"label": "st", "roles": ("data", "factor", "risk"), "rounds": 1}


def admitted_cards(work: Path) -> tuple[dict, dict]:
    cards = sorted((work / "cards").glob("E-*.json"))
    e = json.loads(cards[-1].read_text("utf-8"))
    h = json.loads((work / "cards" / f"{e['hyp_id']}.json").read_text("utf-8"))
    return e, h


class TestWorldExtension(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_extension_is_prefix_and_deterministic(self):
        build_snapshot(self.root / "base", seed=11, tickers=12, days=90,
                       plant=PLANT)
        a = extend_world(self.root / "ea", self.root / "base", 90)
        b = extend_world(self.root / "eb", self.root / "base", 90)
        self.assertEqual(a.manifest_hash, b.manifest_hash)
        base_rows = (self.root / "base/daily/prices.csv").read_text().splitlines()
        ext_rows = (self.root / "ea/daily/prices.csv").read_text().splitlines()
        self.assertEqual(ext_rows[:len(base_rows)], base_rows)
        self.assertEqual(a.manifest["days"], 180)
        # the cached path returns the same fingerprint
        c = extend_world(self.root / "ea", self.root / "base", 90)
        self.assertEqual(c.manifest_hash, a.manifest_hash)

    def test_real_data_world_refuses_extension(self):
        build_snapshot(self.root / "w", seed=3, tickers=12, days=90)
        m = json.loads((self.root / "w/MANIFEST.json").read_text("utf-8"))
        del m["seed"]  # an ingested world has no generator
        (self.root / "w/MANIFEST.json").write_text(
            json.dumps(m, sort_keys=True, separators=(",", ":")) + "\n")
        with self.assertRaises(ValueError) as cm:
            extend_world(self.root / "e", self.root / "w", 20)
        self.assertIn("not a synthetic world", str(cm.exception))


class TestSettlement(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.world = self.root / "planted"
        build_snapshot(self.world, seed=11, tickers=12, days=90, plant=PLANT)
        self.work = self.root / "run"
        self.summary = run_one(self.work, self.world, FULL_STACK)
        self.assertTrue(self.summary["admitted"])
        self.e, self.h = admitted_cards(self.work)
        self.ledger = settlement.SettlementLedger.open(
            self.root / "settlement.jsonl")

    def tearDown(self):
        self.tmp.cleanup()

    def settle(self, **kw) -> dict:
        return settlement.settle_claim(
            self.ledger, self.e, self.h, self.world,
            self.root / "ext", **kw)

    def test_planted_claim_holds_and_entry_recomputes(self):
        entry = self.settle()
        self.assertEqual(entry["outcome"], "held")
        self.assertEqual(entry["world"]["seed"], 11)
        self.assertEqual(entry["world"]["extension_days"], 90)
        self.assertEqual(entry["seq"], 1)
        self.assertEqual(entry["prev_hash"], settlement.GENESIS)
        self.assertEqual(
            settlement.audit_ledger(self.root / "settlement.jsonl"), [])

    def test_settlement_is_deterministic_byte_for_byte(self):
        self.settle()
        first = (self.root / "settlement.jsonl").read_bytes()
        other = settlement.SettlementLedger.open(self.root / "other.jsonl")
        settlement.settle_claim(other, self.e, self.h, self.world,
                                self.root / "ext2")
        self.assertEqual(first, (self.root / "other.jsonl").read_bytes())

    def test_outcome_is_mechanical(self):
        # the same claim judged against a bar it cannot clear falls short —
        # outcome comes from the pre-registered bar, never from opinion
        h = json.loads(json.dumps(self.h))
        h["admission"]["thresholds"]["rankic_mean"]["value"] = 0.9
        led = settlement.SettlementLedger.open(self.root / "high.jsonl")
        entry = settlement.settle_claim(led, self.e, h, self.world,
                                        self.root / "ext-hi")
        self.assertEqual(entry["outcome"], "fell_short")
        self.assertEqual(settlement.audit_ledger(self.root / "high.jsonl"),
                         [])

    def test_double_settlement_refused(self):
        self.settle()
        with self.assertRaises(settlement.SettlementError):
            self.settle()


class TestTamperPaths(unittest.TestCase):
    """FIB 19: edit, delete, reorder, rechain-with-lies, phantom exp_id."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.led_path = self.root / "settlement.jsonl"
        led = settlement.SettlementLedger.open(self.led_path)
        for seed in (11, 22, 33):
            world = self.root / f"w{seed}"
            build_snapshot(world, seed=seed, tickers=12, days=90, plant=PLANT)
            work = self.root / f"r{seed}"
            summary = run_one(work, world, FULL_STACK)
            self.assertTrue(summary["admitted"])
            e, h = admitted_cards(work)
            settlement.settle_claim(led, e, h, world, self.root / f"e{seed}")
        self.assertEqual(settlement.audit_ledger(self.led_path), [])
        self.lines = self.led_path.read_text("utf-8").splitlines()

    def tearDown(self):
        self.tmp.cleanup()

    def _rewrite(self, lines: list[str]) -> None:
        self.led_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _rechain(self, lines: list[str]) -> list[str]:
        # a competent adversary: recompute the chain after editing payloads
        prev = settlement.GENESIS
        out = []
        for i, line in enumerate(lines, 1):
            en = json.loads(line)
            en["seq"] = i
            en["prev_hash"] = prev
            en["entry_hash"] = settlement._entry_hash(en)
            prev = en["entry_hash"]
            out.append(json.dumps(en, sort_keys=True,
                                  separators=(",", ":")))
        return out

    def test_edit_breaks_chain(self):
        en = json.loads(self.lines[1])
        en["claimed"]["value"] = 0.5
        self._rewrite([self.lines[0], json.dumps(en, sort_keys=True,
                                                 separators=(",", ":"))])
        errs = settlement.audit_ledger(self.led_path)
        self.assertTrue(any("entry_hash" in x for x in errs))

    def test_mid_ledger_deletion_breaks_chain(self):
        self._rewrite([self.lines[0], self.lines[2]])
        errs = settlement.audit_ledger(self.led_path)
        self.assertTrue(any("prev_hash" in x or "seq" in x for x in errs))

    def test_reorder_breaks_chain(self):
        self._rewrite(list(reversed(self.lines)))
        errs = settlement.audit_ledger(self.led_path)
        self.assertTrue(any("seq" in x or "prev_hash" in x for x in errs))

    def test_rechained_lie_fails_recompute(self):
        en = json.loads(self.lines[0])
        en["realized"]["rankic_mean"] = 0.42  # the flattering fabrication
        lines = self._rechain([json.dumps(en, sort_keys=True,
                                          separators=(",", ":")),
                               self.lines[1]])
        self._rewrite(lines)
        errs = settlement.audit_ledger(self.led_path)
        self.assertTrue(any("realized.rankic_mean" in x for x in errs))

    def test_rechained_outcome_lie_fails_recompute(self):
        en = json.loads(self.lines[0])
        if en["outcome"] == "held":
            en["outcome"] = "fell_short"
        else:
            en["outcome"] = "held"
        lines = self._rechain([json.dumps(en, sort_keys=True,
                                          separators=(",", ":")),
                               self.lines[1]])
        self._rewrite(lines)
        errs = settlement.audit_ledger(self.led_path)
        self.assertTrue(any("outcome" in x for x in errs))

    def test_phantom_exp_id_caught_with_registry(self):
        en = json.loads(self.lines[0])
        en["exp_id"] = "E-9999"
        lines = self._rechain([json.dumps(en, sort_keys=True,
                                          separators=(",", ":")),
                               self.lines[1]])
        self._rewrite(lines)
        errs = settlement.audit_ledger(
            self.led_path, registry_path=self.root / "r11/registry.jsonl")
        self.assertTrue(any("claim nobody made" in x for x in errs))


class TestReflectionRule(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _ledger(self, outcomes: list[str]) -> settlement.SettlementLedger:
        self._n = getattr(self, "_n", 0) + 1
        led = settlement.SettlementLedger.open(
            self.root / f"l{self._n}.jsonl")
        for i, outcome in enumerate(outcomes, 1):
            led.record({"schema": "settlement", "settle_id": f"S-{i:04d}",
                        "exp_id": f"E-{i:04d}", "family": "f",
                        "outcome": outcome,
                        "base_snapshot_hash": f"{i:064x}"})
        return led

    def test_rule_only_tightens(self):
        led = self._ledger(["fell_short"] * 6)
        mult, basis = settlement.admission_multiplier(led, "f")
        self.assertEqual(mult, settlement.TIGHTEN_MULTIPLIER)
        self.assertIn("fell short", basis)
        # a spotless history never relaxes anything
        led2 = self._ledger(["held"] * 6)
        self.assertEqual(settlement.admission_multiplier(led2, "f")[0], 1.0)
        # mixed history below the trigger ratio: no adjustment
        led3 = self._ledger(["fell_short"] * 2 + ["held"] * 3)
        self.assertEqual(settlement.admission_multiplier(led3, "f")[0], 1.0)
        # too little history: the ledger says nothing
        led4 = self._ledger(["fell_short"] * 4)
        self.assertEqual(settlement.admission_multiplier(led4, "f")[0], 1.0)
        # another family's failures do not tighten this one
        self.assertEqual(settlement.admission_multiplier(led, "other")[0], 1.0)


class TestMiningReflectionIntegration(unittest.TestCase):
    """A shortfall history tightens the next order; the gate re-derives it."""

    def _run(self, work, world, *, rounds=1,
             roles=("data", "factor", "risk"), settlement=None):
        from qsa.ablation import policy_queue
        from qsa.engine import load_frame
        from qsa.llm import ScriptedLLM
        from qsa.mining import run_order

        ds = load_frame(world).dates
        llm = ScriptedLLM(policy_queue(f"{ds[-15]}:{ds[-1]}", rounds) * 3)
        return run_order(work, world, "Mine one factor.", llm, budget=3,
                         family="reflect", roles=roles,
                         debate_rounds=rounds, settlement_ledger=settlement,
                         verbose=False)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        # an audit-clean shortfall history for family 'reflect': six admitted
        # planted claims judged against a bar (0.9) they cannot clear — a
        # test fixture for the rule, settled through the real pipeline
        self.led_path = self.root / "shortfalls.jsonl"
        led = settlement.SettlementLedger.open(self.led_path)
        for seed in (11, 22, 33, 55, 66, 77):
            world = self.root / f"w{seed}"
            build_snapshot(world, seed=seed, tickers=12, days=90, plant=PLANT)
            work = self.root / f"r{seed}"
            summary = self._run(work, world)
            self.assertTrue(summary["admitted"])
            e, h = admitted_cards(work)
            h["admission"]["thresholds"]["rankic_mean"]["value"] = 0.9
            entry = settlement.settle_claim(led, e, h, world,
                                            self.root / f"e{seed}")
            self.assertEqual(entry["outcome"], "fell_short")
        self.assertEqual(settlement.audit_ledger(self.led_path), [])
        mult, _ = settlement.admission_multiplier(led, "reflect")
        self.assertEqual(mult, settlement.TIGHTEN_MULTIPLIER)

    def tearDown(self):
        self.tmp.cleanup()

    def test_next_order_tightens_and_gate_accepts(self):
        world = self.root / "w88"
        build_snapshot(world, seed=88, tickers=12, days=90, plant=PLANT)
        work = self.root / "reflect-run"
        summary = self._run(work, world, settlement=self.led_path)
        self.assertTrue(summary["admitted"])  # the bar rose; truth cleared it
        h = json.loads((work / "cards/H-0001.json").read_text("utf-8"))
        self.assertEqual(h["calibration"]["multiplier"],
                         settlement.TIGHTEN_MULTIPLIER)
        self.assertEqual(
            h["admission"]["thresholds"]["rankic_mean"]["value"], 0.025)
        # the gate re-derived the ledger rule and still merged the PR
        self.assertTrue(any(r.get("merged") for r in summary["iterations"]))

    def test_gate_rejects_calibration_lies(self):
        world = self.root / "w99"
        build_snapshot(world, seed=99, tickers=12, days=90, plant=PLANT)
        work = self.root / "honest-run"
        self._run(work, world, rounds=0, roles=("data", "factor"),
                  settlement=self.led_path)
        h_path = work / "cards/H-0001.json"
        e_path = work / "cards/E-0001.json"

        # 1) dropping the tightening the ledger demands
        h = json.loads(h_path.read_text("utf-8"))
        del h["calibration"]
        h["admission"]["thresholds"]["rankic_mean"]["value"] = 0.02
        h_path.write_text(json.dumps(h, sort_keys=True, indent=2))
        ok, errs = verify.gate(h_path, e_path, world,
                               registry_path=work / "registry.jsonl",
                               settlement_path=self.led_path)
        self.assertFalse(ok)
        self.assertTrue(any("demands" in x for x in errs))

        # 2) claiming a rosier multiplier than the ledger supports
        h = json.loads(h_path.read_text("utf-8"))
        h["calibration"] = {"multiplier": 1.0, "basis": "all held"}
        h_path.write_text(json.dumps(h, sort_keys=True, indent=2))
        ok, errs = verify.gate(h_path, e_path, world,
                               registry_path=work / "registry.jsonl",
                               settlement_path=self.led_path)
        self.assertFalse(ok)
        self.assertTrue(any("rosier" in x for x in errs))

        # 3) a calibration block without any ledger to check it against
        ok, errs = verify.gate(h_path, e_path, world,
                               registry_path=work / "registry.jsonl")
        self.assertFalse(ok)
        self.assertTrue(any("unverifiable calibration" in x for x in errs))


class TestCalibrationReport(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_report_from_ledger(self):
        led = settlement.SettlementLedger.open(self.root / "l.jsonl")
        for i, (claim, real, outcome, plant) in enumerate((
                (0.117, 0.104, "held", True),
                (0.03, 0.01, "fell_short", False),
                (0.05, 0.04, "held", True),
                (0.027, 0.05, "held", False)), 1):
            led.record({
                "schema": "settlement", "settle_id": f"S-{i:04d}",
                "exp_id": f"E-{i:04d}", "family": "f", "iteration": 1,
                "world": {"plant": {"effect": "reversal",
                                    "strength": 0.15} if plant else None},
                "claimed": {"value": claim, "metric": "rankic_mean"},
                "realized": {"rankic_mean": real},
                "outcome": outcome,
                "base_snapshot_hash": f"{i:064x}"})
        rep = settlement.calibration_report(led)
        self.assertEqual(rep["n_settled"], 4)
        self.assertEqual(rep["held"], 3)
        self.assertEqual(rep["fell_short"], 1)
        self.assertEqual(rep["by_truth"]["planted"]["n"], 2)
        self.assertEqual(rep["by_truth"]["noise"]["n"], 2)
        self.assertIn("curve", rep)
        md = settlement.report_markdown(rep)
        self.assertIn("| claimed rank IC bin |", md)
        self.assertIn("- noise: n=2", md)


class TestCalibrationAcceptance(unittest.TestCase):
    """The v0.5 acceptance: >= 50 settled claims, byte-reproducible."""

    def test_full_sweep_is_deterministic_and_meets_bar(self):
        import hashlib
        from qsa.settlement import run_calibration_sweep

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            r1 = run_calibration_sweep(root / "a")
            self.assertEqual(r1["audit_errors"], [])
            self.assertGreaterEqual(r1["report"]["n_settled"], 50)
            r2 = run_calibration_sweep(root / "b")
            h1 = hashlib.sha256(
                (root / "a/report.json").read_bytes()).hexdigest()
            h2 = hashlib.sha256(
                (root / "b/report.json").read_bytes()).hexdigest()
            self.assertEqual(h1, h2)
            led1 = (root / "a/settlement.jsonl").read_bytes()
            led2 = (root / "b/settlement.jsonl").read_bytes()
            self.assertEqual(led1, led2)
            # the honest shape: planted claims calibrate, noise claims decay
            rep = r1["report"]
            self.assertEqual(rep["by_truth"]["planted"]["held"],
                             rep["by_truth"]["planted"]["n"])
            self.assertLess(rep["by_truth"]["noise"]["mean_gap"],
                            rep["by_truth"]["planted"]["mean_gap"])


if __name__ == "__main__":
    unittest.main()
