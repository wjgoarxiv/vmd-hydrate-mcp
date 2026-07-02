"""F3 and F4 water order parameters (F4SPC / F3 conventions).

Units: nm. Highest-risk numerics in the port — pinned by hard goldens
(F4(222_S2 first-10 waters) == 0.926698, exactly 12 O-O pairs).

Design-review rules honored here:
  * C4 — the F3/F4 neighbor list is **distance-only** (``< cutoff**2``); it is
    deliberately NOT the angle-filtered H-bond adjacency (reusing that drops
    pairs and breaks the golden).
  * F4 overall is accumulated **per O-O pair**, never derived from a mean of
    per-atom values. F3 overall averages only atoms that had >=2 neighbors.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple

import numpy as np

from .geometry import Cell

__all__ = ["order_parameters", "OrderParamResult", "neighbor_pairs", "f3_value"]

# cos(109.47 deg)^2 == 1/9 exactly (ideal tetrahedral); the F3-subset variant in
# guest-centric analysis uses 104.5 deg instead (that path lives in occupancy).
_COS2_TET = 1.0 / 9.0


@dataclass
class OrderParamResult:
    f3_overall: float
    f4_overall: float
    n_waters: int
    n_pairs: int
    f3_per_atom: np.ndarray = field(repr=False)
    f4_per_atom: np.ndarray = field(repr=False)

    def summary(self) -> dict:
        return {
            "f3_overall": self.f3_overall,
            "f4_overall": self.f4_overall,
            "n_waters": self.n_waters,
            "n_pairs": self.n_pairs,
        }


# --------------------------------------------------------------------------- #
# Neighbour search (distance-only, PBC-aware, pure NumPy)                      #
# --------------------------------------------------------------------------- #
def _neighbor_pairs_bruteforce(O: np.ndarray, cell: Cell, cutoff: float) -> np.ndarray:
    n = len(O)
    c2 = cutoff * cutoff
    out: List[Tuple[int, int]] = []
    for i in range(n):
        for j in range(i + 1, n):
            if cell.distance_sq(O[i], O[j]) < c2:
                out.append((i, j))
    return np.array(out, dtype=int).reshape(-1, 2)


def _neighbor_pairs_gridded(O: np.ndarray, cell: Cell, cutoff: float) -> np.ndarray:
    """Cell-list neighbour search in fractional space.

    Correct for any cell whose inter-plane spacing exceeds the cutoff along
    every axis (the standard minimum-image assumption). Bins are sized from the
    reciprocal-vector norms so a +/-1 bin halo always covers the cutoff, even
    for triclinic cells.
    """
    n = len(O)
    c2 = cutoff * cutoff
    frac = (O @ cell.inv) % 1.0  # -> [0,1)
    # interplane spacing d_k = 1/|recip_k|; bins so each bin thickness >= cutoff
    spacing = 1.0 / np.linalg.norm(cell.inv, axis=1)
    nb = np.maximum(1, np.floor(spacing / cutoff).astype(int))
    # axes with <3 bins can't use a +/-1 halo safely -> collapse to 1 (search all)
    nb = np.where(nb < 3, 1, nb)

    bin_idx = np.floor(frac * nb).astype(int) % nb  # (n,3)
    buckets: dict = {}
    for i in range(n):
        buckets.setdefault(tuple(bin_idx[i]), []).append(i)

    offs = [(dx, dy, dz) for dx in (-1, 0, 1) for dy in (-1, 0, 1) for dz in (-1, 0, 1)]
    out: List[Tuple[int, int]] = []
    for i in range(n):
        bx, by, bz = bin_idx[i]
        seen = set()
        for dx, dy, dz in offs:
            key = ((bx + dx) % nb[0], (by + dy) % nb[1], (bz + dz) % nb[2])
            if key in seen:
                continue
            seen.add(key)
            for j in buckets.get(key, ()):
                if j <= i:
                    continue
                if cell.distance_sq(O[i], O[j]) < c2:
                    out.append((i, j))
    return np.array(out, dtype=int).reshape(-1, 2)


def neighbor_pairs(O: np.ndarray, cell: Cell, cutoff: float = 0.35) -> np.ndarray:
    """Unique O-O pairs (i<j) within ``cutoff`` (nm), minimum-image.

    Returns an (M, 2) int array. Uses an O(N^2) scan for small systems (exact
    reference) and a cell list for large ones.
    """
    O = np.asarray(O, dtype=float).reshape(-1, 3)
    if len(O) <= 1500:
        return _neighbor_pairs_bruteforce(O, cell, cutoff)
    return _neighbor_pairs_gridded(O, cell, cutoff)


def _adjacency(n: int, pairs: np.ndarray) -> List[List[int]]:
    adj: List[List[int]] = [[] for _ in range(n)]
    for i, j in pairs:
        adj[i].append(int(j))
        adj[j].append(int(i))
    return adj


# --------------------------------------------------------------------------- #
# F3                                                                           #
# --------------------------------------------------------------------------- #
def f3_value(
    O: np.ndarray,
    cell: Cell,
    cutoff: float = 0.35,
    cos_ref_sq: float = _COS2_TET,
    pairs: np.ndarray | None = None,
) -> Tuple[float, np.ndarray]:
    """F3 = <(cos(theta)*|cos(theta)| + cos_ref_sq)^2> over neighbour triplets.

    ``cos_ref_sq`` defaults to cos^2(109.47) = 1/9 (global tetrahedral form);
    pass cos^2(104.5) for the guest-centric hydration-shell variant.
    """
    O = np.asarray(O, dtype=float).reshape(-1, 3)
    n = len(O)
    if pairs is None:
        pairs = neighbor_pairs(O, cell, cutoff)
    adj = _adjacency(n, pairs)
    per = np.full(n, np.nan)
    for i in range(n):
        m = adj[i]
        if len(m) < 2:
            continue
        acc = 0.0
        cnt = 0
        for a in range(len(m)):
            rij = cell.diff(O[m[a]], O[i])
            nij = np.linalg.norm(rij)
            if nij < 1e-10:
                continue
            for b in range(a + 1, len(m)):
                rik = cell.diff(O[m[b]], O[i])
                nik = np.linalg.norm(rik)
                if nik < 1e-10:
                    continue
                cos = np.clip(float(rij @ rik) / (nij * nik), -1.0, 1.0)
                term = cos * abs(cos) + cos_ref_sq
                acc += term * term
                cnt += 1
        if cnt:
            per[i] = acc / cnt
    finite = per[np.isfinite(per)]
    overall = float(np.mean(finite)) if finite.size else float("nan")
    return overall, per


# --------------------------------------------------------------------------- #
# F4                                                                           #
# --------------------------------------------------------------------------- #
def _far_h(cell: Cell, o_other: np.ndarray, h1: np.ndarray, h2: np.ndarray) -> np.ndarray:
    """The hydrogen furthest from the *other* oxygen (F4SPC convention)."""
    return h1 if cell.distance_sq(o_other, h1) > cell.distance_sq(o_other, h2) else h2


def order_parameters(
    O: np.ndarray,
    H1: np.ndarray,
    H2: np.ndarray,
    cell: Cell,
    cutoff: float = 0.35,
) -> OrderParamResult:
    """Compute F3 (109.47) and F4 (<cos 3phi>) for a set of waters.

    ``O``, ``H1``, ``H2`` are (N,3) arrays of oxygen and the two hydrogen
    positions (nm). ``cutoff`` is the O-O neighbour distance (nm).
    """
    O = np.asarray(O, dtype=float).reshape(-1, 3)
    H1 = np.asarray(H1, dtype=float).reshape(-1, 3)
    H2 = np.asarray(H2, dtype=float).reshape(-1, 3)
    n = len(O)

    pairs = neighbor_pairs(O, cell, cutoff)
    f3_overall, f3_per = f3_value(O, cell, cutoff, pairs=pairs)

    f4_per = np.zeros(n)
    f4_cnt = np.zeros(n)
    total = 0.0
    for i, j in pairs:
        oi, oj = O[i], O[j]
        hi = _far_h(cell, oj, H1[i], H2[i])
        hj = _far_h(cell, oi, H1[j], H2[j])
        phi = cell.dihedral(hi, oi, oj, hj)
        c3 = float(np.cos(3.0 * phi))
        total += c3
        f4_per[i] += c3
        f4_per[j] += c3
        f4_cnt[i] += 1
        f4_cnt[j] += 1
    n_pairs = len(pairs)
    f4_overall = float(total / n_pairs) if n_pairs else float("nan")
    with np.errstate(invalid="ignore", divide="ignore"):
        f4_per = np.where(f4_cnt > 0, f4_per / np.where(f4_cnt > 0, f4_cnt, 1), np.nan)

    return OrderParamResult(
        f3_overall=f3_overall,
        f4_overall=f4_overall,
        n_waters=n,
        n_pairs=n_pairs,
        f3_per_atom=f3_per,
        f4_per_atom=f4_per,
    )
