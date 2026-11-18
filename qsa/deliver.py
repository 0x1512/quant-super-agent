"""Deliver — PLAN2 #8 first half / Wave1-live G9: the self-proving
delivery package.

dsh 003: delivery has hard gates — approval coverage, size doors, PR
follow-through. Our settle is currently the END of an order: results
sit in the ledger, reports are layered, but the recipient has to
assemble "which number came from which run, which gate let it
through" by hand. This module packages a settled order into a
directory a third party can re-verify WITHOUT trusting us:

    python -m qsa.deliver --root work --order ORD-xxxx \
        --out deliver/ORD-xxxx
    python -m qsa.deliver --verify deliver/ORD-xxxx --root work

The package (four files, no more):

* ``conclusion.md``   — the four-line card: conclusion first, the
  three key numbers, the evidence pointers, the reproduce command
* ``evidence.json``   — the order's FULL event chain as it exists in
  the hash-chained ledger, plus a number->event map so every digit in
  the card is traceable to one event
* ``reproduce.txt``   — the mechanical commands (order book walk +
  panel + board; a resume delta also gets its resume command)
* ``MANIFEST.json``   — file list + the SIZE DOOR (dsh's <200-line
  gate, byte-flavored): a package over budget is marked
  ``needs_split`` with a suggestion, never silently shipped

``--verify`` re-reads the package against the live ledger: every
event must hash-match the replayed chain, and every number on the
conclusion card must exist in the ledger's own settle event. A
package that disagrees with the ledger fails loudly — delivery is
self-proving or it is not delivery.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from .orders import OrderBook, OrderError

# the size door: a package over this is "needs human splitting", not
# silently shipped (dsh's auto-merge <200 lines, byte-flavored)
SIZE_DOOR_BYTES = 2 * 1024 * 1024

# number keys lifted onto the conclusion card (order matters)
CARD_KEYS = ("verdict", "oos_ic", "icir", "ic_mean", "n_winners",
             "new_thresh", "prev_thresh", "n_candidates", "rows_rescored")


def _events_of(book: OrderBook, order_id: str) -> list[dict[str, Any]]:
    return [ev for ev in book._events if ev.get("order_id") == order_id]


def _card_numbers(results: dict[str, Any]) -> dict[str, Any]:
    return {k: results[k] for k in CARD_KEYS if k in results}


def build(root: Path, order_id: str, out: Path,
          size_door: int = SIZE_DOOR_BYTES) -> dict[str, Any]:
    """Package one SETTLED order. Returns the manifest record."""
    book = OrderBook(Path(root) / "orders.jsonl")
    o = book.orders.get(order_id)
    if o is None:
        raise OrderError(f"unknown order {order_id}")
    if o["state"] != "settled":
        raise OrderError(
            f"{order_id}: state={o['state']} — delivery packages a "
            "SETTLED verdict; live/refused orders are not deliverables")
    results = o["results"] or {}

    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)

    # -- evidence: the raw chain + a number->event map ----------------
    events = _events_of(book, order_id)
    settle_ev = next(ev for ev in events if ev.get("to") == "settled")
    numbers = _card_numbers(results)
    evidence = {
        "order_id": order_id,
        "chain_head": events[-1].get("chain", "")[:16],
        "n_events": len(events),
        "events": events,
        "number_sources": {
            str(k): {"event_index": events.index(settle_ev),
                     "field": k, "value": v}
            for k, v in numbers.items()},
        "resume_of": o.get("resume_of"),
    }
    (out / "evidence.json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=1),
        encoding="utf-8")

    # -- reproduce: mechanical, no trust required ----------------------
    lines = [
        "# reproduce — every command is offline & deterministic",
        "# 1. walk the ledger the order lives in:",
        f"python -m qsa.board --root {root}",
        "# 2. re-open the exact order chain (hash-chained replay):",
        f"python -c \"from qsa.orders import OrderBook; "
        f"b=OrderBook('{root}/orders.jsonl'); "
        f"print(b.orders['{order_id}']['history'])\"",
    ]
    if o.get("resume_of"):
        lines += [
            f"# 3. this is a resume DELTA of {o['resume_of']} — the prior",
            "#    order's evidence packages the same way:",
            f"python -m qsa.deliver --root {root} "
            f"--order {o['resume_of']} --out deliver/{o['resume_of']}",
        ]
    (out / "reproduce.txt").write_text("\n".join(lines) + "\n",
                                       encoding="utf-8")

    # -- conclusion: four lines, conclusion first ----------------------
    nums = "，".join(f"{k}={v}" for k, v in numbers.items())
    resume_line = ""
    if o.get("resume_of"):
        resume_line = (f"\n（本单为 {o['resume_of']} 的一句话复活增量，"
                       f"证据链见其交付包）")
    card = (
        f"# 结论卡 — {order_id}\n\n"
        f"**{results.get('verdict', 'settled')}**\n\n"
        f"- 关键数字：{nums or '(见 evidence.json)'}\n"
        f"- 证据：{len(events)} 条事件，链头 "
        f"`{evidence['chain_head']}…`（evidence.json 可逐条对账）\n"
        f"- 复现：见 reproduce.txt（离线确定性，无需信任我们）"
        f"{resume_line}\n")
    (out / "conclusion.md").write_text(card, encoding="utf-8")

    # -- manifest: file list + the size door ---------------------------
    # self-including: MANIFEST.json lists its own byte size too, so
    # the envelope is part of the sealed package (iterate to a fixed
    # point — the digit count of its own size converges in 2 rounds)
    files = {}
    for p in sorted(out.iterdir()):
        if p.is_file() and p.name != "MANIFEST.json":
            files[p.name] = len(p.read_bytes())
    manifest = {"order_id": order_id, "generated_at": time.time(),
                "files": files, "total_bytes": 0,
                "size_door_bytes": size_door, "needs_split": False}
    for _ in range(3):
        files["MANIFEST.json"] = len(
            json.dumps(manifest, ensure_ascii=False, indent=1)
            .encode("utf-8"))
        total = sum(files.values())
        manifest["total_bytes"] = total
        manifest["needs_split"] = total > size_door
        if manifest["needs_split"]:
            biggest = max(files, key=files.get)
            manifest["split_suggestion"] = (
                f"包 {total} B 超过门 {size_door} B；最大文件 {biggest} "
                f"({files[biggest]} B) 建议按事件分段导出，需人工拆分")
    (out / "MANIFEST.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1),
        encoding="utf-8")
    # self-consistency: the recorded own-size must equal the bytes on
    # disk (digit-count jumps can shift serialization; settle them)
    for _ in range(5):
        actual = len((out / "MANIFEST.json").read_bytes())
        if manifest["files"]["MANIFEST.json"] == actual:
            break
        manifest["files"]["MANIFEST.json"] = actual
        manifest["total_bytes"] = sum(manifest["files"].values())
        manifest["needs_split"] = (manifest["total_bytes"] > size_door)
        (out / "MANIFEST.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=1),
            encoding="utf-8")
    return manifest


def verify(package: Path, root: Path) -> dict[str, Any]:
    """Re-read the package against the live ledger. Three checks:
    (1) every packaged event hash-matches the replayed chain;
    (2) every card number exists in the ledger's settle event;
    (3) the manifest's own file list still matches the bytes on disk."""
    package = Path(package)
    ev = json.loads((package / "evidence.json").read_text("utf-8"))
    order_id = ev["order_id"]
    book = OrderBook(Path(root) / "orders.jsonl")   # chain-verified
    live = {json.dumps(x, sort_keys=True, ensure_ascii=False):
            x for x in _events_of(book, order_id)}
    for packaged in ev["events"]:
        key = json.dumps(packaged, sort_keys=True, ensure_ascii=False)
        if key not in live:
            raise OrderError(
                f"verify FAIL: packaged event (ts={packaged.get('ts')}) "
                f"not in live ledger — the package and the ledger "
                f"disagree")
    o = book.orders[order_id]
    for k, src in ev["number_sources"].items():
        if (o["results"] or {}).get(k) != src["value"]:
            raise OrderError(
                f"verify FAIL: card number {k}={src['value']} absent "
                f"from the ledger's settle event — numbers must come "
                f"from the ledger, not from the copy")
    man = json.loads((package / "MANIFEST.json").read_text("utf-8"))
    for name, size in man["files"].items():
        actual = len((package / name).read_bytes())
        if actual != size:
            raise OrderError(
                f"verify FAIL: {name} is {actual} B, manifest says "
                f"{size} B — the package was edited after sealing")
    return {"order_id": order_id, "events_verified": len(ev["events"]),
            "numbers_verified": len(ev["number_sources"]),
            "total_bytes": man["total_bytes"]}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="package a settled order as a self-proving "
                    "deliverable (PLAN2 #8 first half)")
    ap.add_argument("--root", default="work")
    ap.add_argument("--order", default="")
    ap.add_argument("--out", default="")
    ap.add_argument("--verify", default="",
                    help="verify an existing package against --root")
    a = ap.parse_args(argv)
    if a.verify:
        res = verify(Path(a.verify), Path(a.root))
        print(f"[deliver] verify OK: {res['order_id']} — "
              f"{res['events_verified']} events, "
              f"{res['numbers_verified']} numbers, "
              f"{res['total_bytes']} B, all ledger-matched")
        return 0
    if not a.order:
        ap.error("--order is required (or --verify)")
    out = Path(a.out) if a.out else Path(f"deliver/{a.order}")
    man = build(Path(a.root), a.order, out)
    tag = " | NEEDS SPLIT (size door)" if man["needs_split"] else ""
    print(f"[deliver] {a.order} → {out} "
          f"({man['total_bytes']} B, {man['files']}){tag}")
    print(f"[deliver] verify with: python -m qsa.deliver "
          f"--verify {out} --root {a.root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
