"""Quant Super Agent — evidence plane (v0.2).

Machine-checkable research evidence: hypothesis cards, experiment cards,
immutable data snapshots, a mechanical admission gate, and a deterministic
forge emulation so the full `order -> cards -> gate -> PR` lifecycle runs
offline in seconds.

Zero third-party dependencies: Python >= 3.10 standard library only.
"""

__version__ = "0.2.0"

from .admission import evaluate  # noqa: F401  (re-exported for convenience)
