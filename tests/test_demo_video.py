"""Tests for the demo video builder (v1.2).

The builder's contract: given a REAL run's artifacts, emit a
self-contained HTML whose scenes contain only data-derived content.
These tests build a minimal but honest artifact set (the same shapes
run_orders.py writes) and pin the structural guarantees:
* all scene ids present, template placeholders fully replaced
* verdict numbers in the HTML match the artifacts (settled +0.05,
  refusal -0.05 — parsed back out of the scene HTML)
* the roadmap scene stays explicitly labeled 未实现
* a smoke-run build (different refusal count) yields a caption with
  that run's own numbers, never a hardcoded 17/24
"""
import importlib.util
import json
import re
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "build_demo_video", ROOT / "examples" / "build_demo_video.py")
bdv = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bdv)


def write_artifacts(work: Path, refuse_n: int = 1) -> None:
    work.mkdir(parents=True, exist_ok=True)
    gate = {"ok": True, "checked_at": 0, "checks": [
        {"name": "main fixture", "ok": True, "detail": "x rows"},
        {"name": "tail fixture", "ok": True, "detail": "y rows"},
        {"name": "cap-proxy meta", "ok": True, "detail": "z rows"},
        {"name": "universe", "ok": True, "detail": "300 tickers"},
        {"name": "blackboard clear", "ok": True, "detail": "clear"}]}
    (work / "gate.json").write_text(json.dumps(gate), encoding="utf-8")
    (work / "blackboard.jsonl").write_text(
        json.dumps({"kind": "data_pitfall", "title": "t", "body": "b",
                    "status": "info", "tags": [], "posted_at": 0,
                    "chain": "x"}) + "\n", encoding="utf-8")
    (work / "forks.jsonl").write_text(
        json.dumps({"type": "fork", "fork_id": "F-1", "question": "q",
                    "options": [{"label": "a", "impact": "i"}],
                    "recommended": "a", "default": "a", "raised_at": 0})
        + "\n" +
        json.dumps({"type": "decision", "fork_id": "F-1", "choice": "a",
                    "by": "principal", "rationale": "r", "decided_at": 0})
        + "\n", encoding="utf-8")
    evs = [
        {"type": "create", "ts": 1, "order_id": "O1",
         "hypothesis": "good factor", "note": "",
         "params": {"factor": "good_factor", "universe": "top300"}},
        {"type": "transition", "ts": 2, "order_id": "O1",
         "from": "drafted", "to": "admitted",
         "params": {"factor": "good_factor", "universe": "top300"}},
        {"type": "transition", "ts": 3, "order_id": "O1",
         "from": "admitted", "to": "running"},
        {"type": "transition", "ts": 4, "order_id": "O1",
         "from": "running", "to": "settled",
         "results": {"oos_ic": 0.05, "ic_mean": 0.06, "icir": 1.2,
                     "train_ic": 0.07, "n_months": 24}},
    ]
    for k in range(refuse_n):
        oid = f"O2{k}"
        evs += [
            {"type": "create", "ts": 5 + k, "order_id": oid,
             "hypothesis": f"dead factor {k}", "note": "",
             "params": {"factor": f"dead_{k}", "universe": "top300"}},
            {"type": "transition", "ts": 6 + k, "order_id": oid,
             "from": "drafted", "to": "admitted",
             "params": {"factor": f"dead_{k}", "universe": "top300"}},
            {"type": "transition", "ts": 7 + k, "order_id": oid,
             "from": "admitted", "to": "running"},
            {"type": "transition", "ts": 8 + k, "order_id": oid,
             "from": "running", "to": "refused",
             "reason": f"oos IC {-0.05 - k / 100:.6f} <= 0.03 — "
                       f"signal dead out-of-sample"},
        ]
    # drift demo order
    evs += [
        {"type": "create", "ts": 90, "order_id": "OD",
         "hypothesis": "drift demo: admitted top300, started csi500",
         "note": "d", "params": {"factor": "drift_demo",
                                 "universe": "top300"}},
        {"type": "transition", "ts": 91, "order_id": "OD",
         "from": "drafted", "to": "admitted",
         "params": {"factor": "drift_demo", "universe": "top300"}},
        {"type": "transition", "ts": 92, "order_id": "OD",
         "from": "admitted", "to": "refused",
         "reason": "param drift caught at start: ..."},
    ]
    (work / "orders.jsonl").write_text(
        "\n".join(json.dumps(e, ensure_ascii=False) for e in evs) + "\n",
        encoding="utf-8")


class TestDemoVideo(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory(prefix="demo_")
        self.work = Path(self.d.name) / "orders"

    def tearDown(self):
        self.d.cleanup()

    def _build(self, refuse_n: int = 1) -> list[dict]:
        write_artifacts(self.work, refuse_n)
        art = bdv.load_artifacts(self.work)
        scenes = bdv.build_scenes(art, None, {"n_orders": len(art["orders"]),
                                              "n_board": len(art["board"]),
                                              "n_forks": len(art["forks"]),
                                              "n_tests": 1})
        return scenes

    def test_scenes_complete_and_no_placeholder(self):
        scenes = self._build()
        ids = [s["id"] for s in scenes]
        self.assertEqual(ids, ["title", "gate", "board", "forks",
                               "machine", "verdicts", "drift", "recall",
                               "roadmap", "end"])
        for s in scenes:
            self.assertNotIn("__CSS__", s["html"])
            self.assertNotIn("__SCENES__", s["html"])
            self.assertTrue(s["html"].strip())

    def test_verdict_numbers_from_artifacts(self):
        scenes = self._build(refuse_n=1)
        v = next(s for s in scenes if s["id"] == "verdicts")
        nums = re.findall(r">([+-]\d+\.\d{3})<", v["html"])
        self.assertIn("+0.050", nums)     # settled oos_ic 0.05
        self.assertIn("-0.050", nums)     # refusal -0.05
        # caption carries this run's own dead count (1 of 2 factors)
        self.assertIn("1/2", v["cap"])
        self.assertNotIn("17/24", v["cap"])

    def test_caption_tracks_artifact_not_hardcode(self):
        scenes = self._build(refuse_n=3)
        v = next(s for s in scenes if s["id"] == "verdicts")
        self.assertIn("3/4", v["cap"])
        self.assertNotIn("17/24", v["cap"])

    def test_roadmap_explicitly_unimplemented(self):
        scenes = self._build()
        r = next(s for s in scenes if s["id"] == "roadmap")
        self.assertIn("规划中 · 未实现", r["html"])
        self.assertIn("一行代码未写", r["html"])

    def test_drift_scene_uses_real_order(self):
        scenes = self._build()
        dr = next(s for s in scenes if s["id"] == "drift")
        self.assertIn("PRE-REGISTRATION VIOLATED", dr["html"])
        self.assertIn("csi500", dr["html"])

    def test_gate_scene_reflects_checks(self):
        scenes = self._build()
        g = next(s for s in scenes if s["id"] == "gate")
        self.assertEqual(g["html"].count("[PASS]"), 5)

    def test_full_html_build(self):
        import subprocess
        import sys
        write_artifacts(self.work)
        out = Path(self.d.name) / "demo.html"
        r = subprocess.run(
            [sys.executable, str(ROOT / "examples" / "build_demo_video.py"),
             "--work", str(self.work), "--out", str(out)],
            capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        doc = out.read_text(encoding="utf-8")
        self.assertIn("const SCENES", doc)
        self.assertNotIn("__CSS__", doc)
        self.assertNotIn("NaN", doc.split("const SCENES")[1])


if __name__ == "__main__":
    unittest.main()
