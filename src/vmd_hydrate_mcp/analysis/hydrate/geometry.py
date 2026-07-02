"""PBC-aware geometry for hydrate analysis (triclinic PBC helpers).

Units: nanometers. Supports orthorhombic and (restricted) triclinic cells.

Correctness rules pinned by the design review (PLAN §13):
  * C2 — minimum-image uses **half-away-from-zero** rounding to match Rust's
    ``f64::round``, NOT NumPy's banker's rounding.
  * C3 — the signed dihedral is ``atan2(x, y)`` with ``x = b2·(n1×n2)`` and
    ``y = |b2|·(n1·n2)`` (the F4SPC convention); operand order matters.
"""

from __future__ import annotations

import numpy as np

__all__ = ["Cell", "round_half_away"]

_EPS = 1e-10


def round_half_away(x: np.ndarray) -> np.ndarray:
    """Round half away from zero, matching Rust ``f64::round``.

    ``np.round`` rounds half to even and ``np.floor(x + 0.5)`` rounds half up
    (wrong for negatives); both diverge from the reference implementation on the
    exact-.5 boundary, which perturbs minimum-image wrapping.
    """
    x = np.asarray(x, dtype=float)
    return np.sign(x) * np.floor(np.abs(x) + 0.5)


class Cell:
    """A periodic simulation cell.

    Rows of ``matrix`` are the lattice vectors ``a, b, c`` (nm). A Cartesian
    point ``p`` has fractional coordinates ``f = p @ inv`` and ``p = f @ matrix``.
    """

    __slots__ = ("matrix", "inv", "orthorhombic")

    def __init__(self, matrix: np.ndarray):
        m = np.asarray(matrix, dtype=float).reshape(3, 3)
        if abs(np.linalg.det(m)) < 1e-12:
            raise ValueError("degenerate cell: |det| < 1e-12")
        self.matrix = m
        self.inv = np.linalg.inv(m)
        self.orthorhombic = bool(
            np.allclose(m - np.diag(np.diag(m)), 0.0, atol=1e-9)
        )

    # -- constructors ---------------------------------------------------------
    @classmethod
    def orthorhombic_box(cls, lengths) -> "Cell":
        lx, ly, lz = (float(v) for v in lengths[:3])
        return cls(np.diag([lx, ly, lz]))

    @classmethod
    def from_triclinic(cls, lx, ly, lz, xy=0.0, xz=0.0, yz=0.0) -> "Cell":
        # a = (lx,0,0); b = (xy,ly,0); c = (xz,yz,lz)  -- GROMACS/TRACE convention.
        return cls(np.array([[lx, 0.0, 0.0], [xy, ly, 0.0], [xz, yz, lz]]))

    @classmethod
    def from_vectors(cls, vectors) -> "Cell":
        """From a 3x3 matrix whose rows are a, b, c (e.g. MDAnalysis
        ``triclinic_dimensions`` — see units.cell_from_mda)."""
        return cls(vectors)

    @classmethod
    def from_gro_box(cls, fields) -> "Cell":
        """From a GROMACS ``.gro`` box line (3 or 9 whitespace fields, nm).

        9-field order is ``v1x v2y v3z v1y v1z v2x v2z v3x v3y`` with the
        GROMACS constraint v1y=v1z=v2z=0, i.e. tilts xy=v2x(f5), xz=v3x(f7),
        yz=v3y(f8).
        """
        f = [float(v) for v in fields]
        if len(f) == 3:
            return cls.orthorhombic_box(f)
        if len(f) >= 9:
            return cls.from_triclinic(f[0], f[1], f[2], xy=f[5], xz=f[7], yz=f[8])
        raise ValueError(f"gro box line must have 3 or 9 fields, got {len(f)}")

    # -- geometry -------------------------------------------------------------
    def mic(self, delta: np.ndarray) -> np.ndarray:
        """Minimum-image image of a Cartesian displacement (fractional rounding)."""
        delta = np.asarray(delta, dtype=float)
        frac = delta @ self.inv
        frac = frac - round_half_away(frac)
        return frac @ self.matrix

    def diff(self, a: np.ndarray, b: np.ndarray) -> np.ndarray:
        """Minimum-image ``a - b``."""
        return self.mic(np.asarray(a, float) - np.asarray(b, float))

    def distance_sq(self, a: np.ndarray, b: np.ndarray) -> float:
        d = self.mic(np.asarray(b, float) - np.asarray(a, float))
        return float(d @ d)

    def distance(self, a: np.ndarray, b: np.ndarray) -> float:
        return float(np.sqrt(self.distance_sq(a, b)))

    def angle(self, center: np.ndarray, a: np.ndarray, b: np.ndarray) -> float:
        """Angle a-center-b in **degrees** (vertex at ``center``)."""
        v1 = self.diff(a, center)
        v2 = self.diff(b, center)
        n1 = np.linalg.norm(v1)
        n2 = np.linalg.norm(v2)
        if n1 < _EPS or n2 < _EPS:
            return 180.0
        c = np.clip(float(v1 @ v2) / (n1 * n2), -1.0, 1.0)
        return float(np.degrees(np.arccos(c)))

    def dihedral(self, p1, p2, p3, p4) -> float:
        """Signed dihedral p1-p2-p3-p4 in **radians** (F4SPC atan2 convention).

        Degenerate configurations return ``pi/2`` so ``cos(3*phi) ~= 0``.
        """
        b1 = self.diff(p2, p1)
        b2 = self.diff(p3, p2)
        b3 = self.diff(p4, p3)
        n1 = np.cross(b1, b2)
        n2 = np.cross(b2, b3)
        if (
            np.linalg.norm(n1) < _EPS
            or np.linalg.norm(n2) < _EPS
            or np.linalg.norm(b2) < _EPS
        ):
            return float(np.pi / 2)
        x = float(b2 @ np.cross(n1, n2))
        y = float(np.linalg.norm(b2) * (n1 @ n2))
        return float(np.arctan2(x, y))

    def average(self, points: np.ndarray) -> np.ndarray:
        """PBC-aware centroid: unwrap relative to points[0], mean, re-wrap."""
        pts = np.asarray(points, dtype=float).reshape(-1, 3)
        if len(pts) == 0:
            return np.zeros(3)
        ref = pts[0]
        acc = np.zeros(3)
        for p in pts:
            acc += self.mic(p - ref)
        center = ref + acc / len(pts)
        frac = center @ self.inv
        frac = frac - np.floor(frac)  # wrap into [0,1)
        return frac @ self.matrix
