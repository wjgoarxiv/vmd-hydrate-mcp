"""Security guard against path traversal and Tcl injection.

Two layers:
  * PathGuard (S5): every file argument is realpath-resolved and must live,
    component-wise, under an allowed root. Defeats ``..`` traversal, symlink
    escapes, and the ``/allowed-evil`` prefix trick that ``str.startswith`` lets
    through.
  * The Tcl trust boundary is NOT here — it lives in ``vmd/server.tcl`` as a
    safe-interpreter command allowlist (S1). This module only guards the Python
    side (file paths + selection-string shape) and never builds Tcl by string
    interpolation (S3).
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, List

__all__ = ["PathGuard", "SecurityError", "looks_like_tcl_injection"]


class SecurityError(Exception):
    """Raised when an argument violates the security policy."""


class PathGuard:
    def __init__(self, allowed_roots: Iterable[Path]):
        self.roots: List[Path] = [Path(r).expanduser().resolve() for r in allowed_roots]
        if not self.roots:
            raise ValueError("PathGuard needs at least one allowed root")

    def resolve(self, path: str, must_exist: bool = True) -> Path:
        """Return the realpath of ``path`` if it is inside an allowed root."""
        p = Path(path).expanduser()
        try:
            resolved = p.resolve(strict=must_exist)
        except (FileNotFoundError, RuntimeError) as e:
            raise SecurityError(f"cannot resolve path: {path}") from e
        for root in self.roots:
            if _is_within(resolved, root):
                return resolved
        raise SecurityError(
            f"path {resolved} is outside the allowed roots "
            f"({', '.join(str(r) for r in self.roots)}); "
            f"set VMD_HYDRATE_MCP_ALLOW_DIR to permit it"
        )


def _is_within(child: Path, root: Path) -> bool:
    # Path.is_relative_to compares path components (not string prefixes), so
    # /data-evil is NOT considered within /data.
    try:
        return child == root or child.is_relative_to(root)
    except AttributeError:  # py<3.9 safety (we target 3.10+, kept defensively)
        return str(child) == str(root) or str(child).startswith(str(root) + "/")


# Shape check for selection strings passed to the (safe-interp) VMD side. This
# is defense-in-depth only; the real containment is the safe interpreter. We
# reject characters that enable Tcl command substitution so a selection can
# never break out of `[list set seltext $value]` binding.
_FORBIDDEN_SEL_CHARS = set("[]{}$;`\\\n\r")


def looks_like_tcl_injection(selection: str) -> bool:
    """True if a selection string contains Tcl metacharacters it should not."""
    return any(c in _FORBIDDEN_SEL_CHARS for c in selection)
