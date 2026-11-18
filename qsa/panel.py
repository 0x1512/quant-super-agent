"""Panel — SUPERAGENT_PLAN2 #7: attention-first, zero-JS HTML.

dsh principle (000): "A panel that shows only what needs a person. It
lists first what waits for a person. A healthy state takes no space."

`qsa board` is the whole workshop in one screen; this panel is the
other thing — the to-do list. The first screen carries ONLY what waits
for a human: open fork cards (拍板待选), unresolved blockers, and
queue-overflow receipts (the backpressure notes #2 parks on the
blackboard). The workshop panorama (orders/tasks/incidents/crew) folds
into a collapsed <details> at the tail — healthy state takes no space.

Delivery discipline (三通道制): the file is the deliverable. No
service, no port, and **zero JavaScript** — `grep -c "<script"` on the
output must be 0. Every number is recomputed from the ledgers; the
tests re-derive them independently.

    python -m qsa.panel --root work --out panel.html
"""
from __future__ import annotations

import argparse
import html
import json
import time
from pathlib import Path
from typing import Any

from . import blackboard as bb
from .board import render as board_render

# kinds that wait for a person; amendments (#3) join this list later
AMENDMENT_KIND = "amendment"          # PLAN2 #3, reserved


def collect(root: Path) -> dict[str, list[dict[str, Any]]]:
    """Read-side: everything that waits for a human, from the ledgers."""
    root = Path(root)

    # -- fork cards waiting for a decision ------------------------------
    from .infragate import ForkCards
    forks: list[dict[str, Any]] = []
    fp = root / "forks.jsonl"
    if fp.exists():
        for c in ForkCards(fp).open_forks():
            forks.append({
                "id": c["fork_id"], "question": c["question"],
                "options": c["options"], "default": c.get("default", ""),
                "recommended": c.get("recommended", ""),
                "source": "forks.jsonl",
            })

    # -- unresolved blockers, split by kind -----------------------------
    blockers: list[dict[str, Any]] = []
    overflow: list[dict[str, Any]] = []
    bp = root / "blackboard.jsonl"
    if bp.exists():
        board = bb.Blackboard(bp)
        # blockers() with indices: re-derive index to reference entries
        done = {e["resolves"] for e in board.entries() if "resolves" in e}
        for i, e in enumerate(board.entries()):
            if e.get("status") != "blocker" or i in done:
                continue
            item = {
                "title": e["title"], "body": e.get("body", ""),
                "index": i,
                "hash": (e.get("chain") or "")[:10],
                "source": "blackboard.jsonl",
            }
            if "queue" in (e.get("tags") or []):
                overflow.append(item)          # backpressure receipts
            else:
                blockers.append(item)

    # -- amendment cards waiting for a decision (PLAN2 #3) --------------
    amendments: list[dict[str, Any]] = []
    ap = root / "amendments.jsonl"
    if ap.exists():
        for ln in ap.read_text("utf-8").splitlines():
            if not ln.strip():
                continue
            ev = json.loads(ln)
            if ev.get("type") == AMENDMENT_KIND and "decision" not in ev:
                amendments.append({
                    "id": ev.get("amendment_id", "?"),
                    "question": ev.get("question", ""),
                    "options": ev.get("options", []),
                    "default": ev.get("default", ""),
                    "source": "amendments.jsonl",
                })

    return {"forks": forks, "blockers": blockers, "overflow": overflow,
            "amendments": amendments}


def _waiting_items(w: dict[str, list[dict[str, Any]]]) -> int:
    return sum(len(v) for v in w.values())


_CSS = """
body{font:15px/1.55 -apple-system,"Segoe UI",Roboto,"PingFang SC",
  "Microsoft YaHei",sans-serif;margin:0;background:#fafafa;color:#1a1a1a}
main{max-width:60rem;margin:0 auto;padding:1.5rem 1rem 4rem}
h1{font-size:1.35rem;margin:.2rem 0 .4rem}
h2{font-size:1.05rem;margin:1.6rem 0 .5rem;border-bottom:2px solid
  #e3e3e3;padding-bottom:.25rem}
.meta{color:#667;font-size:.85rem;margin:0 0 1rem}
.card{background:#fff;border:1px solid #e3e3e3;border-radius:8px;
  padding:.8rem 1rem;margin:.6rem 0;box-shadow:0 1px 2px rgba(0,0,0,.04)}
.card h3{margin:.1rem 0 .4rem;font-size:1rem}
.card ol{margin:.3rem 0 .3rem 1.2rem;padding:0}
.src{color:#667;font-size:.8rem;margin:.5rem 0 0}
.cmd{font-family:ui-monospace,Consolas,monospace;font-size:.82rem;
  background:#f2f2f2;border-radius:4px;padding:.15rem .4rem}
.empty{color:#3a7d44;background:#eef7ef;border:1px solid #cde6d2;
  border-radius:8px;padding:.7rem 1rem}
details{margin-top:2.5rem;border-top:1px solid #ddd;padding-top:1rem}
summary{cursor:pointer;color:#667;font-size:.9rem}
pre{background:#fff;border:1px solid #e3e3e3;border-radius:8px;
  padding:.8rem;overflow-x:auto;font-size:.78rem}
.badge{display:inline-block;font-size:.75rem;border-radius:10px;
  padding:.05rem .55rem;margin-left:.4rem;vertical-align:middle}
.badge.fork{background:#e8f0fe;color:#1a56c4}
.badge.blocker{background:#fdecea;color:#b3261e}
.badge.overflow{background:#fef3e0;color:#9a6700}
.badge.amendment{background:#f0e8fe;color:#6b3fc4}
"""


def render_html(root: Path) -> str:
    """Single-file HTML. Zero <script> tags; folding is native <details>."""
    root = Path(root)
    w = collect(root)
    n = _waiting_items(w)
    esc = html.escape
    out: list[str] = [
        "<!doctype html>", '<html lang="zh">', "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        "<title>quant-super-agent panel</title>",
        f"<style>{_CSS}</style>", "</head>", "<body>", "<main>",
        "<h1>等人事项</h1>",
        f'<p class="meta">root={esc(str(root))} · '
        f"generated={time.strftime('%Y-%m-%d %H:%M:%S')} · "
        "健康不占位：本页只列等你的事 · "
        f'<span class="cmd">python -m qsa.panel --root {esc(str(root))} '
        "--out panel.html</span></p>",
    ]

    if n == 0:
        out.append('<p class="empty">没有在等你的事 — 队列、黑板、'
                   "拍板卡全部健康。</p>")

    def section(cls: str, title: str, items: list[dict[str, Any]],
                render_card) -> None:
        if not items:
            return
        out.append(f"<h2>{esc(title)} "
                   f'<span class="badge {cls}">{len(items)}</span></h2>')
        for it in items:
            render_card(it)

    def fork_card(it: dict[str, Any]) -> None:
        opts = "".join(
            f"<li><b>{esc(o.get('label', '?'))}</b>"
            + (f" — {esc(o['desc'])}" if o.get("desc") else "")
            + (" ←默认" if o.get("label") == it["default"] else "")
            + "</li>" for o in it["options"])
        out.append(
            '<div class="card"><h3>' + esc(it["id"]) + " · "
            + esc(it["question"]) + "</h3><ol>" + opts + "</ol>"
            f'<p class="src">来源 {esc(it["source"])} · 拍板方式：回复'
            f'「FORK {esc(it["id"])} 选 N」（无人应答按默认'
            f"「{esc(it['default'])}」执行，账本照记）</p></div>")

    def blocker_card(it: dict[str, Any]) -> None:
        out.append(
            '<div class="card"><h3>blocker #' + str(it["index"]) + " · "
            + esc(it["title"]) + "</h3><p>" + esc(it["body"])
            + f'</p><p class="src">来源 {esc(it["source"])} #{it["index"]}'
            f" · chain {esc(it['hash'])}</p></div>")

    def overflow_card(it: dict[str, Any]) -> None:
        out.append(
            '<div class="card"><h3>队列满溢 · ' + esc(it["title"])
            + "</h3><p>" + esc(it["body"])
            + f'</p><p class="src">来源 {esc(it["source"])} #{it["index"]}'
            f" · chain {esc(it['hash'])} · 处置：腾出队列后重提，或"
            "调大 max_queue</p></div>")

    def amendment_card(it: dict[str, Any]) -> None:
        opts = "".join(
            f"<li><b>{esc(o.get('label', '?'))}</b>"
            + (f" — {esc(o['desc'])}" if o.get("desc") else "")
            + (" ←默认" if o.get("label") == it["default"] else "")
            + "</li>" for o in it["options"])
        out.append(
            '<div class="card"><h3>' + esc(it["id"]) + " · "
            + esc(it["question"]) + "</h3><ol>" + opts + "</ol>"
            f'<p class="src">来源 {esc(it["source"])} · 拍板方式：回复'
            f'「AMEND {esc(it["id"])} 选 N」</p></div>')

    section("fork", "拍板待选", w["forks"], fork_card)
    section("amendment", "修正案待拍板", w["amendments"], amendment_card)
    section("blocker", "未解 blocker", w["blockers"], blocker_card)
    section("overflow", "队列满溢", w["overflow"], overflow_card)

    panorama = board_render(root)
    out.append("<details><summary>车间全景（健康区，点开；平时不占注意"
               "力）</summary><pre>" + esc(panorama) + "</pre></details>")
    out += ["</main>", "</body>", "</html>"]
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="attention-first zero-JS panel (PLAN2 #7)")
    ap.add_argument("--root", default="work")
    ap.add_argument("--out", default="",
                    help="write HTML here; default prints to stdout")
    a = ap.parse_args(argv)
    page = render_html(Path(a.root))
    if a.out:
        Path(a.out).write_text(page, encoding="utf-8")
        print(f"[panel] wrote {a.out} ({len(page)} bytes, zero JS)")
    else:
        print(page)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
