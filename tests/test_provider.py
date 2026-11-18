"""Tests for the provider plane (SUPERAGENT_PLAN #10).

Offline by default, gateway by one env var:

* no key, no network: the rule engine answers deterministically — the
  whole product is functional offline (离线铁律);
* QSA_PROVIDER=gateway routes to OUR OpenAI-compatible gateway
  (QSA_GATEWAY_URL) — verified against a local stub server, not a
  mocked-out client;
* an unknown provider name is refused loudly, not silently ignored.
"""
import json
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from qsa import llm, provider


class TestOfflineDefault(unittest.TestCase):

    def test_default_is_offline_rule_engine(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("QSA_PROVIDER", None)
            eng = provider.get_llm()
            self.assertIsInstance(eng, provider.RuleLLM)

    def test_rule_engine_is_deterministic_and_auditable(self):
        with tempfile.TemporaryDirectory() as td:
            log = Path(td) / "llm.jsonl"
            eng = provider.get_llm(run_log=log)
            a = eng.complete("sys", "把门槛从 0.03 提到 0.05")
            b = eng.complete("sys", "把门槛从 0.03 提到 0.05")
            self.assertEqual(a, b)                  # deterministic
            self.assertIn("0.03", a) and self.assertIn("0.05", a)
            self.assertIn("offline-deterministic", a)
            # every call is in the run log — auditable, not trusted
            rows = [json.loads(x) for x in
                    log.read_text("utf-8").splitlines() if x.strip()]
            self.assertEqual(len(rows), 2)

    def test_rule_engine_never_touches_the_network(self):
        # a gateway env var that would be used if selection leaked
        with mock.patch.dict(os.environ, {"QSA_GATEWAY_URL":
                                          "http://127.0.0.1:1/v1"}):
            eng = provider.get_llm()
            self.assertEqual(eng.name, "rule-offline")
            self.assertIn("digest", eng.complete("s", "u"))


class TestGatewayMode(unittest.TestCase):

    def test_gateway_routes_to_our_openai_compatible_endpoint(self):
        stub_text = "gateway says: proceed"

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                n = int(self.headers.get("Content-Length", 0))
                req = json.loads(self.rfile.read(n))
                seen["request"] = req
                body = json.dumps({
                    "choices": [{"message": {"content": stub_text}}],
                }).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        seen: dict = {}
        srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.shutdown)
        self.addCleanup(srv.server_close)
        port = srv.server_address[1]
        env = {"QSA_PROVIDER": "gateway",
               "QSA_GATEWAY_URL": f"http://127.0.0.1:{port}/v1",
               "QSA_GATEWAY_MODEL": "test-model"}
        with mock.patch.dict(os.environ, env):
            eng = provider.get_llm()
            self.assertIsInstance(eng, llm.OpenAICompatLLM)
            out = eng.complete("system prompt", "user question")
        self.assertEqual(out, stub_text)
        # the request really was OpenAI-shaped to OUR gateway
        self.assertEqual(seen["request"]["model"], "test-model")
        self.assertEqual([m["role"] for m in seen["request"]["messages"]],
                         ["system", "user"])

    def test_gateway_default_url_is_our_gateway(self):
        env = {"QSA_PROVIDER": "gateway"}
        with mock.patch.dict(os.environ, env, clear=False):
            os.environ.pop("QSA_GATEWAY_URL", None)
            eng = provider.get_llm()
        self.assertEqual(eng.base_url, "http://127.0.0.1:8787/v1")

    def test_unknown_provider_refused(self):
        with mock.patch.dict(os.environ, {"QSA_PROVIDER": "pigeon"}):
            with self.assertRaises(llm.LLMError):
                provider.get_llm()


class TestJudge(unittest.TestCase):
    """judge(): the wiring point between rules and (optional) model."""

    def test_offline_defers_to_the_rule_verdict(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("QSA_PROVIDER", None)
            a = provider.judge("面板 2 小时未更新，算问题吗？")
            b = provider.judge("面板 2 小时未更新，算问题吗？")
        self.assertEqual(a, {"answer": "yes", "by": "rule-offline",
                             "reason": "offline default: the rule verdict "
                                       "stands"})
        self.assertEqual(a, b)                    # deterministic

    def test_gateway_answer_is_parsed_and_attributed(self):
        body = ('{"answer": "no", '
                '"reason": "盘后静态数据盘中不更新属正常"}')
        srv = _stub_server(body)
        env = {"QSA_PROVIDER": "gateway",
               "QSA_GATEWAY_URL": f"http://127.0.0.1:{srv['port']}/v1",
               "QSA_GATEWAY_MODEL": "stub-model"}
        with mock.patch.dict(os.environ, env):
            v = provider.judge("面板 2 小时未更新（盘后数据，现在盘中）。"
                               "值得起草修复单吗？")
        self.assertEqual(v["answer"], "no")
        self.assertEqual(v["by"], "gateway:stub-model")
        self.assertIn("盘后", v["reason"])
        srv["shutdown"]()

    def test_gateway_garbage_falls_back_to_rules(self):
        srv = _stub_server("I have no idea what you want")
        env = {"QSA_PROVIDER": "gateway",
               "QSA_GATEWAY_URL": f"http://127.0.0.1:{srv['port']}/v1"}
        with mock.patch.dict(os.environ, env):
            v = provider.judge("worth an order?")
        self.assertEqual(v["answer"], "yes")
        self.assertEqual(v["by"], "fallback")
        self.assertIn("rule verdict stands", v["reason"])
        srv["shutdown"]()

    def test_dead_endpoint_falls_back_to_rules(self):
        env = {"QSA_PROVIDER": "gateway",
               "QSA_GATEWAY_URL": "http://127.0.0.1:9/v1"}   # nothing there
        with mock.patch.dict(os.environ, env):
            v = provider.judge("worth an order?")
        self.assertEqual(v["answer"], "yes")
        self.assertEqual(v["by"], "fallback")

    def test_live_gateway_round_trip(self):
        """Set QSA_GATEWAY_URL (and QSA_PROVIDER=gateway) to run this
        against a real endpoint; skipped otherwise."""
        url = os.environ.get("QSA_GATEWAY_URL")
        if not url:
            self.skipTest("set QSA_GATEWAY_URL for the live round-trip")
        env = {"QSA_PROVIDER": "gateway", "QSA_GATEWAY_URL": url}
        if "QSA_GATEWAY_MODEL" not in os.environ:
            env["QSA_GATEWAY_MODEL"] = "default"
        with mock.patch.dict(os.environ, env):
            v = provider.judge("盘中时段，一个本应实时更新的行情面板"
                               "已经 2 小时没有新数据。值得起草修复单吗？")
        self.assertIn(v["answer"], ("yes", "no"))
        self.assertTrue(v["by"].startswith("gateway:"),
                        f"expected gateway attribution, got {v!r}")
        self.assertTrue(v["reason"])


def _stub_server(content: str) -> dict:
    """A one-shot OpenAI-compatible stub; returns {"port", "shutdown"}."""
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0))
            self.rfile.read(n)
            body = json.dumps({
                "choices": [{"message": {"content": content}}],
            }).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return {"port": srv.server_address[1],
            "shutdown": lambda: (srv.shutdown(), srv.server_close())}


if __name__ == "__main__":
    unittest.main()
