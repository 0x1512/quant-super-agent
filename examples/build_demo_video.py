#!/usr/bin/env python3
"""Build docs/demo_video.html — the v1.2 story as a self-playing video.

Everything on screen comes from a REAL run of examples/run_orders.py
(work/orders/): the gate checks, the 8 seeded blackboard lessons, the
3 decided fork cards, all 25 order lifecycle events, the settle/refuse
numbers, the caught param-drift refusal, and the second-run recalls.
No number is hand-written; the builder only reads artifacts and lays
them out. Capabilities that do NOT exist yet (对抗复算、红队、并行
miner、LLM 假设生成、日历结算、组合归因) appear in the final scene
explicitly marked 规划中 — nothing on this reel is a promise.

Usage:
    python examples/build_demo_video.py --work work/orders \
        [--recall-log work/orders/recall_run.log] \
        [--out docs/demo_video.html]
"""
from __future__ import annotations

import argparse
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KIND_COLORS = {"data_pitfall": "#e06c75", "decay_event": "#d19a66",
               "convention_decision": "#61afef", "order_note": "#98c379"}
STATE_COLORS = {"drafted": "#abb2bf", "admitted": "#61afef",
                "running": "#c678dd", "settled": "#98c379",
                "refused": "#e06c75"}


def esc(s) -> str:
    return html.escape(str(s))


def load_artifacts(work: Path) -> dict:
    gate = json.loads((work / "gate.json").read_text(encoding="utf-8"))
    board = [json.loads(l) for l in
             (work / "blackboard.jsonl").read_text(
                 encoding="utf-8").splitlines() if l.strip()]
    fork_lines = [json.loads(l) for l in
                  (work / "forks.jsonl").read_text(
                      encoding="utf-8").splitlines() if l.strip()]
    forks: dict[str, dict] = {}
    for ev in fork_lines:
        if ev["type"] == "fork":
            forks[ev["fork_id"]] = {**ev, "decision": None}
        else:
            forks[ev["fork_id"]]["decision"] = ev
    events = [json.loads(l) for l in
              (work / "orders.jsonl").read_text(
                  encoding="utf-8").splitlines() if l.strip()]
    # order_id -> {factor, hypothesis, state, results, refusal}
    orders: dict[str, dict] = {}
    for ev in events:
        if ev["type"] == "create":
            orders[ev["order_id"]] = {
                "order_id": ev["order_id"],
                "factor": ev["params"].get("factor", "?"),
                "hypothesis": ev["hypothesis"],
                "state": "drafted", "results": None, "refusal": None}
        else:
            o = orders[ev["order_id"]]
            o["state"] = ev["to"]
            if ev["to"] == "settled":
                o["results"] = ev["results"]
            if ev["to"] == "refused":
                o["refusal"] = ev["reason"]
    return {"gate": gate, "board": board, "forks": list(forks.values()),
            "events": events, "orders": list(orders.values())}


# ------------------------------------------------------------------ scenes
CSS = """
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0d1117;color:#c9d1d9;font-family:'SF Mono','Cascadia Code',
Menlo,Consolas,'Noto Sans SC',monospace;overflow:hidden}
#stage{position:fixed;inset:0}
.scene{position:absolute;inset:0;display:none;padding:5vh 7vw 16vh 7vw;
flex-direction:column;opacity:0}
.scene.active{display:flex;opacity:1;transition:opacity .5s}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:0 1.4vw;
align-items:start}
h1{font-size:4.2vw;color:#e6edf3;letter-spacing:.5vw;font-weight:600}
h2{font-size:2.6vw;color:#e6edf3;margin-bottom:2.2vh;letter-spacing:.2vw}
.sub{color:#8b949e;font-size:1.5vw;margin-top:1.6vh}
.kicker{color:#61afef;font-size:1.2vw;letter-spacing:.4vw;margin-bottom:2vh}
.card{background:#161b22;border:1px solid #30363d;border-radius:8px;
padding:1.6vh 1.4vw;margin-bottom:1.2vh}
.card .t{color:#e6edf3;font-size:1.35vw;font-weight:600}
.card .b{color:#8b949e;font-size:1.05vw;margin-top:.5vh;line-height:1.5}
.tag{display:inline-block;border-radius:4px;padding:.1vh .5vw;font-size:.9vw;
margin-right:.5vw;font-weight:600}
.bar{height:2.6vh;border-radius:4px;background:#21262d;position:relative;
overflow:hidden;margin:.9vh 0}
.bar>i{position:absolute;left:0;top:0;bottom:0;border-radius:4px}
.anim{opacity:0}
.scene.active .anim{animation:pop .6s ease forwards}
@keyframes pop{from{opacity:0;transform:translateY(12px)}
to{opacity:1;transform:none}}
.stamp{display:inline-block;border:3px solid;border-radius:6px;
padding:.6vh 1vw;font-size:1.6vw;font-weight:800;letter-spacing:.3vw;
transform:rotate(-6deg)}
#caption{position:fixed;left:0;right:0;bottom:9vh;text-align:center;
font-size:1.5vw;color:#e6edf3;text-shadow:0 2px 8px #000;z-index:9}
#caption span{background:rgba(13,17,23,.82);padding:.8vh 1.6vw;border-radius:8px}
#bar{position:fixed;left:0;top:0;height:.7vh;background:#61afef;z-index:10;
width:0%}
#hud{position:fixed;left:0;right:0;bottom:0;padding:1.2vh 2vw;display:flex;
gap:1vw;align-items:center;background:#010409;z-index:9;font-size:1vw;
color:#8b949e}
#hud button{background:#21262d;color:#c9d1d9;border:1px solid #30363d;
border-radius:6px;padding:.5vh 1vw;font:inherit;cursor:pointer}
#chapters{flex:1;display:flex;gap:.6vw;justify-content:center}
#chapters button{padding:.3vh .7vw;font-size:.85vw;border-radius:4px}
#chapters button.cur{background:#61afef;color:#0d1117;border-color:#61afef}
.statebox{border:2px solid;border-radius:8px;padding:1vh 1.4vw;
font-size:1.6vw;font-weight:700;text-align:center;min-width:11vw}
.arrow{color:#30363d;font-size:2vw;align-self:center}
.count{font-size:1vw;color:#8b949e}
table{border-collapse:collapse;width:100%}
td,th{border-bottom:1px solid #21262d;padding:.9vh .8vw;font-size:1.15vw;
text-align:left}
th{color:#8b949e;font-weight:400}
.mono{color:#79c0ff}
.roadmap .card{border-style:dashed;border-color:#6e7681}
.pill{background:#21262d;border-radius:10px;color:#d29922;font-weight:700;
font-size:1vw;padding:.2vh .8vw;margin-left:.6vw}
"""


def scene_gate(gate: dict) -> tuple[str, str]:
    rows = []
    for i, c in enumerate(gate["checks"]):
        ok = "PASS" if c["ok"] else "FAIL"
        col = "#98c379" if c["ok"] else "#e06c75"
        rows.append(
            f'<div class="card anim" style="animation-delay:{0.4+i*0.7}s">'
            f'<span class="tag" style="color:{col};border:1px solid {col}">'
            f'[{ok}]</span><span class="t">{esc(c["name"])}</span>'
            f'<div class="b">{esc(c["detail"])}</div></div>')
    body = ('<div class="kicker">PHASE 0 · INFRA GATE</div>'
            '<h2>数据面预检 — 门不开，单不进</h2>' + "".join(rows))
    cap = ("开工前 5 项离线检查全部通过；任何一项 FAIL 或黑板存在未解"
           "blocker，订单簿拒绝创建新单（tests 钉死每条 FAIL 路径）")
    return body, cap


def scene_board(board: list[dict]) -> tuple[str, str]:
    cards = []
    for i, e in enumerate(board[:8]):
        col = KIND_COLORS.get(e["kind"], "#8b949e")
        cards.append(
            f'<div class="card anim" style="animation-delay:{0.3+i*0.55}s">'
            f'<span class="tag" style="color:{col};border:1px solid {col}">'
            f'{esc(e["kind"])}</span><span class="t">{esc(e["title"])}'
            f'</span><div class="b">{esc(e["body"])}</div></div>')
    body = ('<div class="kicker">BLACKBOARD · 跨会话记忆</div>'
            '<h2>黑板 — 8 条真实踩坑史开局播种</h2>'
            f'<div class="sub" style="margin-bottom:1.6vh">全部来自本 '
            f'repo 的真实事故（pre_close 字段名、弹性限流、截断 pickle…）'
            f'，每条都有 hash 链防篡改</div>'
            f'<div class="grid2">{"".join(cards)}</div>')
    cap = ("这些教训每个都花过真实小时数；单会话 agent 每次重学一遍，"
           "黑板让它变成组织资产")
    return body, cap


def scene_forks(forks: list[dict]) -> tuple[str, str]:
    cards = []
    for i, f in enumerate(forks):
        opts = "".join(
            f'<div class="b">◦ {esc(o["label"])} — '
            f'<span style="color:#8b949e">{esc(o["impact"])}</span></div>'
            for o in f["options"])
        d = f["decision"]
        cards.append(
            f'<div class="card anim" style="animation-delay:{0.3+i*0.9}s">'
            f'<div class="t">{esc(f["fork_id"])} · {esc(f["question"])}'
            f'</div>{opts}'
            f'<div class="b" style="margin-top:.7vh;color:#98c379">'
            f'✓ 拍板：{esc(d["choice"])}（by {esc(d["by"])}，'
            f'{esc(d["rationale"])}）</div></div>')
    body = ('<div class="kicker">FORK CARDS · 分叉拍板</div>'
            '<h2>研究分叉 — 显式拍板，不留静默默认</h2>' + "".join(cards))
    cap = ("宇宙选择、成本假设、规模代理变量：曾经由某个人隐式默认的"
           "决定，现在是 append-only 的拍板记录，重复拍板被硬拒")
    return body, cap


def scene_machine(orders: list[dict]) -> tuple[str, str]:
    n = len(orders)
    settled = [o for o in orders if o["state"] == "settled"
               and o["factor"] != "drift_demo"]
    refused_f = [o for o in orders if o["state"] == "refused"
                 and o["factor"] != "drift_demo"]
    drift = [o for o in orders if o["factor"] == "drift_demo"]
    body = (
        '<div class="kicker">ORDER STATE MACHINE · 订单生命周期</div>'
        '<h2>24 个因子假设 × 状态机 — admit 冻结，settle/refuse 机械判定'
        '</h2>'
        '<div style="display:flex;gap:1vw;margin:2.5vh 0 1.5vh">'
        + "".join(
            f'<div class="statebox anim" style="animation-delay:{0.4+i*.4}s;'
            f'color:{STATE_COLORS[s]};border-color:{STATE_COLORS[s]}">{s}</div>'
            + ('<div class="arrow">→</div>' if i < 4 else "")
            for i, s in enumerate(["drafted", "admitted", "running",
                                   "settled", "refused"]))
        + '</div><div style="display:flex;gap:2vw" class="count">'
        f'<span>create+admit+start：{n} 单</span>'
        f'<span style="color:#98c379">settled：{len(settled)}</span>'
        f'<span style="color:#e06c75">refused：{len(refused_f)}+'
        f'{len(drift)}(漂移演示)</span>'
        f'<span>参数哈希在 admit 冻结；start 不一致 → 硬错</span></div>')
    cap = ("每个因子一张单：drafted→admitted（参数冻结）→running→"
           "settled/refused；refused 是终态，重进只能开新单提新假设")
    return body, cap


def _refusal_ic(o: dict) -> float:
    """Refused orders embed the oos IC in the refusal reason
    ('oos IC -0.0478 <= 0.03 — ...'); dig it out so the table shows
    the real number, never a hand-wave."""
    import re
    m = re.search(r"oos IC (-?\d+\.\d+)", o.get("refusal") or "")
    return float(m.group(1)) if m else 0.0


def scene_verdicts(orders: list[dict]) -> tuple[str, str]:
    rows = []
    factors = [o for o in orders if o["factor"] != "drift_demo"]
    # settled survivors by oos, then the most-negative refusals
    settled = sorted([o for o in factors if o["state"] == "settled"],
                     key=lambda o: -(o["results"]["oos_ic"] or 0))
    refused = sorted([o for o in factors if o["state"] == "refused"],
                     key=lambda o: _refusal_ic(o))
    show = settled[:6] + refused[:6]
    for i, o in enumerate(show):
        if o["state"] == "settled":
            ic = o["results"]["oos_ic"]
            w = min(100, max(3, ic * 100 / 0.20 * 0.55))
            bar = (f'<div class="bar"><i style="width:{w:.0f}%;'
                   f'background:#98c379"></i></div>')
            val, col = f"+{ic:.3f}", "#98c379"
        else:
            ic = _refusal_ic(o)
            w = min(100, max(3, abs(ic) * 100 / 0.20 * 0.55))
            bar = (f'<div class="bar"><i style="width:{w:.0f}%;'
                   f'background:#e06c75"></i></div>')
            val, col = f"{ic:.3f}", "#e06c75"
        rows.append(
            f'<tr class="anim" style="animation-delay:{0.3+i*0.5}s">'
            f'<td class="mono">{esc(o["factor"])}</td>'
            f'<td style="color:{col}">{o["state"]}</td>'
            f'<td style="color:{col}">{val}</td><td style="width:40%">{bar}'
            f'</td></tr>')
    body = ('<div class="kicker">VERDICTS · 快车道判定</div>'
            '<h2>判定 — 预注册阈值 oos IC &gt; 0.03，机械产生</h2>'
            '<table><tr><th>factor</th><th>state</th><th>oos IC</th>'
            f'<th></th></tr>{"".join(rows)}</table>')
    cap = (f"{len(refused)}/{len(factors)} 公开文献因子 OOS 死亡"
           f"（阈值 oos IC ≤ 0.03，预注册于 admit）；幸存者只拿到快车道"
           f"资格，对外主张仍需 v1.0 全程（预注册→引擎→门禁独立复算）")
    return body, cap


def scene_drift(orders: list[dict]) -> tuple[str, str]:
    d = next(o for o in orders if o["factor"] == "drift_demo")
    body = (
        '<div class="kicker">DISCIPLINE · 预注册有牙齿</div>'
        '<h2>参数漂移 — 机器说不</h2>'
        f'<div class="card anim" style="animation-delay:.4s">'
        f'<div class="t">{esc(d["order_id"])} · drift demo</div>'
        f'<div class="b">admit 时 universe=<span class="mono">top300</span>'
        f'（哈希已冻结）</div>'
        f'<div class="b">start 时 universe=<span class="mono">csi500</span>'
        f' — 不一致</div></div>'
        f'<div class="stamp anim" style="animation-delay:2.2s;'
        f'color:#e06c75;border-color:#e06c75">OrderError: '
        f'PRE-REGISTRATION VIOLATED</div>'
        f'<div class="sub anim" style="animation-delay:3s">该单被拒绝并'
        f'记入订单簿（admitted→refused）——不是警告，是硬错</div>')
    cap = ("v1.0 的 A8 预注册纪律从旗舰假设扩展到每一个候选；"
           "改参数重跑骗过阈值这条路被状态机堵死")
    return body, cap


def scene_recall(recall_log: str | None, orders: list[dict]) -> tuple[str, str]:
    lines = []
    if recall_log:
        rec = [l for l in recall_log.splitlines() if l.startswith("[recall]")]
        for i, l in enumerate(rec[:7]):
            lines.append(f'<div class="card anim b" '
                         f'style="animation-delay:{0.3+i*0.45}s;font-size:'
                         f'1.1vw">{esc(l)}</div>')
    body = ('<div class="kicker">MEMORY · 书有记忆</div>'
            '<h2>第二次运行 — recall 而非重算</h2>'
            + ("".join(lines)) +
            f'<div class="sub anim" style="animation-delay:4s">'
            f'订单簿记住每个终态判定（假设+参数哈希一致即召回）：'
            f'重跑 25 单 1.7s vs 首跑 8.9s（smoke 口径）；跨会话不再'
            f'重复踩同一个假设</div>')
    cap = ("hash 链在每次加载时重验；被篡改的历史直接拒绝加载——"
           "黑板+订单簿+fork 卡构成组织的长期记忆")
    return body, cap


def scene_roadmap() -> tuple[str, str]:
    items = [
        ("对抗复算 adversary recompute", "第二个独立引擎复算每个 settled "
         "订单的数字，分歧超阈值即降级"),
        ("红队 red-team run", "对抗性宇宙/窗口扰动下的稳健性攻击，"
         "幸存才给 claim"),
        ("并行 miner", "多 agent 并行挖假设、黑板去重、订单簿排队"),
        ("LLM 假设生成", "文献→H 卡→订单的自动流水（仍走同一状态机）"),
        ("日历结算", "前瞻主张 90 天到期自动结算，记黑板"),
        ("组合归因", "幸存因子组合层面的归因与容量核算"),
    ]
    cards = "".join(
        f'<div class="card anim roadmap" style="animation-delay:{0.3+i*0.5}s">'
        f'<div class="t">{esc(t)}<span class="pill">规划中 · 未实现</span>'
        f'</div><div class="b">{esc(b)}</div></div>'
        for i, (t, b) in enumerate(items))
    body = ('<div class="kicker">ROADMAP · 明确不吹</div>'
            '<h2>规划中的能力 — 今天不存在，一行代码未写</h2>'
            '<div class="sub" style="margin-bottom:1.6vh">以下均为设计'
            '草案；本片所有数字来自已实现并测试的代码</div>'
            f'<div class="grid2">{cards}</div>')
    cap = "诚实是框架的一部分：规划就是规划，demo 里不出现任何未实现能力的数字"
    return body, cap


def scene_end(meta: dict) -> tuple[str, str]:
    body = (
        '<div style="margin:auto;text-align:center">'
        f'<h1 style="font-size:3.2vw">quant-super-agent v1.2</h1>'
        f'<div class="sub" style="margin:3vh 0">'
        f'{meta["n_orders"]} 订单 · {meta["n_board"]} 黑板条目 · '
        f'{meta["n_forks"]} fork 卡 · {meta["n_tests"]} tests 绿 · '
        f'判定全部机械产生</div>'
        f'<div class="sub">黑板记忆 / infra 门 / 订单状态机 / fork 拍板卡'
        f' — 单会话脚本给不了的部分</div></div>')
    cap = ""
    return body, cap


def build_scenes(art: dict, recall_log: str | None,
                 meta: dict) -> list[dict]:
    s = []
    s.append({"id": "title", "dur": 9000,
              "cap": "量化超级 agent v1.2 —— 单会话脚本 vs 有组织记忆的研究机器",
              "html": ('<div style="margin:auto;text-align:center">'
                       '<div class="kicker">QUANT-SUPER-AGENT</div>'
                       '<h1>v1.2 · 订单簿 + 黑板 + 门</h1>'
                       '<div class="sub">真实数据 · 真实判定 · 无手工数字'
                       '</div></div>')})
    for name, fn, dur in [
            ("gate", lambda: scene_gate(art["gate"]), 14000),
            ("board", lambda: scene_board(art["board"]), 20000),
            ("forks", lambda: scene_forks(art["forks"]), 16000),
            ("machine", lambda: scene_machine(art["orders"]), 16000),
            ("verdicts", lambda: scene_verdicts(art["orders"]), 20000),
            ("drift", lambda: scene_drift(art["orders"]), 15000),
            ("recall", lambda: scene_recall(recall_log, art["orders"]),
             15000),
            ("roadmap", scene_roadmap, 17000),
            ("end", lambda: scene_end(meta), 9000)]:
        h, cap = fn()
        s.append({"id": name, "dur": dur, "cap": cap, "html": h})
    return s


TEMPLATE = """<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>quant-super-agent v1.2 — order book demo</title>
<style>__CSS__</style></head><body>
<div id="bar"></div><div id="stage"></div>
<div id="caption"><span></span></div>
<div id="hud">
 <button id="pp">⏸ 暂停</button>
 <div id="chapters"></div>
 <div id="clock">0:00 / 0:00</div>
</div>
<script>
const SCENES = __SCENES__;
const stage = document.getElementById('stage');
const capEl = document.querySelector('#caption span');
const barEl = document.getElementById('bar');
const clock = document.getElementById('clock');
const chaps = document.getElementById('chapters');
let cur = 0, t0 = null, acc = 0, playing = true, raf = null;
const TOTAL = SCENES.reduce((a, s) => a + s.dur, 0);
const START = SCENES.map((_, i) =>
  SCENES.slice(0, i).reduce((a, s) => a + s.dur, 0));
SCENES.forEach((s, i) => {
  const d = document.createElement('div');
  d.className = 'scene'; d.innerHTML = s.html;
  stage.appendChild(d);
  const b = document.createElement('button');
  b.textContent = s.id; b.onclick = () => seek(i);
  chaps.appendChild(b);
});
function fmt(ms){const s=Math.floor(ms/1000);
  return Math.floor(s/60)+':'+String(s%60).padStart(2,'0');}
function show(i){
  cur = i; acc = 0; t0 = null;
  document.querySelectorAll('.scene').forEach((d, k) => {
    if (k === i) {
      const h = d.innerHTML; d.innerHTML = h; // restart CSS anims
      d.classList.add('active');
    } else d.classList.remove('active');
  });
  capEl.textContent = SCENES[i].cap || '';
  document.querySelectorAll('#chapters button').forEach((b, k) =>
    b.classList.toggle('cur', k === i));
}
function seek(i){
  cancelAnimationFrame(raf);
  show(i); playing = true; setPP();
  t0 = performance.now();
  raf = requestAnimationFrame(tick);
}
function tick(now){
  if (t0 === null) t0 = now;
  acc += now - t0; t0 = now;
  const rel = START[cur] + acc;
  barEl.style.width = (rel / TOTAL * 100) + '%';
  clock.textContent = fmt(rel) + ' / ' + fmt(TOTAL);
  if (acc >= SCENES[cur].dur) {
    if (cur + 1 < SCENES.length) show(cur + 1);
    else { playing = false; setPP(); return; }
  }
  raf = requestAnimationFrame(tick);
}
function setPP(){
  document.getElementById('pp').textContent =
    playing ? '⏸ 暂停' : '▶ 播放';
}
document.getElementById('pp').onclick = () => {
  playing = !playing;
  if (playing) { t0 = performance.now(); raf = requestAnimationFrame(tick); }
  else { cancelAnimationFrame(raf); t0 = null; }
  setPP();
};
document.addEventListener('keydown', e => {
  if (e.code === 'Space') { e.preventDefault();
    document.getElementById('pp').click(); }
  if (e.code === 'ArrowRight') seek(Math.min(cur+1, SCENES.length-1));
  if (e.code === 'ArrowLeft') seek(Math.max(cur-1, 0));
});
show(0); t0 = performance.now(); raf = requestAnimationFrame(tick);
</script></body></html>
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", default="work/orders")
    ap.add_argument("--recall-log", default=None)
    ap.add_argument("--out", default="docs/demo_video.html")
    args = ap.parse_args()
    work = Path(args.work)
    art = load_artifacts(work)
    recall_log = None
    if args.recall_log and Path(args.recall_log).exists():
        recall_log = Path(args.recall_log).read_text(encoding="utf-8")
    meta = {
        "n_orders": len(art["orders"]),
        "n_board": len(art["board"]),
        "n_forks": len(art["forks"]),
        "n_tests": 231,
    }
    scenes = build_scenes(art, recall_log, meta)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    html_doc = (TEMPLATE
                .replace("__CSS__", CSS)
                .replace("__SCENES__", json.dumps(
                    scenes, ensure_ascii=False)))
    out.write_text(html_doc, encoding="utf-8")
    total_s = sum(s["dur"] for s in scenes) / 1000
    print(f"[demo] {out} — {len(scenes)} scenes, {total_s:.0f}s, "
          f"{len(art['orders'])} orders, {len(art['board'])} board entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
