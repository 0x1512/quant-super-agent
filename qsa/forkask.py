"""Fork ask — v1.4: the fork card becomes a real question to a human.

The mechanism (raise_fork / decide / digest, append-only forks.jsonl)
has existed since v1.2; what was missing is the CONVERSATION: the run
pausing to ask, a default policy when nobody answers, and the recorded
convention being REUSED automatically by later runs of the same kind —
the showcase promise "拍板记录在案，下次同类研究自动沿用".

Rules (mechanical, no discretion):

* an already-decided fork is NEVER re-asked — the recorded choice is
  reused and reported as ``reused``;
* an open fork prints the question with numbered options and waits for
  a choice; invalid choices re-prompt, EOF/empty falls to ``default``;
* the decision (choice, by, rationale) is recorded via the existing
  ForkCards ledger — double-decide stays refused, unknown forks are
  refused by the ledger itself.
"""
from __future__ import annotations

import sys
from typing import Any, TextIO


def ask(cards: Any, fork_id: str, *, question: str,
        options: list[dict[str, str]], recommended: str, default: str,
        rationale: str = "", stdin: TextIO | None = None,
        stdout: TextIO | None = None) -> dict[str, Any]:
    """Raise (if new) and decide (or reuse) a fork. Returns a record."""
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    card = cards.raise_fork(fork_id, question, options, recommended,
                            default)
    if "decision" in card:
        d = card["decision"]
        print(f"[fork] {fork_id} 已有拍板「{d['choice']}」— 沿用，"
              f"不再问人", file=stdout)
        return {"fork_id": fork_id, "choice": d["choice"], "reused": True,
                "applied_default": d.get("by") == "default-policy"}

    labels = [o["label"] for o in options]
    print(f"\n[拍板需要你] {fork_id}: {question}", file=stdout)
    for i, opt in enumerate(options, 1):
        mark = " ←默认" if opt["label"] == default else ""
        note = f" — {opt['desc']}" if opt.get("desc") else ""
        print(f"  {i}. {opt['label']}{note}{mark}", file=stdout)
    while True:
        try:
            line = (stdin.readline() or "").strip()
        except EOFError:
            line = ""
        if not line:
            choice, applied_default = default, True
            break
        if line.isdigit() and 1 <= int(line) <= len(options):
            choice, applied_default = labels[int(line) - 1], False
            break
        if line in labels:
            choice, applied_default = line, False
            break
        print(f"  无效选择 {line!r}，请输入 1-{len(options)} 或选项文本",
              file=stdout)
    cards.decide(fork_id, choice,
                 by="human" if not applied_default else "default-policy",
                 rationale=rationale or ("人工拍板" if not applied_default
                                         else "无人应答，按预注册默认执行"))
    print(f"[fork] {fork_id} → 「{choice}」"
          + ("（默认）" if applied_default else "") + "，已记录在案",
          file=stdout)
    return {"fork_id": fork_id, "choice": choice, "reused": False,
            "applied_default": applied_default}
