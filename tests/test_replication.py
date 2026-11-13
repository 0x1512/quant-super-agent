import csv
import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from qsa import admission, registry, replication, snapshot, verify
from qsa.engine import EVAL_ID, evaluate_signal, load_frame
from qsa.ingest import ingest_csv
from qsa.sandbox import SandboxError, contract_of, run_factor
from qsa.snapshot import sha256_bytes

from qsa.ingest import ingest_csv
from qsa.replication import (GAP_CODE, REVERSAL_CODE, apply_preregistered_rules,
                             group_monthly_returns, ic_summary,
                             month_end_indices, monthly_ic_series,
                             neutralize, spearman_impl_a, spearman_impl_b)
from qsa.sandbox import SandboxError, contract_of, run_factor


def _toy_world(tmp: Path, *, n_tickers=12, days=120, gap_odd=0.01):
    """Deterministic toy OHLCV world: named tickers, odd/even overnight gaps."""
    rows = []
    d0 = date(2024, 1, 1)
    state = {f"T{k}": 100.0 * (1 + k * 0.3) for k in range(n_tickers)}
    gaps = {f"T{k}": (gap_odd if k % 2 == 1 else 0.0) for k in range(n_tickers)}
    for i in range(days):
        d = (d0 + timedelta(days=i)).strftime("%Y%m%d")
        for tk in sorted(state):
            op = state[tk] * (1 + gaps[tk])
            state[tk] = op * 1.001
            rows.append((d, tk, round(state[tk], 4), round(op, 4), 1_000_000))
    p = tmp / "p.csv"
    with p.open("w", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["date", "ticker", "close", "open", "volume"])
        w.writerows(rows)
    return p


class TestSandboxV3(unittest.TestCase):
    def test_contract_detection(self):
        self.assertEqual(contract_of(GAP_CODE), "v3")
        self.assertEqual(contract_of(REVERSAL_CODE), "v1")

    def test_v3_signature_required(self):
        with self.assertRaises(SandboxError):
            contract_of("def factor(closes, opens, tickers, dates, i):\n"
                        "    return {}\n")

    def test_v3_without_opens_refused_loudly(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            csv_p = _toy_world(tmp)
            ingest_csv(csv_p, tmp / "snap", volume_col="volume", open_col="open")
            frame = load_frame(tmp / "snap")
            # volumes present, opens stripped from the frame on purpose
            with self.assertRaises(SandboxError) as cm:
                run_factor(GAP_CODE, frame.closes, frame.tickers,
                           frame.dates, frame.volumes, None)
            self.assertIn("opens", str(cm.exception))

    def test_v3_without_volumes_refused_loudly(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            csv_p = _toy_world(tmp)
            ingest_csv(csv_p, tmp / "snap", volume_col="volume", open_col="open")
            frame = load_frame(tmp / "snap")
            with self.assertRaises(SandboxError) as cm:
                run_factor(GAP_CODE, frame.closes, frame.tickers,
                           frame.dates, None, frame.opens)
            self.assertIn("volumes", str(cm.exception))

    def test_v1_and_v2_still_run(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            csv_p = _toy_world(tmp)
            ingest_csv(csv_p, tmp / "snap", volume_col="volume", open_col="open")
            frame = load_frame(tmp / "snap")
            sig = run_factor(REVERSAL_CODE, frame.closes, frame.tickers,
                             frame.dates, frame.volumes, frame.opens)
            self.assertTrue(sig)
            v2 = ("def factor(closes, volumes, tickers, dates, i):\n"
                  "    return {tk: volumes.get(tk, {}).get(dates[i], 0.0) "
                  "for tk in tickers}\n")
            sig2 = run_factor(v2, frame.closes, frame.tickers,
                              frame.dates, frame.volumes, frame.opens)
            self.assertTrue(sig2)

    def test_ingest_open_column_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            csv_p = _toy_world(tmp)
            info = ingest_csv(csv_p, tmp / "snap", volume_col="volume",
                              open_col="open", snapshot_id="v3-test")
            frame = load_frame(tmp / "snap")
            self.assertEqual(len(frame.opens), 12)
            self.assertEqual(len(frame.opens["T0"]), info.manifest["days"])
            header = (tmp / "snap" / "daily" / "prices.csv").read_text(
                ).splitlines()[0]
            self.assertEqual(header, "date,ticker,close,open,volume")

    def test_ingest_partial_open_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            csv_p = _toy_world(tmp)
            lines = csv_p.read_text().splitlines()
            lines[3] = lines[3].replace(",1000000", ",1000000", 1)
            # blank out the open cell on row 3
            cells = lines[3].split(",")
            cells[3] = ""
            lines[3] = ",".join(cells)
            csv_p.write_text("\n".join(lines) + "\n")
            with self.assertRaises(ValueError):
                ingest_csv(csv_p, tmp / "snap", volume_col="volume", open_col="open")


class TestMonthlyPlane(unittest.TestCase):
    def test_month_end_indices(self):
        dates = ["20240101", "20240102", "20240131", "20240201", "20240229"]
        self.assertEqual(month_end_indices(dates), [2, 4])

    def test_spearman_implementations_agree(self):
        import random
        rng = random.Random(7)
        for _ in range(50):
            x = [rng.gauss(0, 1) for _ in range(30)]
            y = [a * 0.5 + rng.gauss(0, 1) for a in x]
            # add ties
            x = [round(v, 1) for v in x]
            self.assertAlmostEqual(spearman_impl_a(x, y),
                                   spearman_impl_b(x, y), places=12)

    def test_monthly_ic_series_double_compute(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            csv_p = _toy_world(tmp)
            ingest_csv(csv_p, tmp / "snap", volume_col="volume", open_col="open")
            frame = load_frame(tmp / "snap")
            sig = run_factor(GAP_CODE, frame.closes, frame.tickers,
                             frame.dates, frame.volumes, frame.opens)
            series = monthly_ic_series(frame.closes, frame.dates, sig)
            self.assertGreater(len(series), 2)
            for s in series:
                self.assertIn("ic", s)
                self.assertIn("n", s)
            # gap factor high (odd tickers drift faster) -> positive IC here
            summ = ic_summary(series)
            self.assertGreater(summ["ic_mean"], 0.3)

    def test_group_returns_direction(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            csv_p = _toy_world(tmp)
            ingest_csv(csv_p, tmp / "snap", volume_col="volume", open_col="open")
            frame = load_frame(tmp / "snap")
            sig = run_factor(GAP_CODE, frame.closes, frame.tickers,
                             frame.dates, frame.volumes, frame.opens)
            g = group_monthly_returns(frame.closes, frame.dates, sig)
            self.assertEqual(sorted(g), ["G1", "G2", "G3", "G4", "G5"])
            # G1 = LOWEST gap (even tickers, no gap, slow drift);
            # G5 = highest gap (odd, fast drift up) out-earns G1 in this
            # constructed world -> the monthly plane sees the effect
            self.assertGreater(g["G5"], g["G1"])


class TestNeutralize(unittest.TestCase):
    def test_raw_passthrough(self):
        vals = {"A": 1.0, "B": 2.0}
        self.assertEqual(neutralize(vals, None, None, "raw"), vals)

    def test_cap_neutral_kills_cap_loading(self):
        import random
        rng = random.Random(3)
        caps = {f"N{i}": 10 ** rng.uniform(9, 12) for i in range(40)}
        vals = {f"N{i}": 2.0 * __import__("math").log(caps[f"N{i}"])
                + rng.gauss(0, 1e-9) for i in range(40)}
        out = neutralize(vals, caps, None, "cap")
        self.assertLess(max(abs(v) for v in out.values()), 1e-6)

    def test_cap_industry_neutral(self):
        import math
        import random
        rng = random.Random(5)
        caps = {f"N{i}": 10 ** rng.uniform(9, 12) for i in range(60)}
        inds = {f"N{i}": f"I{i % 5}" for i in range(60)}
        vals = {f"N{i}": 1.5 * math.log(caps[f"N{i}"])
                + (2.0 if inds[f"N{i}"] == "I2" else 0.0)
                + rng.gauss(0, 1e-9) for i in range(60)}
        out = neutralize(vals, caps, inds, "cap_industry")
        self.assertLess(max(abs(v) for v in out.values()), 1e-6)

    def test_unknown_names_get_zero_not_silent_drop(self):
        vals = {"A": 1.0, "B": 2.0, "NOCAP": 3.0}
        out = neutralize(vals, {"A": 1e10, "B": 2e10}, None, "cap")
        self.assertIn("NOCAP", out)   # universe stable across variants
        self.assertEqual(out["NOCAP"], 0.0)


class TestPreregisteredRules(unittest.TestCase):
    def _summary(self, raw_ic, p_neg, other_ics):
        variants = {
            "raw": {"ic_mean": raw_ic, "p_ic_negative": p_neg},
            "cap": {"ic_mean": other_ics[0], "p_ic_negative": p_neg},
            "cap_industry": {"ic_mean": other_ics[1], "p_ic_negative": p_neg},
        }
        return {"variants": variants}

    def test_pass(self):
        s = self._summary(-0.09, 0.75, [-0.08, -0.07])
        r = apply_preregistered_rules(s, {"G1": 0.02, "G5": -0.10})
        self.assertEqual(r["verdict"], "replicated")
        self.assertTrue(r["D1_direction"])
        self.assertTrue(r["D2_monotonicity"])

    def test_fail_direction(self):
        s = self._summary(0.02, 0.45, [0.01, -0.04])
        r = apply_preregistered_rules(s, {"G1": 0.02, "G5": -0.10})
        self.assertEqual(r["verdict"], "not_replicated")
        self.assertFalse(r["D1_direction"])

    def test_fail_monotonicity(self):
        s = self._summary(-0.09, 0.75, [-0.08, -0.07])
        r = apply_preregistered_rules(s, {"G1": -0.05, "G5": 0.10})
        self.assertEqual(r["verdict"], "not_replicated")
        self.assertFalse(r["D2_monotonicity"])

    def test_magnitude_band(self):
        s = self._summary(-0.06, 0.75, [-0.06, -0.05])
        r = apply_preregistered_rules(s, {"G1": 0.02, "G5": -0.10})
        self.assertEqual(r["D3_magnitude"], "consistent")
        s2 = self._summary(-0.01, 0.75, [-0.03, -0.035])
        r2 = apply_preregistered_rules(s2, {"G1": 0.02, "G5": -0.10})
        self.assertEqual(r2["D3_magnitude"], "gap")


if __name__ == "__main__":
    unittest.main()


class TestGateReplicationBlock(unittest.TestCase):
    """The full Scenario-A gate path on a toy world: honest card passes,
    each fabrication injection is caught with a named error."""

    def _build(self, tmp: Path):
        csv_p = _toy_world(tmp, n_tickers=12, days=400)
        meta = tmp / "replication_meta"
        meta.mkdir()
        (meta / "monthly_caps.csv").write_text(
            "month,ticker,cap_proxy\n"
            + "".join(f"2024{m // 12:02d}{m % 12 + 1:02d},T{k},{1_000_000 + 1_000 * k}\n"
                      for m in range(1, 25) for k in range(12)),
            encoding="utf-8")
        (meta / "industries.csv").write_text(
            "ticker,industry\n"
            + "".join(f"T{k},I{k % 3}\n" for k in range(12)),
            encoding="utf-8")
        snap = tmp / "snap"
        ingest_csv(csv_p, snap, volume_col="volume", open_col="open",
                   snapshot_id="toy-main", meta_dir=meta)
        full = load_frame(snap)
        signal = run_factor(GAP_CODE, full.closes, full.tickers,
                            full.dates, full.volumes, full.opens)
        frame = load_frame(snap, "20240601:20250131")
        m = replication.load_monthly_meta(snap)
        rb = replication.recompute_replication_block(
            frame.closes, frame.dates, signal, m)
        metrics = evaluate_signal(frame, signal)
        verdict, reasons = admission.evaluate(ADMISSION, metrics)
        assert verdict is not None, reasons
        h = {"schema": "hypothesis", "hyp_id": "H-901", "family": "overnight",
             "mechanism": "overnight gap earns lower next-month returns",
             "falsifiable_condition": "monthly IC not negative, or G1<=G5",
             "admission": ADMISSION, "window": "20240601:20250131",
             "ttl_days": 3650, "status": "registered",
             "created_at": "2025-01-01",
             "preregistered_rules": replication.PREREGISTERED_RULES}
        e = {"schema": "experiment_result", "exp_id": "E-901",
             "hyp_id": "H-901",
             "snapshot_hash": snapshot.fingerprint(snap).manifest_hash,
             "window": "20240601:20250131", "engine": EVAL_ID,
             "factor_code": GAP_CODE,
             "factor_code_sha256": sha256_bytes(GAP_CODE.encode("utf-8")),
             "metrics": metrics, "replication_block": rb,
             "verdict": verdict, "settled_at": "2024-12-31"}
        h_p, e_p = tmp / "h.json", tmp / "e.json"
        h_p.write_text(json.dumps(h))
        e_p.write_text(json.dumps(e))
        reg_p = tmp / "registry.jsonl"
        reg = registry.Registry.open(reg_p)
        if not reg.has_hypothesis("H-901"):
            reg.register_hypothesis(h)
        return snap, h_p, e_p, reg_p, e, h, rb

    def test_honest_card_passes_full_gate(self):
        with tempfile.TemporaryDirectory() as td:
            snap, h_p, e_p, reg_p, *_ = self._build(Path(td))
            ok, errs = verify.gate(h_p, e_p, snap, registry_path=reg_p)
            self.assertTrue(errs == [], errs)
            self.assertTrue(ok)

    def test_metric_edit_injection_caught(self):
        with tempfile.TemporaryDirectory() as td:
            snap, h_p, e_p, reg_p, e, *_ = self._build(Path(td))
            bad = json.loads(json.dumps(e))
            bad["replication_block"]["ic_variants"]["raw"]["ic_mean"] += 0.01
            bad_p = Path(td) / "bad.json"
            bad_p.write_text(json.dumps(bad))
            ok, errs = verify.gate(h_p, bad_p, snap, registry_path=reg_p)
            self.assertFalse(ok)
            self.assertTrue(any("replication_block" in x for x in errs), errs)

    def test_rules_verdict_injection_caught(self):
        # flipping the pre-registered verdict itself must not survive:
        # the gate re-derives it mechanically
        with tempfile.TemporaryDirectory() as td:
            snap, h_p, e_p, reg_p, e, *_ = self._build(Path(td))
            bad = json.loads(json.dumps(e))
            rules = dict(bad["replication_block"]["rules"])
            rules["verdict"] = ("not_replicated"
                                if rules["verdict"] == "replicated"
                                else "replicated")
            bad["replication_block"]["rules"] = rules
            bad_p = Path(td) / "bad.json"
            bad_p.write_text(json.dumps(bad))
            ok, errs = verify.gate(h_p, bad_p, snap, registry_path=reg_p)
            self.assertFalse(ok)
            self.assertTrue(any("replication_block.rules" in x for x in errs),
                            errs)

    def test_meta_swap_breaks_fingerprint(self):
        # editing a pinned meta file must fail the fingerprint reconciliation
        with tempfile.TemporaryDirectory() as td:
            snap, h_p, e_p, reg_p, *_ = self._build(Path(td))
            p = snap / "meta" / "monthly_caps.csv"
            p.write_text(p.read_text().replace("1000000", "9000000"))
            ok, errs = verify.gate(h_p, e_p, snap, registry_path=reg_p)
            self.assertFalse(ok)
            self.assertTrue(any("tampered" in x for x in errs), errs)


ADMISSION = {
    "required_metrics": ["rankic_mean"],
    "thresholds": {"rankic_mean": {"op": "<", "value": -0.03}},
    "min_observations": 20,
}
