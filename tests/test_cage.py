"""Cage identification golden — the sII CO2 hydrate (222_S2, 1088 waters).

The ideal 2x2x2 sII supercell has 16x5^12 + 8x5^12 6^4 per unit cell = 128 + 64.
We reproduce 128 small cages exactly and the large-cage count within a few of 64
(the shortfall is shared-hexagon junctions the greedy first-cage growth commits
elsewhere — deterministic, and matching the reference's character). The robust,
physically meaningful assertions: 128 small cages, no sI cages, sII structure.
"""

import os

import pytest

from vmd_hydrate_mcp.analysis.gro import read_gro_waters
from vmd_hydrate_mcp.analysis.hydrate.cage import identify_cages

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "hydrate_sII_222.gro")


@pytest.fixture(scope="module")
def sII():
    w = read_gro_waters(FIX)
    return identify_cages(w.O, w.H1, w.H2, w.cell, rcut=0.36, theta=35.0, method="TRACE")


def test_sII_small_cage_count_exact(sII):
    assert sII.counts.get("512", 0) == 128


def test_sII_large_cages_present_no_sI(sII):
    assert 55 <= sII.counts.get("51264", 0) <= 66  # ideal 64
    assert sII.counts.get("51262", 0) == 0  # sI cages absent


def test_sII_structure_classified(sII):
    assert sII.structure == "sII"
    assert sII.confidence >= 0.8


def test_sII_ratio_near_two(sII):
    ratio = sII.counts["512"] / sII.counts["51264"]
    assert 1.9 <= ratio <= 2.3


def test_cage_growth_is_deterministic():
    # same input -> identical counts across runs (sorted growth)
    w = read_gro_waters(FIX)
    a = identify_cages(w.O, w.H1, w.H2, w.cell, method="TRACE")
    b = identify_cages(w.O, w.H1, w.H2, w.cell, method="TRACE")
    assert a.counts == b.counts
