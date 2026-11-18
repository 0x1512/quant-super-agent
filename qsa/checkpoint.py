"""Checkpoint — SUPERAGENT_PLAN #2 (dsh's persistence, provable).

Per-job results land on disk as they complete; ``--resume`` reloads
them by (stream, job-key) and only the missing jobs run. Because every
job is a pure function of (descriptor, inputs) — the dispatcher's
load-bearing contract — a resumed run is byte-identical to an
uninterrupted one, and that is testable, not aspirational.

Layout: ``<dir>/<kind>/<sha1(key)[:16]>.json`` with
``{"key", "fingerprint", "row"}``. The fingerprint (the run's plan
fingerprint) guards against resuming a cache that belongs to a
different plan.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path


def _key_str(job: tuple) -> str:
    return json.dumps(job, ensure_ascii=False, sort_keys=False,
                      default=str)


class Checkpoint:
    def __init__(self, dirpath: "os.PathLike[str] | str",
                 fingerprint: str) -> None:
        self.dir = Path(dirpath)
        self.fp = fingerprint
        self.hits = 0
        self.misses = 0

    def _path(self, kind: str, job: tuple) -> Path:
        h = hashlib.sha1(_key_str(job).encode()).hexdigest()[:16]
        return self.dir / kind / f"{h}.json"

    def get(self, kind: str, job: tuple):
        p = self._path(kind, job)
        if not p.exists():
            self.misses += 1
            return None
        try:
            rec = json.loads(p.read_text("utf-8"))
        except (OSError, json.JSONDecodeError):
            self.misses += 1            # torn write (crash mid-put)
            return None
        if rec.get("fingerprint") != self.fp:
            self.misses += 1            # a different plan's cache
            return None
        self.hits += 1
        return rec.get("row")

    def put(self, kind: str, job: tuple, row) -> None:
        p = self._path(kind, job)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(
            {"key": _key_str(job), "fingerprint": self.fp, "row": row},
            ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, p)

    def stats(self) -> dict:
        return {"hits": self.hits, "misses": self.misses,
                "fingerprint": self.fp}
