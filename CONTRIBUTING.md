# Contributing — public-repo discipline

This repository is PUBLIC. Everything pushed here is research record,
marketing surface, and code — and it is also an attack surface for
accidental disclosure. The rules below are enforced mechanically by
`tools/check_public.py` (runs in CI on every push; run it locally
before committing).

## 1. Language: English everywhere in the public record

- Commit messages (subject AND body): English only.
- Documentation, code comments, issue/PR text: English.
- Chinese remains fine in private workspaces and internal notes —
  the public repo is the English record.

## 2. Dual-repo policy: research is public, intelligence is not

**Public (this repo):**
- measured results, including failures and honest zeros;
- gate definitions, calibration corrections, and the reasoning;
- methodology (how the funnel, graveyard, and gauntlet work).

**Private (internal workspace, never this repo):**
- competitor/prototype gap analyses and internal benchmarking notes;
- roadmap bets, user decision logs beyond what the research record
  requires, staffing/workflow details;
- any file whose name starts with `SUPERAGENT_PLAN` — these are
  internal planning artifacts by convention.

## 3. Identity and infrastructure hygiene

- Commit as the project identity (`0x1512 <…@users.noreply.github.com>`),
  never a personal name/email. Check `git config user.name user.email`.
- No local absolute paths (cluster mounts, `/home/<user>/…`) in any
  tracked file — use repo-relative paths.
- No internal hostnames, workspace paths, or ops-tool names
  (notification bots, agent-workspace tooling) in tracked files.
- Attribution to the public MIT upstream (`dsh-superagent`) is a
  license duty and is allowed.

## 4. Before you commit / push

Install the local hooks once per clone:

```
cp tools/git_hooks/pre-commit .git/hooks/pre-commit
cp tools/git_hooks/pre-push   .git/hooks/pre-push
```

- `pre-commit` blocks the commit if staged files are internal
  artifacts or the configured identity is not the project identity.
- `pre-push` re-runs the full gate (tree, content, history, language)
  before anything leaves the machine.
- CI runs the same gate as a job; red `public-hygiene` blocks merge.

## 5. History rewrites

If a leak lands in history, the fix is a coordinated rewrite
(backup bundle first, then `git filter-branch` with env/msg
filters, then force-push) — see the 2026-11-18 hygiene commit for
the worked example. Prefer the pre-push gate over rewrites.
