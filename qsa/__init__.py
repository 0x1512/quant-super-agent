"""Quant Super Agent — roles + adversarial review (v0.4).

Machine-checkable research evidence: hypothesis cards, experiment cards,
immutable data snapshots, a mechanical admission gate, a deterministic
forge emulation so the full `order -> cards -> gate -> PR` lifecycle runs
offline in seconds, and (v0.3) a gated research loop: experiment registry,
multiple-testing deflation, sandboxed LLM factor mining under budget, and
real-data ingestion. v0.4 adds ablatable quant roles and a bull/bear
adversarial review gate before admission.

Zero third-party dependencies: Python >= 3.10 standard library only.
"""

# Versioning policy (decided v1.3): new capability planes are rare; all
# ongoing R&D ships as patch releases under the current minor line
# (v1.3.0 -> v1.3.1 -> ...). The next release is v1.3.1.
__version__ = "1.4.0"

from .admission import evaluate  # noqa: F401  (re-exported for convenience)
from . import checkpoint  # noqa: F401  (SUPERAGENT_PLAN #2: --resume)
