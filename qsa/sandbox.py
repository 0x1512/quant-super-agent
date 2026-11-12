"""Sandboxed execution of factor code (LLM-written or human-written).

The mining loop executes factor code that a language model produced. Before
anything runs, the code is checked against a strict AST whitelist — imports,
attribute access (``__import__``, ``.open``, …), global/nonlocal, while-loops
and friends are rejected outright — and then executed with a minimal builtins
table and a capped ``range``. The result must be a signal matrix of finite
floats.

This is a *research* sandbox: it removes the obvious footguns deterministically
and makes every rejection legible, but it is not a hardened security boundary
against a determined adversary — the authoritative line of defence is that
nothing a factor computes ever touches anything outside the workdir, and every
card it produces must still clear the verify gate.
"""
from __future__ import annotations

import ast
import math
from typing import Any

ALLOWED_NODES: tuple[type, ...] = (
    ast.Module, ast.FunctionDef, ast.Return, ast.arguments, ast.arg,
    ast.Assign, ast.AugAssign, ast.AnnAssign, ast.For, ast.If, ast.IfExp,
    ast.Expr, ast.Compare, ast.BinOp, ast.UnaryOp, ast.BoolOp, ast.Subscript,
    ast.Slice, ast.Name, ast.Load, ast.Store, ast.Constant, ast.Dict, ast.List,
    ast.Tuple, ast.Call, ast.keyword, ast.Attribute, ast.comprehension,
    ast.ListComp, ast.DictComp, ast.SetComp, ast.GeneratorExp, ast.Lambda,
    ast.Not, ast.USub, ast.UAdd, ast.And, ast.Or, ast.Eq, ast.NotEq, ast.Lt,
    ast.LtE, ast.Gt, ast.GtE, ast.Is, ast.IsNot, ast.Add, ast.Sub, ast.Mult,
    ast.Div, ast.FloorDiv, ast.Mod, ast.Pow, ast.Pass, ast.Break, ast.Continue,
)

BANNED_CALLS = {"eval", "exec", "compile", "open", "input", "globals", "locals",
                "vars", "getattr", "setattr", "delattr", "type", "help"}


class SandboxError(ValueError):
    """Legible rejection: the message is safe to show in a gate report."""


SAFE_ATTRS = {"get", "items", "keys", "values", "append"}


class _CappedRange:
    """range() that refuses to materialize absurd iteration counts."""

    LIMIT = 5_000_000

    def __call__(self, *args: int):
        r = range(*args)
        if len(r) > self.LIMIT:
            raise SandboxError(f"range({args}) exceeds sandbox limit {self.LIMIT}")
        return r


SAFE_BUILTINS: dict[str, Any] = {
    "abs": abs, "len": len, "min": min, "max": max, "sum": sum,
    "sorted": sorted, "zip": zip, "enumerate": enumerate, "float": float,
    "int": int, "round": round, "pow": pow, "list": list, "dict": dict,
    "tuple": tuple, "set": set, "bool": bool, "str": str, "range": _CappedRange(),
    "sqrt": math.sqrt, "log": math.log, "log1p": math.log1p, "exp": math.exp,
    "fabs": math.fabs, "True": True, "False": False, "None": None,
}


def check_code(code: str) -> None:
    """AST-whitelist the factor code; raise SandboxError naming the offense."""
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        raise SandboxError(f"factor code does not parse: {exc}") from exc

    defs = [n for n in tree.body if isinstance(n, ast.FunctionDef)]
    if len(defs) != 1 or defs[0].name != "factor":
        raise SandboxError("factor code must define exactly one function: "
                           "factor(closes, tickers, dates, i)")
    args = [a.arg for a in defs[0].args.args]
    if args[:4] != ["closes", "tickers", "dates", "i"]:
        raise SandboxError("factor(closes, tickers, dates, i) — first four "
                           "parameters must be closes, tickers, dates, i")

    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            if node.attr not in SAFE_ATTRS or node.attr.startswith("__"):
                raise SandboxError(f"attribute access '.{node.attr}' is not allowed "
                                   f"in factor code (line {node.lineno})")
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            raise SandboxError("imports are not allowed in factor code "
                               f"(line {node.lineno})")
        if isinstance(node, (ast.While,)):
            raise SandboxError("while-loops are not allowed (for-loops over the "
                               f"data are; line {node.lineno})")
        if isinstance(node, (ast.Global, ast.Nonlocal)):
            raise SandboxError(f"global/nonlocal are not allowed (line {node.lineno})")
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in BANNED_CALLS:
                raise SandboxError(f"call to {node.func.id}() is not allowed in factor code")
            if not (isinstance(node.func, ast.Name)
                    or (isinstance(node.func, ast.Attribute)
                        and node.func.attr in SAFE_ATTRS)):
                raise SandboxError("only plain-name or whitelisted-method calls "
                                   f"are allowed (line {node.lineno})")
        if not isinstance(node, ALLOWED_NODES):
            raise SandboxError(f"{type(node).__name__} is not allowed in factor code "
                               f"(line {getattr(node, 'lineno', '?')})")


def run_factor(code: str, closes: dict[str, dict[str, float]], tickers: list[str],
               dates: list[str]) -> dict[str, dict[str, float]]:
    """AST-check, execute and validate a factor; returns the signal matrix.

    The lookahead defence is structural: the factor function is called once
    per date *i* with **truncated inputs** — ``closes`` and ``dates`` contain
    only what existed up to and including date *i*. A factor that wants
    tomorrow's price simply cannot name it. (Cost: O(D) calls with O(D·N)
    copies each — fine at research scale; streaming evaluation lands with
    the portfolio plane.)
    """
    check_code(code)
    namespace: dict[str, Any] = {"__builtins__": SAFE_BUILTINS}
    try:
        exec(compile(code, "<factor>", "exec"), namespace)  # noqa: S102 (whitelisted above)
    except SandboxError:
        raise
    except Exception as exc:  # noqa: BLE001 — surfaced to the gate report
        raise SandboxError(f"factor code raised {type(exc).__name__}: {exc}") from exc

    fn = namespace.get("factor")
    matrix: dict[str, dict[str, float]] = {tk: {} for tk in tickers}
    for i, d in enumerate(dates):
        truncated = {tk: {dd: v for dd, v in row.items() if dd <= d}
                     for tk, row in closes.items()}
        try:
            values = fn(truncated, tickers, dates[:i + 1], i)
        except SandboxError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise SandboxError(f"factor raised {type(exc).__name__} at date "
                               f"{d}: {exc}") from exc
        if values is None:
            values = {}
        if not isinstance(values, dict):
            raise SandboxError(f"factor must return dict[ticker, value] at each "
                               f"date (got {type(values).__name__} at {d})")
        for tk, v in values.items():
            if not isinstance(tk, str) or v is None:
                continue
            if isinstance(v, bool) or not isinstance(v, (int, float)) \
                    or not math.isfinite(v):
                raise SandboxError(f"factor value signal[{tk}][{d}] is not a "
                                   f"finite number")
            matrix[tk][d] = float(v)
    populated = sum(1 for row in matrix.values() if row)
    if populated < 5:
        raise SandboxError(f"factor produced signal for only {populated} tickers "
                           f"(need >= 5 for cross-sectional evaluation)")
    return matrix
