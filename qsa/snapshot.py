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
                   plant: dict[str, Any] | None = None,
                   costs: dict[str, Any] | None = None) -> SnapshotInfo:
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
    if len(start) == 8:  # compact YYYYMMDD (manifest format) — accepted, and
        start = f"{start[:4]}-{start[4:6]}-{start[6:]}"  # 3.10 needs dashed
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
    if costs is not None:
        # v0.7 transaction-cost model (TC estimator): per-side bps the engine
        # deducts from the gross spread. Optional and *pinned* — a world whose
        # costs are part of the hypothesis carries them in the fingerprinted
        # manifest, so the gate recomputes net metrics with the same model the
        # admission used. Default worlds (costs=None) omit the block: their
        # manifests stay byte-identical to the historical generator.
        bps = costs.get("per_side_bps")
        if not isinstance(bps, (int, float)) or isinstance(bps, bool) \
                or bps < 0:
            raise ValueError("costs.per_side_bps must be a non-negative number")
        manifest["costs"] = {"per_side_bps": float(bps)}
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


def extend_world(out_dir: Path, base_dir: Path, extension_days: int,
                 *, cache: bool = True) -> SnapshotInfo:
    """Deterministically continue a synthetic world past its ``as_of`` (v0.5).

    Settlement needs data the admission never touched. For synthetic worlds
    the generator is the simulator: rebuilding with ``days + extension_days``
    from the same seed replays the identical draws day by day, so the base
    snapshot is a strict prefix of the extension (asserted byte-for-byte on
    the price rows — a drifted generator fails loudly, it never settles
    silently). Real (ingested) data has no simulator: those worlds settle
    only when new data arrives, never by invention.

    ``cache=True`` reuses an existing extension whose fingerprint matches —
    deterministic worlds rebuild identically, so caching is safe.
    """
    if extension_days <= 0:
        raise ValueError("extension_days must be positive")
    base = fingerprint(base_dir)
    m = base.manifest
    if "seed" not in m:
        raise ValueError(
            f"{base_dir}: not a synthetic world (no generator seed in the "
            f"manifest) — real data settles when new data arrives, not by "
            f"simulating an extension")
    out_dir = Path(out_dir)
    expected_days = m["days"] + extension_days
    p = m.get("plant")
    if p is None:
        plant = None
    elif (isinstance(p, dict) and p.get("effect") == "reversal"
            and isinstance(p.get("strength"), (int, float))):
        plant = {"effect": "reversal", "strength": float(p["strength"])}
    else:
        raise ValueError("manifest plant block is malformed")
    costs = m.get("costs")  # v0.7: the extension must price trades exactly
    if costs is not None and not isinstance(costs, dict):  # like the base world
        raise ValueError("manifest costs block is malformed")
    if cache and (out_dir / "MANIFEST.json").exists():
        try:
            info = fingerprint(out_dir)
            if (info.manifest.get("days") == expected_days
                    and info.manifest.get("seed") == m["seed"]):
                _assert_prefix(base_dir, out_dir)
                return info
        except ValueError:
            pass  # stale cache: rebuild below
    info = build_snapshot(out_dir, seed=m["seed"], tickers=m["tickers"],
                          days=expected_days, start=m["start"], plant=plant,
                          costs=costs)
    _assert_prefix(base_dir, out_dir)
    return info


def _assert_prefix(base_dir: Path, ext_dir: Path) -> None:
    base_rows = (Path(base_dir) / "daily" / "prices.csv").read_text(
        encoding="utf-8").splitlines()
    ext_rows = (Path(ext_dir) / "daily" / "prices.csv").read_text(
        encoding="utf-8").splitlines()
    if len(ext_rows) <= len(base_rows):
        raise ValueError("extension is not a prefix of the base world")
    for i in range(1, len(base_rows)):
        if ext_rows[i] != base_rows[i]:
            raise ValueError(
                f"extension row {i} diverges from the base world at "
                f"{base_rows[i].split(',')[0]} — the generator drifted; "
                f"refusing to settle on a foreign world")


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


def load_volumes(out_dir: Path) -> dict[str, dict[str, float]]:
    """Return {ticker: {date: volume}} — empty when the file has no volume
    column (ingested worlds may omit it; the engine degrades gracefully)."""
    fingerprint(out_dir)  # refuse to load anything that fails recon
    volumes: dict[str, dict[str, float]] = {}
    with (Path(out_dir) / "daily" / "prices.csv").open(encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        if "volume" not in (reader.fieldnames or []):
            return volumes
        for row in reader:
            v = row.get("volume")
            if v is None or v == "":
                continue
            volumes.setdefault(row["ticker"], {})[row["date"]] = float(v)
    return volumes
