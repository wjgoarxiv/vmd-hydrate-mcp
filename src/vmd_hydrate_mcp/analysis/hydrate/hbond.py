"""Water-water H-bond network (TRACE/GRADE H-bond criterion).

Units: nm. A bond exists between waters i and j iff their oxygens are within
``rcut`` (min-image) AND at least one of the four donor configurations has
angle(H, O_donor, O_acceptor) < ``theta`` degrees (i.e. O_donor-H...O_acceptor
> 180 - theta). Requires explicit hydrogens.

Defaults: rcut = 0.36 nm, theta = 35 deg (cage/HTR/GRADE convention).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

import numpy as np

from .geometry import Cell
from .order_params import neighbor_pairs

__all__ = ["hbond_network", "HBondResult"]


@dataclass
class HBondResult:
    n_waters: int
    n_bonds: int
    avg_coordination: float
    adjacency: List[List[int]] = field(repr=False)
    pairs: np.ndarray = field(repr=False)

    def summary(self) -> dict:
        return {
            "n_waters": self.n_waters,
            "n_bonds": self.n_bonds,
            "avg_coordination": self.avg_coordination,
        }


def _donates(cell: Cell, o_don, h1, h2, o_acc, theta: float) -> bool:
    # angle vertex is the donor oxygen; ray to its own H and to the acceptor O
    return (
        cell.angle(o_don, h1, o_acc) < theta
        or cell.angle(o_don, h2, o_acc) < theta
    )


def hbond_network(
    O: np.ndarray,
    H1: np.ndarray,
    H2: np.ndarray,
    cell: Cell,
    rcut: float = 0.36,
    theta: float = 35.0,
) -> HBondResult:
    O = np.asarray(O, dtype=float).reshape(-1, 3)
    H1 = np.asarray(H1, dtype=float).reshape(-1, 3)
    H2 = np.asarray(H2, dtype=float).reshape(-1, 3)
    n = len(O)

    candidate = neighbor_pairs(O, cell, rcut)  # O-O within rcut, distance-only
    adj: List[List[int]] = [[] for _ in range(n)]
    bonds = 0
    for i, j in candidate:
        oi, oj = O[i], O[j]
        # i donates to j, or j donates to i
        if _donates(cell, oi, H1[i], H2[i], oj, theta) or _donates(
            cell, oj, H1[j], H2[j], oi, theta
        ):
            adj[i].append(int(j))
            adj[j].append(int(i))
            bonds += 1
    for a in adj:
        a.sort()  # deterministic ordering (matches reference)

    avg_coord = (2.0 * bonds / n) if n else 0.0
    return HBondResult(
        n_waters=n,
        n_bonds=bonds,
        avg_coordination=avg_coord,
        adjacency=adj,
        pairs=candidate,
    )
