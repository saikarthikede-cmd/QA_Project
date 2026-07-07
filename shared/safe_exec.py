"""Restricted Python execution for LLM-generated data-analysis code.

The agent in app6_data_analyst asks the model to write Python to compute answers
from retrieved PDF numbers. This module runs that code in a locked-down
environment: no imports, no file/network access, no dangerous builtins, and
AST-level forbiddance of risky constructs.
"""
from __future__ import annotations

import ast
import contextlib
import io
import math
import traceback
from typing import Any, Dict


# Built-ins that are safe for numeric/text data analysis.
_ALLOWED_BUILTINS = {
    "abs": abs,
    "all": all,
    "any": any,
    "bool": bool,
    "dict": dict,
    "enumerate": enumerate,
    "float": float,
    "int": int,
    "len": len,
    "list": list,
    "max": max,
    "min": min,
    "print": print,
    "range": range,
    "round": round,
    "set": set,
    "sorted": sorted,
    "str": str,
    "sum": sum,
    "tuple": tuple,
    "zip": zip,
}

# AST node types we never allow. Keep the whitelist small and conservative.
_FORBIDDEN_NODES = (
    ast.Import,
    ast.ImportFrom,
    ast.ClassDef,
    ast.FunctionDef,
    ast.AsyncFunctionDef,
    ast.Lambda,
    ast.Try,
    ast.TryStar,
    ast.With,
    ast.AsyncWith,
    ast.Raise,
    ast.Assert,
    ast.Global,
    ast.Nonlocal,
    ast.Delete,
    ast.Yield,
    ast.YieldFrom,
    ast.Await,
    ast.Match,  # Python 3.10+
)

# Attributes that are always forbidden because they provide escape hatches.
_FORBIDDEN_ATTRIBUTES = {
    "__class__",
    "__bases__",
    "__mro__",
    "__subclasses__",
    "__globals__",
    "__code__",
    "__closure__",
    "__dict__",
    "__import__",
}


def _validate_ast(node: ast.AST) -> None:
    """Walk the AST and reject any forbidden construct."""
    for child in ast.walk(node):
        if isinstance(child, _FORBIDDEN_NODES):
            raise ValueError(f"Forbidden syntax: {type(child).__name__}")

        if isinstance(child, ast.Call):
            func = child.func
            # Disallow attribute calls like obj.method() unless on allowed names.
            if isinstance(func, ast.Attribute):
                if func.attr in _FORBIDDEN_ATTRIBUTES:
                    raise ValueError(f"Forbidden attribute access: {func.attr}")

        if isinstance(child, ast.Attribute):
            if child.attr in _FORBIDDEN_ATTRIBUTES:
                raise ValueError(f"Forbidden attribute access: {child.attr}")


class _NoImport:
    """Replacement for __import__ that always fails."""

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("Imports are not allowed in sandboxed code.")


def run_sandboxed_python(code: str) -> str:
    """Execute Python code in a restricted environment.

    Returns the captured stdout, or an error string prefixed with "ERROR:".
    """
    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError as e:
        return f"ERROR:\nSyntaxError: {e}"

    try:
        _validate_ast(tree)
    except ValueError as e:
        return f"ERROR:\nSecurityError: {e}"

    restricted_globals: Dict[str, Any] = {
        "__builtins__": {**_ALLOWED_BUILTINS, "__import__": _NoImport()},
        "math": math,
    }

    stdout_capture = io.StringIO()
    try:
        with contextlib.redirect_stdout(stdout_capture):
            exec(compile(tree, "<sandbox>", "exec"), restricted_globals)  # noqa: S102
        output = stdout_capture.getvalue().strip()
        return output if output else "Code ran but produced no output. Use print() to show results."
    except Exception:
        return f"ERROR:\n{traceback.format_exc()}"
