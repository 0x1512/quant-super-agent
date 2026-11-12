"""User-data ingestion — turn your own price CSV into a legal snapshot.

Local-first by design: the file never leaves your machine; the tool only
adds the discipline (canonical format, strict validation, MANIFEST with
content hashes) that the snapshot fingerprint and the verify gate require.
Accepts a CSV with columns date, ticker, close (volume optional; ISO dates
or YYYYMMDD; extra columns are ignored). Everything the factory does on a
synthetic snapshot works unchanged on yours.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path
from typing import Any

from .snapshot import SnapshotInfo, canonical_json, fingerprint, sha256_file


def _norm_date(raw: str, where: str) -> str:
    s = raw.strip()
    for fmt in ("%Y-%m-%d", "%Y%m%d"):
        try:
            from datetime import datetime
            return datetime.strptime(s, fmt).strftime("%Y%m%d")
        except ValueError:
            continue
    raise ValueError(f"{where}: date {raw!r} is neither YYYY-MM-DD nor YYYYMMDD")


def _num(raw: str, where: str) -> float:
    try:
        return float(raw)
    except (TypeError, ValueError):
        raise ValueError(f"{where}: {raw!r} is not numeric") from None


def ingest_csv(csv_path: Path, out_dir: Path, *, snapshot_id: str | None = None,
               date_col: str = "date", ticker_col: str = "ticker",
               close_col: str = "close", volume_col: str | None = None
               ) -> SnapshotInfo:
    """Validate a user price CSV and materialize a snapshot directory."""
    csv_path, out_dir = Path(csv_path), Path(out_dir)
    with csv_path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        cols = reader.fieldnames or []
        for need in (date_col, ticker_col, close_col):
            if need not in cols:
                raise ValueError(f"CSV must have a '{need}' column (found: {cols})")
        rows: list[tuple[str, str, str, str]] = []
        seen: dict[tuple[str, str], int] = {}
        for n, row in enumerate(reader, start=2):
            where = f"row {n}"
            d = _norm_date(row[date_col], where)
            tk = (row[ticker_col] or "").strip()
            if not tk:
                raise ValueError(f"{where}: empty ticker")
            close = _num(row[close_col], where)
            key = (d, tk)
            if key in seen:
                raise ValueError(f"{where}: duplicate (date, ticker) {key}, "
                                 f"first seen on row {seen[key]}")
            seen[key] = n
            vol = ""
            if volume_col and volume_col in row and (row[volume_col] or "").strip():
                vol = str(int(_num(row[volume_col], where)))
            rows.append((d, tk, format(close, ".10g"), vol))
    if not rows:
        raise ValueError("CSV contains no data rows")
    rows.sort(key=lambda r: (r[0], r[1]))

    (out_dir / "daily").mkdir(parents=True, exist_ok=True)
    prices = out_dir / "daily" / "prices.csv"
    has_vol = any(r[3] for r in rows)
    with prices.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        header = ["date", "ticker", "close"] + (["volume"] if has_vol else [])
        writer.writerow(header)
        for d, tk, close, vol in rows:
            writer.writerow([d, tk, close, vol] if has_vol else [d, tk, close])

    dates = sorted({r[0] for r in rows})
    tickers = sorted({r[1] for r in rows})
    manifest: dict[str, Any] = {
        "format": 1,
        "snapshot_id": snapshot_id or "user-supplied",
        "generator": "qsa.ingest (user-supplied data; never leaves the machine)",
        "seed": None,
        "tickers": len(tickers),
        "days": len(dates),
        "start": dates[0],
        "as_of": dates[-1],
        "rows": len(rows),
        "files": {"daily/prices.csv": sha256_file(prices)},
    }
    (out_dir / "MANIFEST.json").write_bytes(canonical_json(manifest) + b"\n")
    return fingerprint(out_dir)


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 2:
        print("usage: python -m qsa.ingest <prices.csv> <snapshot-dir>")
        return 2
    prices = Path(args[0])
    out_dir = Path(args[1])
    try:
        info = ingest_csv(prices, out_dir)
    except ValueError as exc:
        print(f"ingest rejected: {exc}")
        return 1
    print(f"snapshot ok: {info.manifest['rows']} rows, "
          f"{info.manifest['tickers']} tickers, sha256 {info.manifest_hash}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
