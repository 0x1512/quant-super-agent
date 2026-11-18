"""Tests for the channel plane (SUPERAGENT_PLAN #8).

Continuity across channels: the SAME follow-up asked over CLI, over an
inbox directory and over a webhook must reuse the SAME previous
leaderboard and produce the SAME verdict — the memory lives in the run
artifacts, not in the channel.
"""
import json
import tempfile
import unittest
from pathlib import Path

from qsa import channels


def prev_dir(tmp: Path) -> Path:
    """A cheap stand-in for a finished run: leaderboard + config."""
    d = tmp / "prev"
    d.mkdir(parents=True, exist_ok=True)
    (d / "leaderboard.json").write_text(json.dumps({
        "library": [
            {"id": "A", "oos_ic": 0.06, "n_months": 14,
             "ic_mean": 0.1, "icir": 1.0},
            {"id": "B", "oos_ic": 0.04, "n_months": 14,
             "ic_mean": 0.1, "icir": 1.0},
            {"id": "D", "oos_ic": 0.09, "n_months": 3,
             "ic_mean": 0.1, "icir": 1.0},
        ],
    }), encoding="utf-8")
    (d / "run_config.json").write_text(json.dumps(
        {"thresh": 0.03, "min_months": 12, "goal": "g",
         "fingerprint": "fp", "elapsed_s": 21.0}), encoding="utf-8")
    return d


class ChannelCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="qsa-chan-"))
        self.addCleanup(self._rm)
        self.prev = prev_dir(self.tmp)

    def _rm(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _snapshot_followup(self) -> dict:
        d = json.loads((self.prev / "followup.json").read_text("utf-8"))
        return {k: v for k, v in d.items() if k != "elapsed_s"}


class TestCLIChannel(ChannelCase):

    def test_rejudge_via_cli(self):
        ch = channels.CLIChannel(self.prev)
        reply = ch.deliver("门槛提到 0.05")
        self.assertEqual(reply["mode"], "rejudge")
        self.assertEqual(reply["channel"], "cli")
        self.assertIn("零重算", reply["summary"])
        self.assertTrue(Path(reply["report"]).exists())

    def test_refuse_is_polite_not_guessed(self):
        ch = channels.CLIChannel(self.prev)
        reply = ch.deliver("换一批数据源吧")
        self.assertEqual(reply["mode"], "refuse")
        self.assertIsNone(reply["report"])


class TestInboxChannel(ChannelCase):

    def _drop(self, mid: str, text: str) -> None:
        (self.tmp / "inbox" / f"{mid}.json").write_text(
            json.dumps({"id": mid, "text": text}, ensure_ascii=False),
            encoding="utf-8")

    def test_poll_answers_each_message_once(self):
        ch = channels.InboxChannel(self.tmp, self.prev)
        self._drop("m1", "门槛提到 0.05")
        replies = ch.poll()
        self.assertEqual(len(replies), 1)
        self.assertEqual(replies[0]["mode"], "rejudge")
        out = json.loads((self.tmp / "outbox" / "m1.json")
                         .read_text("utf-8"))
        self.assertEqual(out["id"], "m1")
        # second poll: already answered, nothing new
        self.assertEqual(ch.poll(), [])

    def test_cross_channel_verdict_is_identical(self):
        cli = channels.CLIChannel(self.prev).deliver("门槛提到 0.05")
        snap_cli = self._snapshot_followup()
        ch = channels.InboxChannel(self.tmp, self.prev)
        self._drop("m2", "门槛提到 0.05")
        inbox = ch.poll()[0]
        snap_inbox = self._snapshot_followup()
        # same mode, same winners, byte-identical verdict payload
        self.assertEqual(inbox["mode"], cli["mode"])
        self.assertEqual(snap_inbox, snap_cli)


class TestWebhookChannel(ChannelCase):

    def test_post_message_round_trip(self):
        ch = channels.WebhookChannel(self.tmp, self.prev, port=0)
        ch.port = ch._srv.server_address[1]      # ephemeral port
        ch.start()
        self.addCleanup(ch.stop)
        reply = ch.deliver("门槛提到 0.05", msg_id="wh-1")
        self.assertEqual(reply["mode"], "rejudge")
        # the message landed in the shared inbox and was answered there
        self.assertTrue((self.tmp / "inbox" / "wh-1.json").exists())
        self.assertTrue((self.tmp / "outbox" / "wh-1.json").exists())

    def test_health_endpoint(self):
        import urllib.request
        ch = channels.WebhookChannel(self.tmp, self.prev, port=0)
        ch.port = ch._srv.server_address[1]
        ch.start()
        self.addCleanup(ch.stop)
        with urllib.request.urlopen(
                f"http://127.0.0.1:{ch.port}/health", timeout=10) as r:
            self.assertEqual(json.loads(r.read()), {"ok": True})


if __name__ == "__main__":
    unittest.main()
