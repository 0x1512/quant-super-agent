#!/usr/bin/env python3
"""README storefront policy checker (5th correction, internal #1/#4/#10).

The public README is a STABLE STOREFRONT: capability verbs and commands,
never per-round measurements. This checker makes that rule mechanical:

* LINT — outside the STATUS CARD and outside fenced code blocks, the
  README must not contain compact/ISO dates, 16-hex fingerprints,
  precise seconds, minute counts, volatile candidate/order/winner/test
  counts, or signed 4-decimal IC-style values. Structural constants
  (catalog sizes like "30-factor", panel specs, the 4.0x anchor,
  version tags) are allowed — they are properties of shipped code, not
  of a run.
* SSOT — the STATUS CARD must be byte-identical to what
  ``tools/render_readme.py`` produces from docs/STATUS.json.
* FREEZE — between releases README.md must equal the latest snapshot in
  ``docs/releases/v*/README.md``; a difference is only legal when the
  change was made by a ``docs(readme):`` / ``release:`` / ``ci:``
  commit (see docs/README_POLICY.md).

Exit codes: 0 = storefront clean, 1 = violation (printed), 2 = setup
error (e.g. no snapshot yet).
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
READMES = [ROOT / "README.md", ROOT / "README.zh-CN.md"]
CARD_BEGIN = "<!-- BEGIN STATUS CARD"
CARD_END = "<!-- END STATUS CARD -->"
RELEASES = ROOT / "docs" / "releases"
CONVENTION = re.compile(r"^(docs\(readme\)|release|ci)[:\s]")

FORBIDDEN = [
    (re.compile(r"\b20\d{6}\b"), "compact date (e.g. 20260116)"),
    (re.compile(r"\b20\d{2}-\d{2}-\d{2}\b"), "ISO date"),
    (re.compile(r"\b[0-9a-f]{16}\b"), "16-hex fingerprint"),
    (re.compile(r"\b\d+\.\d+\s*s\b"), "precise seconds"),
    (re.compile(r"\b~?\d+\s*min\b"), "minute count"),
    (re.compile(r"\b\d+(?:\s+\w+){0,2}\s+"
                r"(?:candidates|orders|winners|tests|assertions)\b"),
     "volatile count (candidates/orders/winners/tests)"),
    (re.compile(r"\b\d+\s*(?:[张个项条]\s*)?"
                r"(?:候选|订单|赢家|过线|测试|断言)\b"),
     "volatile count, zh (候选/订单/赢家/测试)"),
    (re.compile(r"[+-]\d\.\d{3,4}\b"), "IC-style signed 4-decimal"),
]


def strip_fences_and_card(text: str) -> str:
    """Lint only prose: fenced examples and the status card are exempt."""
    out, in_fence = [], False
    for line in text.splitlines():
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if CARD_BEGIN in line or CARD_END in line:
            continue
        out.append(line)
    # drop the card body itself (between markers)
    b = text.find(CARD_BEGIN)
    e = text.find(CARD_END)
    body = "" if b == -1 or e == -1 else text[b:e + len(CARD_END)]
    joined = "\n".join(out)
    for ln in body.splitlines():
        joined = joined.replace(ln, "")
    return joined


def lint(text: str) -> list[str]:
    hits = []
    prose = strip_fences_and_card(text)
    for rx, why in FORBIDDEN:
        for m in rx.finditer(prose):
            hits.append(f"{why}: …{prose[max(0, m.start()-30):m.end()+20]!r}…")
    return hits


def head_subject() -> str:
    try:
        return subprocess.run(
            ["git", "log", "-1", "--format=%s"], cwd=ROOT,
            capture_output=True, text=True, check=True).stdout.strip()
    except subprocess.CalledProcessError:
        return ""


def latest_snapshot() -> Path | None:
    if not RELEASES.exists():
        return None
    snaps = sorted(RELEASES.glob("v*/README.md"))
    return snaps[-1] if snaps else None


def freeze_ok(readme: Path) -> tuple[bool, str]:
    snap = latest_snapshot()
    if snap is None:
        return False, "no release snapshot under docs/releases/ — run " \
                      "`make release-readme V=x.y.z` first"
    if readme.read_text("utf-8") == snap.read_text("utf-8"):
        return True, f"frozen: matches {snap.relative_to(ROOT)}"
    subj = head_subject()
    if CONVENTION.match(subj):
        return True, (f"README differs from {snap.relative_to(ROOT)} but "
                      f"the change is conventioned ({subj!r})")
    return False, (f"README differs from {snap.relative_to(ROOT)} without "
                   f"a docs(readme):/release:/ci: commit (HEAD: {subj!r}) "
                   "— the storefront is frozen between releases")


def main() -> int:
    problems = []
    for readme in READMES:
        if not readme.exists():
            continue
        text = readme.read_text("utf-8")
        for h in lint(text):
            problems.append(f"{readme.name}: {h}")
        if CARD_BEGIN not in text:
            problems.append(f"{readme.name}: no STATUS CARD "
                            "(run `make readme-render`)")
    # SSOT: card must match the renderer output
    sys.path.insert(0, str(ROOT / "tools"))
    from render_readme import check as card_check  # noqa: E402
    for readme, lang in [(ROOT / "README.md", "en"),
                         (ROOT / "README.zh-CN.md", "zh")]:
        if readme.exists() and not card_check(readme, lang):
            problems.append(f"{readme.name}: STATUS CARD is stale or "
                            "hand-edited — run `make readme-render`")
    ok, why = freeze_ok(ROOT / "README.md")
    if not ok:
        problems.append(f"README.md: freeze violated — {why}")
    else:
        print(f"[policy] {why}")
    if problems:
        print("[policy] ⛔ storefront violations:")
        for p in problems:
            print(f"  - {p}")
        print("[policy] numbers live in EVIDENCE/NEWS/CASES/TOUR_NUMBERS/"
              "the status card — see docs/README_POLICY.md")
        return 1
    print("[policy] ✅ storefront clean: no per-round numbers, card is "
          "SSOT, freeze holds")
    return 0


if __name__ == "__main__":
    sys.exit(main())
