"""Locate a runnable VMD binary and synthesize its runtime environment.

VMD ships as a .app bundle on macOS (the CLI binary lives inside it) and as a
csh wrapper on Linux; we resolve to the actual arch-suffixed executable and
derive VMDDIR + the STRIDE/SURF/TACHYON/TCL_LIBRARY env it needs, so callers get
a headless-ready (binary, env) pair without hardcoding any path.
"""

from __future__ import annotations

import glob
import os
import shutil
from dataclasses import dataclass
from typing import Dict, List, Optional

__all__ = ["VmdInstall", "discover_vmd"]


@dataclass
class VmdInstall:
    binary: str
    vmddir: str
    env: Dict[str, str]


def _candidates(explicit: Optional[str]) -> List[str]:
    out: List[str] = []
    # macOS app bundles (any VMD*.app, any arch-suffixed binary)
    out += sorted(glob.glob("/Applications/VMD*.app/Contents/*/vmd_MACOSX*"))
    out += sorted(glob.glob(os.path.expanduser("~/Applications/VMD*.app/Contents/*/vmd_MACOSX*")))
    # Linux / generic: direct arch binaries then the wrapper on PATH
    for base in ("/usr/local/lib/vmd", "/opt/vmd", "/usr/local/lib64/vmd"):
        out += sorted(glob.glob(os.path.join(base, "vmd_LINUX*")))
    w = shutil.which("vmd")
    if w:
        out.append(w)
    # de-dup, keep order
    seen = set()
    uniq = []
    for c in out:
        if c and c not in seen and os.path.exists(c):
            seen.add(c)
            uniq.append(c)
    return uniq


def _synth_env(binary: str) -> Optional[VmdInstall]:
    vmddir = os.path.dirname(os.path.abspath(binary))
    env = dict(os.environ)
    env["VMDDIR"] = vmddir

    tcl = os.path.join(vmddir, "scripts", "tcl")
    if os.path.isdir(tcl):
        env["TCL_LIBRARY"] = tcl
    pyscripts = os.path.join(vmddir, "scripts", "python")
    if os.path.isdir(pyscripts):
        env["PYTHONPATH"] = pyscripts + os.pathsep + env.get("PYTHONPATH", "")

    # helper binaries share the binary's arch suffix (e.g. _MACOSXARM64)
    for var, prefix in (("STRIDE_BIN", "stride_"), ("SURF_BIN", "surf_"), ("TACHYON_BIN", "tachyon_")):
        hits = sorted(glob.glob(os.path.join(vmddir, prefix + "*")))
        if hits:
            env[var] = hits[0]
    return VmdInstall(binary=binary, vmddir=vmddir, env=env)


def discover_vmd(explicit: Optional[str] = None) -> Optional[VmdInstall]:
    """Return a runnable VMD install, or None if none is found.

    If ``explicit`` (or ``$VMD_BIN``) is set it is honored **strictly**: we use
    exactly that binary or return None — we never silently fall back to a
    different VMD. Otherwise we auto-search app bundles and PATH (the arch binary
    is preferred over the csh wrapper, which can be broken / wrong-arch, as on
    Apple Silicon with a Linux tree).
    """
    explicit = explicit or os.environ.get("VMD_BIN") or None
    if explicit:
        if os.path.isfile(explicit) and os.access(explicit, os.X_OK):
            return _synth_env(explicit)
        return None
    for cand in _candidates(None):
        if os.path.isfile(cand) and os.access(cand, os.X_OK):
            return _synth_env(cand)
    return None


def tachyon_binary(install: VmdInstall) -> Optional[str]:
    return install.env.get("TACHYON_BIN")
