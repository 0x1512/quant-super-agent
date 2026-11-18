"""Followup — v1.4: conversational incremental research.

The showcase promise "研报不是终点，是对话的开始" becomes mechanical
here: a follow-up instruction is parsed, classified by what it can
invalidate, and only the affected work is redone.

Two paths, honestly labelled:

* **re-judge (bar change)** — if the instruction only moves the
  pre-declared bar (threshold / min_months), the per-candidate rows from
  the previous run are REUSED verbatim and only the verdict walk is
  redone. This is the true incremental path: seconds, zero rescoring,
  byte-stable because it is a pure function of the cached leaderboard.
* **recompute (universe/window change)** — anything that can change a
  score (universe filter, new windows) triggers an honest re-run of the
  affected streams through the same dispatcher the full run uses. The
  report records exactly which streams recomputed and how long it took.

What this module NEVER does: silently mix the two. Every follow-up
report states its mode, and a re-judge can never be issued for an
instruction that changes scores — that would be the incremental lie.

    python -m qsa.followup --prev work/offense "门槛提到 0.05"
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from typing import Any

from .planner import fingerprint  # noqa: F401  (re-exported convenience)

BAR_WORDS = {"严格": 0.05, "宁缺毋滥": 0.05, "宽松": 0.02, "多看候选": 0.02}


def parse_instruction(text: str) -> dict[str, Any]:
    """Classify a follow-up into a machine instruction.

    Returns {"mode": "rejudge"|"recompute"|"refuse", ...params}.
    Refuse (rather than guess) when nothing known matches — the
    conversational layer must not invent capabilities.
    """
    t = text.strip()
    ins: dict[str, Any] = {"mode": "refuse", "raw": t}

    m = re.search(r"(?:0\.\d+)", t)
    bar = float(m.group(0)) if m else None
    for w, v in BAR_WORDS.items():
        if w in t:
            bar = v
            break
    m = re.search(r"(?:至少|不少于)\s*(\d+)\s*个?月", t)
    min_months = int(m.group(1)) if m else None

    universe: dict[str, Any] | None = None
    if re.search(r"剔除小盘|去掉小盘|排除小盘", t):
        universe = {"name": "top300", "exclude": "smallcap"}
    elif "小盘" in t:
        universe = {"name": "smallcap"}

    if bar is not None or min_months is not None:
        if universe is not None:
            ins.update(mode="recompute", universe=universe)
        else:
            ins.update(mode="rejudge")
        if bar is not None:
            ins["thresh"] = bar
        if min_months is not None:
            ins["min_months"] = min_months
        return ins

    if universe is not None:
        ins.update(mode="recompute", universe=universe)
        return ins

    ins["reason"] = "无法把这句话解析成已支持的追问（改门槛/改窗口/换范围）"
    return ins


def _winners_from(rows: list[dict[str, Any]], thresh: float,
                  min_months: int) -> list[dict[str, Any]]:
    out = []
    seen: set[str] = set()
    for r in sorted(rows, key=lambda r: -(r["oos_ic"] or -9)):
        if r["id"] in seen or r["oos_ic"] is None:
            continue
        seen.add(r["id"])
        if r["oos_ic"] > thresh and (r["n_months"] or 0) >= min_months:
            out.append(r)
    return out


def rejudge(prev: dict[str, Any], ins: dict[str, Any]) -> dict[str, Any]:
    """Pure re-verdict from the cached leaderboard — no rescoring."""
    t0 = time.perf_counter()
    thresh = ins.get("thresh", prev["config"]["thresh"])
    min_months = ins.get("min_months", prev["config"]["min_months"])
    rows = prev["rows"]
    old = _winners_from(rows, prev["config"]["thresh"],
                        prev["config"]["min_months"])
    new = _winners_from(rows, thresh, min_months)
    old_ids = {r["id"] for r in old}
    new_ids = {r["id"] for r in new}
    return {
        "mode": "rejudge", "instruction": ins["raw"],
        "prev_thresh": prev["config"]["thresh"],
        "new_thresh": thresh, "new_min_months": min_months,
        "kept": sorted(new_ids & old_ids),
        "added": sorted(new_ids - old_ids),
        "dropped": sorted(old_ids - new_ids),
        "n_candidates": len(rows), "n_winners": len(new),
        "elapsed_s": round(time.perf_counter() - t0, 3),
        "rows_reused": len(rows), "rows_rescored": 0,
        "winners": [r["id"] for r in new],
    }


def load_prev(work_dir: Path) -> dict[str, Any]:
    lb = json.loads((work_dir / "leaderboard.json").read_text("utf-8"))
    cfg_path = work_dir / "run_config.json"
    if cfg_path.exists():
        cfg = json.loads(cfg_path.read_text("utf-8"))
    else:  # a v1.3 run: reconstruct the config from the report contract
        cfg = {"thresh": 0.03, "min_months": 12, "workers": None,
               "goal": "(v1.3 run, no recorded goal)",
               "fingerprint": None}
    rows = (lb.get("library", []) + lb.get("interactions", [])
            + lb.get("mutations", []) + lb.get("forge", []))
    return {"rows": rows, "config": cfg, "leaderboard": lb,
            "work_dir": work_dir}


def render(res: dict[str, Any]) -> str:
    mode_cn = {"rejudge": "仅改判定（复用上一轮评分，零重算）",
               "recompute": "重算受影响部分"}[res["mode"]]
    lines = [
        "# 追问报告（增量）", "",
        f"- 追问：「{res['instruction']}」",
        f"- 模式：{mode_cn}",
        f"- 门槛：{res.get('prev_thresh')} → {res.get('new_thresh')}"
        if "prev_thresh" in res else f"- 范围：{res.get('universe')}",
        f"- 候选 {res['n_candidates']} 个（复用 {res.get('rows_reused', 0)}"
        f" / 重算 {res.get('rows_rescored', 0)}）",
        f"- 结果：保留 {len(res['kept'])} · 新增 {len(res['added'])} · "
        f"落选 {len(res['dropped'])}",
        f"- 耗时 {res['elapsed_s']}s（上一轮全量 "
        f"{res.get('prev_elapsed_s', '?')}s）", "",
        "## 保留", "",
    ]
    lines += [f"- {x}" for x in res["kept"]] or ["- （无）"]
    lines += ["", "## 新增", ""]
    lines += [f"- {x}" for x in res["added"]] or ["- （无）"]
    lines += ["", "## 落选", ""]
    lines += [f"- {x}" for x in res["dropped"]] or ["- （无）"]
    return "\n".join(lines)


def run(prev_dir: Path, instruction: str) -> dict[str, Any]:
    prev = load_prev(prev_dir)
    ins = parse_instruction(instruction)
    if ins["mode"] == "refuse":
        return {"mode": "refuse", "instruction": instruction,
                "reason": ins["reason"]}
    if ins["mode"] == "rejudge":
        res = rejudge(prev, ins)
    else:
        from . import recompute  # lazy: heavier import path
        res = recompute.run(prev, ins)
    res.setdefault("prev_elapsed_s",
                   prev["config"].get("elapsed_s"))
    out = prev_dir / "followup_report.md"
    out.write_text(render(res), encoding="utf-8")
    res["report"] = str(out)
    (prev_dir / "followup.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    return res


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) < 3 or argv[0] != "--prev":
        print('usage: python -m qsa.followup --prev work/offense "追问"')
        return 2
    res = run(Path(argv[1]), argv[2])
    if res["mode"] == "refuse":
        print(f"[refuse] {res['reason']}")
        return 1
    print(render(res))
    print(f"\n-> {res['report']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
