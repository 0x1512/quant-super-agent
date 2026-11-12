"""Quant Super Agent — research loop (v0.3).

Machine-checkable research evidence: hypothesis cards, experiment cards,
immutable data snapshots, a mechanical admission gate, a deterministic
forge emulation so the full `order -> cards -> gate -> PR` lifecycle runs
offline in seconds, and (v0.3) a gated research loop: experiment registry,
multiple-testing deflation, sandboxed LLM factor mining under budget, and
real-data ingestion.

Zero third-party dependencies: Python >= 3.10 standard library only.
"""

__version__ = "0.3.0"

from .admission import evaluate  # noqa: F401  (re-exported for convenience)
