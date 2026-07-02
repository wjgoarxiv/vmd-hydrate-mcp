"""Minimal, dependency-free GROMACS ``.gro`` reader (units: nm, verbatim).

Used by the hydrate tools so the pure-NumPy science path needs neither VMD nor
MDAnalysis. Water detection uses a canonical hydrate resname list (VMD's
``water``/``name OW`` macros return 0 atoms on bare ``.gro`` — PLAN §13 C7).
Fixed-width columns: resname [5:10], atomname [10:15], x[20:28] y[28:36] z[36:44].
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

import numpy as np

from .hydrate.geometry import Cell

__all__ = ["Waters", "read_gro_waters", "count_frames", "WATER_RESNAMES"]

# Canonical hydrate/water residue names.
WATER_RESNAMES = {
    "SOL", "WAT", "HOH", "H2O", "TIP", "TIP3", "TIP3P", "TIP4", "TIP4P",
    "TIP5", "TIP5P", "SPC", "SPCE", "SPC/E", "HSL", "ICE", "HYD", "HYW",
    "CAGE", "WCL", "WATC",
}


@dataclass
class Waters:
    """Oxygen + two hydrogen positions per water (nm), plus the periodic cell."""

    O: np.ndarray  # (N,3)
    H1: np.ndarray  # (N,3)
    H2: np.ndarray  # (N,3)
    cell: Cell
    resids: List[str]
    o_index: List[int]  # 0-based atom index of each water's oxygen in the frame

    @property
    def n(self) -> int:
        return len(self.O)


def _is_oxygen(name: str) -> bool:
    u = name.upper()
    return u.startswith("O") or ("OW" in u)


def _is_hydrogen(name: str) -> bool:
    u = name.upper()
    return u.startswith("H") and ("HE" not in u)


def _frame_atom_count(lines: List[str], start: int) -> int:
    return int(lines[start + 1].strip())


def count_frames(path: str) -> int:
    lines = _read_lines(path)
    frames = 0
    i = 0
    while i + 1 < len(lines):
        try:
            natoms = int(lines[i + 1].strip())
        except (ValueError, IndexError):
            break
        block = 3 + natoms  # title + count + atoms + box
        if i + block - 1 >= len(lines):
            break
        frames += 1
        i += block
    return frames


def _read_lines(path: str) -> List[str]:
    with open(path, "r") as fh:
        return fh.read().splitlines()


def read_gro_waters(path: str, frame: int = 0) -> Waters:
    """Read waters (and cell) from frame ``frame`` of a ``.gro`` file.

    Groups atoms per residue: each water contributes one oxygen and its first
    two hydrogens (4/5-site dummies are naturally ignored).
    """
    lines = _read_lines(path)

    # locate the requested frame block
    i = 0
    fidx = 0
    while fidx < frame:
        natoms = _frame_atom_count(lines, i)
        i += 3 + natoms
        fidx += 1
    natoms = _frame_atom_count(lines, i)
    atom_start = i + 2
    box_line = lines[i + 2 + natoms]

    O_list: List[np.ndarray] = []
    H1_list: List[np.ndarray] = []
    H2_list: List[np.ndarray] = []
    resids: List[str] = []
    o_index: List[int] = []

    cur = {"o": None, "h": [], "res": None, "oidx": -1}

    def flush():
        if cur["o"] is not None and len(cur["h"]) >= 2:
            O_list.append(cur["o"])
            H1_list.append(cur["h"][0])
            H2_list.append(cur["h"][1])
            resids.append(cur["res"])
            o_index.append(cur["oidx"])

    for k in range(atom_start, atom_start + natoms):
        ln = lines[k]
        if len(ln) < 44:
            continue
        resname = ln[5:10].strip()
        if resname.upper() not in WATER_RESNAMES:
            continue
        resnum = ln[0:5].strip()
        aname = ln[10:15].strip()
        x = float(ln[20:28]); y = float(ln[28:36]); z = float(ln[36:44])
        pos = np.array([x, y, z])
        if _is_oxygen(aname):
            flush()
            cur = {"o": pos, "h": [], "res": resnum, "oidx": k - atom_start}
        elif _is_hydrogen(aname) and cur["o"] is not None and cur["res"] == resnum and len(cur["h"]) < 2:
            cur["h"].append(pos)
    flush()

    cell = Cell.from_gro_box(box_line.split())
    return Waters(
        O=np.array(O_list).reshape(-1, 3),
        H1=np.array(H1_list).reshape(-1, 3),
        H2=np.array(H2_list).reshape(-1, 3),
        cell=cell,
        resids=resids,
        o_index=o_index,
    )
