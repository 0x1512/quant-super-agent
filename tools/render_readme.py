#!/usr/bin/env python3
"""README storefront renderer (5th correction, internal #2/#6).

The README's only numeric content is the STATUS CARD — a block between
HTML markers, rendered from ``docs/STATUS.json`` (the single source of
truth). Placeholders ({{VERSION}} …) live HERE, never in README, so the
checked-in README cannot accumulate hand-typed numbers.

    python tools/render_readme.py           # render the card into README(s)
    python tools/render_readme.py --check   # exit 1 if the card is stale

The card updates only via ``make release-readme`` — never by a routine
run (see docs/README_POLICY.md).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATUS = ROOT / "docs" / "STATUS.json"
BEGIN = "<!-- BEGIN STATUS CARD"
END = "<!-- END STATUS CARD -->"

EN_TEMPLATE = """<!-- BEGIN STATUS CARD — rendered from docs/STATUS.json by `make readme-render`; hand edits are overwritten at release -->
**Release status card — v{{VERSION}} ({{DATE}})** · machine-generated, frozen until the next release.

| as of v{{VERSION}} | |
|---|---|
| test suite | {{TESTS}} tests, offline & deterministic — `make verify` (live count: the badge above) |
| reference full run | {{CANDIDATES}} candidates → {{WINNERS}} settled orders, {{THROUGHPUT}}, on the {{PANEL}} pinned panel |
| parallelism | {{RELATIVE}} |
| conversation | {{CONVERSATION}} |

Numbers live in [EVIDENCE](docs/EVIDENCE.md) · [NEWS](docs/NEWS.md) · [CASES](docs/CASES.md) · [TOUR_NUMBERS.json](docs/TOUR_NUMBERS.json) (regenerate & drift-check: `make tour`). This card is the README's only numeric content and changes only via `make release-readme`.
<!-- END STATUS CARD -->"""

ZH_TEMPLATE = """<!-- BEGIN STATUS CARD — 由 docs/STATUS.json 经 `make readme-render` 渲染；手改会在发版时被覆盖 -->
**发版口径卡 — v{{VERSION}}（{{DATE}}）** · 机器生成，冻结至下一次发版。

| 截至 v{{VERSION}} | |
|---|---|
| 测试套件 | {{TESTS}} 项测试，离线确定性 —— `make verify`（实时数量见上方徽章） |
| 参考全量跑 | {{CANDIDATES}} 个候选 → {{WINNERS}} 张 settle 订单，{{THROUGHPUT}}，{{PANEL}} 钉死面板 |
| 并行性 | {{RELATIVE}} |
| 对话增量 | {{CONVERSATION}} |

数字住 [EVIDENCE](docs/EVIDENCE.md) · [NEWS](docs/NEWS.md) · [CASES](docs/CASES.md) · [TOUR_NUMBERS.json](docs/TOUR_NUMBERS.json)（再生与漂移检查：`make tour`）。本卡是本 README 唯一的数字内容，只经 `make release-readme` 变更。
<!-- END STATUS CARD -->"""


def card_text(lang: str = "en") -> str:
    s = json.loads(STATUS.read_text("utf-8"))
    tpl = EN_TEMPLATE if lang == "en" else ZH_TEMPLATE
    out = tpl
    for key, val in s.items():
        if not key.startswith("_"):
            out = out.replace("{{" + key.upper() + "}}", str(val))
    if "{{" in out:
        raise SystemExit(f"[render] unresolved placeholder in {lang} card")
    return out


def render(path: Path, lang: str) -> bool:
    """Write the card into README; returns True if anything changed."""
    text = path.read_text("utf-8")
    b = text.find(BEGIN)
    e = text.find(END)
    if b == -1 or e == -1 or e < b:
        raise SystemExit(f"[render] {path.name} has no STATUS CARD markers")
    new = text[:b] + card_text(lang) + text[e + len(END):]
    if new != text:
        path.write_text(new, encoding="utf-8")
        return True
    return False


def check(path: Path, lang: str) -> bool:
    text = path.read_text("utf-8")
    return card_text(lang) in text


def main() -> int:
    args = sys.argv[1:]
    targets = [(ROOT / "README.md", "en")]
    zh = ROOT / "README.zh-CN.md"
    if zh.exists():
        targets.append((zh, "zh"))
    if "--check" in args:
        stale = [p.name for p, lang in targets if not check(p, lang)]
        if stale:
            print("[render] STALE status card in: " + ", ".join(stale)
                  + " — run `make readme-render`")
            return 1
        print("[render] status cards up to date")
        return 0
    for p, lang in targets:
        changed = render(p, lang)
        print(f"[render] {p.name}: {'re-rendered' if changed else 'unchanged'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
