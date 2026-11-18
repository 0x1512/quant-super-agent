"""ALPHA_PLAN S3 — Loop 1 replay (historical, under graveyard v2).

Loop 1 was sealed 2026-11-17 under graveyard v1 (docs/loops/
loop1.json — the sealed SSOT, not overwritten by this replay).
The 2026-11-18 user correction re-sentenced v1's 10 permanent bans
to PARKED (single-implementation fails): replaying the same sweep
today yields the same verdicts but tier=parked, and thin cells are
now RECORDED (v1 kept them only in the seal). This script prints
the replay; pass --write to store it as loop1_replay_v2.json.

    python examples/run_family_loop1.py [--write]
"""
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from qsa import snapshot                      # noqa: E402
from qsa.family import run_family_tree, seal_to_disk  # noqa: E402
from qsa.ingest import ingest_csv             # noqa: E402
from qsa.orders import OrderBook              # noqa: E402

FIXTURE = ROOT / "examples" / "data"
LOOPS = ROOT / "docs" / "loops"


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="loop1r-snap-") as td:
        snap = Path(td) / "snap"
        ingest_csv(FIXTURE / "ashare_top300_main.csv", snap,
                   volume_col="volume", open_col="open",
                   snapshot_id="loop1-replay",
                   meta_dir=FIXTURE / "replication_meta")
        closes = snapshot.load_closes(snap)
        inputs = {"closes": closes,
                  "opens": snapshot.load_opens(snap),
                  "volumes": snapshot.load_volumes(snap),
                  "dates": sorted({d for row in closes.values()
                                   for d in row})}
        # fresh graveyard: the replay must not touch the real ledger
        with tempfile.TemporaryDirectory() as gd:
            book = OrderBook(Path(gd) / "replay_orders.jsonl")
            seal = run_family_tree(
                book, inputs, budget=24,
                graveyard_path=Path(gd) / "graveyard.json")
        print(f"[loop1-replay] gate={seal['gate_version']} "
              f"impl={seal['implementation']}")
        for k in ("tested", "survived_stage2", "graveyard_new_fails",
                  "graveyard_new_bans", "thin_new",
                  "graveyard_savings", "revisit_attempted",
                  "grid_not_generated"):
            print(f"[loop1-replay] {k}: {seal[k]}")
        print(f"[loop1-replay] tiers: {seal['graveyard_tiers']}")
        print("[loop1-replay] note: v1 sealed the same sweep as "
              "10 banned; v2 records them parked (2-implementation "
              "rule) and keeps thin cells in the ledger")
        if "--write" in sys.argv:
            out = seal_to_disk(LOOPS / "loop1_replay_v2.json", seal)
            print(f"[loop1-replay] written -> {out}")


if __name__ == "__main__":
    main()
