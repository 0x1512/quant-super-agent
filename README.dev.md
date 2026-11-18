# README.dev — working status (not the storefront)

This page is for people already inside the repo. It may churn freely,
every round, without any convention or release — that is the point of
the split (see [README_POLICY.md](docs/README_POLICY.md)). The public
storefront is [README.md](README.md).

## Current line — v1.4.1 (2026-11-16)

**Last effectiveness round (full numbers in
[NEWS.md](docs/NEWS.md) / [EVIDENCE.md](docs/EVIDENCE.md) / Case 2 in
[CASES.md](docs/CASES.md)):** smallcap residual attack, plan
fingerprint `d86e69253189c37b` — 84 candidates → 28 orders (head
`mom_24m` +0.1372), the forged `forge_turnover_shock_21` cleared the
0.04 bar (+0.0418), bar-raise follow-up 0 rescored, smallcap-recompute
30.1s, tour drift correctly exits 1. Three product fixes shipped:
verbose bar parsing, intent-universe honoring, forge→EnvSmith role
mapping.

**Storefront stabilization round:** all 20 README measures landed
(policy charter, STATUS SSOT + render/check/release tools, freeze
snapshots, dual README, badge writer, NEWS/CASES split, CI wiring,
pre-push convention gate, unit tests for the tooling).

## Suite

353 tests green (`make verify`); the public badge counts the same
deterministic unittest discovery.

## Open items

- [ ] streaming sandbox (the truncated-view sandbox is O(D²); 6 forge
      candidates cost 297.6s of the 336.6s round — Case 2)
- [ ] more intents through the conversation plane (recompute/
      rejudge/refuse each have exactly one measured case)
- [ ] roadmap: live trade gate, more starters, provider health
