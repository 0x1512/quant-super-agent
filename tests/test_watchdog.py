"""Tests for the watchdog plane (SUPERAGENT_PLAN #7).

The watchdog is an external control loop, deliberately NOT part of the
agent: rules only, mechanical downgrades, every verdict attributed in
an append-only incident log. These tests pin the three rules with real
detached tasks:

* infra_died — pid gone without a terminal field -> attributed incident
  + the card self-heals to interrupted;
* budget_exhausted — runtime beyond --max-runtime -> SIGTERM the group,
  card cancelled, incident written;
* no_progress — footprint (log bytes + files) unchanged for N
  consecutive ticks -> cancelled with an attribution;
* progress resets the stall counter — a chatty task is never killed.
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
from qsa import watchdog as W

ROOT = Path(__file__).resolve().parents[1]

SLEEPER = "import time; time.sleep(300)"
CHATTY = ("import time, sys\n"
          "for _ in range(20):\n"
          "    print('tick', _, flush=True)\n"
          "    time.sleep(0.2)\n")


class WatchdogCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="qsa-wd-"))
        self.addCleanup(self._cleanup)
        self._old_root = os.environ.get("QSA_TASKS_ROOT")
        os.environ["QSA_TASKS_ROOT"] = str(self.tmp)

    def _cleanup(self):
        for c in T.list_cards(self.tmp):
            if c.get("state") == "running":
                T.cancel(c["id"], root=str(self.tmp))
        if self._old_root is None:
            os.environ.pop("QSA_TASKS_ROOT", None)
        else:
            os.environ["QSA_TASKS_ROOT"] = self._old_root
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _spawn(self, code: str = SLEEPER) -> dict:
        card = T.start([sys.executable, "-c", code], root=str(self.tmp))
        self.assertEqual(card["state"], "running")
        return card

    def _incidents(self) -> list[dict]:
        p = self.tmp / "watchdog" / "incidents.jsonl"
        if not p.exists():
            return []
        return [json.loads(x) for x in
                p.read_text("utf-8").splitlines() if x.strip()]

    def _card(self, tid: str) -> dict:
        return T.read_card(self.tmp, tid)


class TestRules(WatchdogCase):

    def test_infra_died_is_attributed_not_mysterious(self):
        card = self._spawn()
        os.kill(card["pid"], 9)                    # infra dies, no notice
        deadline = time.time() + 10
        while T._alive(card["pid"]) and time.time() < deadline:
            time.sleep(0.05)
        W.tick(self.tmp, {}, max_runtime=0, no_progress_ticks=0)
        self.assertEqual(self._card(card["id"])["state"], "interrupted")
        inc = self._incidents()
        self.assertEqual(len(inc), 1)
        self.assertEqual(inc[0]["attribution"], "infra_died")
        self.assertEqual(inc[0]["task"], card["id"])

    def test_budget_exhausted_cancels_the_group(self):
        card = self._spawn()
        # age the card beyond the budget without waiting
        c = self._card(card["id"])
        c["started_at"] = time.time() - 3600
        (self.tmp / "tasks" / card["id"] / "task.json").write_text(
            json.dumps(c), encoding="utf-8")
        W.tick(self.tmp, {}, max_runtime=60, no_progress_ticks=0)
        self.assertEqual(self._card(card["id"])["state"], "cancelled")
        deadline = time.time() + 10
        while T._alive(card["pid"]) and time.time() < deadline:
            time.sleep(0.05)
        self.assertFalse(T._alive(card["pid"]))
        self.assertEqual(self._incidents()[0]["attribution"],
                         "budget_exhausted")

    def test_no_progress_after_n_stalled_ticks(self):
        card = self._spawn()                       # silent: nothing lands
        state = {}
        for _ in range(3):
            state = W.tick(self.tmp, state, max_runtime=0,
                           no_progress_ticks=3)
            time.sleep(0.05)
        self.assertEqual(self._card(card["id"])["state"], "cancelled")
        self.assertEqual(self._incidents()[-1]["attribution"],
                         "no_progress")
        self.assertIn("3 ticks", self._incidents()[-1]["detail"])

    def test_progress_resets_the_stall_counter(self):
        card = self._spawn(CHATTY)                 # log grows every 0.2s
        state = {}
        for _ in range(6):
            state = W.tick(self.tmp, state, max_runtime=0,
                           no_progress_ticks=3)
            time.sleep(0.25)
        self.assertEqual(self._card(card["id"])["state"], "running")
        self.assertEqual(self._incidents(), [])
        T.cancel(card["id"], root=str(self.tmp))

    def test_terminal_tasks_are_ignored(self):
        card = self._spawn("print('quick')")
        T.wait(card["id"], timeout=30, root=str(self.tmp))
        W.tick(self.tmp, {}, max_runtime=0.001, no_progress_ticks=1)
        # settled stays settled, no incident, no state churn
        self.assertEqual(self._card(card["id"])["state"], "settled")
        self.assertEqual(self._incidents(), [])


class TestFootprint(WatchdogCase):

    def test_footprint_tracks_log_growth_and_files(self):
        card = self._spawn(CHATTY)
        fp0 = W._footprint(self.tmp, card)
        time.sleep(0.5)
        fp1 = W._footprint(self.tmp, card)
        self.assertGreater(fp1[0], fp0[0])         # log bytes grew
        self.assertEqual(fp1[1], fp0[1])           # file count stable
        T.cancel(card["id"], root=str(self.tmp))

    def test_state_is_returned_for_persistence(self):
        card = self._spawn()
        state = W.tick(self.tmp, {}, max_runtime=0, no_progress_ticks=0)
        self.assertIn(card["id"], state)
        self.assertEqual(state[card["id"]]["stalls"], 1)
        T.cancel(card["id"], root=str(self.tmp))


class TestCLI(WatchdogCase):

    def test_once_runs_a_tick_and_persists_state(self):
        card = self._spawn()
        r = subprocess.run(
            [sys.executable, "-m", "qsa.watchdog", "--root", str(self.tmp),
             "--once", "--no-progress-ticks", "5"],
            capture_output=True, text=True, timeout=60, cwd=str(ROOT))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("tick done", r.stdout)
        self.assertTrue((self.tmp / "watchdog" / "state.json").exists())
        T.cancel(card["id"], root=str(self.tmp))


if __name__ == "__main__":
    unittest.main()
