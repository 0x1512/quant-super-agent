# README storefront policy (5th correction, 2026-11-16)

**The public README is a stable storefront, not a lab notebook.** It
answers *what this can do* and *how to verify it* — never *what last
round's run produced*. Per-round measurements have their own addresses
and never flow back into the storefront.

## Where numbers live

| Address | Content | Updates |
|---|---|---|
| `docs/EVIDENCE.md` | the evidence inventory: per-version acceptance tables, machine-emitted verdicts with reproduce commands | every round, freely |
| `docs/NEWS.md` | per-round run log (what shipped, what was measured) | every round, freely |
| `docs/CASES.md` | case archive: date, plan fingerprint, reproduce command, full numbers per case | when a case is added |
| `docs/TOUR_NUMBERS.json` | the machine-regenerable tour baseline; `make tour` re-derives it from artifacts and drift-alarms | `make tour-write` after a pinned run |
| README **status card** | the storefront's ONLY numeric content: version, suite size, reference-run counts, throughput tier — rendered from `docs/STATUS.json` | only `make release-readme` |
| `README.dev.md` | dev-facing current status | freely (it is not the storefront) |

## Allowed vs forbidden in the storefront

**Allowed** — structural constants, properties of shipped code:
catalog sizes ("30-factor cited library"), panel specifications, the
parallelism anchor ("4.0×, byte-identical for any N"), version tags,
magnitudes ("minute-level", "hundreds of candidates").

**Forbidden** — per-round measurements: wall-clock seconds/minutes of a
specific run, that run's candidate/order/winner counts, dates, plan
fingerprints, signed 4-decimal IC values, hand-typed test counts.

## The mechanisms (all 20, one place each)

Internal process:

1. **charter + CI lint** — this document is the charter;
   `tools/check_readme.py` is the lint, wired into CI
2. **SSOT injection** — `docs/STATUS.json` is the only source;
   `tools/render_readme.py` renders the card
3. **release snapshots** — `docs/releases/vX.Y.Z/` freeze the README;
   `tools/release_readme.py` (via `make release-readme V=x.y.z`)
4. **change convention** — README edits ride `docs(readme):` /
   `release:` / `ci:` commits; the pre-push hook and CI refuse the rest
5. **NEWS.md split** — round logs go to NEWS, never the storefront
6. **placeholder rendering** — `{{…}}` lives in the generator, not the
   README, so hand-typed numbers cannot accumulate
7. **TOUR_NUMBERS as the demo-number source** — the card and STATUS
   page point at it; `make tour` regenerates and alarms
8. **self-check question 11** — "does the storefront contain per-round
   measurements?" (constitution: POSITIONING.md 五次纠偏)
9. **fixed skeleton** — the section structure below; time-bound content
   has no section to live in
10. **dual README** — `README.md` frozen storefront; `README.dev.md`
    current status; freeze asserted against the latest snapshot

Presentation:

11. capability verbs ("scores", "settles", "drift-alarms") instead of
    result numbers
12. numbers sink to a one-line EVIDENCE link card
13. magnitudes, not decimals ("minute-level", not "49.2s")
14. the versioned status card ("as of v1.4.1") instead of live numbers
15. commands as evidence: every Quickstart line names its expected
    artifacts and its self-verify command — visitors generate numbers
16. dynamic badges (CI status, live test count) carry freshness so the
    text never has to
17. case layering: README keeps an index (case + one line, no ICs);
    CASES.md keeps the archive
18. relative anchors ("4.0×, byte-identical") instead of absolute times
19. four-question opening (what you get / how fast, as a magnitude /
    why believe it / start now) — same wording as the showcase
20. separated status page: in-repo `docs/STATUS.md`, generated at
    release (not a CDN live page — four-channel rules intact)

## Storefront skeleton (fixed)

1. title + badges (CI, tests, license, python)
2. four-question opening
3. status card (rendered)
4. Quickstart — commands as evidence
5. what it can do — capability verbs per plane
6. case index → CASES.md
7. why / how it works (stable deep-dive)
8. comparison table (structural)
9. evidence & status links (EVIDENCE, NEWS, CASES, STATUS, dev README)
10. roadmap summary, documentation, acknowledgments, citation, license

## How to change the storefront

```bash
# routine rounds: never touch README.md; write NEWS.md + EVIDENCE.md
# a deliberate copy change:
git commit -m "docs(readme): <what and why>"     # convention required
# a release (card + snapshot + status page):
make release-readme V=1.4.2                      # commit as release:
```

Enforcement: `make readme-check` (lint + SSOT + freeze) runs locally,
in CI on every push/PR, and in the pre-push hook (`.githooks/`). CI
additionally recounts the suite and requires `docs/badge/tests.json`
to match (`make badge` refreshes it; `make release-readme` does so
automatically).
