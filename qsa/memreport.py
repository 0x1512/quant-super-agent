"""Memory report — v1.4 ⑧: the "越用越聪明" claim gets evidence.

The blackboard (hash-chained, real incidents since v1.2) is the memory;
this module turns it into a MEASURABLE statement:

* ``ratchet_check`` — every ``standard`` entry on the board declares a
  named bar, a direction (only "tighten" is legal) and a numeric value
  with a declared sense ("min" = the bar may only rise, "max" = only
  fall). The check replays them in order and fails on ANY loosening —
  the memory's promise is 只紧不松, so the check must be able to fail.
* ``ledger`` — renders the memory ledger page: every lesson grouped by
  kind (data pits / decay / conventions / standards), the ratchet
  verdict, and the run manifests it can find, so "它学到了什么" is a
  page, not a metaphor.

Determinism: pure functions of the blackboard JSONL + manifests — no
wall-clock feeds the verdict (times are display-only).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SECTION_TITLES = {
    "data_pitfall": "数据坑（真实代价换来的）",
    "decay_event": "衰减与死亡判定",
    "convention_decision": "约定与拍板",
    "order_note": "订单备忘",
    "standard": "标准收紧记录",
}


def ratchet_check(board: Any) -> dict[str, Any]:
    """Replay `standard` entries; bars may only move tighten-ward."""
    history: dict[str, list[Any]] = {}
    violations: list[str] = []
    for e in board.entries("standard"):
        st = e.get("standard")
        if not st:
            violations.append(f"standard 条目缺 standard 名："
                              f"「{e.get('title', '?')}」")
            continue
        direction = e.get("direction", "tighten")
        if direction != "tighten":
            violations.append(f"{st}: direction={direction}"
                              f"（记忆只允许 tighten，不允许松）")
            continue
        val = e.get("value")
        if not isinstance(val, (int, float)):
            history.setdefault(st, []).append(val)
            continue
        sense = e.get("sense", "min")
        prev = [v for v in history.get(st, [])
                if isinstance(v, (int, float))]
        if prev:
            p = prev[-1]
            if sense == "min" and val < p:
                violations.append(f"{st}: {p} -> {val} 变松（sense=min，"
                                  f"下界只许上移）")
            if sense == "max" and val > p:
                violations.append(f"{st}: {p} -> {val} 变松（sense=max，"
                                  f"上界只许下移）")
        history.setdefault(st, []).append(val)
    return {"ok": not violations, "n_standards": len(history),
            "history": {k: list(v) for k, v in history.items()},
            "violations": violations}


def ledger(board: Any, runs_root: Path | None = None) -> str:
    """Markdown memory ledger: lessons by kind + ratchet + run manifests."""
    r = ratchet_check(board)
    lines = ["## 记忆黑板台账（跨会话，哈希链防篡改）", ""]
    any_entry = False
    for kind, title in SECTION_TITLES.items():
        entries = board.entries(kind)
        if not entries:
            continue
        any_entry = True
        lines += [f"### {title}", ""]
        for e in entries:
            note = f"：{e['body'][:100]}…" if e.get("body") else ""
            lines.append(f"- **{e['title']}**{note}")
        lines.append("")
    if not any_entry:
        lines.append("- （黑板为空——还没有教训，或还没有开始工作）")
    lines += [
        "### 只紧不松检查（standard 重放）", "",
        ("✅ 通过" if r["ok"] else "⛔ 失败")
        + (f" — {'; '.join(r['violations'])}" if r["violations"]
           else f"（{r['n_standards']} 个标准单调收紧，无变松记录）"),
        "",
    ]
    if runs_root is not None:
        mans = _load_manifests(runs_root)
        if mans:
            lines += ["### 运行清单（分身编制）", "",
                      "| run | workers | 角色×任务 | 耗时 |",
                      "|-----|---------|-----------|------|"]
            for m in mans:
                roles = ", ".join(f"{k}×{v}" for k, v in
                                  sorted(m.get("jobs_by_role",
                                               {}).items()))
                lines.append(f"| {m.get('run', '?')} | "
                             f"{m.get('workers', '?')} | {roles} | "
                             f"{m.get('elapsed_s', '?')}s |")
            lines.append("")
    return "\n".join(lines).rstrip()


def _load_manifests(runs_root: Path) -> list[dict[str, Any]]:
    out = []
    if not runs_root.exists():
        return out
    for man in sorted(runs_root.glob("*/manifest.json")):
        try:
            out.append(json.loads(man.read_text("utf-8")))
        except (json.JSONDecodeError, OSError):
            continue
    return out


def main(argv: list[str] | None = None) -> int:
    """Memory ledger CLI: qsa.memreport <work_dir> [runs_root]."""
    import sys
    from .blackboard import Blackboard
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print("usage: python -m qsa.memreport <run_dir|work_root> "
              "[runs_root]")
        return 2
    d = Path(argv[0])
    board_path = d / "blackboard.jsonl" if (d / "blackboard.jsonl").exists() \
        else d / "work" / "blackboard.jsonl"
    if not board_path.exists():
        print(f"[mem] no blackboard at {board_path}")
        return 2
    runs_root = Path(argv[1]) if len(argv) > 1 else board_path.parent.parent
    print(ledger(Blackboard(board_path), runs_root))
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
