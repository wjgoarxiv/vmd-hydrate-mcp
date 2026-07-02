"""Build VMD control requests as safe Tcl lists.

Every argument is quoted as a single Tcl list element so that a selection like
``] ; exec sh`` becomes one inert literal, never a command (PLAN §13 S3). We use
brace-quoting for anything non-trivial and refuse inputs that cannot be brace-
quoted safely (unbalanced braces / trailing backslash / NUL) rather than trying
to be clever.
"""

from __future__ import annotations

import re

from ..security import SecurityError

__all__ = ["tcl_quote", "tcl_list"]

_SIMPLE = re.compile(r"^[A-Za-z0-9_./:=+\-]+$")


def _braces_balanced(s: str) -> bool:
    depth = 0
    for ch in s:
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth < 0:
                return False
    return depth == 0


def tcl_quote(value) -> str:
    s = str(value)
    if s == "":
        return "{}"
    if _SIMPLE.match(s):
        return s
    if "\x00" in s:
        raise SecurityError("NUL byte in Tcl argument")
    if _braces_balanced(s) and not s.endswith("\\"):
        return "{" + s + "}"
    raise SecurityError(f"cannot safely quote Tcl argument: {s!r}")


def tcl_list(parts) -> str:
    return " ".join(tcl_quote(p) for p in parts)
