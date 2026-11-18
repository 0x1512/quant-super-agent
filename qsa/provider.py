"""Provider — SUPERAGENT_PLAN #10 (pluggable judgement, zero keys by default).

Selection layer over the LLM adapters: the DEFAULT is the offline
rule engine (deterministic, no network, no key — the whole product is
fully functional without any external dependency, per the 离线铁律).
Setting ``QSA_PROVIDER=gateway`` routes judgement to the gateway YOU
supply: any OpenAI-compatible chat endpoint (a local vLLM or Ollama,
a hosted DeepSeek-style API, anything speaking ``/chat/completions``)
behind ``QSA_GATEWAY_URL`` — one env var, no vendor lock, and the
endpoint never receives anything you don't explicitly point it at.

The offline rule engine is not a stub: it produces deterministic,
auditable completions (a digest + the numbers it can mechanically
extract), which is exactly what the rules-first planes (watchdog,
watch, patrol) consume. :func:`judge` is the wiring point used by
those planes — offline it always defers to the rule verdict, so
flipping the env var can only ever change behaviour through a
recorded, attributable model answer.

    QSA_PROVIDER=gateway QSA_GATEWAY_URL=http://your-endpoint/v1 \
        python -m qsa.provider "question"
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from . import llm


class RuleLLM(llm.BaseLLM):
    """The offline default: deterministic, auditable, no network."""

    name = "rule-offline"

    def _complete(self, system: str, user: str) -> str:
        numbers = re.findall(r"-?\d+(?:\.\d+)?", user)
        digest = llm.sha256_bytes((system + "\n" + user).encode())[:16]
        return (f"[rule-engine digest={digest}] "
                f"numbers={numbers or 'none'} "
                f"policy=offline-deterministic")


def judge(question: str, context: str = "",
          run_log: "Path | None" = None) -> dict:
    """A yes/no judgement with an auditable trail — the wiring point
    between the rule planes and (optionally) a model.

    * offline (default): the RULE VERDICT STANDS — ``answer=yes`` with
      ``by=rule-offline``. No network, no key, byte-identical to the
      pre-provider behavior; every CI test runs through this path.
    * gateway: asks the configured OpenAI-compatible endpoint (the
      USER-SUPPLIED one — any vLLM/Ollama/DeepSeek-style server behind
      ``QSA_GATEWAY_URL``) and returns its answer + reason for the
      caller to record next to its own rule verdict.
    * any gateway failure falls back to the rule verdict, tagged
      ``by=fallback`` — a dead endpoint can never silently change
      behavior, only fail to improve it.

    Returns ``{"answer": "yes"|"no", "by": str, "reason": str}``.
    """
    engine = get_llm(run_log=run_log)
    if isinstance(engine, RuleLLM):
        return {"answer": "yes", "by": "rule-offline",
                "reason": "offline default: the rule verdict stands"}
    try:
        raw = engine.complete(
            "You are the judgement plane of a quant research agent. "
            "Answer strictly with one JSON object of the form "
            '{"answer": "yes"|"no", "reason": "<one line>"}.',
            f"Context:\n{context}\n\nQuestion: {question}")
        obj = llm.extract_json(raw)
        ans = str(obj.get("answer", "")).strip().lower()
        if ans not in ("yes", "no"):
            raise llm.LLMError(f"unparseable answer {ans!r}")
        return {"answer": ans, "by": f"gateway:{engine.model}",
                "reason": str(obj.get("reason", ""))[:200]}
    except Exception as exc:                      # noqa: BLE001
        return {"answer": "yes", "by": "fallback",
                "reason": f"gateway unavailable ({type(exc).__name__}: "
                          f"{exc}); rule verdict stands"}


def get_llm(run_log: Path | None = None) -> llm.BaseLLM:
    """The one selection point. Offline unless explicitly opted in."""
    mode = os.environ.get("QSA_PROVIDER", "offline").strip().lower()
    if mode == "gateway":
        return llm.OpenAICompatLLM(
            base_url=os.environ.get("QSA_GATEWAY_URL",
                                    "http://127.0.0.1:8787/v1"),
            api_key=os.environ.get("QSA_GATEWAY_API_KEY", "local"),
            model=os.environ.get("QSA_GATEWAY_MODEL", "default"),
            run_log=run_log)
    if mode != "offline":
        raise llm.LLMError(f"unknown QSA_PROVIDER {mode!r} "
                           f"(use 'offline' or 'gateway')")
    return RuleLLM(run_log=run_log)


def main(argv: list[str] | None = None) -> int:            # pragma: no cover
    args = sys.argv[1:] if argv is None else argv
    if not args:
        print("usage: python -m qsa.provider \"question\"")
        return 2
    engine = get_llm()
    print(f"[provider] {engine.name}")
    print(engine.complete("You are the quant super agent's rule engine.",
                          " ".join(args)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
