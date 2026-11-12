"""Immutable data snapshots — toy dataset, content addressing, fingerprints.

The snapshot is **synthetic** (seeded random walk: no real market data, ever).
What makes it a snapshot rather than "a csv" is the discipline:

* ``MANIFEST.json`` records the generator parameters, the row count, and the
  sha256 of every data file;
* the snapshot hash that cards cite is the sha256 of the canonical MANIFEST
  itself, so any byte of any file (or of the manifest) changing breaks the
  fingerprint (FIB class 4);
* the manifest carries ``start`` and ``as_of`` bounds, which the gate uses for
  window-alignment / no-lookahead checks (FIB classes 3, 15).

Everything is deterministic: the same seed builds byte-identical files.
"""
from __future__ import annotations

import csv
import hashlib
import json
import random
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any


def canonical_json(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


@dataclass(frozen=True)
class SnapshotInfo:
    dir: Path
    manifest_hash: str
    manifest: dict


def _business_days(start: str, days: int) -> list[str]:
    d = date.fromisoformat(start)
    out: list[str] = []
    while len(out) < days:
        if d.weekday() < 5:
            out.append(d.isoformat().replace("-", ""))
        d += timedelta(days=1)
    return out


def build_snapshot(out_dir: Path, *, seed: int = 42, tickers: int = 12,
                   days: int = 90, start: str = "2024-01-02",
                   plant: dict[str, Any] | None = None) -> SnapshotInfo:
    """Generate the toy snapshot deterministically. Pure synthetic data.

    ``plant`` optionally injects a *known* cross-sectional effect so that
    discovery is measurable in ablations: ``{"effect": "reversal", "strength":
    s}`` makes each day's log-return carry ``-s * z`` of the previous day's
    cross-sectionally standardized return (a real 1-day reversal that a
    ``-(prev return)`` factor can discover). ``plant=None`` (default) is
    byte-identical to the historical generator; planted manifests record the
    plant parameters so the fingerprint proves which world the data came from.
    """
    if plant is not None and plant.get("effect") != "reversal":
        raise ValueError(f"unknown plant effect {plant.get('effect')!r}")
    out_dir = Path(out_dir)
    (out_dir / "daily").mkdir(parents=True, exist_ok=True)

    names = [f"T{i:03d}" for i in range(1, tickers + 1)]
    dates = _business_days(start, days)
    rng = random.Random(seed)
    drift = {t: rng.gauss(0.0002, 0.0003) for t in names}

    strength = float(plant["strength"]) if plant else 0.0
    prev_ret: dict[str, float] | None = None

    rows: list[tuple[str, str, str, str]] = []
    closes: dict[str, float] = {t: 100.0 for t in names}
    for d in dates:
        if prev_ret is not None and strength:
            mean_r = sum(prev_ret.values()) / tickers
            sd_r = (sum((v - mean_r) ** 2 for v in prev_ret.values())
                    / tickers) ** 0.5 or 1e-12
            z = {t: (prev_ret[t] - mean_r) / sd_r for t in names}
        else:
            z = None
        today_ret: dict[str, float] = {}
        for t in names:
            # call order (gauss then uniform, per ticker) matches the
            # historical generator exactly when strength == 0
            shock = rng.gauss(0.0, 0.012)
            logret = drift[t] + shock
            if z is not None:
                logret -= strength * 0.012 * z[t]
            today_ret[t] = logret
            closes[t] *= pow(2.718281828459045, logret)
            volume = int(rng.uniform(1e5, 5e6))
            rows.append((d, t, f"{closes[t]:.4f}", str(volume)))
        prev_ret = today_ret

    csv_path = out_dir / "daily" / "prices.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        writer.writerow(["date", "ticker", "close", "volume"])
        writer.writerows(rows)

    manifest = {
        "format": 1,
        "snapshot_id": f"toy-{seed}-{tickers}x{days}",
        "generator": "qsa.snapshot (synthetic random walk; not market data)",
        "seed": seed,
        "tickers": tickers,
        "days": days,
        "start": dates[0],
        "as_of": dates[-1],
        "rows": len(rows),
        "files": {"daily/prices.csv": sha256_file(csv_path)},
    }
    if plant is not None:
        manifest["plant"] = {"effect": "reversal",
                             "strength": float(plant["strength"])}
    (out_dir / "MANIFEST.json").write_bytes(canonical_json(manifest) + b"\n")
    return fingerprint(out_dir)


def fingerprint(out_dir: Path) -> SnapshotInfo:
    """Recompute the snapshot fingerprint and self-check the manifest.

    Raises ValueError if the data files no longer match the manifest — the
    reconciliation stub for v0.2 (deeper reconciliation lands with real
    sources in a later version).
    """
    out_dir = Path(out_dir)
    manifest_path = out_dir / "MANIFEST.json"
    if not manifest_path.exists():
        raise ValueError(f"{out_dir}: no MANIFEST.json — not a snapshot")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for rel, claimed in manifest.get("files", {}).items():
        f = out_dir / rel
        if not f.exists():
            raise ValueError(f"manifest lists {rel} but the file is missing")
        actual = sha256_file(f)
        if actual != claimed:
            raise ValueError(
                f"snapshot tampered: {rel} sha256 {actual[:12]}… != manifest "
                f"{claimed[:12]}…")
    return SnapshotInfo(out_dir, sha256_bytes(canonical_json(manifest)), manifest)


def load_closes(out_dir: Path) -> dict[str, dict[str, float]]:
    """Return {ticker: {date: close}} from the snapshot's price file."""
    snap = fingerprint(out_dir)  # refuse to load anything that fails recon
    closes: dict[str, dict[str, float]] = {}
    with (Path(out_dir) / "daily" / "prices.csv").open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            closes.setdefault(row["ticker"], {})[row["date"]] = float(row["close"])
    if not closes:
        raise ValueError(f"{snap.dir}: snapshot has no rows")
    return closes
