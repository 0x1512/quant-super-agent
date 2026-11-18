#!/usr/bin/env python3
"""Test-count badge writer (5th correction, presentation #6).

Counts the deterministic stdlib unittest suite (no pytest needed, same
discovery CI uses) and writes a shields.io endpoint JSON. The badge in
the README points at this file, so the count stays fresh without anyone
editing the storefront: CI refreshes the JSON, the README never moves.

    python tools/write_badge.py [docs/badge/tests.json]
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def count_tests() -> int:
    # script mode puts tools/ (not the repo root) on sys.path[0], so test
    # modules that `import qsa` fail to load and discovery counts import
    # placeholders instead of tests — inject the root explicitly.
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    loader = unittest.TestLoader()
    suite = loader.discover(str(ROOT / "tests"))
    return suite.countTestCases()


def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 \
        else ROOT / "docs" / "badge" / "tests.json"
    n = count_tests()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "schemaVersion": 1,
        "label": "tests",
        "message": f"{n} passed",
        "color": "brightgreen",
    }) + "\n", encoding="utf-8")
    where = out.relative_to(ROOT) if out.is_relative_to(ROOT) else out
    print(f"[badge] {where}: {n} tests")
    return 0


if __name__ == "__main__":
    sys.exit(main())
