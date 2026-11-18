"""Factor forge — v1.4 ⑥: sandbox factor generation as a closed loop.

The showcase promise: 遇到缺口不是报错停止，而是自己补——生成候选、
沙盒执行、同一把残差尺子评估、来源标注可追溯。 This module is that
loop, mechanically:

* ``detect_gaps`` — two gap kinds, both machine-detectable:
  1. *panel gaps*: factor families the catalog would offer but cannot,
     because a declared panel is absent from the snapshot;
  2. *stream gaps*: the plan promised a stream and it produced nothing
     above zero (an honest zero is a result — but the loop still tries
     one templated family before accepting it).
* ``generate`` — deterministic template codegen (three families, two
  windows each). No LLM in the loop: the product ships the mechanism;
  an LLM hypothesis line can WRITE INTO it later, but every candidate
  still walks the same sandbox.
* ``evaluate_specs`` — each template runs through ``sandbox.run_factor``
  (AST whitelist, truncated inputs = structural no-lookahead) and is
  scored by the SAME ``offense.evaluate`` residual objective as every
  other candidate. Clones still earn nothing.
* every emitted row carries ``source: "sandbox-forge"``, the gap it
  fills, and a sha256[:8] fingerprint of the exact code that ran —
  沙盒生成 never masquerades as a cited factor.

A template that the sandbox rejects is returned as a refused row, not
an exception — the loop's job is to stay legible under failure.
"""
from __future__ import annotations

import hashlib
from typing import Any, Callable

from qsa import offense, sandbox

WINDOWS = (10, 21)

# --- templates: window -> code (signature declares its contract) --------

_TURNOVER_SHOCK = """
def factor(closes, volumes, tickers, dates, i):
    out = {}
    for tk in tickers:
        vrow = volumes.get(tk, {})
        vs = []
        for d in dates:
            v = vrow.get(d)
            if v is not None:
                vs.append(v)
        if len(vs) < @WIN@ + 1:
            continue
        base = sum(vs[-@WIN@ - 1:-1]) / @WIN@
        if base and base > 0:
            out[tk] = vs[-1] / base
    return out
"""

_OVERNIGHT_REVERSAL = """
def factor(closes, opens, volumes, tickers, dates, i):
    out = {}
    for tk in tickers:
        crow = closes.get(tk, {})
        orow = opens.get(tk, {})
        cs, os_ = [], []
        for d in dates:
            c = crow.get(d)
            if c is not None:
                cs.append(c)
            o = orow.get(d)
            if o is not None:
                os_.append(o)
        if len(cs) < 2 or len(os_) < 1:
            continue
        prev, cur, todays_open = cs[-2], cs[-1], os_[-1]
        if prev and prev > 0 and cur and cur > 0 and todays_open > 0:
            gap = todays_open / prev - 1
            rev = 1 - cur / todays_open
            out[tk] = gap * rev
    return out
"""

_PRICE_VOLUME_DIV = """
def factor(closes, volumes, tickers, dates, i):
    out = {}
    n = @WIN@
    for tk in tickers:
        crow = closes.get(tk, {})
        vrow = volumes.get(tk, {})
        cs, vs = [], []
        for d in dates:
            c = crow.get(d)
            if c is not None:
                cs.append(c)
            v = vrow.get(d)
            if v is not None:
                vs.append(v)
        if len(cs) < n + 2 or len(vs) < n + 2:
            continue
        rs, dv = [], []
        for k in range(len(cs) - n - 1, len(cs) - 1):
            if cs[k] and cs[k + 1] and vs[k] and vs[k + 1]:
                rs.append(cs[k + 1] / cs[k] - 1)
                dv.append(vs[k + 1] / vs[k] - 1)
        if len(rs) < n:
            continue
        mr = sum(rs) / len(rs)
        mv = sum(dv) / len(dv)
        num = sum((a - mr) * (b - mv) for a, b in zip(rs, dv))
        da = sum((a - mr) ** 2 for a in rs) ** 0.5
        db = sum((b - mv) ** 2 for b in dv) ** 0.5
        if da > 0 and db > 0:
            out[tk] = -(num / (da * db))
    return out
"""


def _templates() -> list[tuple[str, str, Callable[[int], str]]]:
    return [
        ("forge_turnover_shock", "换手冲击（量能异常，v2 沙盒模板）",
         lambda w: _TURNOVER_SHOCK.replace("@WIN@", str(w))),
        ("forge_overnight_reversal", "隔夜跳空反转（v3 沙盒模板）",
         lambda w: _OVERNIGHT_REVERSAL),
        ("forge_price_volume_div", "量价背离（滚动负相关，v2 沙盒模板）",
         lambda w: _PRICE_VOLUME_DIV.replace("@WIN@", str(w))),
    ]


def detect_gaps(inputs: dict[str, Any], plan_streams: dict[str, bool],
                stream_rows: dict[str, list[dict[str, Any]]],
                catalog_needs: set[str] | None = None) -> list[dict[str, str]]:
    """Machine-detectable gaps: missing panels and empty promised streams."""
    gaps: list[dict[str, str]] = []
    available = {k for k in inputs if k != "dates"}
    if catalog_needs:
        for panel in sorted(catalog_needs - available):
            gaps.append({"kind": "panel", "name": panel,
                         "why": f"因子库声明需要 {panel}，快照缺失"})
    for stream in ("library", "interactions", "mutations"):
        if not plan_streams.get(stream, False):
            continue
        rows = stream_rows.get(stream, [])
        if not rows or all((r.get("oos_ic") or -9) <= 0 for r in rows):
            gaps.append({"kind": "stream", "name": stream,
                         "why": f"计划承诺 {stream} 流，但没有产出任何 "
                                f"oos IC > 0 的候选"})
    return gaps


def generate(gaps: list[dict[str, str]]) -> list[dict[str, Any]]:
    """Deterministic codegen: every template family x window, each tagged
    with the first gap it answers and the exact code fingerprint."""
    specs: list[dict[str, Any]] = []
    for fid, desc, code_of in _templates():
        for win in WINDOWS:
            code = code_of(win)
            fp = hashlib.sha256(code.encode()).hexdigest()[:8]
            specs.append({
                "id": f"{fid}_{win}", "family": fid,
                "needs": ["closes", "volumes", "opens"],
                "source": "sandbox-forge",
                "desc": f"{desc} win={win} code@{fp}",
                "code": code, "code_fp": fp,
                "fills": [f"{g['kind']}:{g['name']}" for g in gaps] or
                         ["none"],
            })
    return specs


def evaluate_specs(specs: list[dict[str, Any]], inputs: dict[str, Any],
                   basis: list[dict[str, Any]] | None = None,
                   ) -> list[dict[str, Any]]:
    """Run each spec through the sandbox and the residual objective.

    Sandbox rejections become refused rows (ok=False) — the loop never
    dies on its own candidates. Pass-through rows carry the same shape
    as every other leaderboard row, plus the forge annotations.
    """
    tickers = sorted(inputs["closes"])
    rows: list[dict[str, Any]] = []
    for spec in specs:
        row = {"id": spec["id"], "family": spec["family"],
               "source": spec["source"], "desc": spec["desc"],
               "oos_ic": None, "ic_mean": None, "icir": None,
               "train_ic": None, "n_months": None,
               "fills": spec["fills"],
               "code_fp": spec["code_fp"], "ok": False}
        try:
            sig = sandbox.run_factor(
                spec["code"], inputs["closes"], tickers,
                inputs["dates"], volumes=inputs.get("volumes"),
                opens=inputs.get("opens"))
        except sandbox.SandboxError as exc:
            row["refused"] = f"SandboxError: {exc}"
            rows.append(row)
            continue
        ev = offense.evaluate(
            {"id": spec["id"], "source": spec["source"],
             "desc": spec["desc"], "build": lambda _inp, _s=sig: _s},
            inputs, basis)
        # merge the FULL evaluation row (train_ic included) so forge rows
        # render through the same leaderboard path as every other row
        rows.append({**row, **ev, "fills": spec["fills"],
                     "code_fp": spec["code_fp"], "ok": True})
    return rows


def fill_gaps(inputs: dict[str, Any], plan_streams: dict[str, bool],
              stream_rows: dict[str, list[dict[str, Any]]],
              basis: list[dict[str, Any]] | None = None,
              catalog_needs: set[str] | None = None, force: bool = False
              ) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """The whole loop in one call: detect -> generate -> sandbox+score.

    ``force`` (the intent said 沙盒生成/补缺口) runs the templates even
    without a machine-detected gap — explicitly requested, never silent.
    """
    gaps = detect_gaps(inputs, plan_streams, stream_rows, catalog_needs)
    if force and not any(g["kind"] == "request" for g in gaps):
        gaps.append({"kind": "request", "name": "forge",
                     "why": "研究意图点名沙盒生成（计划已声明，非静默）"})
    if not gaps:
        return [], []
    rows = evaluate_specs(generate(gaps), inputs, basis)
    return rows, gaps


def render_forge_log(rows: list[dict[str, Any]],
                     gaps: list[dict[str, str]]) -> str:
    """Appendix block: what was missing, what was forged, what survived."""
    if not gaps:
        return "- 无缺口：所有承诺流都有正产出，未触发生成。"
    lines = ["缺口（机器检测）："]
    for g in gaps:
        lines.append(f"- [{g['kind']}] {g['name']} — {g['why']}")
    lines += ["", "生成 → 沙盒 → 残差评估：", ""]
    for r in rows:
        if not r.get("ok"):
            lines.append(f"- ⛔ {r['id']}：{r.get('refused', 'refused')}")
            continue
        ic = r["oos_ic"]
        if ic is None:
            lines.append(f"- {r['id']}（code@{r['code_fp']}，补 "
                         f"{','.join(r['fills'])}）：样本不足")
            continue
        star = " ★过线" if ic > 0.03 else ""
        lines.append(f"- {r['id']}（code@{r['code_fp']}，补 "
                     f"{','.join(r['fills'])}）：residual oos IC "
                     f"{ic:+.4f}{star}")
    lines += ["", "来源标注：以上全部为 sandbox-forge 生成候选，与引用库候选"
              "同尺评估、同门槛过线，报告与 leaderboard 一律带 "
              "`source` 字段，不冒充引用因子。"]
    return "\n".join(lines)
