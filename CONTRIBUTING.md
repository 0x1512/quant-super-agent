# Contributing

Thanks for your interest. This is a research project with a strict honesty norm — contributions are welcome, overclaims are not.

## Ways to help right now (v0.1)

- **Review the FIB benchmark spec** ([docs/BENCHMARK.md](docs/BENCHMARK.md)) — missing injection classes, adjudication rubrics, ways a system could game a class. Open an issue with the `benchmark` label.
- **Porting questions** — if you run an agentic quant framework and want to be an FIB baseline, open an issue with `baseline`.
- **Docs clarity** — anything unclear in the architecture or evidence pages, PRs welcome.

## Ground rules

1. **No fabricated results, ever.** Every number in a PR must be machine-reproducible from artifacts in the repo or clearly labeled as pilot-internal with an inventory pointer.
2. **Negative results are contributions.** A well-attributed failure is a merge; a suspicious pass is not.
3. **Design changes go through issues first** (spec-level), then PRs.
4. **Security**: never commit keys, tokens, or internal paths. CI rejects secrets.
5. **Tone**: we cite related work generously (see acknowledgments in README).

## Dev setup

Nothing to build yet (v0.1 is docs). v0.2 will land `make init && make demo-order` with a pinned toy dataset.
