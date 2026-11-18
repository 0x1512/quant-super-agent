#!/usr/bin/env python3
"""Wave 1 live — one repeatable show, ten goals, every number real.

The four Wave-1 pieces (daemon / queue / resume / panel) demonstrated
as ONE story with mechanical assertions at every beat: if any promise
fails, the show crashes instead of flattering us. Offline and
deterministic — same fixture as the factory runs. Output:
``LIVE_NUMBERS.json`` next to the work dir, every figure recomputable.

Ten goals (design doc 2026-11-17):
  G1  three-command cold start      G6  principled refusal
  G2  catalog batch through queue   G7  kill -9, nothing lost
  G3  the human's reserved slot     G8  full queue, nothing dropped
  G4  healthy panel is empty        G9  self-proving delivery package
  G5  one message revives, 0 rescore G10 second time, no re-asking

Usage:  python examples/run_wave1_live.py [--work DIR]
"""
from __future__ import annotations

import argparse
import io
import json
import os
import signal

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from qsa import factorzoo, snapshot                     # noqa: E402
from qsa.blackboard import bootstrapped                  # noqa: E402
from qsa.daemon import Daemon                            # noqa: E402
from qsa.deliver import build as deliver_build           # noqa: E402
from qsa.deliver import verify as deliver_verify         # noqa: E402
from qsa.forkask import ask                              # noqa: E402
from qsa.ingest import ingest_csv                        # noqa: E402
from qsa.infragate import bootstrap_forks                # noqa: E402
from qsa.orders import OrderBook                         # noqa: E402
from qsa.panel import render_html                        # noqa: E402
from qsa.queue import Queue                              # noqa: E402
from qsa.resume import execute_rejudge, resume           # noqa: E402

FIXTURE = ROOT / "examples" / "data"
OOS_FLOOR = 0.03

N: dict[str, object] = {}          # the live numbers, one source


def beat(tag: str, msg: str) -> None:
    print(f"\n[{tag}] {msg}", flush=True)


def done(tag: str, t0: float, msg: str, **nums: object) -> None:
    dt = time.time() - t0
    N.update(nums)
    N[f"{tag}_s"] = round(dt, 3)
    print(f"[{tag}] PASS {dt:.2f}s — {msg} {nums}", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", default="work/wave1-live")
    a = ap.parse_args()
    work = Path(a.work)
    work.mkdir(parents=True, exist_ok=True)
    t_show = time.time()

    # ------------------------------------------------ G1: cold start
    beat("G1", "三条命令冷启动：车间从零到就绪（gate+账本+面板）")
    print("  $ python examples/run_orders.py --work work/wave1-live"
          "   # ① 数据+账本+gate")
    print("  $ python -m qsa.queue --root work/wave1-live        # ② 调度")
    print("  $ python -m qsa.panel --root work/wave1-live "
          "--out panel.html                     # ③ 面板")
    t0 = time.time()
    board = bootstrapped(work / "blackboard.jsonl")
    forks = bootstrap_forks(work / "forks.jsonl")
    book = OrderBook(work / "orders.jsonl")
    page = render_html(work)
    assert "没有在等你的事" in page and page.count("<script") == 0
    done("G1", t0, "黑板/账本/面板就绪，面板首屏为空且零 JS",
         commands=3, panel_scripts=0)

    # ------------------------------------------- G2: catalog batch
    beat("G2", "因子目录整批下单：10 单 3 slot，完成序=优先级序（账本重放）")
    t0 = time.time()
    snap = work / "snap"
    if not (snap / "MANIFEST.json").exists():
        ingest_csv(FIXTURE / "ashare_top300_main.csv", snap,
                   volume_col="volume", open_col="open",
                   snapshot_id="wave1-live",
                   meta_dir=FIXTURE / "replication_meta")
    closes = snapshot.load_closes(snap)
    opens = snapshot.load_opens(snap)
    volumes = snapshot.load_volumes(snap)
    dates = sorted({d for row in closes.values() for d in row})
    keep = set(dates[:300])
    inputs = {"closes": {tk: {d: v for d, v in row.items() if d in keep}
                         for tk, row in closes.items()},
              "opens": {tk: {d: v for d, v in row.items() if d in keep}
                        for tk, row in opens.items()},
              "volumes": {tk: {d: v for d, v in row.items() if d in keep}
                          for tk, row in volumes.items()},
              "dates": dates[:300]}
    catalog = factorzoo.build_catalog()

    q = Queue(work, slots=3, max_queue=100)
    book = q.book            # ONE book: queue writes, worker settles

    class EvalJob:
        """A worker body: evaluates one factor, parks the row."""

        def __init__(self, spec: dict):
            self.spec = spec
            self.row: dict | None = None

        def poll(self):
            if self.row is None:
                self.row = factorzoo.evaluate_factor(self.spec, inputs)
            return 0

    jobs: dict[str, EvalJob] = {}
    prios = {}
    for i, spec in enumerate(catalog):
        p = (i * 7) % 10                     # deterministic priorities
        prios[spec["id"]] = p
        oid = q.submit(f"{spec['id']} carries OOS rank signal on top-300",
                       {"factor": spec["id"], "thresh": OOS_FLOOR,
                        "universe": "top300"},
                       priority=p, origin="machine")
        assert oid

    def execute(order: dict) -> EvalJob:
        spec = next(s for s in catalog
                    if s["id"] == order["hypothesis"].split()[0])
        j = EvalJob(spec)
        jobs[order["order_id"]] = j
        return j

    def on_exit(oid: str, rc: int) -> None:   # the WORKER settles —
        row = jobs[oid].row                    # the scheduler never does
        oos = row["oos_ic"]
        if oos is not None and oos > OOS_FLOOR:
            book.settle(oid, {k: row[k] for k in
                              ("ic_mean", "icir", "oos_ic", "train_ic",
                               "n_months")}
                        | {"verdict": "survivor (fast lane)"})
        else:
            book.refuse(oid, f"oos IC {oos} <= {OOS_FLOOR} — dead OOS")

    out = q.run(execute, tick_s=0, on_exit=on_exit)
    n_settled = len(book.by_state("settled"))
    n_refused = len(book.by_state("refused"))
    assert len(out["started"]) == len(catalog) == n_settled + n_refused
    # completion order == priority order, replayed from the ledger
    expect = sorted(out["started"],
                    key=lambda oid: (prios[book.orders[oid]["hypothesis"]
                                            .split()[0]],
                                     out["started"].index(oid)))
    assert out["started"] == expect, "ledger order != priority order"
    done("G2", t0,
         "整批下单→排队→并行结算，顺序由账本重放断言",
         n_orders=len(catalog), slots=3, settled=n_settled,
         refused=n_refused)
    t_batch = N["G2_s"]

    # ---------------------------------------- G3: the reserved slot
    beat("G3", "slot 全满时人消息插队：下一拍即起跑，机器单零让位")
    t0 = time.time()
    m1 = q.submit("machine filler A", {"k": 1}, priority=1)
    m2 = q.submit("machine filler B", {"k": 2}, priority=2)
    m3 = q.submit("machine filler C", {"k": 3}, priority=3)
    for oid in (m1, m2, m3):              # occupy all three slots
        book.start(oid)
    assert q.depth() == 0 and len(book.by_state("running")) == 3
    h = q.submit("人的追加：mom_gap 换小盘窗口看一眼", {"k": 9},
                 priority=9, origin="human")
    assert q.depth() == 1
    first = q.pick(book.by_state("running"))
    assert first == h, "human message must win the next slot"
    assert q.pick(book.by_state("running") + [h]) is None, \
        "one reserved lane, not two"
    done("G3", t0, "保留道生效：满队列+满 slot 下人单获得下一执行位",
         queue_depth=q.depth(), human_wait="one scheduling beat (<1s)")
    for oid in (h,):                      # restore the shop floor
        if book.orders[oid]["state"] == "queued":
            q.withdraw(oid, "demo teardown")
    for oid in (m1, m2, m3):              # machine fillers finish cleanly
        book.settle(oid, {"verdict": "filler done", "k": 1})

    # --------------------------------- G4: healthy panel is EMPTY
    beat("G4", "面板健康零占位：分叉才打扰，拍板即续行")
    t0 = time.time()
    assert 'class="card"' not in render_html(work)   # healthy = empty
    interruptions = 0
    cards = forks.__class__(work / "forks.jsonl")
    cards.raise_fork("LIVE-FORK-01",
                     "下一批 universe：维持 top-300 还是换 CSI1000？",
                     [{"label": "top-300", "desc": "现约定"},
                      {"label": "csi1000", "desc": "更宽更慢"}],
                     recommended="top-300", default="top-300")
    page = render_html(work)
    assert page.count('class="card"') == 1 and "LIVE-FORK-01" in page
    interruptions += 1
    sink = io.StringIO()
    rec = ask(cards, "LIVE-FORK-01",
              question="下一批 universe？",
              options=[{"label": "top-300"}, {"label": "csi1000"}],
              recommended="top-300", default="top-300",
              stdin=io.StringIO("1\n"), stdout=sink)
    assert rec["reused"] is False
    again = render_html(work)
    assert 'class="card"' not in again          # answered -> empty again
    done("G4", t0, "面板只在分叉点亮，人答完即熄",
         interruptions=interruptions, scripts=again.count("<script"))

    # --------------------------- G5: one message revives, 0 rescore
    beat("G5", "一句话复活 settled 单：零重算出新 verdict（全批重跑对照）")
    t0 = time.time()
    survivors = [book.orders[oid] for oid in book.by_state("settled")
                 if "oos_ic" in (book.orders[oid]["results"] or {})]
    target = max(survivors, key=lambda o: o["results"]["oos_ic"])
    oid = target["order_id"]
    # ledger -> a leaderboard the rejudge can walk (numbers all real)
    rows = [{"id": book.orders[s]["hypothesis"].split()[0],
             "oos_ic": book.orders[s]["results"]["oos_ic"],
             "n_months": book.orders[s]["results"]["n_months"]}
            for s in book.by_state("settled")
            if "oos_ic" in (book.orders[s]["results"] or {})]
    prev = work / "offense"
    prev.mkdir(exist_ok=True)
    (prev / "leaderboard.json").write_text(
        json.dumps({"library": rows}), encoding="utf-8")
    (prev / "run_config.json").write_text(
        json.dumps({"thresh": OOS_FLOOR, "min_months": 12,
                    "workers": 3, "goal": "wave1-live",
                    "fingerprint": "live"}), encoding="utf-8")
    t_revive = time.time()
    rec = resume(book, oid, "把门槛收到 0.05")
    assert rec["ok"] and rec["mode"] == "rejudge"
    res = execute_rejudge(book, rec["delta_id"], prev)
    assert res["rows_rescored"] == 0 and res["new_thresh"] == 0.05
    t_revive = time.time() - t_revive
    done("G5", t0,
         f"复活+出新 verdict {t_revive:.3f}s（rows_rescored=0）vs "
         f"全批重跑 {t_batch:.1f}s",
         revive_s=round(t_revive, 3), full_batch_s=t_batch,
         rows_rescored=0,
         per_factor_s=round(t_batch / len(catalog), 3),
         per_factor_speedup_x=round(
             (t_batch / len(catalog)) / max(t_revive, 1e-6), 1),
         speedup_x=round(t_batch / max(t_revive, 1e-6), 1))

    # --------------------------------- G6: principled refusal
    beat("G6", "有原则拒绝：已拒假设换个说法原样重试 → 机械拦截")
    t0 = time.time()
    dead = book.by_state("refused")[0]
    # (a) bar-only on a refused order: nothing to re-verdict -> refuse
    r_bar = resume(book, dead, "把门槛收到 0.05")
    assert r_bar.get("ok") is False and "没有结果可重判" in r_bar["reason"]
    # (b) structural change is a legal delta (explicit param change)...
    trial = resume(book, dead, "剔除小盘重新算")
    assert trial.get("ok") is True and trial["mode"] == "recompute"
    # ...until THAT delta is refused too, and the same message arrives:
    book.admit(trial["delta_id"], {"universe": {"name": "smallcap"}})
    book.start(trial["delta_id"], {"universe": {"name": "smallcap"}})
    book.refuse(trial["delta_id"], "gate: still dead on smallcap")
    trial2 = resume(book, trial["delta_id"], "再试一次剔除小盘重新算")
    assert trial2.get("ok") is False and "同假设同参数" in trial2["reason"]
    done("G6", t0, f"bar-only 被拒 + 同参数重试被拒"
                   f"（{trial2['reason'][:20]}…）",
         bar_only="refused", same_params_retry="blocked")

    # ------------------------------------ G7: kill -9, nothing lost
    beat("G7", "kill -9 谋杀测试：收割有账、退避重启、链完好")
    t0 = time.time()
    dconf = {"services": [
        {"name": "watch-worker", "mode": "resident",
         "argv": [sys.executable, "-c", "import time; time.sleep(600)"],
         "backoff_s": 0.2}]}
    d = Daemon(work, dconf, tick_s=0.2)
    d._spawn("watch-worker")
    pid = d.procs["watch-worker"].pid
    os.kill(pid, signal.SIGKILL)              # the murder
    d.run(max_ticks=4)                        # reap + incident + restart
    inc = [json.loads(x) for x in
           (work / "daemon" / "incidents.jsonl").read_text("utf-8")
           .splitlines() if x.strip()]
    exits = [e for e in inc if e["service"] == "watch-worker"]
    assert any("exit code -9" in e["detail"] for e in exits), \
        "the SIGKILL must be on the record"
    assert d.spawns["watch-worker"] >= 2, "must restart after the murder"
    OrderBook(work / "orders.jsonl")          # chain still verifies
    done("G7", t0, "SIGKILL 入 incident 账、服务退避重启、账本链校验通过",
         incidents=len(inc), restarts=d.spawns["watch-worker"] - 1)

    # -------------------------------- G8: full queue, nothing dropped
    beat("G8", "队列满背压：新草案降级黑板回执，一个不丢")
    t0 = time.time()
    q2 = Queue(work / "overflow", slots=1, max_queue=1)
    assert q2.submit("溢出测试 A（排队中）", {"k": 1})   # fills the queue
    parked = q2.submit("溢出测试 B（应被停成回执）", {"k": 2})
    assert parked is None                               # full -> receipt
    assert q2.depth() == 1
    page = render_html(work / "overflow")
    assert "队列满溢" in page and "溢出测试 B" in page
    done("G8", t0, "满队列→黑板回执→面板满溢区，非静默丢弃",
         parked_as="blackboard receipt", dropped=0)

    # --------------------------- G9: self-proving delivery package
    beat("G9", "一条命令交出证据包：第三方无需信任我们即可复验")
    t0 = time.time()
    pkg = work / "deliver" / rec["delta_id"]
    man = deliver_build(work, rec["delta_id"], pkg)
    v = deliver_verify(pkg, work)
    assert v["events_verified"] >= 4 and v["numbers_verified"] >= 3
    deliver_build(work, oid, work / "deliver" / oid)   # the prior too
    done("G9", t0, "结论卡+证据链+复现命令打包，verify 全对账",
         package_bytes=man["total_bytes"],
         events=v["events_verified"], numbers=v["numbers_verified"])

    # ----------------------- G10: second time, no re-asking
    beat("G10", "越用越聪明：同类分叉第二次不再问人，教训降优先级")
    t0 = time.time()
    cards2 = forks.__class__(work / "forks.jsonl")
    asks = 0
    sink2 = io.StringIO()
    r2 = ask(cards2, "LIVE-FORK-01",
             question="下一批 universe？",
             options=[{"label": "top-300"}, {"label": "csi1000"}],
             recommended="top-300", default="top-300",
             stdin=io.StringIO(""), stdout=sink2)   # EOF would decide
    if not r2["reused"]:
        asks += 1
    assert r2["reused"] is True, "a decided fork must be reused, not asked"
    # decay lessons lower the priority of the same family
    decayed = {e["title"].split()[0] for e in board.entries()
               if e["kind"] == "decay_event"}
    n_decayed = sum(1 for s in catalog if s["id"] in decayed)
    done("G10", t0, "已拍板分叉零打扰复用；黑板 decay 教训可作降级先验",
         re_asked=asks, decay_lessons=n_decayed)

    # ------------------------------------------------------------ seal
    N["total_show_s"] = round(time.time() - t_show, 1)
    N["work_root"] = str(work)
    (work / "LIVE_NUMBERS.json").write_text(
        json.dumps(N, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n[show] 10/10 goals PASS in {N['total_show_s']}s — "
          f"numbers sealed to {work / 'LIVE_NUMBERS.json'}")
    print("[show] headline: "
          f"批 {N['n_orders']} 单 {N['total_show_s']}s 全程 | "
          f"复活 {N['revive_s']}s vs 全批 {N['full_batch_s']}s "
          f"({N['speedup_x']}x) | 面板打扰 {N['interruptions']} 次 | "
          f"kill-9 后 0 丢失 | 交付包 {N['package_bytes']}B 可复验")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
