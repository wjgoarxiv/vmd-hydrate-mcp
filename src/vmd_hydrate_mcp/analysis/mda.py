"""MDAnalysis-backed loading and measurements (topology-aware, broad formats).

Unit policy (PLAN §13 C1): MDAnalysis stores positions AND box dimensions in
**Angstrom**. Anything feeding the nm hydrate pipeline is converted here
(``* 0.1``). Generic measurements are reported in Angstrom and labelled as such,
so the two unit systems never silently mix.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

import numpy as np

from .hydrate.geometry import Cell

ANGSTROM_TO_NM = 0.1

_MDA_HINT = (
    "MDAnalysis is required for this operation. Install it with: "
    "pip install 'vmd-hydrate-mcp[mda]'"
)


def _require_mda():
    try:
        import MDAnalysis as mda  # type: ignore

        return mda
    except ImportError as e:  # pragma: no cover - environment dependent
        raise RuntimeError(_MDA_HINT) from e


def load_universe(path: str, topology: Optional[str] = None):
    mda = _require_mda()
    if topology:
        return mda.Universe(topology, path)
    return mda.Universe(path)


def cell_from_universe(universe, to_nm: bool = True) -> Cell:
    """Build a Cell from ``universe.triclinic_dimensions`` (3x3 vectors, Angstrom).

    Using the 3x3 vector form (not the a,b,c,alpha,beta,gamma tuple) is required
    so triclinic cells get correct basis vectors (PLAN §13 C5).
    """
    vecs = np.asarray(universe.triclinic_dimensions, dtype=float)  # rows a,b,c (A)
    if to_nm:
        vecs = vecs * ANGSTROM_TO_NM
    return Cell.from_vectors(vecs)


def resolve_selection(path: str, selection: str, topology: Optional[str] = None) -> int:
    """Return the atom count matched by an MDAnalysis selection (0-atom trap check)."""
    u = load_universe(path, topology)
    try:
        return int(u.select_atoms(selection).n_atoms)
    except Exception as e:  # noqa: BLE001 - MDAnalysis raises many selection errors
        raise ValueError(f"invalid selection {selection!r}: {e}") from e


def radius_of_gyration(
    path: str, selection: str = "all", topology: Optional[str] = None, frame: int = 0
) -> float:
    """Radius of gyration (Angstrom) of a selection at ``frame``."""
    u = load_universe(path, topology)
    u.trajectory[frame]
    ag = u.select_atoms(selection)
    if ag.n_atoms == 0:
        raise ValueError(f"selection {selection!r} matched 0 atoms")
    return float(ag.radius_of_gyration())


def measure_geometry(
    path: str, indices: List[int], topology: Optional[str] = None, frame: int = 0
) -> Tuple[str, float]:
    """Distance (2 idx), angle (3), or dihedral (4) in Angstrom/degrees."""
    u = load_universe(path, topology)
    u.trajectory[frame]
    pos = u.atoms.positions
    p = [np.asarray(pos[i], float) for i in indices]
    if len(p) == 2:
        return "distance_angstrom", float(np.linalg.norm(p[0] - p[1]))
    if len(p) == 3:
        a = p[0] - p[1]
        b = p[2] - p[1]
        c = np.clip(a @ b / (np.linalg.norm(a) * np.linalg.norm(b)), -1, 1)
        return "angle_degrees", float(np.degrees(np.arccos(c)))
    if len(p) == 4:
        b1, b2, b3 = p[1] - p[0], p[2] - p[1], p[3] - p[2]
        n1, n2 = np.cross(b1, b2), np.cross(b2, b3)
        x = np.linalg.norm(b2) * (b1 @ n2)
        y = n1 @ n2
        return "dihedral_degrees", float(np.degrees(np.arctan2(x, y)))
    raise ValueError("indices must have length 2 (distance), 3 (angle), or 4 (dihedral)")


def load_waters_mda(
    path: str,
    topology: Optional[str] = None,
    frame: int = 0,
    water_selection: str = "resname SOL WAT HOH H2O TIP3 SPC",
):
    """Extract O/H1/H2 arrays (nm) + Cell for hydrate analysis via MDAnalysis.

    Used for non-.gro inputs; for .gro the pure nm parser in ``gro.py`` is
    preferred (no element-guessing, no unit conversion).
    """
    u = load_universe(path, topology)
    u.trajectory[frame]
    water = u.select_atoms(water_selection)
    if water.n_atoms == 0:
        raise ValueError(
            f"water selection {water_selection!r} matched 0 atoms; pass an explicit "
            "water_selection or load a topology with element/name data"
        )
    O_list, H1_list, H2_list = [], [], []
    for res in water.residues:
        names = res.atoms.names
        pos = res.atoms.positions * ANGSTROM_TO_NM
        o_idx = [i for i, n in enumerate(names) if n.upper().startswith("O") or "OW" in n.upper()]
        h_idx = [i for i, n in enumerate(names) if n.upper().startswith("H") and "HE" not in n.upper()]
        if not o_idx or len(h_idx) < 2:
            continue
        O_list.append(pos[o_idx[0]])
        H1_list.append(pos[h_idx[0]])
        H2_list.append(pos[h_idx[1]])
    cell = cell_from_universe(u, to_nm=True)
    return (
        np.array(O_list).reshape(-1, 3),
        np.array(H1_list).reshape(-1, 3),
        np.array(H2_list).reshape(-1, 3),
        cell,
    )
