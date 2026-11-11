#!/usr/bin/env python3
"""Offline lifecycle demo — thin entry point; the implementation lives in
qsa.demo so it stays importable and testable."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from qsa.demo import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
