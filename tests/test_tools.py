"""Tool-layer tests. Hydrate/security tools run with no VMD; viz tools use the
mock session. Real VMD is exercised separately in test_integration_vmd.py."""

import os
from pathlib import Path

import pytest

from vmd_hydrate_mcp.config import Settings
from vmd_hydrate_mcp.security import SecurityError
from vmd_hydrate_mcp.tools import Tools

from mock_vmd import MockVmdSession

FIXTURES = Path(__file__).parent / "fixtures"
FIX_GRO = str(FIXTURES / "hydrate_10waters.gro")
FIX_SII = str(FIXTURES / "hydrate_sII_222.gro")


def _tools(tmp_path=None):
    roots = [FIXTURES] + ([Path(tmp_path)] if tmp_path else [])
    return Tools(Settings(allow_dirs=roots))


# --------------------------------------------------------------------------- #
# hydrate tools (pure science, no VMD)                                         #
# --------------------------------------------------------------------------- #
def test_hydrate_order_params_tool_golden():
    t = _tools()
    out = t.hydrate_order_params(FIX_GRO)
    assert out["n_pairs"] == 12
    assert abs(out["f4_overall"] - 0.926698) < 1e-5
    assert "interpretation" in out


def test_hbond_network_tool():
    t = _tools()
    out = t.hbond_network(FIX_GRO)
    assert out["n_waters"] == 10
    assert out["rcut_nm"] == 0.36


def test_identify_cages_tool_sII():
    t = _tools()
    out = t.identify_cages(FIX_SII)
    assert out["counts"]["512"] == 128
    assert out["structure"] == "sII"


def test_hydrate_tool_rejects_path_outside_allowlist():
    t = _tools()
    with pytest.raises(SecurityError):
        t.hydrate_order_params("/etc/hosts")


# --------------------------------------------------------------------------- #
# viz tools (mock session)                                                     #
# --------------------------------------------------------------------------- #
def test_load_structure_rejects_coord_only(tmp_path):
    t = _tools(tmp_path)
    t._session = MockVmdSession()
    xtc = tmp_path / "traj.xtc"
    xtc.write_bytes(b"\x00")
    with pytest.raises(ValueError, match="coordinate-only"):
        t.load_structure(str(xtc))


def test_set_representation_blocks_injection(tmp_path):
    t = _tools(tmp_path)
    t._session = MockVmdSession()
    with pytest.raises(SecurityError):
        t.set_representation(0, "Lines", "Name", "Opaque", "all] ; puts HACK ; [")


def test_set_representation_forwards_benign_selection(tmp_path):
    t = _tools(tmp_path)
    mock = MockVmdSession()
    t._session = mock
    out = t.set_representation(0, "VDW", "Name", "Opaque", "water and name OW")
    assert out["molid"] == 0
    # the selection reached the session as a single argument (safe list element)
    recipe, args = mock.calls[-1]
    assert recipe == "recipe_representation"
    assert args[-1] == "water and name OW"


def test_vmd_status_reports_unavailable_gracefully(tmp_path):
    # point discovery at a non-existent binary -> status reports unavailable, no crash
    t = Tools(Settings(allow_dirs=[Path(tmp_path)], vmd_bin=str(tmp_path / "nope")))
    status = t.vmd_status()
    assert status["vmd_available"] is False


# --------------------------------------------------------------------------- #
# MDAnalysis-backed tools (need the [mda] extra)                               #
# --------------------------------------------------------------------------- #
def test_resolve_selection_counts_atoms():
    pytest.importorskip("MDAnalysis")
    t = _tools()
    out = t.resolve_selection(FIX_GRO, "resname H2O")
    assert out["n_atoms"] == 30  # 10 waters x 3 atoms
