"""Deterministic forge emulation — issues, PRs, refs, CI check runs.

A forge (GitHub/Gitea/…) is where the lifecycle becomes externally visible:
orders arrive as issues, evidence lands via PRs, and branch protection makes
the verify gate *the only door to main*. This module emulates that surface
offline, deterministically:

* no wall clock — every mutation carries the caller's logical sequence via
  the internal counter, and state bytes depend only on the call sequence;
* ``push`` runs a real CI command as a subprocess (the gate itself), records
  a check run with its conclusion and output tail;
* ``merge`` refuses any PR whose head sha lacks successful check runs —
  branch protection, so a failing gate cannot reach main no matter what the
  "agent" wants.

State lives in ``<root>/state.json`` + ``events.jsonl`` (append-only), both
canonical JSON.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from .snapshot import canonical_json, sha256_bytes


class Forge:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.state_path = self.root / "state.json"
        self.events_path = self.root / "events.jsonl"
        self.state: dict[str, Any] = json.loads(self.state_path.read_text("utf-8")) \
            if self.state_path.exists() else self._empty()

    # -- lifecycle ------------------------------------------------------
    @classmethod
    def init(cls, root: Path) -> "Forge":
        root = Path(root)
        root.mkdir(parents=True, exist_ok=True)
        forge = cls(root)
        if not forge.state_path.exists():
            forge._flush()
        return forge

    @staticmethod
    def _empty() -> dict[str, Any]:
        return {"seq": 0, "refs": {"main": None}, "issues": [], "prs": [],
                "commits": [], "check_runs": []}

    def _flush(self) -> None:
        self.state_path.write_bytes(canonical_json(self.state) + b"\n")

    def _ev(self, etype: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.state["seq"] += 1
        event = {"seq": self.state["seq"], "type": etype, **payload}
        with self.events_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n")
        self._flush()
        return event

    # -- surface --------------------------------------------------------
    def create_issue(self, title: str, body: str) -> int:
        number = self.state["seq"] + 1
        issue = {"number": number, "title": title, "body": body,
                 "state": "open", "comments": []}
        self.state["issues"].append(issue)
        self._ev("issue_opened", {"issue": number, "title": title})
        return number

    def add_comment(self, issue_number: int, body: str) -> None:
        issue = self._issue(issue_number)
        issue["comments"].append({"body": body})
        self._ev("issue_commented", {"issue": issue_number})

    def commit(self, branch: str, message: str, files: dict[str, str]) -> str:
        """Record a commit on *branch*; sha is content-addressed (deterministic)."""
        parent = self.state["refs"].get(branch)
        payload = canonical_json({"parent": parent, "message": message,
                                  "files": files})
        sha = sha256_bytes(payload)
        self.state["commits"].append({"sha": sha, "branch": branch,
                                      "message": message, "files": files})
        self.state["refs"][branch] = sha
        self._ev("commit", {"branch": branch, "sha": sha, "message": message})
        return sha

    def push(self, branch: str, ci_cmd: list[str], cwd: Path | None = None,
             ci_name: str = "verify") -> dict[str, Any]:
        """Post-receive hook: run CI (the gate) on the branch head and record
        the check run. The command's exit code decides the conclusion."""
        sha = self.state["refs"].get(branch)
        if sha is None:
            raise ValueError(f"branch {branch!r} has no commits")
        proc = subprocess.run(ci_cmd, capture_output=True, text=True,
                              cwd=cwd, timeout=300)
        conclusion = "success" if proc.returncode == 0 else "failure"
        tail = [ln for ln in (proc.stdout + proc.stderr).splitlines() if ln.strip()][-3:]
        run = {"sha": sha, "name": ci_name, "conclusion": conclusion,
               "output_tail": tail}
        self.state["check_runs"].append(run)
        self._ev("check_run", {"sha": sha, "name": ci_name,
                               "conclusion": conclusion})
        return run

    def create_pr(self, title: str, head: str, base: str = "main",
                  body: str = "") -> int:
        number = self.state["seq"] + 1
        pr = {"number": number, "title": title, "head": head, "base": base,
              "body": body, "state": "open"}
        self.state["prs"].append(pr)
        self._ev("pr_opened", {"pr": number, "head": head, "base": base})
        return number

    def merge_pr(self, number: int) -> bool:
        """Branch protection: merge only when the head sha has successful CI."""
        pr = self._pr(number)
        head_sha = self.state["refs"].get(pr["head"])
        runs = [r for r in self.state["check_runs"] if r["sha"] == head_sha]
        if not runs:
            self._ev("merge_blocked", {"pr": number, "reason": "no check runs on head"})
            return False
        failed = [r for r in runs if r["conclusion"] != "success"]
        if failed:
            reason = "; ".join(f"{r['name']}: {r['conclusion']}"
                               f" ({' | '.join(r['output_tail'])})" for r in failed)
            self._ev("merge_blocked", {"pr": number, "reason": reason})
            return False
        pr["state"] = "merged"
        self.state["refs"][pr["base"]] = head_sha
        self._ev("merged", {"pr": number, "base": pr["base"], "sha": head_sha})
        return True

    # -- lookup ---------------------------------------------------------
    def _issue(self, number: int) -> dict[str, Any]:
        for issue in self.state["issues"]:
            if issue["number"] == number:
                return issue
        raise KeyError(f"no issue #{number}")

    def _pr(self, number: int) -> dict[str, Any]:
        for pr in self.state["prs"]:
            if pr["number"] == number:
                return pr
        raise KeyError(f"no PR #{number}")
