"""Tests for the async task plane (SUPERAGENT_PLAN #1).

A long research run must never hold the human hostage: start returns
immediately (Started), every transition lands on disk, and a killed
process leaves an auditable state — never a mystery. These tests pin
the whole card lifecycle with REAL detached processes:

* settled — payload exits 0, card records exit_code, log captured;
* failed — payload exits 3, card says failed (not a mystery);
* cancelled — SIGTERM reaches the whole group, state cancelled;
* interrupted — pid gone without a terminal field self-heals on
  refresh, and stays that way on disk;
* CLI — start/status/wait work end-to-end over the registry.
"""
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from qsa import tasks as T

ROOT = Path(__file__).resolve().parents[1]


class TaskCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="qsa-tasks-"))
        self.addCleanup(self._cleanup)
        self._old_root = os.environ.get("QSA_TASKS_ROOT")
        os.environ["QSA_TASKS_ROOT"] = str(self.tmp)
        T._root(str(self.tmp))          # create <tmp>/tasks/

    def _cleanup(self):
        if self._old_root is None:
            os.environ.pop("QSA_TASKS_ROOT", None)
        else:
            os.environ["QSA_TASKS_ROOT"] = self._old_root

    def _spawn(self, code: str, root=None) -> dict:
        card = T.start([sys.executable, "-c", code],
                       root=str(root) if root else str(self.tmp))
        self.assertEqual(card["state"], "running")
        self.assertTrue(T._alive(card["pid"]))
        return card


class TestLifecycle(TaskCase):

    def test_settled_records_exit_code_and_log(self):
        card = self._spawn("print('hello task'); import sys; "
                           "sys.stdout.flush()")
        done, timed_out = T.wait(card["id"], timeout=30, root=str(self.tmp))
        self.assertFalse(timed_out)
        self.assertEqual(done["state"], "settled")
        self.assertEqual(done["exit_code"], 0)
        log = (self.tmp / "tasks" / card["id"] / "child.log")
        self.assertIn("hello task", log.read_text("utf-8", "replace"))

    def test_failed_is_not_a_mystery(self):
        card = self._spawn("import sys; sys.exit(3)")
        done, _ = T.wait(card["id"], timeout=30, root=str(self.tmp))
        self.assertEqual(done["state"], "failed")
        self.assertEqual(done["exit_code"], 3)

    def test_cancel_kills_the_group(self):
        card = self._spawn("import time; time.sleep(300)")
        out = T.cancel(card["id"], root=str(self.tmp))
        self.assertEqual(out["state"], "cancelled")
        deadline = time.time() + 10
        while T._alive(card["pid"]) and time.time() < deadline:
            time.sleep(0.05)
        self.assertFalse(T._alive(card["pid"]))
        # the card is terminal: wait returns immediately, cancel is a no-op
        done, timed_out = T.wait(card["id"], timeout=1, root=str(self.tmp))
        self.assertFalse(timed_out)
        self.assertEqual(done["state"], "cancelled")
        again = T.cancel(card["id"], root=str(self.tmp))
        self.assertEqual(again["state"], "cancelled")

    def test_wait_timeout_returns_running_card(self):
        card = self._spawn("import time; time.sleep(300)")
        self.addCleanup(T.cancel, card["id"], str(self.tmp))
        c, timed_out = T.wait(card["id"], timeout=0.4, root=str(self.tmp))
        self.assertTrue(timed_out)
        self.assertEqual(c["state"], "running")
        T.cancel(card["id"], root=str(self.tmp))

    def test_interrupted_self_heals_from_disk(self):
        card = self._spawn("import time; time.sleep(300)")
        # infra death: SIGKILL the whole detached group — the wrapper
        # never gets to write a terminal field
        os.killpg(os.getpgid(card["pid"]), 9)
        deadline = time.time() + 10
        while T._alive(card["pid"]) and time.time() < deadline:
            time.sleep(0.05)
        self.assertFalse(T._alive(card["pid"]))
        fresh = T.read_card(Path(self.tmp), card["id"])
        self.assertEqual(fresh["state"], "running")   # stale on disk
        healed = T.refresh({**fresh, "_root": str(self.tmp)},
                           Path(self.tmp))
        self.assertEqual(healed["state"], "interrupted")
        # persisted — a later status/wait sees the same verdict
        self.assertEqual(T.read_card(Path(self.tmp), card["id"])["state"],
                         "interrupted")

    def test_no_such_task(self):
        with self.assertRaises(SystemExit):
            T.cancel("T-does-not-exist", root=str(self.tmp))
        with self.assertRaises(SystemExit):
            T.wait("T-does-not-exist", timeout=1, root=str(self.tmp))


class TestRegistry(TaskCase):

    def test_list_cards_and_filter(self):
        a = self._spawn("print('a')")
        b = self._spawn("import time; time.sleep(300)")
        self.addCleanup(T.cancel, b["id"], str(self.tmp))
        T.wait(a["id"], timeout=30, root=str(self.tmp))
        ids = {c["id"] for c in T.list_cards(Path(self.tmp))}
        self.assertEqual(ids, {a["id"], b["id"]})
        # torn/corrupt cards are skipped, not fatal
        bad = self.tmp / "tasks" / "T-torn" / "task.json"
        bad.parent.mkdir(parents=True)
        bad.write_text('{"id": "T-tor', encoding="utf-8")
        ids = {c["id"] for c in T.list_cards(Path(self.tmp))}
        self.assertNotIn("T-torn", ids)
        T.cancel(b["id"], root=str(self.tmp))


class TestCLI(TaskCase):

    def _cli(self, *args):
        return subprocess.run(
            [sys.executable, "-m", "qsa.tasks", *args],
            capture_output=True, text=True, timeout=60, cwd=str(ROOT),
            env={**os.environ, "QSA_TASKS_ROOT": str(self.tmp)})

    def test_start_status_wait(self):
        r = self._cli("start", "--", sys.executable, "-c",
                      "print('cli payload')")
        self.assertEqual(r.returncode, 0, r.stderr)
        tid = r.stdout.strip().splitlines()[-1]
        self.assertTrue(tid.startswith("T-"))
        w = self._cli("wait", tid, "--timeout", "30")
        self.assertEqual(w.returncode, 0, w.stderr)
        card = json.loads(w.stdout.strip().splitlines()[0])
        self.assertEqual(card["state"], "settled")
        s = self._cli("status")
        self.assertIn(tid, s.stdout)
        self.assertIn("settled", s.stdout)

    def test_wait_exit_code_is_payload_exit_code(self):
        r = self._cli("start", "--", sys.executable, "-c",
                      "import sys; sys.exit(5)")
        tid = r.stdout.strip().splitlines()[-1]
        w = self._cli("wait", tid, "--timeout", "30")
        self.assertEqual(w.returncode, 5)


if __name__ == "__main__":
    unittest.main()
