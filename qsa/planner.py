"""Planner — v1.4: one-sentence intent -> pre-registered plan + tree.

The showcase promise "you give a goal, it lays out the research plan"
becomes mechanical here. NO LLM in this module: the parser is a
deterministic, rule-based compiler from free-form Chinese goal text to a
``Plan`` dict the runner can execute. Anything the parser cannot ground
is surfaced in ``plan["notes"]`` — the planner never invents parameters
it did not read; it falls back to the pre-declared defaults and says so.

Determinism contract:

* ``intent_to_plan(goal)`` is a pure function of the goal string — no
  wall-clock, no RNG, no environment peeking;
* ``fingerprint(plan)`` = sha256 over the canonical JSON of the plan, so
  the same goal always compiles to the same fingerprinted plan (the
  "锁定的方案" the showcase promises);
* the runner consumes plans through ``windows_for``/``streams_for`` only,
  so an unknown hint can never smuggle an unregistered parameter in.

The plan tree (``tree()``) is the artifact the report renders: every node
carries an id, a title, a status and an annotation slot the runner fills
in as stages complete — the tree is written by the run, not hand-drawn.

Usage:

    python -m qsa.planner "低波动股票什么时候跑赢高波动股票？"
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from dataclasses import dataclass, field
from typing import Any

# pre-declared defaults — mirror examples/run_offense.py v1.3
DEFAULTS: dict[str, Any] = {
    "thresh": 0.03,            # residual oos IC to earn an order
    "min_months": 12,
    "month_families": ["mom", "mom_gap"],
    "day_families": ["dist_high", "sharpe", "intraday", "vol_of_vol"],
    "month_wins": [3, 6, 9, 18, 24],
    "day_wins": [10, 42, 63, 126, 252],
    "top_k": 4,
}

BARS = {"严格": 0.05, "strict": 0.05, "宁缺毋滥": 0.05,
        "宽松": 0.02, "loose": 0.02, "多看候选": 0.02}

STREAM_HINTS: list[tuple[str, str]] = [
    ("交互", "interactions"), ("组合条件", "interactions"),
    ("interaction", "interactions"),
    ("窗口", "mutations"), ("变体", "mutations"), ("参数扫描", "mutations"),
    ("文献", "library"), ("引用因子", "library"), ("开源因子", "library"),
    ("worldquant", "library"), ("101", "library"),
    ("沙盒生成", "forge"), ("沙盒因子", "forge"), ("forge", "forge"),
    ("补缺口", "forge"), ("自动补", "forge"),
]


@dataclass
class Plan:
    goal: str
    streams: dict[str, bool] = field(default_factory=lambda: {
        "zoo": True, "library": True, "interactions": True,
        "mutations": True, "forge": False})
    thresh: float = DEFAULTS["thresh"]
    min_months: int = DEFAULTS["min_months"]
    month_wins: list[int] = field(
        default_factory=lambda: list(DEFAULTS["month_wins"]))
    day_wins: list[int] = field(
        default_factory=lambda: list(DEFAULTS["day_wins"]))
    month_families: list[str] = field(
        default_factory=lambda: list(DEFAULTS["month_families"]))
    day_families: list[str] = field(
        default_factory=lambda: list(DEFAULTS["day_families"]))
    top_k: int = DEFAULTS["top_k"]
    universe: dict[str, Any] = field(default_factory=lambda: {
        "name": "top300"})
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal": self.goal, "streams": self.streams,
            "thresh": self.thresh, "min_months": self.min_months,
            "month_wins": self.month_wins, "day_wins": self.day_wins,
            "month_families": self.month_families,
            "day_families": self.day_families, "top_k": self.top_k,
            "universe": self.universe, "notes": self.notes,
        }


def canonical(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"))


def fingerprint(plan: Plan | dict[str, Any]) -> str:
    """sha256[:16] over the canonical plan — the locked 方案指纹."""
    d = plan.to_dict() if isinstance(plan, Plan) else plan
    return hashlib.sha256(canonical(d).encode("utf-8")).hexdigest()[:16]


def intent_to_plan(goal: str) -> Plan:
    """Deterministic compiler: goal text -> Plan.

    Rules (each adds a *note*, so every non-default value is traceable
    to a phrase in the goal — no silent parameter minting):
    """
    p = Plan(goal=goal.strip())
    g = goal.lower()

    # --- bar hints -------------------------------------------------
    for word, bar in BARS.items():
        if word in g:
            p.thresh = bar
            p.notes.append(f"bar: 「{word}」-> residual oos IC > {bar}")
            break
    m = re.search(r"(?:门槛|阈值)[^0-9]{0,30}?(0\.\d+)", g)
    if m:
        p.thresh = float(m.group(1))
        p.notes.append(f"bar: 显式阈值 {m.group(1)}")

    # --- stream hints ----------------------------------------------
    seen: set[str] = set()
    for word, stream in STREAM_HINTS:
        if word in g and stream not in seen:
            seen.add(stream)
    for stream in ("interactions", "mutations", "library"):
        if stream in seen:
            p.streams[stream] = True
    if "forge" in seen:
        p.streams["forge"] = True
        p.notes.append("forge: 意图点名沙盒生成——模板候选照跑沙盒与残差尺")
    # an explicit focus disables the unstated optional streams
    if seen:
        for stream in ("interactions", "mutations", "library"):
            if stream not in seen:
                p.streams[stream] = False
                p.notes.append(f"stream: 未提及，跳过 {stream}")

    # --- window hints ------------------------------------------------
    mm = re.search(r"(?:至少|不少于)\s*(\d+)\s*个?月", g)
    if mm:
        p.min_months = int(mm.group(1))
        p.notes.append(f"bar: 样本下界 min_months={mm.group(1)}（至少 "
                       f"{mm.group(1)} 个月才准过线）")
        g = g[:mm.start()] + g[mm.end():]      # not a sweep window!
    days = [int(x) for x in re.findall(r"(\d+)\s*日", g)]
    months = [int(x) for x in re.findall(r"(\d+)\s*个?月", g)]
    if days:
        p.day_wins = sorted({w for w in p.day_wins} | set(days))
        p.notes.append(f"windows: 显式日窗 {sorted(set(days))} 并入")
    if months:
        p.month_wins = sorted({w for w in p.month_wins} | set(months))
        p.notes.append(f"windows: 显式月窗 {sorted(set(months))} 并入")

    # --- universe hints ------------------------------------------------
    if "剔除小盘" in g or "去掉小盘" in g or "排除小盘" in g:
        p.universe = {"name": "top300", "exclude": "smallcap"}
        p.notes.append("universe: 剔除小盘（按成交额下界过滤）")
    elif "小盘" in g:
        p.universe = {"name": "smallcap"}
        p.notes.append("universe: 只看小盘")
    return p


def windows_for(plan: Plan) -> tuple[list[str], list[str], list[int],
                                     list[int]]:
    """The runner-facing window access — plans never leak raw internals."""
    return (plan.month_families, plan.day_families,
            plan.month_wins, plan.day_wins)


def streams_for(plan: Plan) -> dict[str, bool]:
    return dict(plan.streams)


# ------------------------------------------------------------- the tree

def tree(goal: str, fp: str) -> dict[str, Any]:
    """Empty research tree skeleton; the runner fills status/annotations."""
    return {
        "goal": goal, "fingerprint": fp,
        "nodes": [
            {"id": "gate", "title": "环境与数据核对",
             "status": "pending", "note": "", "role": "EnvSmith"},
            {"id": "snapshot", "title": "面板装配（缺列不硬算）",
             "status": "pending", "note": "", "role": "EnvSmith"},
            {"id": "basis", "title": "已知规律基线（zoo 幸存者）",
             "status": "pending", "note": "", "role": "GateKeeper"},
            {"id": "library", "title": "引用因子库扫描",
             "status": "pending", "note": "", "role": "RepoSmith"},
            {"id": "interactions", "title": "组合条件挖掘",
             "status": "pending", "note": "", "role": "FlowMapper"},
            {"id": "mutations", "title": "窗口变体扫描",
             "status": "pending", "note": "", "role": "SmokeRunner"},
            {"id": "forge", "title": "沙盒生成补缺口（如触发）",
             "status": "pending", "note": "", "role": "EnvSmith"},
            {"id": "orders", "title": "复核与成文（诚实判定）",
             "status": "pending", "note": "", "role": "SmokeProbe"},
        ],
    }


def render_tree(t: dict[str, Any]) -> str:
    """Markdown rendering of the (running or finished) tree."""
    out = [f"## 研究计划树 · 指纹 `{t['fingerprint']}`", "",
           f"目标：「{t['goal']}」", ""]
    for n in t["nodes"]:
        mark = {"done": "✓", "running": "…", "pending": "·",
                "skipped": "—"}.get(n["status"], "·")
        role = n.get("role", "")
        out.append(f"- {mark} **{n['title']}**"
                   + (f"（{role}）" if role else "")
                   + (f" — {n['note']}" if n.get("note") else ""))
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print("usage: python -m qsa.planner \"研究目标\"")
        return 2
    goal = " ".join(argv)
    p = intent_to_plan(goal)
    fp = fingerprint(p)
    print(render_tree(tree(goal, fp)))
    print()
    print(canonical(p.to_dict()))
    print(f"\n指纹 {fp} · 方案已锁定（同目标必得同指纹）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
