# Security Policy

## Reporting a vulnerability

Please report security issues privately via [private vulnerability report](https://github.com/0x1512/quant-super-agent/security/advisories/new) — **not** via public issues. We aim to acknowledge reports within 48 hours and will coordinate a fix and disclosure timeline.

## Scope

This project is a **research skeleton** (v0.1). It contains no credentials, no live trading connectivity, and no production data. The repository is deliberately free of:

- keys, tokens, or any secret material (`.gitignore` blocks common patterns; CI in later releases will add `gitleaks` as a gate),
- internal infrastructure addresses or paths,
- raw or derived market datasets (reproducible recipes only, from v0.2+).

If you find any of the above in a release, report it and we will treat it as a release-blocking incident.

## Safe-harbor notes

- The project does **not** connect to brokerages or real-data vendors; any integration is out of scope (see `docs/ROADMAP.md`).
- The "paper" execution engine is a deterministic research emulation, not a live order router.
