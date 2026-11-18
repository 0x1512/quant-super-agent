#!/usr/bin/env python3
"""Public-repo hygiene gate — blocks leaks before they ship.

Checks (all mechanical, zero judgment calls):
1. TREE — no internal artifacts: the internal planning docs are
   dual-repo material (private workspace), never public files.
2. TREE — no local absolute paths (/dfs, /home/<user>), internal
   hostnames, or internal tool names (feishu/rind-bot/...) in any
   tracked file.
3. TREE — author identity: no personal names/emails; commits come
   from the project identity (noreply) only.
4. LOG  — commit subjects are English-only (CJK in a subject means
   the message was not written for the public record).

Run: python tools/check_public.py   (exit 1 = leak found)
Wired into CI on every push; run locally before committing.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

INTERNAL_FILES = [
    # dual-repo policy: internal planning/benchmarking docs live in
    # the private workspace; their presence here is a leak by name
    "docs/SUPERAGENT_PLAN.md",
    "docs/SUPERAGENT_PLAN2.md",
]

PATH_PATTERNS = [
    re.compile(r"/dfs/"),
    re.compile(r"/home/[a-z][a-z0-9_-]*/"),
    re.compile(r"\bDSA_QiYUAN\w*"),
]

INTERNAL_TOOL_WORDS = [
    # internal ops stack, never public: notification bot, agent
    # workspaces, internal channel names. (dsh-superagent is the
    # public MIT upstream — attribution is a license duty, allowed.)
    "feishu", "rind_bot", "rind-bot", "agents-management",
    "workspaces/",
]

PERSONAL_AUTHOR = re.compile(
    r"^(?!0x1512<131221908\+0x1512@users\.noreply\.github\.com>$)"
    r".*<(?!131221908\+0x1512@users\.noreply\.github\.com)"
    r"(?!0x1512@users\.noreply\.github\.com)"
    r"[^<>]+@[^<>]+>$")

CJK = re.compile(r"[\u4e00-\u9fff]")


def sh(*args: str) -> str:
    return subprocess.run(args, cwd=ROOT, check=True,
                          capture_output=True, text=True).stdout


def check_tree_files() -> list[str]:
    problems = []
    tracked = sh("git", "ls-files").splitlines()
    for f in tracked:
        if f in INTERNAL_FILES:
            problems.append(f"internal artifact tracked: {f}")
    return problems


SKIPS = {"tools/check_public.py",
           ".github/workflows/ci.yml"}   # gate files quote patterns


def check_tree_content() -> list[str]:
    problems = []
    tracked = [f for f in sh("git", "ls-files").splitlines()
               if f not in SKIPS
               and Path(ROOT, f).is_file()
               and Path(ROOT, f).stat().st_size < 2_000_000]
    for f in tracked:
        try:
            text = Path(ROOT, f).read_text(encoding="utf-8",
                                           errors="ignore")
        except OSError:
            continue
        for pat in PATH_PATTERNS:
            m = pat.search(text)
            if m:
                problems.append(
                    f"{f}: local path pattern {m.group(0)!r}")
        low = text.lower()
        for w in INTERNAL_TOOL_WORDS:
            if w in low:
                problems.append(f"{f}: internal tool/host word {w!r}")
    return problems


def check_authors() -> list[str]:
    problems = []
    ids = set(sh("git", "log", "--format=%an<%ae>").splitlines())
    for ident in sorted(ids):
        if not ident.startswith("0x1512"):
            problems.append(
                f"non-project author identity in history: {ident!r}")
    return problems


def check_subject_language() -> list[str]:
    problems = []
    subjects = sh("git", "log", "--format=%h %s").splitlines()
    for line in subjects:
        if CJK.search(line):
            problems.append(f"non-English commit subject: {line!r}")
    return problems


def staged_snapshot() -> list[str]:
    """Files in the staged tree (index), not just HEAD."""
    return subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        cwd=ROOT, capture_output=True, text=True).stdout.splitlines()


def check_staged() -> list[str]:
    problems = []
    for f in staged_snapshot():
        if f in INTERNAL_FILES:
            problems.append(f"internal artifact staged: {f}")
    ident = sh("git", "config", "user.name").strip(),         sh("git", "config", "user.email").strip()
    if ident[0] != "0x1512" or "noreply.github.com" not in ident[1]:
        problems.append(
            f"commit identity is {ident!r} — set the project identity "
            "(see CONTRIBUTING.md)")
    return problems


def main() -> int:
    problems = (check_tree_files() + check_tree_content()
                + check_authors() + check_subject_language())
    if "--staged" in sys.argv:
        problems += check_staged()
    if problems:
        print("[public-hygiene] FAIL — public-repo leaks found:")
        for p in problems:
            print("  -", p)
        print("[public-hygiene] fix before pushing; see "
              "CONTRIBUTING.md for the dual-repo and language rules.")
        return 1
    print("[public-hygiene] clean: no internal artifacts, no local "
          "paths, no personal identities, English-only subjects")
    return 0


if __name__ == "__main__":
    sys.exit(main())
