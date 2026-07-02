"""Clathrate-hydrate cage identification (TRACE/HTR method).

Pipeline (TRACE method):
  H-bond graph -> find all topological 4/5/6-rings -> geometric validation
  (PBC closure + GRADE diagonal floors) -> assemble SEC cages by constraint-
  propagation growth -> Euler validation (F-E+V=2, edge in 2 faces, vertex in 3)
  -> classify by face composition (5^12, 5^12 6^2, 5^12 6^4, ...).

Golden (sII CO2 hydrate 222_S2, 1088 waters): ~128 x 5^12 + ~64 x 5^12 6^4,
ratio ~2, no 5^12 6^2. Units: nm.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

from .geometry import Cell
from .hbond import hbond_network

__all__ = ["identify_cages", "CageResult", "Cage"]

MAX_CAGE_FACES = 20

_CAGE_TYPES = {
    (0, 12, 0): "512", (0, 12, 2): "51262", (0, 12, 3): "51263",
    (0, 12, 4): "51264", (0, 12, 5): "51265", (0, 12, 6): "51266",
    (0, 12, 8): "51268", (1, 10, 2): "4151062", (1, 10, 3): "4151063",
    (1, 10, 4): "4151064", (1, 10, 5): "4151065", (2, 8, 1): "425861",
    (2, 8, 2): "425862", (2, 8, 3): "425863", (2, 8, 4): "425864",
    (3, 6, 3): "435663", (3, 6, 4): "435664",
}


@dataclass
class Cage:
    cage_type: str
    vertices: List[int]
    center: np.ndarray = field(repr=False)
    n4: int
    n5: int
    n6: int


@dataclass
class CageResult:
    cages: List[Cage]
    counts: Dict[str, int]
    structure: str
    confidence: float
    n_rings: int

    def summary(self) -> dict:
        return {
            "n_cages": len(self.cages),
            "counts": self.counts,
            "structure": self.structure,
            "confidence": self.confidence,
            "n_rings": self.n_rings,
        }


# --------------------------------------------------------------------------- #
# Ring finding                                                                 #
# --------------------------------------------------------------------------- #
def _normalize_ring(ring: List[int]) -> Tuple[int, ...]:
    n = len(ring)
    min_pos = min(range(n), key=lambda i: ring[i])
    prev = ring[(min_pos + n - 1) % n]
    nxt = ring[(min_pos + 1) % n]
    if prev < nxt:
        return tuple(ring[(min_pos + n - i) % n] for i in range(n))
    return tuple(ring[(min_pos + i) % n] for i in range(n))


def _ring_dfs(current, start, path, visited, adj, size, out, seen):
    if len(path) == size:
        if start in adj[current]:
            norm = _normalize_ring(path)
            if norm not in seen:
                seen.add(norm)
                out.append(list(norm))
        return
    for nxt in adj[current]:
        if nxt == start and len(path) < size:
            continue
        if nxt in visited:
            continue
        if len(path) == 1 and nxt < start:  # first-edge pruning
            continue
        visited.add(nxt)
        path.append(nxt)
        _ring_dfs(nxt, start, path, visited, adj, size, out, seen)
        path.pop()
        visited.discard(nxt)


def _find_rings(adj: List[List[int]], size: int) -> List[List[int]]:
    out: List[List[int]] = []
    seen: set = set()
    for start in range(len(adj)):
        _ring_dfs(start, start, [start], {start}, adj, size, out, seen)
    return out


def _is_primitive(ring: List[int], adj: List[List[int]]) -> bool:
    """HTR: no non-adjacent ring vertices are directly bonded (chordless)."""
    n = len(ring)
    aset = [set(adj[v]) for v in ring]
    for i in range(n):
        for j in range(i + 2, n):
            if i == 0 and j == n - 1:
                continue
            if ring[j] in aset[i]:
                return False
    return True


def _valid_ring(ring: List[int], O: np.ndarray, cell: Cell, rcut: float) -> bool:
    n = len(ring)
    pos = [O[v] for v in ring]
    # PBC closure: MIC edge vectors must sum to ~0 (reject box-wrapping ghosts)
    pbc = np.zeros(3)
    for i in range(n):
        pbc += cell.diff(pos[(i + 1) % n], pos[i])
    if np.any(np.abs(pbc) > 0.1):
        return False
    # GRADE diagonal floors
    if n == 4:
        lr = 1.2 * rcut - 0.08
        for i in range(4):
            if cell.distance(pos[i], pos[(i + 2) % 4]) < lr:
                return False
    elif n == 5:
        lr = 1.6 * rcut - 0.18
        for i in range(n):
            for j in range(i + 2, n):
                if i == 0 and j == n - 1:
                    continue
                if cell.distance(pos[i], pos[j]) < lr:
                    return False
    elif n == 6:
        lr = 2.0 * rcut - 0.26
        for i in range(3):
            if cell.distance(pos[i], pos[i + 3]) < lr:
                return False
    return True


# --------------------------------------------------------------------------- #
# Cage growth (constraint propagation + bounded DFS)                           #
# --------------------------------------------------------------------------- #
def _edge(u: int, v: int) -> Tuple[int, int]:
    return (u, v) if u < v else (v, u)


def _ring_edges(ring: List[int]):
    n = len(ring)
    return [_edge(ring[i], ring[(i + 1) % n]) for i in range(n)]


def _build_edge_index(rings: List[List[int]]) -> Dict[Tuple[int, int], List[int]]:
    idx: Dict[Tuple[int, int], List[int]] = defaultdict(list)
    for ri, ring in enumerate(rings):
        for e in _ring_edges(ring):
            idx[e].append(ri)
    return idx


class _Grower:
    def __init__(self, rings, edge_index):
        self.rings = rings
        self.edge_index = edge_index

    def _add(self, ri, ec, vc):
        for e in _ring_edges(self.rings[ri]):
            ec[e] = ec.get(e, 0) + 1
        for v in self.rings[ri]:
            vc[v] = vc.get(v, 0) + 1

    def _remove(self, ri, ec, vc):
        for e in _ring_edges(self.rings[ri]):
            ec[e] -= 1
            if ec[e] == 0:
                del ec[e]
        for v in self.rings[ri]:
            vc[v] -= 1
            if vc[v] == 0:
                del vc[v]

    def _addition_valid(self, ri, ec, vc):
        ring = self.rings[ri]
        for e in _ring_edges(ring):
            if ec.get(e, 0) >= 2:
                return False
        return all(vc.get(v, 0) < 3 for v in ring)

    def _candidates(self, edge, face_set, ec, vc):
        # sorted for deterministic, reproducible growth (review nice-to-have)
        return sorted(
            ri for ri in self.edge_index.get(edge, ())
            if ri not in face_set and self._addition_valid(ri, ec, vc)
        )

    def grow(self, seed: int) -> Optional[List[int]]:
        faces = [seed]
        face_set = {seed}
        ec: Dict[Tuple[int, int], int] = {}
        vc: Dict[int, int] = {}
        self._add(seed, ec, vc)
        if any(c > 2 for c in ec.values()) or any(c > 3 for c in vc.values()):
            return None
        return self._recurse(faces, face_set, ec, vc)

    def _recurse(self, faces, face_set, ec, vc) -> Optional[List[int]]:
        propagated: List[int] = []

        def undo():
            for ri in reversed(propagated):
                faces.pop()
                face_set.discard(ri)
                self._remove(ri, ec, vc)

        while True:
            open_edges = sorted(e for e, c in ec.items() if c == 1)
            if not open_edges:
                if _validate_euler(faces, self.rings):
                    return list(faces)
                undo()
                return None
            if len(faces) >= MAX_CAGE_FACES:
                undo()
                return None

            forced = False
            for edge in open_edges:
                if ec.get(edge, 0) != 1:
                    continue
                cands = self._candidates(edge, face_set, ec, vc)
                if not cands:
                    undo()
                    return None
                if len(cands) == 1:
                    ri = cands[0]
                    faces.append(ri)
                    face_set.add(ri)
                    self._add(ri, ec, vc)
                    propagated.append(ri)
                    forced = True
                    break

            if forced:
                continue

            # branch on the most-constrained open edge
            best_edge = None
            best_cands: List[int] = []
            best = 1 << 30
            for edge in open_edges:
                if ec.get(edge, 0) != 1:
                    continue
                cands = self._candidates(edge, face_set, ec, vc)
                if not cands:
                    undo()
                    return None
                if len(cands) < best:
                    best = len(cands)
                    best_cands = cands
                    best_edge = edge
            if best_edge is None:
                undo()
                return None
            for cand in best_cands:
                faces.append(cand)
                face_set.add(cand)
                self._add(cand, ec, vc)
                res = self._recurse(faces, face_set, ec, vc)
                faces.pop()
                face_set.discard(cand)
                self._remove(cand, ec, vc)
                if res is not None:
                    undo()
                    return res
            undo()
            return None


def _validate_euler(face_indices: List[int], rings: List[List[int]]) -> bool:
    f = len(face_indices)
    if f < 4:
        return False
    ecount: Dict[Tuple[int, int], int] = defaultdict(int)
    vcount: Dict[int, int] = defaultdict(int)
    for fi in face_indices:
        ring = rings[fi]
        n = len(ring)
        for i in range(n):
            vcount[ring[i]] += 1
            ecount[_edge(ring[i], ring[(i + 1) % n])] += 1
    e = len(ecount)
    v = len(vcount)
    if f - e + v != 2:
        return False
    if any(c != 2 for c in ecount.values()):
        return False
    if any(c != 3 for c in vcount.values()):
        return False
    return True


# --------------------------------------------------------------------------- #
# Structure classification (GRADE)                                             #
# --------------------------------------------------------------------------- #
def _classify_structure(counts: Dict[str, int]) -> Tuple[str, float]:
    n512 = counts.get("512", 0)
    n51262 = counts.get("51262", 0)
    n51264 = counts.get("51264", 0)
    n435663 = counts.get("435663", 0)
    n51268 = counts.get("51268", 0)
    total = n512 + n51262 + n51264 + n435663 + n51268
    if total == 0:
        return "amorphous", 0.0
    if n435663 > 0 or n51268 > 0:  # sH branch
        if n512 > 0:
            tot = n512 + n435663 + n51268
            dev = (abs(n512 / tot - 0.5) + abs(n435663 / tot - 0.333) + abs(n51268 / tot - 0.167)) / 3
            conf = min(max(1 - 2 * dev, 0.2), 1.0)
            if (n51262 + n51264) > 0.3 * total:
                return "mixed", 0.5
            return "sH", conf
    has_51262 = n51262 > 0
    has_51264 = n51264 > 0
    if has_51262 and not has_51264:
        ratio = n51262 / n512 if n512 else 0
        return "sI", min(max(1 - abs(ratio - 3) / 3, 0.1), 1.0)
    if has_51264 and not has_51262:
        ratio = n512 / n51264 if n51264 else 0
        return "sII", min(max(1 - abs(ratio - 2) / 2, 0.1), 1.0)
    if has_51262 and has_51264:
        return "mixed", 0.5
    if n512 > 0:
        return "unknown", 0.3
    return "amorphous", 0.0


# --------------------------------------------------------------------------- #
# Public entry                                                                 #
# --------------------------------------------------------------------------- #
def identify_cages(
    O: np.ndarray,
    H1: np.ndarray,
    H2: np.ndarray,
    cell: Cell,
    rcut: float = 0.36,
    theta: float = 35.0,
    method: str = "TRACE",
) -> CageResult:
    """Identify clathrate cages from water positions.

    method="TRACE" uses all topological rings; "HTR" uses only primitive
    (chordless) rings.
    """
    O = np.asarray(O, dtype=float).reshape(-1, 3)
    if len(O) < 20:
        return CageResult([], {}, "amorphous", 0.0, 0)

    adj = hbond_network(O, H1, H2, cell, rcut=rcut, theta=theta).adjacency

    rings: List[List[int]] = []
    for size in (4, 5, 6):
        for ring in _find_rings(adj, size):
            if method == "HTR" and not _is_primitive(ring, adj):
                continue
            if _valid_ring(ring, O, cell, rcut):
                rings.append(ring)

    edge_index = _build_edge_index(rings)
    grower = _Grower(rings, edge_index)

    seen_keys: set = set()
    cages: List[Cage] = []
    for seed in range(len(rings)):
        faces = grower.grow(seed)
        if faces is None:
            continue
        key = tuple(sorted(faces))
        if key in seen_keys:
            continue
        seen_keys.add(key)
        n4 = sum(1 for fi in faces if len(rings[fi]) == 4)
        n5 = sum(1 for fi in faces if len(rings[fi]) == 5)
        n6 = sum(1 for fi in faces if len(rings[fi]) == 6)
        ctype = _CAGE_TYPES.get((n4, n5, n6), "other")
        verts = sorted({v for fi in faces for v in rings[fi]})
        center = cell.average(np.array([O[i] for i in verts]))
        cages.append(Cage(cage_type=ctype, vertices=verts, center=center, n4=n4, n5=n5, n6=n6))

    counts = dict(Counter(c.cage_type for c in cages))
    structure, confidence = _classify_structure(counts)
    return CageResult(cages=cages, counts=counts, structure=structure,
                      confidence=confidence, n_rings=len(rings))
