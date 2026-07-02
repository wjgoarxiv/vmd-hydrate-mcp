"""Numeric goldens for the pure-NumPy hydrate science.

The F4 golden (0.926698, exactly 12 O-O pairs on the first 10 waters of the
sII CO2 hydrate 222_S2) is the load-bearing regression that proves the parser,
minimum-image geometry, far-H selection, and <cos 3phi> are all correct.
"""

import os

import numpy as np
import pytest

from vmd_hydrate_mcp.analysis.gro import read_gro_waters, count_frames
from vmd_hydrate_mcp.analysis.hydrate.geometry import Cell, round_half_away
from vmd_hydrate_mcp.analysis.hydrate.order_params import (
    order_parameters,
    neighbor_pairs,
    _neighbor_pairs_bruteforce,
    _neighbor_pairs_gridded,
    f3_value,
)
from vmd_hydrate_mcp.analysis.hydrate.hbond import hbond_network

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "hydrate_10waters.gro")


# --------------------------------------------------------------------------- #
# geometry                                                                    #
# --------------------------------------------------------------------------- #
def test_round_half_away_from_zero():
    got = round_half_away(np.array([-1.5, -0.5, 0.5, 1.5, 2.5, -2.5]))
    assert np.array_equal(got, [-2.0, -1.0, 1.0, 2.0, 3.0, -3.0])
    # differs from banker's rounding on exact halves (the whole point)
    assert not np.array_equal(got, np.round([-1.5, -0.5, 0.5, 1.5, 2.5, -2.5]))


def test_dihedral_cis_and_trans():
    cell = Cell.orthorhombic_box([100.0, 100.0, 100.0])  # effectively no PBC
    p2 = np.array([0.0, 0.0, 0.0]); p3 = np.array([1.0, 0.0, 0.0])
    p1 = np.array([0.0, 1.0, 0.0])
    cis = cell.dihedral(p1, p2, p3, np.array([1.0, 1.0, 0.0]))
    trans = cell.dihedral(p1, p2, p3, np.array([1.0, -1.0, 0.0]))
    assert abs(cis) < 1e-9
    assert abs(abs(trans) - np.pi) < 1e-9


def test_mic_wraps_across_boundary():
    cell = Cell.orthorhombic_box([10.0, 10.0, 10.0])
    # points near opposite faces are actually 0.2 apart under min-image
    d = cell.distance(np.array([0.1, 0, 0]), np.array([9.9, 0, 0]))
    assert abs(d - 0.2) < 1e-9


def test_triclinic_cell_from_gro_box():
    cell = Cell.from_gro_box(["3.0", "3.0", "3.0", "0", "0", "0.5", "0", "0.3", "0.2"])
    assert not cell.orthorhombic
    assert np.allclose(cell.matrix[1], [0.5, 3.0, 0.0])  # b = (xy, ly, 0)
    assert np.allclose(cell.matrix[2], [0.3, 0.2, 3.0])  # c = (xz, yz, lz)


# --------------------------------------------------------------------------- #
# gro reader / units                                                          #
# --------------------------------------------------------------------------- #
def test_gro_reader_units_and_count():
    w = read_gro_waters(FIX)
    assert w.n == 10
    # box must be ~3.462 nm, NOT 34.62 (the Angstrom trap)
    assert np.allclose(np.diag(w.cell.matrix), 3.462, atol=1e-3)
    assert count_frames(FIX) == 1


# --------------------------------------------------------------------------- #
# F4 golden — the load-bearing regression                                     #
# --------------------------------------------------------------------------- #
def test_f4_golden_222s2_first10():
    w = read_gro_waters(FIX)
    res = order_parameters(w.O, w.H1, w.H2, w.cell, cutoff=0.35)
    assert res.n_pairs == 12  # C4: exactly 12 O-O pairs
    assert abs(res.f4_overall - 0.926698) < 1e-5


def test_f3_ordered_fragment_is_small():
    w = read_gro_waters(FIX)
    res = order_parameters(w.O, w.H1, w.H2, w.cell, cutoff=0.35)
    # a near-perfect tetrahedral crystal fragment -> F3 ~ 0
    assert res.f3_overall < 0.05


def test_f3_subset_uses_reference_angle():
    # F3 with the 104.5-deg guest-centric reference differs from the 109.47 form
    w = read_gro_waters(FIX)
    glob, _ = f3_value(w.O, w.cell, cutoff=0.35)  # 1/9 default
    sub, _ = f3_value(w.O, w.cell, cutoff=0.35, cos_ref_sq=np.cos(np.radians(104.5)) ** 2)
    assert glob != sub


# --------------------------------------------------------------------------- #
# neighbour search: gridded == bruteforce                                     #
# --------------------------------------------------------------------------- #
def _canon(pairs):
    return {tuple(sorted(map(int, p))) for p in pairs}


def test_gridded_matches_bruteforce_orthorhombic():
    rng = np.random.default_rng(7)
    cell = Cell.orthorhombic_box([4.0, 4.0, 4.0])
    O = rng.uniform(0, 4.0, size=(400, 3))
    bf = _neighbor_pairs_bruteforce(O, cell, 0.35)
    gr = _neighbor_pairs_gridded(O, cell, 0.35)
    assert _canon(bf) == _canon(gr)


def test_gridded_matches_bruteforce_triclinic():
    rng = np.random.default_rng(11)
    cell = Cell.from_triclinic(4.0, 4.0, 4.0, xy=0.3, xz=0.2, yz=0.1)
    frac = rng.uniform(0, 1, size=(300, 3))
    O = frac @ cell.matrix
    bf = _neighbor_pairs_bruteforce(O, cell, 0.35)
    gr = _neighbor_pairs_gridded(O, cell, 0.35)
    assert _canon(bf) == _canon(gr)


# --------------------------------------------------------------------------- #
# hbond network                                                               #
# --------------------------------------------------------------------------- #
def test_hbond_network_on_fixture():
    w = read_gro_waters(FIX)
    hb = hbond_network(w.O, w.H1, w.H2, w.cell, rcut=0.36, theta=35.0)
    assert hb.n_waters == 10
    assert hb.n_bonds >= 0
    # adjacency is symmetric and sorted
    for i, neigh in enumerate(hb.adjacency):
        assert neigh == sorted(neigh)
        for j in neigh:
            assert i in hb.adjacency[j]
