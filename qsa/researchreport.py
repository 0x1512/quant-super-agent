"""Research report layering — v1.4 ⑨.

The v1.3 report was one flat leaderboard. The showcase promised a
LAYERED read instead — a reader should get the answer in the first
screen and the receipts in the appendix:

* 档案条 (archive strip): one glance — run id, window, universe,
  basis, candidates, winners, elapsed, workers. The run as a file card.
* 前 3 四行卡 (top-3 four-line cards): each winner in exactly four
  lines — 是什么 / 多强 / 凭什么信 / 下一步. If it doesn't fit in
  four lines it isn't understood well enough to report.
* 正文 leaderboard (top 20) then appendices: full factor library
  manifest, sandbox-forge log, honesty statement.

Pure functions of run data; golden-testable byte-for-byte.
"""
from __future__ import annotations

from typing import Any

THRESH_NOTE = "residual oos IC"


def archive_strip(meta: dict[str, Any]) -> str:
    """One-line-per-fact archive strip for the run."""
    return " | ".join([
        f"run {meta['run']}",
        f"窗口 {meta['dates'][0]}..{meta['dates'][1]} ×{meta['dates'][2]}日",
        f"标的 {meta['universe']}（{meta['n_tickers']} 只）",
        f"残差基 {meta['basis_n']} 因子 @{meta['basis_digest']}",
        f"候选 {meta['n_candidates']}",
        f"过线 {meta['n_winners']}",
        f"{meta['workers']} workers",
        f"{meta['elapsed_s']}s",
    ])


def four_line_card(row: dict[str, Any], rank: int, thresh: float,
                   min_months: int) -> str:
    """The four-line card: 是什么 / 多强 / 凭什么信 / 下一步."""
    src = row.get("source", "?")
    n = row.get("n_months")
    lines = [
        f"### {rank}. {row['id']}",
        f"- **是什么**：{row.get('desc', '?')}"
        + ("（沙盒生成）" if src == "sandbox-forge" else ""),
        f"- **多强**：{THRESH_NOTE} {row['oos_ic']:+.4f}"
        f"（ic_mean {row['ic_mean']:+.4f}，icir {row['icir']:+.2f}）",
        f"- **凭什么信**：{n} 个月样本 ≥ {min_months}、门槛 "
        f"{THRESH_NOTE} > {thresh} 预注册、对残差基正交后评估"
        + (f"，code@{row['code_fp']}" if row.get("code_fp") else ""),
        "- **下一步**：v1.0 全程（预注册→沙盒引擎→独立复算→判定）"
        "——快车道资格 ≠ 对外主张。",
    ]
    return "\n".join(lines)


def render_layered(meta: dict[str, Any], winners: list[dict[str, Any]],
                   board_md: str, thresh: float, min_months: int,
                   library_md: str = "", forge_md: str = "",
                   tree_md: str = "") -> str:
    """Full layered report: strip -> cards -> board -> appendices."""
    parts = [
        "# 进攻报告（分层版）",
        "",
        f"> 档案条：{archive_strip(meta)}",
        "",
    ]
    if tree_md:
        parts += [tree_md, ""]
    if winners:
        parts += ["## 前 3 名四行卡", ""]
        for i, row in enumerate(winners[:3], 1):
            parts += [four_line_card(row, i, thresh, min_months), ""]
    else:
        parts += ["## 前 3 名四行卡", "",
                  "- 本轮无过线候选——诚实零也是结果（门槛与样本下界"
                  "均预注册，未因结果调松）。", ""]
    parts += [board_md]
    if library_md:
        parts += ["", "## 附录 A · 因子库清单", "", library_md]
    if forge_md:
        parts += ["", "## 附录 B · 沙盒生成闭环", "", forge_md]
    parts += [
        "",
        "## 诚实声明",
        "",
        "- 快车道只授予资格：settle ≠ 认证；对外主张唯一路径仍是 "
        "v1.0 门禁。",
        "- 残差目标抑制克隆，不校正多重检验；正式主张计入 deflation "
        "计数。",
        "- 沙盒生成候选一律带 `source: sandbox-forge` 与代码指纹，"
        "与引用库候选同尺同门槛。",
    ]
    return "\n".join(parts) + "\n"
