"""Resume — SUPERAGENT_PLAN2 #6: one human message revives the mandate.

dsh 001: an ended Ticket keeps its Subscription — one message from the
person revives it under the SAME Mandate, no re-evaluation. Our orders
are hash-chained and terminal states are terminal, so resurrection
here is a DELTA ORDER, not a state rollback:

    settled/refused ORD-A  --(human message)-->  delta ORD-B
         ORD-A gains a `resume` event (stays terminal, cites ORD-B)
         ORD-B's create cites resume_of=ORD-A + the prior-run context

The machine enforces three disciplines a script cannot:

* **the human gate** — only a human revives (`by="human"`); the watch
  loops and the scheduler never resurrect anything on their own
  (不拍板零执行). A live order (drafted..running) does not resume —
  it takes new instructions through the normal channels;
* **classification, not guessing** — the message goes through
  followup's ``parse_instruction``: bar-only ("把门槛收到 0.05") is a
  zero-rescoring re-verdict (rejudge); structural changes (universe /
  window) are a recompute that reuses checkpoints. Unparseable text
  refuses loudly and creates NOTHING;
* **the refusal gate (stricter than dsh, on purpose)** — a refused
  order cannot be revived with the same hypothesis and the same
  params. A refused order also has no results to re-verdict, so a
  bar-only message on it is refused outright: re-trying a rejected
  hypothesis must be an explicit parameter change, our
  multiple-testing discipline.

    python -m qsa.resume --root work --order ORD-xxxx \
        --msg "把门槛收到 0.05" --prev-dir work/offense
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .followup import load_prev, parse_instruction, rejudge
from .orders import OrderBook, OrderError, _hash

TERMINAL = ("settled", "refused")


def _old_params(o: dict[str, Any]) -> dict[str, Any]:
    create_ev = o["history"][0]
    return create_ev.get("params", {})


def resume(book: OrderBook, order_id: str, message: str, *,
           by: str = "human") -> dict[str, Any]:
    """Revive a terminal order as a delta order. Returns a record;
    ``ok=False`` means nothing was written (the machine refused)."""
    o = book.orders.get(order_id)
    if o is None:
        raise OrderError(f"unknown order {order_id}")

    # -- the human gate: machines never resurrect (不拍板零执行) -----
    if by != "human":
        raise OrderError(
            f"{order_id}: resume is a human act — got by={by!r}. The "
            "watch loops and the scheduler may not revive orders.")

    # -- a live order does not resume; it takes new instructions -----
    if o["state"] not in TERMINAL:
        raise OrderError(
            f"{order_id}: state={o['state']} is not terminal — a live "
            "order takes new instructions, it does not need reviving")

    # -- classification, not guessing ---------------------------------
    ins = parse_instruction(message)
    if ins["mode"] == "refuse":
        return {"ok": False, "order_id": order_id, "mode": "refuse",
                "reason": ins["reason"],
                "note": "message parsed to nothing executable — "
                        "no delta order, no ledger event"}

    params_delta = {k: v for k, v in ins.items()
                    if k not in ("mode", "raw")}

    # -- the refusal gate (stricter than dsh, deliberately) ----------
    if o["state"] == "refused":
        if ins["mode"] == "rejudge":
            return {"ok": False, "order_id": order_id, "mode": "rejudge",
                    "reason": "已拒绝的订单没有结果可重判（bar-only "
                              "复活在 refused 单上无意义）——结构性改参后"
                              "再试",
                    "note": "refusal gate: refused orders revive only "
                            "through explicit structural change"}
        new_params = {**_old_params(o), **params_delta}
        same = _hash([o["hypothesis"], new_params]) == \
            _hash([o["hypothesis"], _old_params(o)])
        if same:
            return {"ok": False, "order_id": order_id,
                    "mode": ins["mode"],
                    "reason": "同假设同参数已被拒绝，不能换个说法原样"
                              "重试——请显式改参数",
                    "note": "refusal gate: same (hypothesis, params) "
                            "hash as the refused original"}

    # -- create the delta order + the resume event --------------------
    context = {"prev_state": o["state"], "message": message,
               "mode": ins["mode"], "params_delta": params_delta}
    if o.get("results"):
        context["prev_results_keys"] = sorted(o["results"].keys())
    delta_id = book.create(
        o["hypothesis"], {**_old_params(o), **params_delta},
        priority=o["history"][0].get("priority", 5),
        note=f"resume of {order_id}: {message}",
        origin="human", resume_of=order_id, context=context)
    book.note_resume(order_id, delta_id, message, ins["mode"], by=by)
    return {"ok": True, "order_id": order_id, "delta_id": delta_id,
            "mode": ins["mode"], "params_delta": params_delta}


def execute_rejudge(book: OrderBook, delta_id: str,
                    prev_dir: Path) -> dict[str, Any]:
    """Zero-rescoring verdict for a rejudge delta order: reuse the
    cached leaderboard verbatim, walk the new bar, settle in seconds.
    The delta order must be in drafted state (as resume left it)."""
    o = book.orders.get(delta_id)
    if o is None:
        raise OrderError(f"unknown order {delta_id}")
    if not o.get("resume_of"):
        raise OrderError(f"{delta_id}: not a resume delta order")
    ctx = o.get("context") or {}
    if ctx.get("mode") != "rejudge":
        raise OrderError(
            f"{delta_id}: mode={ctx.get('mode')} — execute_rejudge "
            "is the bar-only path; structural deltas recompute")
    ins = {"mode": "rejudge", "raw": ctx.get("message", ""),
           **(ctx.get("params_delta") or {})}
    prev = load_prev(Path(prev_dir))
    res = rejudge(prev, ins)
    res["resume_of"] = o["resume_of"]
    params = o["history"][0]["params"]
    book.admit(delta_id, params)     # freeze the delta params
    book.start(delta_id, params)
    book.settle(delta_id, res)       # rows_rescored == 0, by contract
    return res


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="revive a terminal order with one human message "
                    "(PLAN2 #6)")
    ap.add_argument("--root", default="work")
    ap.add_argument("--order", required=True)
    ap.add_argument("--msg", required=True)
    ap.add_argument("--by", default="human")
    ap.add_argument("--prev-dir", default="",
                    help="prior run dir (leaderboard.json) — a rejudge "
                         "delta settles immediately, zero rescoring")
    a = ap.parse_args(argv)
    book = OrderBook(Path(a.root) / "orders.jsonl")
    rec = resume(book, a.order, a.msg, by=a.by)
    if not rec.get("ok"):
        print(f"[resume] 拒绝：{rec['reason']}")
        return 1
    print(f"[resume] {a.order} → delta {rec['delta_id']} "
          f"(mode={rec['mode']}, params_delta={rec['params_delta']})")
    if a.prev_dir and rec["mode"] == "rejudge":
        res = execute_rejudge(book, rec["delta_id"], Path(a.prev_dir))
        print(f"[resume] 零重算出新 verdict：thresh="
              f"{res.get('new_thresh')}，winners={res.get('n_winners')}"
              f"（rows_rescored={res.get('rows_rescored')}）")
    print("[resume] 链已入账：旧单保持终态，复活链可审计 "
          f"({json.dumps(rec['params_delta'], ensure_ascii=False)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
