"""Tests for the v1.4 dispatch extensions: ROLE_NAMES, auto_workers,
manifest. The N-choice must be a pure function of (jobs, cpu) — pinned
formula clamp(ceil(jobs/8), 1, cpu, 16) — and the manifest must name
crew roles, not anonymous hands.
"""
import json
import tempfile
import unittest
from pathlib import Path

from qsa import dispatch


class TestAutoWorkers(unittest.TestCase):
    def test_formula(self):
        self.assertEqual(dispatch.auto_workers(0), 1)
        self.assertEqual(dispatch.auto_workers(1), 1)
        self.assertEqual(dispatch.auto_workers(8), 1)
        self.assertEqual(dispatch.auto_workers(9), 2)
        self.assertEqual(dispatch.auto_workers(78, cpu=64), 10)
        self.assertEqual(dispatch.auto_workers(102, cpu=64), 13)

    def test_clamped_by_cpu_and_cap(self):
        self.assertEqual(dispatch.auto_workers(1000, cpu=8), 8)
        self.assertEqual(dispatch.auto_workers(1000, cpu=64), 16)
        self.assertEqual(dispatch.auto_workers(4, cpu=2), 1)

    def test_default_workers_unchanged(self):
        self.assertEqual(dispatch.default_workers(7), 7)
        self.assertEqual(dispatch.default_workers(None), 4)


class TestRoleNames(unittest.TestCase):
    def test_every_kind_maps_to_a_crew_role(self):
        for kind in ("zoo", "lib", "ix", "mut"):
            self.assertIn(dispatch.ROLE_NAMES[kind],
                          ("GateKeeper", "RepoSmith", "FlowMapper",
                           "SmokeRunner"))
        self.assertNotIn("手", "".join(dispatch.ROLE_NAMES.values()))


class TestManifest(unittest.TestCase):
    def test_manifest_names_roles_and_writes(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "manifest.json"
            m = dispatch.manifest("offense-full", 13,
                                  {"zoo": 24, "lib": 30, "ix": 18,
                                   "mut": 30, "forge": 6},
                                  50.72, out_path=p)
            self.assertTrue(p.exists())
            on_disk = json.loads(p.read_text("utf-8"))
            self.assertEqual(on_disk, m)
            self.assertEqual(m["jobs_by_role"]["GateKeeper"], 24)
            self.assertEqual(m["jobs_by_role"]["RepoSmith"], 30)
            self.assertEqual(m["jobs_by_role"]["EnvSmith"], 6)  # forge
            self.assertEqual(m["workers"], 13)
            self.assertEqual(m["elapsed_s"], 50.7)

    def test_manifest_without_path_returns_only(self):
        m = dispatch.manifest("x", 4, {"zoo": 10}, 1.0)
        self.assertEqual(m["jobs_by_role"], {"GateKeeper": 10})


if __name__ == "__main__":
    unittest.main()
