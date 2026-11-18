"""S9 live: fast lane -> funnel -> gauntlet, the whole chain fired.

The story this script runs mechanically (reproduce with
``python examples/run_gauntlet_live.py``):

1. FAST LANE — the 24 public-literature factors on the first 300
   days; survivors settle (oos_ic > 0.03, cheap triage);
2. FUNNEL (S1) — every settled survivor auto-promotes to a gauntlet
   order with the stage-2 criteria FROZEN at promotion;
3. GAUNTLET (S6 recheck + S9 walk-forward) — each gauntlet order
   runs on the FULL sample: the frozen stage-2 admission rechecked,
   then the rolling decay trigger / block half-life / consistency
   check; the order settles with a verdict that names its stage.

Expected on the pinned fixture (Loop 0's lesson): most/all fast-lane
survivors die at the stage-2 recheck — short-window survivors are
triage artefacts. That death, executed by orders through the whole
chain, IS the demo: the conveyor now ends in a verdict, not a pipe.
"""
import json
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from qsa import factorzoo, snapshot                # noqa: E402
from qsa.funnel import promote                     # noqa: E402
from qsa.ingest import ingest_csv                  # noqa: E402
from qsa.orders import OrderBook                   # noqa: E402
from qsa.walkforward import run_gauntlet           # noqa: E402

FIXTURE = ROOT / "examples" / "data"
OUT = ROOT / "docs" / "loops" / "gauntlet_live.json"


def main() -> int:
    t0 = time.time()
    with tempfile.TemporaryDirectory(prefix="g-snap-") as td:
        snap = Path(td) / "snap"
        ingest_csv(FIXTURE / "ashare_top300_main.csv", snap,
                   volume_col="volume", open_col="open",
                   snapshot_id="gauntlet-live",
                   meta_dir=FIXTURE / "replication_meta")
        closes = snapshot.load_closes(snap)
        opens = snapshot.load_opens(snap)
        volumes = snapshot.load_volumes(snap)
        full = {"closes": closes, "opens": opens, "volumes": volumes,
                "dates": sorted({d for r in closes.values()
                                 for d in r})}
        keep = set(full["dates"][:300])

        def cut(panel):
            return {tk: {d: v for d, v in row.items() if d in keep}
                    for tk, row in panel.items()}
        fast = {"closes": cut(closes), "opens": cut(opens),
                "volumes": cut(volumes), "dates": full["dates"][:300]}

        # -- 1. fast lane ------------------------------------------------
        catalog = factorzoo.build_catalog()
        book = OrderBook(Path(td) / "orders.jsonl")
        survivors = []
        for spec in catalog:
            row = factorzoo.evaluate_factor(spec, fast)
            params = {"factor": spec["id"], "thresh": 0.03,
                      "universe": "top300"}
            oid = book.create(
                f"{spec['id']} carries OOS rank signal on top-300",
                params, origin="machine")
            book.admit(oid, params)
            book.enqueue(oid)
            book.start(oid)
            if (row.get("oos_ic") or -1) > 0.03:
                book.settle(oid, {k: row.get(k) for k in
                                  ("ic_mean", "icir", "oos_ic",
                                   "train_ic", "n_months")}
                            | {"verdict": "survivor (fast lane)"})
                survivors.append((oid, spec))
            else:
                book.refuse(oid, "oos IC below floor in fast window")
        print(f"[gauntlet-live] fast lane: {len(survivors)} settled "
              f"survivors / {len(catalog)} refused-or-dead")

        # -- 2. funnel: promote each survivor ---------------------------
        promoted = [(promote(book, oid), spec)
                    for oid, spec in survivors]
        print(f"[gauntlet-live] funnel: {len(promoted)} gauntlet "
              f"orders created+admitted+queued (criteria frozen)")

        # -- 3. gauntlet: full sample, wired checks ---------------------
        tally = {"stage2_recheck_fail": 0, "walkforward_fail": 0,
                 "wired_chain_pass": 0, "walkforward_inconclusive": 0}
        first_deaths = []
        for gid, spec in promoted:
            res = run_gauntlet(book, gid, spec, full)
            if res["gauntlet_passed"]:
                tally["wired_chain_pass"] += 1
            elif "stage-2 recheck" in res["verdict"]:
                tally["stage2_recheck_fail"] += 1
            else:
                tally["walkforward_fail"] += 1
                wf = res.get("walkforward", {})
                if wf.get("verdict") == "inconclusive":
                    tally["walkforward_inconclusive"] += 1
                trig = (wf.get("detail") or {}).get(
                    "decay_triggers") or []
                if trig:
                    first_deaths.append(
                        {"cell": spec["id"],
                         "first_dead_window":
                         f"{trig[0]['start_date']}.."
                         f"{trig[0]['end_date']}"})
        wall = time.time() - t0
        print(f"[gauntlet-live] gauntlet: {tally}")
        for d in first_deaths[:5]:
            print(f"[gauntlet-live]   decay caught: {d['cell']} "
                  f"locally dead {d['first_dead_window']}")
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps({
            "ran_at": time.time(), "wall_seconds": round(wall, 1),
            "fast_lane_survivors": len(survivors),
            "promoted": len(promoted),
            "gauntlet": tally,
            "decay_first_windows": first_deaths,
            "settled_orders": len(book.by_state("settled")),
        }, ensure_ascii=False, indent=1, sort_keys=True),
            encoding="utf-8")
        print(f"[gauntlet-live] sealed -> {OUT} ({wall:.0f}s wall)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
