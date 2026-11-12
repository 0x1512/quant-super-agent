"""LLM adapters for the mining loop — provider-agnostic, offline-testable.

Two implementations, zero third-party dependencies:

* :class:`ScriptedLLM` replays a fixed queue of responses — the mining loop
  is fully deterministic and testable in CI with no network, no API key and
  no cost. Every acceptance test runs through this.
* :class:`OpenAICompatLLM` speaks the OpenAI-compatible ``/chat/completions``
  protocol via the standard library, so DeepSeek, OpenAI, vLLM, Ollama and
  friends all plug in with two environment variables:
  ``QSA_LLM_BASE_URL`` and ``QSA_LLM_API_KEY`` (plus ``QSA_LLM_MODEL``).

Every call is appended to a run log (JSONL: prompt, response, model, sha) —
the run-level counterpart of evidence cards, so an agent run can be
audited, not just trusted.
"""
from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path
from typing import Any

from .snapshot import canonical_json, sha256_bytes


class LLMError(RuntimeError):
    pass


class BaseLLM:
    name = "base"

    def __init__(self, run_log: Path | None = None) -> None:
        self.run_log = Path(run_log) if run_log else None
        self._seq = 0

    def complete(self, system: str, user: str) -> str:
        response = self._complete(system, user)
        self._log(system, user, response)
        return response

    def _complete(self, system: str, user: str) -> str:  # pragma: no cover
        raise NotImplementedError

    def _log(self, system: str, user: str, response: str) -> None:
        if not self.run_log:
            return
        self._seq += 1
        entry = {"seq": self._seq, "model": self.name,
                 "prompt_sha256": sha256_bytes((system + "\x00" + user).encode()),
                 "response_sha256": sha256_bytes(response.encode()),
                 "system": system, "user": user, "response": response}
        with self.run_log.open("a", encoding="utf-8") as fh:
            fh.write(canonical_json(entry).decode("utf-8") + "\n")


class ScriptedLLM(BaseLLM):
    """Deterministic response queue — the mining loop's test double."""

    name = "scripted"

    def __init__(self, responses: list[str], run_log: Path | None = None) -> None:
        super().__init__(run_log)
        self._responses = list(responses)

    def _complete(self, system: str, user: str) -> str:
        if not self._responses:
            raise LLMError("ScriptedLLM queue exhausted")
        return self._responses.pop(0)


class OpenAICompatLLM(BaseLLM):
    """Minimal OpenAI-compatible chat client over the standard library."""

    def __init__(self, model: str | None = None, base_url: str | None = None,
                 api_key: str | None = None, temperature: float = 0.0,
                 timeout: int = 120, run_log: Path | None = None) -> None:
        super().__init__(run_log)
        self.model = model or os.environ.get("QSA_LLM_MODEL", "")
        self.base_url = (base_url or os.environ.get("QSA_LLM_BASE_URL", "")
                         ).rstrip("/")
        self.api_key = api_key or os.environ.get("QSA_LLM_API_KEY", "")
        self.temperature = temperature
        self.timeout = timeout
        self.name = f"openai-compat:{self.model or 'unset'}"
        if not self.base_url:
            raise LLMError("set QSA_LLM_BASE_URL (or pass base_url) to use "
                           "OpenAICompatLLM")

    def _complete(self, system: str, user: str) -> str:
        payload = {"model": self.model, "temperature": self.temperature,
                   "messages": [{"role": "system", "content": system},
                                {"role": "user", "content": user}]}
        req = urllib.request.Request(
            self.base_url + "/chat/completions",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {self.api_key}"})
        last_error = ""
        for attempt in range(2):
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    body = json.loads(resp.read())
                content = body["choices"][0]["message"]["content"]
                if not content:
                    raise LLMError("empty completion")
                return content
            except LLMError:
                raise
            except Exception as exc:  # noqa: BLE001
                last_error = f"{type(exc).__name__}: {exc}"
        raise LLMError(f"OpenAICompatLLM failed twice ({last_error})")


def extract_json(text: str) -> dict[str, Any]:
    """Pull the first balanced JSON object out of an LLM response."""
    start = text.find("{")
    if start < 0:
        raise LLMError(f"no JSON object in response: {text[:120]!r}")
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    obj = json.loads(text[start:i + 1])
                except json.JSONDecodeError as exc:
                    raise LLMError(f"malformed JSON in response: {exc}") from exc
                if isinstance(obj, dict):
                    return obj
                raise LLMError("JSON payload is not an object")
    raise LLMError("unbalanced JSON in response")
