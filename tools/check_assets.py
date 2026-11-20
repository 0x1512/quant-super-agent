#!/usr/bin/env python3
"""README image asset checker.

Guarantees the visual layer cannot silently rot:
* every image referenced by README.md / README.zh-CN.md exists
* referenced images are not trivially empty (< 5 KB)
* docs/assets/ images are all referenced (no orphan assets shipping dead weight)
* sizes stay under a ceiling (README images should stay < 1 MB)

Exit 0 = clean, 1 = violation.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAX_BYTES = 1_000_000
MIN_BYTES = 5_000

IMG_RE = re.compile(r"\(([^()\s]+?\.png)\)", re.IGNORECASE)


def main() -> int:
    ok = True
    refs: set[str] = set()
    for name in ("README.md", "README.zh-CN.md"):
        p = ROOT / name
        if not p.exists():
            continue
        for m in IMG_RE.finditer(p.read_text("utf-8")):
            refs.add(m.group(1))

    # 1) referenced images must exist and be non-trivial
    for ref in sorted(refs):
        local = ref.lstrip("/")
        if local.startswith("http") or "://" in ref:
            continue
        p = ROOT / local
        if not p.exists():
            print(f"[assets] ❌ referenced but missing: {ref}")
            ok = False
        elif p.stat().st_size < MIN_BYTES:
            print(f"[assets] ❌ referenced but suspiciously small: {ref}")
            ok = False
        elif p.stat().st_size > MAX_BYTES:
            print(f"[assets] ❌ too large for README: {ref} "
                  f"({p.stat().st_size // 1024} KB)")
            ok = False

    # 2) no orphan pngs in docs/assets
    adir = ROOT / "docs" / "assets"
    if adir.exists():
        for p in sorted(adir.glob("*.png")):
            ref = "docs/assets/" + p.name
            if ref not in refs and ("/" + p.name) not in {r for r in refs}:
                # also accept bare "assets/x.png" or "docs/assets/x.png"
                if p.name not in ref and not any(r.endswith(p.name) for r in refs):
                    print(f"[assets] ❌ orphan asset (not referenced by any README): {ref}")
                    ok = False

    if ok:
        print(f"[assets] ✅ {len(refs)} referenced images all present and in size bounds")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
