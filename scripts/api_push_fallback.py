#!/usr/bin/env python3
"""Push pending local commits to GitHub via the REST API — fallback for when
git-over-HTTPS is flaky (TLS resets, connect timeouts, intermittent auth).

What it does, per pending commit on main (oldest first):
  1. resolves the true remote head via the API (never trusts the stale
     origin/main tracking ref — explicit-URL pushes do not update it);
  2. uploads each changed file as a blob — exact bytes, no strip()
     (a strip() once ate trailing newlines and corrupted the tree);
  3. builds the tree on the remote parent's tree, creates the commit with the
     local message, and fast-forwards refs/heads/main;
  4. asserts remote tree sha == local tree sha (hard fail on mismatch);
  5. realigns the local branch: fetch + `git reset --mixed origin/main`
     (safe — never touches the working tree; trees are byte-identical).

Note: API-created commits get a different SHA than the local ones (GitHub
stamps its own committer metadata), so step 5 replaces local commits with
their remote twins — same tree, same message, clean status.

Usage:  python3 scripts/api_push_fallback.py   (from anywhere inside the repo)
Auth:   GITHUB_TOKEN (+ optional GITHUB_REPO) read from the repo's .env;
        the repo name otherwise comes from `git remote get-url origin`.
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parents[1]
REMOTE = "origin/main"
API = "https://api.github.com"


def env(key):
    path = REPO_DIR / ".env"
    if not path.exists():
        return None
    for line in path.read_text().splitlines():
        if line.startswith(key + "="):
            return line.split("=", 1)[1].strip().strip('"') or None
    return None


def detect_repo():
    """owner/repo from the git remote; .env GITHUB_REPO overrides if set."""
    override = env("GITHUB_REPO")
    if override:
        return override
    url = git("remote", "get-url", "origin")
    m = re.search(r"github\.com[:/]([^/]+/[^/]+?)(?:\.git)?$", url)
    if not m:
        raise RuntimeError(f"cannot parse owner/repo from remote url: {url}")
    return m.group(1)


TOKEN = env("GITHUB_TOKEN")
if not TOKEN:
    sys.exit("GITHUB_TOKEN missing from .env")
REPO = detect_repo()


def api_call(path, payload=None, method=None, tries=6):
    """GET/POST with retries on transient errors. Never prints the token.

    Retried: network errors, 5xx, 403 (rate limit), and 404 — a freshly
    created object can 404 for a moment (read-after-write consistency).
    Other 4xx are real answers and fail fast.
    """
    data = json.dumps(payload).encode() if payload is not None else None
    last = None
    for i in range(tries):
        req = urllib.request.Request(
            API + path,
            data=data,
            method=method or ("POST" if data is not None else "GET"),
            headers={
                "Authorization": f"Bearer {TOKEN}",
                "Accept": "application/vnd.github+json",
                "User-Agent": "qsa-release-fallback",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=40) as r:
                body = r.read()
                return r.status, json.loads(body) if body else {}
        except urllib.error.HTTPError as e:
            detail = e.read().decode()[:400]
            if 400 <= e.code < 500 and e.code not in (403, 404):
                raise RuntimeError(f"HTTP {e.code} on {path}: {detail}")
            last = RuntimeError(f"HTTP {e.code} on {path}: {detail}")
        except Exception as e:  # noqa: BLE001 — network flake
            last = e
        time.sleep(5 * (i + 1))
    raise last


def git(*args):
    return subprocess.run(
        ["git", "-C", str(REPO_DIR), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def git_raw(*args):
    """Like git() but WITHOUT strip() — file content must keep its exact bytes
    (strip() ate trailing newlines and corrupted uploaded blobs)."""
    return subprocess.run(
        ["git", "-C", str(REPO_DIR), *args], check=True, capture_output=True, text=True
    ).stdout


def realign_local():
    """After an API push, local and remote SHAs diverge (same trees). Point the
    local branch at its remote twin. reset --mixed never touches the working
    tree, so a tree mismatch would surface as an honest dirty status."""
    if subprocess.run(
        ["git", "-C", str(REPO_DIR), "fetch", "origin", "main"],
        capture_output=True,
    ).returncode != 0:
        print("realignment skipped: git fetch failed — run it later, then:")
        print("  git reset --mixed origin/main")
        return
    git("reset", "--mixed", "origin/main")
    print("local realigned to", git("rev-parse", "--short", "origin/main"))


def main():
    # Refresh the tracking ref when possible; stale refs only cause redundant
    # work (the per-commit remote-head check skips already-pushed SHAs anyway).
    subprocess.run(
        ["git", "-C", str(REPO_DIR), "fetch", "origin", "main"], capture_output=True
    )
    local_head = git("rev-parse", "HEAD")
    pending = git("rev-list", "--reverse", f"{REMOTE}..HEAD").split()
    if not pending:
        print("nothing to push; HEAD == ", git("rev-parse", "--short", REMOTE))
        return 0
    print(f"pending commits: {[c[:7] for c in pending]}")

    for sha in pending:
        _, remote_ref = api_call(f"/repos/{REPO}/git/ref/heads/main")
        remote_head = remote_ref["object"]["sha"]
        if remote_head == sha:
            print(f"{sha[:7]} already on remote — skip")
            continue
        msg = git("log", "-1", "--format=%B", sha)
        parent = remote_head  # linear history assumption
        files = git("diff", "--name-only", f"{parent}..{sha}").splitlines()
        if not files:
            print(f"{sha[:7]}: no file diff vs remote parent {parent[:7]} — skip")
            continue
        base_tree = api_call(f"/repos/{REPO}/git/commits/{parent}")[1]["tree"]["sha"]
        tree_items = []
        for f in files:
            content = git_raw("show", f"{sha}:{f}")
            blob_sha = api_call(
                f"/repos/{REPO}/git/blobs", {"content": content, "encoding": "utf-8"}
            )[1]["sha"]
            local_blob = git("rev-parse", f"{sha}:{f}")
            if blob_sha != local_blob:
                print(f"BLOB MISMATCH for {f}: api {blob_sha[:10]} != local {local_blob[:10]} — aborting")
                return 1
            mode = "100755" if git("ls-tree", sha, "--", f).startswith("100755") else "100644"
            tree_items.append({"path": f, "mode": mode, "type": "blob", "sha": blob_sha})
        tree = api_call(f"/repos/{REPO}/git/trees", {"base_tree": base_tree, "tree": tree_items})[1]["sha"]
        local_tree = git("rev-parse", f"{sha}^{{tree}}")
        if tree != local_tree:
            print(f"TREE MISMATCH ({tree[:10]} != {local_tree[:10]}) — ref NOT updated; investigate")
            return 1
        commit = api_call(
            f"/repos/{REPO}/git/commits",
            {"message": msg, "tree": tree, "parents": [parent]},
        )[1]["sha"]
        api_call(f"/repos/{REPO}/git/refs/heads/main", {"sha": commit, "force": False}, method="PATCH")
        print(f"pushed {sha[:7]} -> remote {commit[:7]} tree_match=True")
    print("ALL-PUSHED")
    realign_local()
    return 0


if __name__ == "__main__":
    sys.exit(main())
