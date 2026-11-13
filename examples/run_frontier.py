#!/usr/bin/env python3
"""α-frontier + budget envelope — the P̂ estimator (v0.7).

P̂ (the probability that an admitted discovery is true) is not observable in
production — the truth is precisely what is missing. It *is* observable in
worlds where the truth was planted. This script measures, on a planted/noise
world pair:

* **frontier** — at a grid of admission floors z: power (share of planted
  worlds whose reversal factor clears z) vs false-positive rate (share of
  noise worlds). P̂ = power / (power + fpr) at 50/50 prevalence;
* **envelope** — the breadth/verification tradeoff the budget equation
  predicts: at N cumulative trials the ledger's Bonferroni floor z(N)
  suppresses marginal discoveries while sqrt(N) breadth grows. The envelope
  value discovery(N)·sqrt(N) peaks somewhere; that peak is the operating
  point. No term is asserted — every number below is measured.

Deterministic: same inputs -> byte-identical outputs.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from qsa import engine  # noqa: E402
from qsa.budget import envelope, frontier  # noqa: E402
from qsa.sandbox import run_factor  # noqa: E402
from qsa.snapshot import build_snapshot  # noqa: E402

# planted: the reversal effect at a strength ladder, so t-stats spread
# across the floor grid (0.05 barely visible, 0.20 unmistakable)
PLANTED = [(s, seed) for s in (0.05, 0.08, 0.10, 0.12, 0.15, 0.20)
           for seed in (11, 22, 33, 55, 66, 77)]
NOISE_SEEDS = tuple(range(1, 25))
FLOORS = [1.5, 2.0, 2.24, 2.5, 2.75, 3.0, 3.25, 3.5]
NS = list(range(1, 25)) + [32, 48, 64, 96, 128, 192, 256, 384, 512, 1024,
                            2048, 4096, 8192, 16384, 32768, 65536, 131072,
                            262144, 524288, 1048576]
# envelope pools are HOMOGENEOUS in strength: the operating point N* is a
# property of the effect pool (weak effects die at small N*, strong ones
# survive longer) — mixing strengths would blur the peak into the strongest
# tail and the curve would never turn over inside any honest grid
ENVELOPE_STRENGTHS = (0.08, 0.15)

F_REV = '''def factor(closes, tickers, dates, i):
    if i < 1:
        return {}
    out = {}
    t = dates[i]
    lag = dates[i - 1]
    for tk in tickers:
        row = closes[tk]
        a = row.get(t)
        b = row.get(lag)
        if a is None or b is None or b == 0:
            continue
        out[tk] = -(a / b - 1.0)
    return out
'''


def tstat_for(world: Path) -> float:
    frame = engine.load_frame(world)
    signal = run_factor(F_REV, frame.closes, frame.tickers, frame.dates,
                        frame.volumes)
    return engine.evaluate_signal(frame, signal)["rankic_tstat"]


def main() -> int:
    out_dir = Path(__file__).resolve().parents[1] / "work" / "frontier"
    out_dir.mkdir(parents=True, exist_ok=True)
    worlds_dir = out_dir / "worlds"
    worlds_dir.mkdir(exist_ok=True)

    t_planted, t_noise = [], []
    for strength, seed in PLANTED:
        d = worlds_dir / f"planted-s{strength}-seed{seed}"
        if not d.exists():
            build_snapshot(d, seed=seed, tickers=12, days=90,
                           plant={"effect": "reversal",
                                  "strength": strength})
        t_planted.append(tstat_for(d))
    for seed in NOISE_SEEDS:
        d = worlds_dir / f"noise-{seed}"
        if not d.exists():
            build_snapshot(d, seed=seed, tickers=12, days=90)
        t_noise.append(tstat_for(d))

    t_planted = [round(t, 6) for t in t_planted]
    t_noise = [round(t, 6) for t in t_noise]
    f_rows = frontier(t_planted, t_noise, FLOORS)
    envelopes = {}
    peaks = {}
    for s in ENVELOPE_STRENGTHS:
        rows_s = [t for (strength, seed), t in zip(PLANTED, t_planted)
                  if strength == s]
        envelopes[f"{s}"] = envelope(rows_s, t_noise, NS)
        peaks[f"{s}"] = max(envelopes[f"{s}"], key=lambda r: r["envelope"])

    lines = [
        "## α-frontier (P̂ estimator; truth planted, 50/50 prevalence)",
        "",
        "| floor z | power (planted) | FPR (noise) | P̂ |",
        "|---|---|---|---|",
    ]
    for r in f_rows:
        lines.append(f"| {r['floor']:.2f} | {r['power']:.4f} | "
                     f"{r['fpr']:.4f} | {r['p_hat']:.4f} |")
    for s in ENVELOPE_STRENGTHS:
        lines += ["",
                  f"## budget envelope, effect strength {s} "
                  f"(discovery·sqrt(N) vs deflation)", "",
                  "| N | floor z(N) | discovery | FPR | P̂ | envelope |",
                  "|---|---|---|---|---|---|"]
        for r in envelopes[f"{s}"]:
            lines.append(f"| {r['N']} | {r['floor']:.4f} | "
                         f"{r['discovery']:.4f} | {r['fpr']:.4f} | "
                         f"{r['p_hat']:.4f} | {r['envelope']:.4f} |")
        pk = peaks[f"{s}"]
        lines += ["",
                  f"envelope peak at N*={pk['N']} (floor {pk['floor']:.4f}, "
                  f"discovery {pk['discovery']:.4f}, envelope "
                  f"{pk['envelope']:.4f}) — the operating point for this "
                  f"effect strength"]
    md = "\n".join(lines) + "\n"
    (out_dir / "frontier.md").write_text(md, encoding="utf-8")
    (out_dir / "frontier.json").write_text(
        json.dumps({"t_planted": t_planted, "t_noise": t_noise,
                    "frontier": f_rows, "envelopes": envelopes,
                    "peaks": peaks}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")

    print(f"frontier: power {f_rows[0]['power']:.3f}->{f_rows[-1]['power']:.3f}, "
          f"p_hat {f_rows[0]['p_hat']:.3f}->{f_rows[-1]['p_hat']:.3f} "
          f"over floors {FLOORS[0]}..{FLOORS[-1]}")
    for s in ENVELOPE_STRENGTHS:
        pk = peaks[f"{s}"]
        print(f"envelope s={s}: peak N*={pk['N']} at value "
              f"{pk['envelope']:.4f}")
    print(f"[+] wrote {out_dir / 'frontier.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
