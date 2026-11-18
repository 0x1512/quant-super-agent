"""Funnel — ALPHA_PLAN S1: the conveyor from fast lane to gauntlet.

The 2026-11-17 diagnosis: a fast-lane settle is a dead end. The
verdict literally says "gauntlet still required" and nothing in the
system carries the survivor there — the funnel was a pipe with its
last section missing. This module is that section, mechanical:

* ``promote()`` — a settled fast-lane survivor gets a GAUNTLET order
  (same hypothesis, same params, plus the frozen stage-2 admission
  criteria and the full-chain checklist), admitted and enqueued at a
  LOW priority: the gauntlet runs when slots are idle, never in front
  of fresh research;
* **double-promotion is refused** — a settled order promotes exactly
  once (the ledger is scanned for an existing ``promoted_from``), so
  the funnel cannot mint duplicate gauntlet work off one survivor;
* **only fast-lane survivors promote** — refused orders, live orders
  and non-fast-lane settles are refused with the named reason.

What the gauntlet order CARRIES (and what is still honestly unwired):
walk-forward OOS, FIB budget accounting and portfolio-increment
settlement (ALPHA_PLAN S9/S10) are listed in the params as the
contract; the machinery for the last two lands with those programs.

    from qsa.funnel import promote
    promote(book, "ORD-xxxx")            # -> gauntlet order id
"""
from __future__ import annotations

from typing import Any

from .admission import STAGE2_ADMISSION
from .orders import OrderBook, OrderError

GAUNTLET_CHECKS = ["stage2_composite", "walk_forward_oos",
                   "fib_budget_accounting", "portfolio_increment"]


def promoted_from(book: OrderBook, order_id: str) -> str | None:
    """The gauntlet order this settled order already promoted (if any)."""
    for o in book.orders.values():
        if (o["history"][0].get("params") or {}).get(
                "promoted_from") == order_id:
            return o["order_id"]
    return None


def promote(book: OrderBook, order_id: str, priority: int = 7) -> str:
    """Create + admit + enqueue the gauntlet order for a fast-lane
    survivor. Priority defaults low (7): idle-slot work, never in
    front of fresh research. Returns the gauntlet order id."""
    o = book.orders.get(order_id)
    if o is None:
        raise OrderError(f"unknown order {order_id}")
    if o["state"] != "settled":
        raise OrderError(
            f"{order_id}: state={o['state']} — only settled orders "
            "promote; the funnel starts at a verdict, not at a hope")
    verdict = (o.get("results") or {}).get("verdict", "")
    if "fast lane" not in verdict:
        raise OrderError(
            f"{order_id}: verdict={verdict!r} — only fast-lane "
            "survivors promote (a full-chain verdict IS the gauntlet)")
    dup = promoted_from(book, order_id)
    if dup is not None:
        raise OrderError(
            f"{order_id}: already promoted as {dup} — the funnel "
            f"promotes each survivor exactly once")

    base = o["history"][0].get("params") or {}
    params: dict[str, Any] = {**base,
                              "stage": 2,
                              "admission": STAGE2_ADMISSION,
                              "gauntlet_checks": GAUNTLET_CHECKS,
                              "promoted_from": order_id,
                              "unwired": ["walk_forward_oos",
                                          "fib_budget_accounting",
                                          "portfolio_increment"]}
    gid = book.create(
        o["hypothesis"], params, priority=priority,
        note=f"funnel: fast-lane survivor {order_id} -> gauntlet "
             f"(stage-2 criteria frozen at promotion)",
        origin="machine")
    book.admit(gid, params)          # freeze — promotion has teeth
    book.enqueue(gid)                # idle-slot work
    return gid
