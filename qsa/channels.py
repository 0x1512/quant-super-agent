"""Channels — SUPERAGENT_PLAN #8 (continuity across channels).

The same conversation continues whether the human is at the terminal,
dropping files into an inbox directory, or POSTing a webhook: every
channel funnels into the same handler, which CHAINS the previous run's
leaderboard (memory lives on the blackboard + run artifacts, not in
the channel). A follow-up asked over CLI and over inbox therefore
reuses the SAME leaderboard and produces the SAME verdict — asserted
in tests.

Adapters:

* CLIChannel     — direct call, response returned as text;
* InboxChannel   — poll <root>/inbox/*.json, reply to <root>/outbox/;
* WebhookChannel — stdlib http server; POST /message appends to the
  inbox dir (so webhook degrades to the inbox path), GET /health.

Message JSON: {"id": "...", "text": "把门槛收紧到 0.05"}.
Reply JSON: {"id", "mode", "summary", "report", "channel"}.
"""
from __future__ import annotations

import json
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import followup


def handle(text: str, prev_dir: Path, channel: str = "cli") -> dict:
    """One message in, one verdict out — chained to the last run."""
    res = followup.run(Path(prev_dir), text)
    if res["mode"] == "refuse":
        return {"mode": "refuse", "summary": res["reason"],
                "report": None, "channel": channel}
    n = len(res.get("winners", res.get("kept", [])))
    return {"mode": res["mode"],
            "summary": (f"{res['mode']}: {n} 个候选留在新门槛下"
                        f"（零重算，链式复用上次 leaderboard）"),
            "report": res.get("report"), "channel": channel}


class CLIChannel:
    """The human is here, right now."""

    name = "cli"

    def __init__(self, prev_dir: Path):
        self.prev_dir = Path(prev_dir)

    def deliver(self, text: str) -> dict:
        return handle(text, self.prev_dir, channel=self.name)


class InboxChannel:
    """The human drops JSON files; replies land next to them."""

    name = "inbox"

    def __init__(self, root: Path, prev_dir: Path):
        self.root = Path(root)
        self.prev_dir = Path(prev_dir)
        (self.root / "inbox").mkdir(parents=True, exist_ok=True)
        (self.root / "outbox").mkdir(parents=True, exist_ok=True)

    def poll(self) -> list[dict]:
        """Process every pending message once; returns the replies."""
        replies = []
        for p in sorted((self.root / "inbox").glob("*.json")):
            if (self.root / "outbox" / p.name).exists():
                continue                        # already answered
            try:
                msg = json.loads(p.read_text("utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            reply = handle(msg.get("text", ""), self.prev_dir,
                           channel=self.name)
            reply["id"] = msg.get("id", p.stem)
            out = self.root / "outbox" / p.name
            out.write_text(json.dumps(reply, ensure_ascii=False,
                                      indent=1), encoding="utf-8")
            replies.append(reply)
        return replies


class WebhookChannel:
    """POST /message {"text": "..."} -> inbox file -> poll for reply.

    Deliberately thin: the webhook never runs research inline. It
    appends to the inbox and the same poll loop answers every channel.
    """

    name = "webhook"

    def __init__(self, root: Path, prev_dir: Path, host: str = "127.0.0.1",
                 port: int = 8788):
        self.root = Path(root)
        self.prev_dir = Path(prev_dir)
        self.inbox = InboxChannel(root, prev_dir)
        self.port = port
        chan = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):          # silence per-request noise
                pass

            def do_GET(self):
                if self.path == "/health":
                    body = b'{"ok": true}'
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                else:
                    self.send_response(404)
                    self.end_headers()

            def do_POST(self):
                if self.path != "/message":
                    self.send_response(404)
                    self.end_headers()
                    return
                n = int(self.headers.get("Content-Length", 0))
                try:
                    msg = json.loads(self.rfile.read(n) or b"{}")
                except json.JSONDecodeError:
                    self.send_response(400)
                    self.end_headers()
                    return
                mid = msg.get("id") or f"wh-{time.strftime('%H%M%S')}"
                (chan.inbox.root / "inbox" / f"{mid}.json").write_text(
                    json.dumps({"id": mid, "text": msg.get("text", "")},
                               ensure_ascii=False), encoding="utf-8")
                # answer synchronously through the SAME poll path
                replies = chan.inbox.poll()
                reply = next((r for r in replies if r["id"] == mid),
                             {"id": mid, "mode": "queued"})
                body = json.dumps(reply, ensure_ascii=False).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self._srv = ThreadingHTTPServer((host, port), Handler)
        self._thread: threading.Thread | None = None

    def start(self) -> "WebhookChannel":
        self._thread = threading.Thread(target=self._srv.serve_forever,
                                        daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        self._srv.shutdown()
        self._srv.server_close()

    def deliver(self, text: str, msg_id: str | None = None) -> dict:
        msg_id = msg_id or f"wh-{time.strftime('%H%M%S')}"
        payload = json.dumps({"id": msg_id, "text": text}).encode()
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/message", data=payload,
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
